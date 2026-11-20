"""Research from a goal.

1. The author writes the goal; the AI turns it into a plan (questions, keywords, Wikipedia
   entries, Reddit and YouTube searches) that the author can edit.
2. TALeport collects evergreen material in the background: Wikipedia articles, Reddit
   discussions, YouTube suggestions. The author adds video links (audio downloaded and
   transcribed on the PC), documents, pasted text, and web research done by their own chat.
3. The AI builds a dossier (notions, rules, examples, experiences, mistakes, quotes), every
   point with its source numbers; general AI knowledge, if allowed, is kept apart.
4. From the dossier: posts (through the long-content generator) or an article.
"""

from __future__ import annotations

import json
import logging
import queue
import shutil
import sqlite3
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from taleport.ai import prompts
from taleport.ai.providers.base import ProviderError
from taleport.ai.service import AIService
from taleport.ai.structured import parse_answer, run_structured
from taleport.collectors.http import HttpClient
from taleport.core.errors import AppError
from taleport.core.events import EventBus
from taleport.db.database import Database
from taleport.generator.extract import extract_text, limit_content
from taleport.research import links, web_sources
from taleport.research.schemas import (
    SECTIONS,
    Article,
    Dossier,
    ResearchPlan,
    SourceDigest,
    WebResearch,
)

log = logging.getLogger(__name__)

MAX_PROJECTS = 100
MAX_SOURCES = 40
MAX_VIDEO_LINKS = 10
MIN_GOAL_CHARS = 15
DIGEST_MIN_CHARS = 4000  # longer sources are summarized for the goal before the dossier
DIGEST_INPUT_CHARS = 24_000
DOSSIER_SOURCES_CHARS = 48_000
MAX_TOKENS = 12_000
LANGUAGES = ("it", "en", "es")
_NOW = "strftime('%Y-%m-%dT%H:%M:%fZ', 'now')"

AI_KNOWLEDGE = {
    True: {
        "it": 'Puoi aggiungere in "ai_knowledge" nozioni generali che conosci bene e che le fonti '
        "non contengono: senza fonti, verranno mostrate a parte come conoscenza generale dell'AI.",
        "en": 'You may add in "ai_knowledge" general notions you know well that the sources do '
        "not contain: no sources, they are shown apart as the AI's general knowledge.",
        "es": 'Puedes añadir en "ai_knowledge" nociones generales que conoces bien y que las '
        "fuentes no contienen: sin fuentes, se mostrarán aparte como conocimiento general "
        "de la IA.",
    },
    False: {
        "it": 'Lascia vuoto "ai_knowledge": usa solo le fonti.',
        "en": 'Leave "ai_knowledge" empty: use only the sources.',
        "es": 'Deja vacío "ai_knowledge": usa solo las fuentes.',
    },
}
ARTICLE_LENGTH = {
    "short": {"it": "circa 600 parole", "en": "about 600 words", "es": "unas 600 palabras"},
    "medium": {"it": "circa 1000 parole", "en": "about 1000 words", "es": "unas 1000 palabras"},
    "long": {"it": "circa 1600 parole", "en": "about 1600 words", "es": "unas 1600 palabras"},
}
DEFAULT_TONE = {
    "it": "chiaro, autorevole e vicino al lettore",
    "en": "clear, authoritative and close to the reader",
    "es": "claro, con autoridad y cercano al lector",
}
SECTION_TITLES = {
    "it": {"notions": "Nozioni", "rules": "Regole", "examples": "Esempi",
           "experiences": "Esperienze", "mistakes": "Errori da evitare", "quotes": "Citazioni",
           "ai_knowledge": "Conoscenza generale dell'AI (senza fonte)", "sources": "Fonti"},
    "en": {"notions": "Notions", "rules": "Rules", "examples": "Examples",
           "experiences": "Experiences", "mistakes": "Mistakes to avoid", "quotes": "Quotes",
           "ai_knowledge": "AI general knowledge (no source)", "sources": "Sources"},
    "es": {"notions": "Nociones", "rules": "Reglas", "examples": "Ejemplos",
           "experiences": "Experiencias", "mistakes": "Errores que evitar", "quotes": "Citas",
           "ai_knowledge": "Conocimiento general de la IA (sin fuente)", "sources": "Fuentes"},
}  # fmt: skip


def _fmt_time(seconds: float) -> str:
    seconds = int(seconds)
    hours, rest = divmod(seconds, 3600)
    return (
        f"{hours}:{rest // 60:02d}:{rest % 60:02d}"
        if hours
        else f"{rest // 60:02d}:{rest % 60:02d}"
    )


def transcript_text(segments: list[Any]) -> str:
    """Transcript with a [mm:ss] mark about every 30 seconds, for quotes with timestamps."""
    lines: list[str] = []
    current: list[str] = []
    mark = None
    for seg in segments:
        if mark is None or seg.start - mark >= 30:
            if current:
                lines.append(" ".join(current))
            current = [f"[{_fmt_time(seg.start)}]"]
            mark = seg.start
        current.append(seg.text)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


class ResearchService:
    def __init__(
        self,
        db: Database,
        ai: AIService,
        bus: EventBus,
        http: Callable[[], HttpClient] | None = None,
        *,
        start_worker: bool = True,
        transcribe: Callable[[Path], Any] | None = None,
        download: Callable[..., tuple[Path, links.VideoInfo]] | None = None,
        search_videos: Callable[[str], list[links.VideoInfo]] | None = None,
        extract_wav: Callable[[Path, Path], bool] | None = None,
    ) -> None:
        self._db = db
        self._ai = ai
        self._bus = bus
        self._http = http or (lambda: HttpClient(min_interval={"www.reddit.com": 7.0}))
        self._start_worker = start_worker
        self._transcribe = transcribe
        self._download = download or links.download_audio
        self._search_videos = search_videos or links.search_youtube
        self._extract_wav = extract_wav
        self._queue: queue.Queue[tuple[str, int]] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._collecting: set[int] = set()

    # -- projects ----------------------------------------------------------------------

    def _project_row(self, conn: sqlite3.Connection, project_id: int) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM research_projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            raise AppError("research.not_found", status=404)
        return row

    def _source_dict(self, row: sqlite3.Row, *, full: bool = False) -> dict[str, Any]:
        out = {
            "id": row["id"], "project_id": row["project_id"], "kind": row["kind"],
            "title": row["title"], "url": row["url"], "author": row["author"],
            "language": row["language"], "status": row["status"], "step": row["step"],
            "error_code": row["error_code"], "meta": json.loads(row["meta"] or "{}"),
            "chars": len(row["content"] or ""),
            "digest": json.loads(row["digest"]) if row["digest"] else None,
            "created_at": row["created_at"],
        }  # fmt: skip
        if full:
            out["content"] = row["content"]
        return out

    def _project_dict(self, conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        sources = conn.execute(
            "SELECT * FROM research_sources WHERE project_id = ? ORDER BY id", (row["id"],)
        ).fetchall()
        return {
            "id": row["id"], "goal": row["goal"], "title": row["title"],
            "languages": json.loads(row["languages"]),
            "plan": json.loads(row["plan"]) if row["plan"] else None,
            "dossier": json.loads(row["dossier"]) if row["dossier"] else None,
            "article": json.loads(row["article"]) if row["article"] else None,
            "collecting": row["id"] in self._collecting,
            "sources": [self._source_dict(s) for s in sources],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }  # fmt: skip

    def list_projects(self) -> list[dict[str, Any]]:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT p.id, p.goal, p.title, p.updated_at, p.dossier IS NOT NULL AS has_dossier,"
                " (SELECT COUNT(*) FROM research_sources s WHERE s.project_id = p.id) AS sources"
                " FROM research_projects p ORDER BY p.updated_at DESC"
            ).fetchall()
        return [dict(r) | {"has_dossier": bool(r["has_dossier"])} for r in rows]

    def get(self, project_id: int) -> dict[str, Any]:
        with self._db.connect() as conn:
            return self._project_dict(conn, self._project_row(conn, project_id))

    def create(self, goal: str, languages: list[str]) -> dict[str, Any]:
        goal = goal.strip()
        if len(goal) < MIN_GOAL_CHARS:
            raise AppError("research.goal_short", min=MIN_GOAL_CHARS)
        languages = [lang for lang in dict.fromkeys(languages) if lang in LANGUAGES] or ["it"]
        with self._db.connect() as conn:
            if conn.execute("SELECT COUNT(*) FROM research_projects").fetchone()[0] >= MAX_PROJECTS:
                raise AppError("research.too_many", max=MAX_PROJECTS)
            cur = conn.execute(
                "INSERT INTO research_projects (goal, title, languages) VALUES (?, ?, ?)",
                (goal[:4000], goal[:80], json.dumps(languages)),
            )
            project_id = cur.lastrowid
        return self.get(project_id)

    def update(self, project_id: int, changes: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if "goal" in changes:
            goal = str(changes["goal"]).strip()
            if len(goal) < MIN_GOAL_CHARS:
                raise AppError("research.goal_short", min=MIN_GOAL_CHARS)
            fields["goal"] = goal[:4000]
        if "title" in changes:
            fields["title"] = str(changes["title"]).strip()[:160]
        if "languages" in changes:
            langs = [x for x in dict.fromkeys(changes["languages"]) if x in LANGUAGES] or ["it"]
            fields["languages"] = json.dumps(langs)
        if "plan" in changes:
            plan = ResearchPlan.model_validate(changes["plan"]) if changes["plan"] else None
            fields["plan"] = plan.model_dump_json() if plan else None
        if "dossier" in changes:
            dossier = Dossier.model_validate(changes["dossier"]) if changes["dossier"] else None
            if dossier:
                with self._db.connect() as conn:
                    old = self._project_row(conn, project_id)["dossier"]
                keep = json.loads(old or "{}").get("sources", [])
                fields["dossier"] = json.dumps({**dossier.model_dump(), "sources": keep})
            else:
                fields["dossier"] = None
        with self._db.connect() as conn:
            self._project_row(conn, project_id)
            if fields:
                sets = ", ".join(f"{k} = ?" for k in fields)
                conn.execute(
                    f"UPDATE research_projects SET {sets}, updated_at = {_NOW} WHERE id = ?",
                    (*fields.values(), project_id),
                )
        return self.get(project_id)

    def delete(self, project_id: int) -> None:
        with self._db.connect() as conn:
            self._project_row(conn, project_id)
            conn.execute("DELETE FROM research_projects WHERE id = ?", (project_id,))

    def _touch(self, conn: sqlite3.Connection, project_id: int) -> None:
        conn.execute(
            f"UPDATE research_projects SET updated_at = {_NOW} WHERE id = ?", (project_id,)
        )

    # -- AI plumbing -------------------------------------------------------------------

    def _ask(
        self, prompt: prompts.Prompt, schema: type[BaseModel], mode: str | None, feature: str
    ) -> tuple[str, Any]:
        resolved, provider, fallback = self._ai.resolve(mode)
        if provider is None:
            return "chat", {
                "mode": "chat",
                "fallback": fallback,
                "handoff": self._ai.handoff(prompt),
            }
        try:
            answer = run_structured(
                provider,
                prompt,
                schema,
                self._ai.recorder(provider, feature),
                max_tokens=MAX_TOKENS,
            )
        except ProviderError as exc:
            raise AppError.from_provider(exc) from exc
        return resolved, answer

    def _lang(self) -> str:
        return self._ai.language()

    # -- 1. plan -----------------------------------------------------------------------

    def _plan_prompt(self, row: sqlite3.Row) -> prompts.Prompt:
        names = prompts.LANGUAGE_NAMES[self._lang()]
        langs = ", ".join(f"{names.get(x, x)} ({x})" for x in json.loads(row["languages"]))
        return prompts.render("research_plan", self._lang(), goal=row["goal"], languages=langs)

    def plan(self, project_id: int, mode: str | None = None) -> dict[str, Any]:
        with self._db.connect() as conn:
            row = self._project_row(conn, project_id)
        resolved, answer = self._ask(self._plan_prompt(row), ResearchPlan, mode, "research_plan")
        if resolved == "chat":
            return answer
        return {"mode": resolved, "project": self._save_plan(row, answer)}

    def parse_plan(self, project_id: int, text: str) -> dict[str, Any]:
        with self._db.connect() as conn:
            row = self._project_row(conn, project_id)
        return {"mode": "chat", "project": self._save_plan(row, parse_answer(text, ResearchPlan))}

    def _save_plan(self, row: sqlite3.Row, plan: ResearchPlan) -> dict[str, Any]:
        first = json.loads(row["languages"])[0]
        for field in ("keywords", "wikipedia"):  # a list without languages goes to the first one
            value = getattr(plan, field)
            if "" in value:
                value.setdefault(first, []).extend(value.pop(""))
        changes: dict[str, Any] = {"plan": plan.model_dump()}
        if plan.title and row["title"] == row["goal"][:80]:
            changes["title"] = plan.title
        return self.update(row["id"], changes)

    # -- 2. sources --------------------------------------------------------------------

    def _count_sources(self, conn: sqlite3.Connection, project_id: int) -> int:
        return conn.execute(
            "SELECT COUNT(*) FROM research_sources WHERE project_id = ?", (project_id,)
        ).fetchone()[0]

    def _insert_source(
        self, conn: sqlite3.Connection, project_id: int, kind: str, title: str, url: str = "",
        content: str = "", *, status: str = "ready", author: str = "",
        language: str | None = None, meta: dict | None = None, digest: dict | None = None,
    ) -> int:  # fmt: skip
        if self._count_sources(conn, project_id) >= MAX_SOURCES:
            raise AppError("research.too_many_sources", max=MAX_SOURCES)
        if (
            url
            and conn.execute(
                "SELECT 1 FROM research_sources"
                " WHERE project_id = ? AND url = ? AND kind != 'youtube'",
                (project_id, url),
            ).fetchone()
        ):
            raise AppError("research.duplicate_source")
        cur = conn.execute(
            "INSERT INTO research_sources (project_id, kind, title, url, author, language, content,"
            " status, meta, digest) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, kind, title[:300], url[:1000], author[:200], language, content,
             status, json.dumps(meta or {}), json.dumps(digest) if digest else None),
        )  # fmt: skip
        self._touch(conn, project_id)
        return cur.lastrowid

    def collect(self, project_id: int) -> dict[str, Any]:
        """Search Wikipedia, Reddit and YouTube from the plan, in the background."""
        with self._db.connect() as conn:
            row = self._project_row(conn, project_id)
        if not row["plan"]:
            raise AppError("research.no_plan")
        if project_id in self._collecting:
            raise AppError("research.busy", status=409)
        self._collecting.add(project_id)
        self._enqueue("collect", project_id)
        return self.get(project_id)

    def _do_collect(self, project_id: int) -> None:
        try:
            with self._db.connect() as conn:
                row = self._project_row(conn, project_id)
            plan = ResearchPlan.model_validate_json(row["plan"])
            http = self._http()
            try:
                found = web_sources.wikipedia(http, plan.wikipedia)
                self._publish(project_id, "collect", "wikipedia")
                found += web_sources.reddit(http, plan.reddit_queries)
            finally:
                http.close()
            self._publish(project_id, "collect", "youtube")
            videos: list[links.VideoInfo] = []
            for query in plan.youtube_queries[:3]:
                videos += self._search_videos(query)
            with self._db.connect() as conn:
                known = {
                    r[0]
                    for r in conn.execute(
                        "SELECT url FROM research_sources WHERE project_id = ?", (project_id,)
                    )
                }
                added = 0
                for item in found:
                    if item.url in known:
                        continue
                    try:
                        self._insert_source(conn, project_id, item.kind, item.title, item.url,
                                            item.content, language=item.language)  # fmt: skip
                        known.add(item.url)
                        added += 1
                    except AppError:
                        break
                for video in videos[:8]:
                    if video.url in known:
                        continue
                    try:
                        self._insert_source(
                            conn, project_id, "youtube", video.title, video.url, status="found",
                            author=video.channel,
                            meta={"duration": video.duration, "views": video.views},
                        )  # fmt: skip
                        known.add(video.url)
                    except AppError:
                        break
            log.info("Research %s: %d texts and %d videos found", project_id, added, len(videos))
        except Exception:
            log.exception("Research %s: collection failed", project_id)
        finally:
            self._collecting.discard(project_id)
            self._publish(project_id, "collected")

    def add_videos(self, project_id: int, urls: list[str]) -> dict[str, Any]:
        cleaned = [u.strip() for u in urls if u.strip()]
        if not cleaned:
            raise AppError("research.no_videos")
        if len(cleaned) > MAX_VIDEO_LINKS:
            raise AppError("research.too_many_videos", max=MAX_VIDEO_LINKS)
        bad = [u for u in cleaned if not links.is_url(u)]
        if bad:
            raise AppError("research.not_a_link", link=bad[0][:80])
        queued = []
        with self._db.connect() as conn:
            self._project_row(conn, project_id)
            for url in dict.fromkeys(cleaned):
                queued.append(
                    self._insert_source(conn, project_id, "video", url, url, status="queued")
                )
        for source_id in queued:
            self._enqueue("video", source_id)
        return self.get(project_id)

    def transcribe_suggestion(self, source_id: int) -> dict[str, Any]:
        """A YouTube suggestion found by the search: download and transcribe it."""
        with self._db.connect() as conn:
            row = self._source_row(conn, source_id)
            if row["kind"] != "youtube" or row["status"] not in ("found", "error"):
                raise AppError("research.not_a_suggestion")
            conn.execute(
                "UPDATE research_sources SET kind = 'video', status = 'queued', error_code = NULL"
                " WHERE id = ?",
                (source_id,),
            )
        self._enqueue("video", source_id)
        return self.get(row["project_id"])

    def retry_source(self, source_id: int) -> dict[str, Any]:
        with self._db.connect() as conn:
            row = self._source_row(conn, source_id)
            if row["kind"] != "video" or row["status"] != "error":
                raise AppError("research.not_a_suggestion")
            conn.execute(
                "UPDATE research_sources SET status = 'queued', error_code = NULL, step = NULL"
                " WHERE id = ?",
                (source_id,),
            )
        self._enqueue("video", source_id)
        return self.get(row["project_id"])

    def _source_row(self, conn: sqlite3.Connection, source_id: int) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM research_sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise AppError("research.source_not_found", status=404)
        return row

    def source(self, source_id: int) -> dict[str, Any]:
        with self._db.connect() as conn:
            return self._source_dict(self._source_row(conn, source_id), full=True)

    def delete_source(self, source_id: int) -> dict[str, Any]:
        with self._db.connect() as conn:
            row = self._source_row(conn, source_id)
            conn.execute("DELETE FROM research_sources WHERE id = ?", (source_id,))
            self._touch(conn, row["project_id"])
        return self.get(row["project_id"])

    def add_document(self, project_id: int, filename: str, data_base64: str) -> dict[str, Any]:
        text, _ = limit_content(extract_text(filename, data_base64))
        if len(text.strip()) < 100:
            raise AppError("content.too_short")
        with self._db.connect() as conn:
            self._project_row(conn, project_id)
            self._insert_source(conn, project_id, "document", filename, "", text)
        return self.get(project_id)

    def add_text(self, project_id: int, title: str, text: str) -> dict[str, Any]:
        text, _ = limit_content(text.strip())
        if len(text) < 100:
            raise AppError("content.too_short")
        with self._db.connect() as conn:
            self._project_row(conn, project_id)
            self._insert_source(conn, project_id, "text", title.strip() or text[:60], "", text)
        return self.get(project_id)

    def _questions(self, row: sqlite3.Row) -> str:
        plan = json.loads(row["plan"]) if row["plan"] else {}
        return "\n".join(f"- {q}" for q in plan.get("questions", [])) or "-"

    def web_prompt(self, project_id: int) -> dict[str, Any]:
        """Web research needs a chat with web search (Claude, ChatGPT...): always a handoff."""
        with self._db.connect() as conn:
            row = self._project_row(conn, project_id)
        names = prompts.LANGUAGE_NAMES[self._lang()]
        langs = ", ".join(names.get(x, x) for x in json.loads(row["languages"]))
        prompt = prompts.render("research_web", self._lang(), goal=row["goal"],
                                questions=self._questions(row), languages=langs)  # fmt: skip
        return {"mode": "chat", "fallback": None, "handoff": self._ai.handoff(prompt)}

    def parse_web(self, project_id: int, text: str) -> dict[str, Any]:
        found = parse_answer(text, WebResearch)
        with self._db.connect() as conn:
            self._project_row(conn, project_id)
            for item in found.sources:
                body = "\n".join(f"- {p}" for p in item.points)
                try:
                    self._insert_source(conn, project_id, "web", item.title or item.url,
                                        item.url, body, author=item.author)  # fmt: skip
                except AppError as exc:
                    if exc.code == "research.duplicate_source":
                        continue
                    raise
        return self.get(project_id)

    # -- background work ---------------------------------------------------------------

    def _enqueue(self, job: str, item_id: int) -> None:
        self._queue.put((job, item_id))
        if not self._start_worker:
            return
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(target=self._work, name="research", daemon=True)
                self._worker.start()

    def run_pending(self) -> None:
        """Process the queue in the calling thread (tests)."""
        while not self._queue.empty():
            self._run_job(*self._queue.get())

    def _work(self) -> None:
        while True:
            try:
                job, item_id = self._queue.get(timeout=30)
            except queue.Empty:
                return
            try:
                self._run_job(job, item_id)
            finally:
                self._queue.task_done()

    def _run_job(self, job: str, item_id: int) -> None:
        try:
            if job == "collect":
                self._do_collect(item_id)
            elif job == "video":
                self._do_video(item_id)
        except Exception:
            log.exception("Research job %s %s failed", job, item_id)

    def resume(self) -> None:
        """At startup: videos left in the queue when the app was closed start again."""
        with self._db.connect() as conn:
            conn.execute(
                "UPDATE research_sources SET status = 'queued' WHERE status = 'processing'"
            )
            pending = [
                r[0]
                for r in conn.execute("SELECT id FROM research_sources WHERE status = 'queued'")
            ]
        for source_id in pending:
            self._enqueue("video", source_id)

    def _publish(self, project_id: int, status: str, step: str | None = None,
                 source_id: int | None = None) -> None:  # fmt: skip
        self._bus.publish(
            "research.changed",
            {"project_id": project_id, "source_id": source_id, "status": status, "step": step},
        )

    def _set_source(self, source_id: int, project_id: int, **fields: Any) -> None:
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self._db.connect() as conn:
            conn.execute(f"UPDATE research_sources SET {sets} WHERE id = ?",
                         (*fields.values(), source_id))  # fmt: skip
        self._publish(project_id, fields.get("status", "processing"), fields.get("step"), source_id)

    def _do_video(self, source_id: int) -> None:
        with self._db.connect() as conn:
            try:
                row = self._source_row(conn, source_id)
            except AppError:
                return  # deleted while waiting
            goal = self._project_row(conn, row["project_id"])["goal"]
        if row["status"] == "ready":
            return
        project_id = row["project_id"]
        work = Path(tempfile.mkdtemp(prefix="taleport-video-"))
        try:
            self._set_source(source_id, project_id, status="processing", step="download")
            audio, info = self._download(
                row["url"], work, self._ensure_runtime(source_id, project_id)
            )
            self._set_source(source_id, project_id, status="processing", step="transcribe",
                             title=info.title or row["title"], author=info.channel,
                             meta=json.dumps({"duration": info.duration, "views": info.views,
                                              **info.meta}))  # fmt: skip
            wav = work / "audio.wav"
            extract = self._extract_wav or _default_extract_wav
            if not extract(audio, wav):
                raise AppError("research.video_no_audio")
            transcribe = self._transcribe or _default_transcribe
            transcript = transcribe(wav)
            text = transcript_text(transcript.segments)
            if len(text) < 50:
                raise AppError("research.video_no_speech")
            self._set_source(source_id, project_id, status="processing", step="summary",
                             content=text, language=transcript.language)  # fmt: skip
            digest = self._digest_in_background(goal, info.title, "video", text)
            self._set_source(source_id, project_id, status="ready", step=None,
                             digest=json.dumps(digest) if digest else None)  # fmt: skip
        except AppError as exc:
            log.info("Research video %s: %s", source_id, exc.code)
            self._set_source(source_id, project_id, status="error", step=None, error_code=exc.code)
        except Exception:
            log.exception("Research video %s failed", source_id)
            self._set_source(source_id, project_id, status="error", step=None,
                             error_code="research.video_failed")  # fmt: skip
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _ensure_runtime(self, source_id: int, project_id: int) -> Callable[[], None]:
        def ensure() -> None:
            self._set_source(source_id, project_id, status="processing", step="runtime")
            http = self._http()
            try:
                links.install_deno(lambda url: _get_bytes(http, url))
            finally:
                http.close()
            self._set_source(source_id, project_id, status="processing", step="download")

        return ensure

    def _digest_in_background(self, goal: str, title: str, kind: str, text: str) -> dict | None:
        """Goal-focused summary right after a transcription, when an AI the app can call is
        selected (with "Open in chat" it happens in the dossier step)."""
        resolved, provider, _ = self._ai.resolve(None)
        if provider is None:
            return None
        try:
            digest = run_structured(provider, self._digest_prompt(goal, title, kind, text),
                                    SourceDigest, self._ai.recorder(provider, "research_digest"),
                                    max_tokens=MAX_TOKENS)  # fmt: skip
        except Exception:
            log.info("Background summary failed: the dossier step will retry", exc_info=True)
            return None
        return digest.model_dump()

    def _digest_prompt(self, goal: str, title: str, kind: str, text: str) -> prompts.Prompt:
        return prompts.render("source_digest", self._lang(), goal=goal, title=title or "-",
                              kind=kind, content=text[:DIGEST_INPUT_CHARS])  # fmt: skip

    # -- 3. dossier --------------------------------------------------------------------

    def _ready_sources(self, conn: sqlite3.Connection, project_id: int) -> list[sqlite3.Row]:
        return conn.execute(
            "SELECT * FROM research_sources WHERE project_id = ? AND status = 'ready'"
            " AND content != '' ORDER BY id",
            (project_id,),
        ).fetchall()

    def _sources_block(self, rows: list[sqlite3.Row]) -> str:
        budget = max(1500, DOSSIER_SOURCES_CHARS // max(1, len(rows)))
        parts = []
        for n, row in enumerate(rows, start=1):
            head = f"[{n}] ({row['kind']}) {row['title']}" + (
                f" — {row['url']}" if row["url"] else ""
            )
            digest = json.loads(row["digest"]) if row["digest"] else None
            if digest:
                body = (
                    digest.get("summary", "")
                    + "\n"
                    + "\n".join(
                        f"- ({p.get('kind', '')}{', ' + p['time'] if p.get('time') else ''})"
                        f" {p['text']}"
                        for p in digest.get("points", [])
                    )
                )
            else:
                body = row["content"][:budget]
            parts.append(f"{head}\n{body.strip()}")
        return "\n\n".join(parts)

    def _dossier_prompt(self, row: sqlite3.Row, sources: list[sqlite3.Row], ai_knowledge: bool):
        lang = self._lang()
        return prompts.render(
            "research_dossier", lang, goal=row["goal"], questions=self._questions(row),
            sources=self._sources_block(sources), ai_knowledge=AI_KNOWLEDGE[ai_knowledge][lang],
        )  # fmt: skip

    def build_dossier(
        self, project_id: int, mode: str | None = None, ai_knowledge: bool = False
    ) -> dict[str, Any]:
        with self._db.connect() as conn:
            row = self._project_row(conn, project_id)
            sources = self._ready_sources(conn, project_id)
        if not sources:
            raise AppError("research.no_sources")
        resolved, provider, fallback = self._ai.resolve(mode)
        if provider is not None:  # summarize long sources for the goal first
            for source in sources:
                if source["digest"] or len(source["content"]) < DIGEST_MIN_CHARS:
                    continue
                try:
                    digest = run_structured(
                        provider,
                        self._digest_prompt(row["goal"], source["title"], source["kind"],
                                            source["content"]),
                        SourceDigest, self._ai.recorder(provider, "research_digest"),
                        max_tokens=MAX_TOKENS,
                    )  # fmt: skip
                except ProviderError as exc:
                    raise AppError.from_provider(exc) from exc
                except AppError:
                    continue  # this source goes in as text
                with self._db.connect() as conn:
                    conn.execute("UPDATE research_sources SET digest = ? WHERE id = ?",
                                 (digest.model_dump_json(), source["id"]))  # fmt: skip
            with self._db.connect() as conn:
                sources = self._ready_sources(conn, project_id)
        prompt = self._dossier_prompt(row, sources, ai_knowledge)
        if provider is None:
            return {"mode": "chat", "fallback": fallback, "handoff": self._ai.handoff(prompt)}
        try:
            dossier = run_structured(provider, prompt, Dossier,
                                     self._ai.recorder(provider, "research_dossier"),
                                     max_tokens=MAX_TOKENS)  # fmt: skip
        except ProviderError as exc:
            raise AppError.from_provider(exc) from exc
        return {"mode": resolved, "project": self._save_dossier(project_id, sources, dossier)}

    def parse_dossier(self, project_id: int, text: str) -> dict[str, Any]:
        with self._db.connect() as conn:
            self._project_row(conn, project_id)
            sources = self._ready_sources(conn, project_id)
        dossier = parse_answer(text, Dossier)
        return {"mode": "chat", "project": self._save_dossier(project_id, sources, dossier)}

    def _save_dossier(self, project_id: int, sources: list[sqlite3.Row], dossier: Dossier):
        numbered = [
            {"n": n, "id": s["id"], "title": s["title"], "url": s["url"], "kind": s["kind"]}
            for n, s in enumerate(sources, start=1)
        ]
        valid = {s["n"] for s in numbered}
        for section in SECTIONS:
            for item in getattr(dossier, section):
                item.sources = [n for n in item.sources if n in valid]
        for item in dossier.ai_knowledge:
            item.sources = []
        with self._db.connect() as conn:
            conn.execute(
                f"UPDATE research_projects SET dossier = ?, updated_at = {_NOW} WHERE id = ?",
                (json.dumps({**dossier.model_dump(), "sources": numbered}), project_id),
            )
        return self.get(project_id)

    def dossier_text(self, project_id: int) -> dict[str, Any]:
        """The dossier as plain text, for the post generator ("from long content")."""
        with self._db.connect() as conn:
            row = self._project_row(conn, project_id)
        if not row["dossier"]:
            raise AppError("research.no_dossier")
        text = render_dossier(json.loads(row["dossier"]), self._lang(), row["goal"])
        return {"title": row["title"], "text": text}

    # -- 4. article --------------------------------------------------------------------

    def _article_prompt(self, row: sqlite3.Row, language: str, length: str, tone: str):
        dossier = json.loads(row["dossier"])
        lang = self._lang()
        sources = "\n".join(
            f"[{s['n']}] {s['title']}" + (f" — {s['url']}" if s["url"] else "")
            for s in dossier.get("sources", [])
        )
        names = prompts.LANGUAGE_NAMES[lang]
        return prompts.render(
            "research_article", lang, goal=row["goal"],
            dossier=render_dossier(dossier, lang, None, with_sources=False),
            sources=sources or "-", article_language=names.get(language, language),
            length=ARTICLE_LENGTH.get(length, ARTICLE_LENGTH["medium"])[lang],
            tone=tone or DEFAULT_TONE[lang],
        )  # fmt: skip

    def write_article(
        self, project_id: int, language: str, length: str = "medium", tone: str = "",
        mode: str | None = None,
    ) -> dict[str, Any]:  # fmt: skip
        with self._db.connect() as conn:
            row = self._project_row(conn, project_id)
        if not row["dossier"]:
            raise AppError("research.no_dossier")
        resolved, answer = self._ask(self._article_prompt(row, language, length, tone),
                                     Article, mode, "research_article")  # fmt: skip
        if resolved == "chat":
            return answer
        return {"mode": resolved, "project": self._save_article(project_id, answer, language)}

    def parse_article(self, project_id: int, text: str, language: str) -> dict[str, Any]:
        with self._db.connect() as conn:
            self._project_row(conn, project_id)
        article = parse_answer(text, Article)
        return {"mode": "chat", "project": self._save_article(project_id, article, language)}

    def _save_article(self, project_id: int, article: Article, language: str) -> dict[str, Any]:
        with self._db.connect() as conn:
            conn.execute(
                f"UPDATE research_projects SET article = ?, updated_at = {_NOW} WHERE id = ?",
                (json.dumps({**article.model_dump(), "language": language}), project_id),
            )
        return self.get(project_id)

    def article_docx(self, project_id: int) -> dict[str, Any]:
        from taleport.core import exports
        from taleport.research.docx import article_docx

        with self._db.connect() as conn:
            row = self._project_row(conn, project_id)
        if not row["article"]:
            raise AppError("research.no_article")
        article = json.loads(row["article"])
        dossier = json.loads(row["dossier"] or "{}")
        data = article_docx(article, dossier.get("sources", []), self._lang())
        label = exports.safe_label(article.get("title") or row["title"])
        name = f"Articolo_{label}_{exports.stamp()}.docx"
        return exports.save(name, data)


def render_dossier(
    dossier: dict[str, Any], lang: str, goal: str | None, *, with_sources: bool = True
) -> str:
    titles = SECTION_TITLES.get(lang, SECTION_TITLES["en"])
    parts = [dossier.get("title") or "", dossier.get("summary") or ""]
    if goal:
        parts.insert(0, goal)
    for section in (*SECTIONS, "ai_knowledge"):
        items = dossier.get(section) or []
        if not items:
            continue
        lines = [f"## {titles[section]}"]
        for item in items:
            refs = (
                f" [{', '.join(map(str, item.get('sources') or []))}]"
                if item.get("sources")
                else ""
            )
            lines.append(f"- {item['text']}{refs}")
        parts.append("\n".join(lines))
    if with_sources and dossier.get("sources"):
        parts.append(f"## {titles['sources']}\n" + "\n".join(
            f"[{s['n']}] {s['title']}" + (f" — {s['url']}" if s.get("url") else "")
            for s in dossier["sources"]
        ))  # fmt: skip
    return "\n\n".join(p for p in parts if p).strip()


def _get_bytes(http: HttpClient, url: str) -> bytes:
    response = http.get(url)
    if response.status_code >= 400:
        raise AppError("research.js_runtime_missing")
    return response.content


def _default_extract_wav(source: Path, target: Path) -> bool:
    from taleport.video import media

    return media.extract_wav(source, target)


def _default_transcribe(wav: Path) -> Any:
    from taleport.video import transcribe

    if not transcribe.package_available():
        raise AppError("research.transcriber_missing")
    return transcribe.transcribe(wav)
