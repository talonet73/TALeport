"""Research from a goal: plan, evergreen sources, video transcripts, dossier, article."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from taleport.ai import prompts
from taleport.api.context import AppContext, build_context
from taleport.collectors.http import HttpClient
from taleport.core.errors import AppError
from taleport.db.database import Database
from taleport.research import links
from taleport.research.schemas import Dossier, ResearchPlan
from taleport.research.service import ResearchService, render_dossier, transcript_text
from tests.conftest import TEST_TOKEN
from tests.test_ai import FakeProvider

GOAL = "Articolo su cosa fa un social media strategist: regole, errori, esperienze ed esempi"
PLAN = {
    "title": "Il social media strategist",
    "questions": ["Che cosa fa?", "Quali errori evitare?"],
    "keywords": {"it": ["social media strategist"]},
    "wikipedia": {"it": ["Social media marketing"]},
    "reddit_queries": ["social media strategist experience"],
    "youtube_queries": ["social media strategy tutorial"],
    "content_types": ["guide"],
}
LONG_TEXT = "Il social media marketing usa le piattaforme sociali per promuovere un marchio. " * 80
DOSSIER = {
    "title": "Social media strategist",
    "summary": "Chi è e cosa fa.",
    "notions": [{"text": "Definisce obiettivi e KPI", "sources": [1, 99]}],
    "rules": [{"text": "Prima la strategia, poi i contenuti", "sources": [2]}],
    "examples": [],
    "experiences": [],
    "mistakes": ["Pubblicare senza un piano"],
    "quotes": [],
    "ai_knowledge": [{"text": "Il ruolo è nato con i social", "sources": [1]}],
    "gaps": ["Stipendi"],
}


def _wiki_and_reddit(request: httpx.Request) -> httpx.Response:
    if "wikipedia.org" in request.url.host:
        params = request.url.params
        if params.get("list") == "search":
            return httpx.Response(
                200, json={"query": {"search": [{"title": "Social media marketing"}]}}
            )
        extract = LONG_TEXT + "\n== Note ==\nriferimenti da togliere"
        return httpx.Response(200, json={"query": {"pages": {"1": {"extract": extract}}}})
    if "reddit.com" in request.url.host:
        rss = (
            '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            "<title>Come ho impostato la strategia per un cliente</title>"
            '<link href="https://www.reddit.com/r/socialmedia/comments/1"/>'
            '<content type="html">Prima ho definito i KPI. submitted by /u/someone</content>'
            "</entry></feed>"
        )
        return httpx.Response(200, text=rss, headers={"content-type": "application/atom+xml"})
    return httpx.Response(404)


@pytest.fixture
def fake() -> FakeProvider:
    return FakeProvider([])


@pytest.fixture
def rctx(db: Database, fake: FakeProvider) -> AppContext:
    return build_context(
        db, TEST_TOKEN, collectors_factory=lambda: [], ai_provider_factory=lambda *a: fake,
        start_video_worker=False,
    )  # fmt: skip


class Downloads:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: AppError | None = None

    def __call__(self, url: str, folder: Path, ensure_runtime=None):
        self.calls.append(url)
        if self.fail:
            raise self.fail
        folder.mkdir(parents=True, exist_ok=True)
        audio = folder / "audio.m4a"
        audio.write_bytes(b"x" * 2000)
        info = links.VideoInfo(title="Intervista a una strategist", url=url, channel="Canale",
                               duration=600, meta={"site": "Youtube"})  # fmt: skip
        return audio, info


def _segments():
    seg = SimpleNamespace
    return SimpleNamespace(
        language="it",
        segments=[
            seg(start=0.0, end=4.0, text="La prima regola è avere un obiettivo misurabile."),
            seg(start=12.0, end=16.0, text="Il primo errore è copiare i competitor."),
            seg(start=45.0, end=50.0, text="Con un cliente abbiamo raddoppiato le vendite."),
        ],
    )


@pytest.fixture
def downloads() -> Downloads:
    return Downloads()


@pytest.fixture
def research(rctx: AppContext, downloads: Downloads) -> ResearchService:
    service = ResearchService(
        rctx.db, rctx.ai, rctx.bus,
        http=lambda: HttpClient(transport=httpx.MockTransport(_wiki_and_reddit), max_attempts=1),
        start_worker=False,
        transcribe=lambda wav: _segments(),
        download=downloads,
        search_videos=lambda q: [links.VideoInfo(title=f"Video {q}", url=f"https://youtu.be/{len(q)}",
                                                 channel="Canale", duration=300)],
        extract_wav=lambda src, dst: dst.write_bytes(b"w" * 2000) > 0,
    )  # fmt: skip
    rctx.research = service
    rctx.settings.update({"default_ai": "openai"})  # background summaries use the default AI
    return service


def _with_plan(research: ResearchService, fake: FakeProvider) -> int:
    project = research.create(GOAL, ["it", "en"])
    fake.answers.append(json.dumps(PLAN))
    research.plan(project["id"], "openai")
    return project["id"]


def test_create_and_plan(research: ResearchService, fake: FakeProvider) -> None:
    with pytest.raises(AppError) as info:
        research.create("corto", ["it"])
    assert info.value.code == "research.goal_short"

    project = research.create(GOAL, ["it", "xx", "en"])
    assert project["languages"] == ["it", "en"] and project["plan"] is None

    fake.answers.append(json.dumps({"plan": {**PLAN, "keywords": ["strategist", "piano"]}}))
    planned = research.plan(project["id"], "openai")["project"]
    assert planned["plan"]["questions"] == PLAN["questions"]
    assert planned["plan"]["keywords"] == {"it": ["strategist", "piano"]}  # no language: first
    assert planned["title"] == PLAN["title"]
    assert GOAL in fake.calls[-1][1] and "inglese (en)" in fake.calls[-1][1]

    handoff = research.plan(project["id"], "chat")
    assert GOAL in handoff["handoff"]["prompt"]
    edited = research.update(project["id"], {"plan": {**PLAN, "questions": ["Una sola"]}})
    assert edited["plan"]["questions"] == ["Una sola"]
    assert research.parse_plan(project["id"], json.dumps(PLAN))["project"]["plan"]["questions"][0]


def test_collect_finds_wikipedia_reddit_and_youtube(research, fake) -> None:
    project_id = _with_plan(research, fake)
    with pytest.raises(AppError):
        research.collect(research.create(GOAL, ["it"])["id"])  # no plan yet
    assert research.collect(project_id)["collecting"]
    research.run_pending()

    sources = research.get(project_id)["sources"]
    kinds = {s["kind"] for s in sources}
    assert kinds == {"wikipedia", "reddit", "youtube"}
    wiki = next(s for s in sources if s["kind"] == "wikipedia")
    assert research.source(wiki["id"])["content"].strip().endswith("marchio.")  # "Note" dropped
    reddit = research.source(next(s["id"] for s in sources if s["kind"] == "reddit"))
    assert "someone" not in reddit["content"] and "KPI" in reddit["content"]
    youtube = next(s for s in sources if s["kind"] == "youtube")
    assert youtube["status"] == "found" and youtube["author"] == "Canale"
    assert not research.get(project_id)["collecting"]


def test_video_links_are_transcribed_and_summarized(research, fake, downloads) -> None:
    project_id = _with_plan(research, fake)
    with pytest.raises(AppError) as info:
        research.add_videos(project_id, ["non è un link"])
    assert info.value.code == "research.not_a_link"

    project = research.add_videos(project_id, ["https://www.youtube.com/watch?v=abc"])
    assert project["sources"][0]["status"] == "queued"
    fake.answers.append(json.dumps({
        "summary": "Regole e un caso reale.",
        "points": [{"kind": "rule", "text": "Avere un obiettivo misurabile", "time": "00:00"}],
    }))  # fmt: skip
    research.run_pending()

    video = research.source(project["sources"][0]["id"])
    assert video["status"] == "ready" and video["title"] == "Intervista a una strategist"
    assert video["content"].startswith("[00:00] La prima regola") and "[00:45]" in video["content"]
    assert video["digest"]["points"][0]["kind"] == "rule"
    assert GOAL in fake.calls[-1][1]  # the summary is focused on the goal


def test_video_errors_and_youtube_suggestions(research, fake, downloads) -> None:
    project_id = _with_plan(research, fake)
    downloads.fail = AppError("research.video_private")
    project = research.add_videos(project_id, ["https://www.instagram.com/reel/x"])
    research.run_pending()
    failed = research.get(project_id)["sources"][0]
    assert failed["status"] == "error" and failed["error_code"] == "research.video_private"

    downloads.fail = None
    fake.answers.append(json.dumps({"summary": "ok", "points": ["punto"]}))
    research.retry_source(failed["id"])
    research.run_pending()
    assert research.source(failed["id"])["status"] == "ready"

    research.collect(project_id)
    research.run_pending()
    suggestion = next(s for s in research.get(project_id)["sources"] if s["kind"] == "youtube")
    fake.answers.append(json.dumps({"summary": "ok", "points": ["punto"]}))
    research.transcribe_suggestion(suggestion["id"])
    research.run_pending()
    assert research.source(suggestion["id"])["kind"] == "video"
    assert downloads.calls[-1] == suggestion["url"]
    assert project["id"] == project_id


def test_background_summary_waits_for_the_dossier_with_chat(research, rctx, fake) -> None:
    rctx.settings.update({"default_ai": "chat"})
    project_id = research.create(GOAL, ["it"])["id"]
    research.add_videos(project_id, ["https://youtu.be/x"])
    research.run_pending()
    video = research.get(project_id)["sources"][0]
    assert video["status"] == "ready" and video["digest"] is None and fake.calls == []


def test_documents_texts_and_web_research(research, fake) -> None:
    from docx import Document

    project_id = research.create(GOAL, ["it"])["id"]
    doc = Document()
    doc.add_paragraph("Appunti del corso: " + LONG_TEXT[:600])
    data = io.BytesIO()
    doc.save(data)
    research.add_document(project_id, "corso.docx", base64.b64encode(data.getvalue()).decode())
    research.add_text(project_id, "Mie note", "Le mie esperienze con i clienti. " * 10)
    with pytest.raises(AppError):
        research.add_text(project_id, "", "troppo corto")

    web = research.web_prompt(project_id)
    assert web["mode"] == "chat" and GOAL in web["handoff"]["prompt"]
    answer = {"sources": [
        {"title": "Guida HubSpot", "url": "https://blog.example/guida", "points": ["Regola 1"]},
        {"title": "Senza punti", "url": "https://x.example", "points": []},
    ]}  # fmt: skip
    project = research.parse_web(project_id, f"Ecco:\n```json\n{json.dumps(answer)}\n```")
    assert [s["kind"] for s in project["sources"]] == ["document", "text", "web"]
    research.parse_web(project_id, json.dumps(answer))  # the same link again is skipped
    assert len(research.get(project_id)["sources"]) == 3


def test_dossier_from_sources(research, fake) -> None:
    project_id = research.create(GOAL, ["it"])["id"]
    with pytest.raises(AppError) as info:
        research.build_dossier(project_id, "openai")
    assert info.value.code == "research.no_sources"
    research.add_text(project_id, "Fonte lunga", LONG_TEXT)
    research.add_text(project_id, "Fonte breve", "Prima la strategia, poi i contenuti. " * 6)

    fake.answers += [
        json.dumps({"summary": "Definizione", "points": ["Definisce obiettivi e KPI"]}),
        json.dumps(DOSSIER),
    ]
    project = research.build_dossier(project_id, "openai", ai_knowledge=True)["project"]
    digest_call, dossier_call = fake.calls[-2], fake.calls[-1]
    assert "Fonte lunga" in digest_call[1]
    assert "[1] (text) Fonte lunga" in dossier_call[1] and "Definisce obiettivi" in dossier_call[1]
    assert "conoscenza generale" in dossier_call[0]

    dossier = project["dossier"]
    assert dossier["notions"][0]["sources"] == [1]  # 99 does not exist
    assert dossier["ai_knowledge"][0]["sources"] == []  # general knowledge has no source
    assert dossier["mistakes"][0]["text"] == "Pubblicare senza un piano"
    assert [s["title"] for s in dossier["sources"]] == ["Fonte lunga", "Fonte breve"]

    text = research.dossier_text(project_id)["text"]
    assert "## Regole" in text and "Prima la strategia, poi i contenuti [2]" in text
    assert "## Fonti" in text and "senza fonte" in text.lower()

    trimmed = research.update(project_id, {"dossier": {**dossier, "rules": []}})["dossier"]
    assert trimmed["rules"] == [] and trimmed["sources"] == dossier["sources"]

    handoff = research.build_dossier(project_id, "chat")
    assert "Fonte breve" in handoff["handoff"]["prompt"]
    assert research.parse_dossier(project_id, json.dumps(DOSSIER))["project"]["dossier"]


def test_article_and_word_export(research, fake) -> None:
    project_id = research.create(GOAL, ["it"])["id"]
    research.add_text(project_id, "Fonte", "Prima la strategia, poi i contenuti. " * 6)
    with pytest.raises(AppError) as info:
        research.write_article(project_id, "it", mode="openai")
    assert info.value.code == "research.no_dossier"
    research.parse_dossier(project_id, json.dumps(DOSSIER))

    article = {
        "title": "Cosa fa davvero un social media strategist",
        "subtitle": "Regole ed errori",
        "intro": "Molti lo confondono con il social media manager.",
        "sections": [{"heading": "Prima la strategia", "paragraphs": ["Obiettivi e KPI."]},
                     {"heading": "Vuota", "paragraphs": []}],
        "conclusion": "Parti dagli obiettivi.",
        "sources_used": [1],
    }  # fmt: skip
    fake.answers.append(json.dumps({"article": article}))
    saved = research.write_article(project_id, "en", "long", "", "openai")["project"]["article"]
    assert saved["title"].startswith("Cosa fa") and len(saved["sections"]) == 1
    assert saved["language"] == "en"
    assert "about 1600 words" not in fake.calls[-1][0] and "circa 1600 parole" in fake.calls[-1][0]
    assert "inglese" in fake.calls[-1][0]

    exported = research.article_docx(project_id)
    assert exported["name"].endswith(".docx")
    from docx import Document

    doc = Document(exported["path"])
    texts = [p.text for p in doc.paragraphs]
    assert "Prima la strategia" in texts and "Fonti" in texts


def test_api_flow(client: TestClient, research: ResearchService, fake) -> None:
    created = client.post("/api/research", json={"goal": GOAL, "languages": ["it"]})
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]
    assert client.get("/api/research").json()[0]["id"] == project_id
    assert (
        client.patch(f"/api/research/{project_id}", json={"title": "Nuovo"}).json()["title"]
        == "Nuovo"
    )
    fake.answers.append(json.dumps(PLAN))
    assert (
        client.post(f"/api/research/{project_id}/plan", json={"mode": "openai"}).status_code == 200
    )
    videos = client.post(
        f"/api/research/{project_id}/videos", json={"urls": ["https://youtu.be/1"]}
    )
    assert videos.json()["sources"][0]["status"] == "queued"
    assert client.post("/api/research", json={"goal": "x"}).status_code == 400
    assert client.get("/api/research/999").status_code == 404
    assert client.delete(f"/api/research/{project_id}").status_code == 204


def test_transcript_marks_and_links_helpers(monkeypatch) -> None:
    seg = SimpleNamespace
    text = transcript_text([seg(start=0, text="a"), seg(start=10, text="b"),
                            seg(start=31, text="c"), seg(start=3725, text="d")])  # fmt: skip
    assert text.splitlines() == ["[00:00] a b", "[00:31] c", "[1:02:05] d"]
    assert links.is_youtube("https://youtu.be/x") and links.is_youtube("https://m.youtube.com/w")
    assert not links.is_youtube("https://www.instagram.com/reel/x")
    assert links.is_url("https://tiktok.com/@a/video/1") and not links.is_url("ciao")
    assert (
        links._explain(Exception("ERROR: Private video. Sign in")).code == "research.video_private"
    )
    assert links._explain(Exception("Unsupported URL: x")).code == "research.video_unsupported"
    monkeypatch.setattr(links.shutil, "which", lambda name: None)
    monkeypatch.setattr(links, "_deno_path", lambda: Path("/nonexistent/deno"))
    assert links.find_js_runtime() == {}
    monkeypatch.setattr(
        links.shutil, "which", lambda name: "/usr/bin/node" if name == "node" else None
    )
    assert links.find_js_runtime() == {"node": {"path": "/usr/bin/node"}}


def test_tolerant_schemas() -> None:
    plan = ResearchPlan.model_validate(
        {"domande": "Che cos'è?\nCome si fa?", "keywords": {"IT": "a"}}
    )
    assert plan.questions == ["Che cos'è?", "Come si fa?"] and plan.keywords == {"it": ["a"]}
    dossier = Dossier.model_validate({"dossier": {"sezioni": {"regole": ["r1"], "esempi": [
        {"testo": "e1", "fonti": ["[2]"]}]}}})  # fmt: skip
    assert dossier.rules[0].text == "r1" and dossier.examples[0].sources == [2]
    with pytest.raises(ValueError):
        Dossier.model_validate({"title": "vuoto"})


@pytest.mark.parametrize("language", ["it", "en", "es"])
def test_research_templates_render(language: str) -> None:
    for name in ("research_plan", "source_digest", "research_dossier", "research_web",
                 "research_article"):  # fmt: skip
        values = dict(goal="g", languages="l", title="t", kind="k", content="c", questions="q",
                      sources="s", ai_knowledge="a", dossier="d", article_language="x",
                      length="n", tone="t")  # fmt: skip
        prompt = prompts.render(name, language, **values)
        assert "{{" not in prompt.system + prompt.user, name
    assert render_dossier({"rules": [{"text": "r", "sources": []}]}, language, None)


def test_wav_is_read_without_pyav(tmp_path: Path) -> None:
    import wave

    import numpy as np

    from taleport.video.transcribe import read_wav

    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(np.array([16384, -16384, 32767, 32767], dtype=np.int16).tobytes())
    audio = read_wav(path)
    assert audio.dtype == np.float32 and audio.shape == (2,)
    assert abs(audio[0]) < 1e-6 and audio[1] > 0.99


def test_reddit_queries_are_shortened_and_retried(monkeypatch) -> None:
    from taleport.research import web_sources

    calls = []

    def answer(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        return httpx.Response(404 if request.url.params["sort"] == "relevance" else 200,
                              text='<feed xmlns="http://www.w3.org/2005/Atom"></feed>')  # fmt: skip

    http = HttpClient(transport=httpx.MockTransport(answer), max_attempts=1)
    assert (
        web_sources.reddit(http, ["r/socialmedia - consigli per strategist alle prime armi"]) == []
    )
    assert [c["sort"] for c in calls] == ["relevance", "new"]
    assert calls[0]["q"] == '"consigli per strategist alle prime armi"'
