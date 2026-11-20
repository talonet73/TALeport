"""Video links: audio download with yt-dlp, and YouTube search without an API key.

Only the audio track is downloaded, into a temporary folder, and deleted after the
transcription. YouTube needs a JavaScript runtime for its player: Deno or Node already on the
PC are used; otherwise Deno (open source, MIT) is downloaded once into
`%LOCALAPPDATA%\\TALeport\\tools\\`. Instagram, TikTok, Facebook and most other sites do not
need it.
"""

from __future__ import annotations

import io
import logging
import shutil
import sys
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from taleport.core.errors import AppError
from taleport.core.paths import data_dir

log = logging.getLogger(__name__)

MAX_DURATION_SECONDS = 3 * 3600
SEARCH_RESULTS = 5
DENO_URL = (
    "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip"
)
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


@dataclass
class VideoInfo:
    title: str = ""
    url: str = ""
    channel: str = ""
    duration: float = 0
    views: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def is_url(text: str) -> bool:
    parts = urlsplit(text.strip())
    return parts.scheme in ("http", "https") and bool(parts.hostname)


def is_youtube(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _YOUTUBE_HOSTS)


def tools_dir() -> Path:
    path = data_dir() / "tools"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _deno_path() -> Path:
    return tools_dir() / ("deno.exe" if sys.platform == "win32" else "deno")


def find_js_runtime() -> dict[str, dict[str, str]]:
    """yt-dlp `js_runtimes` option: TALeport's Deno, then Deno/Node/Bun on the PATH."""
    if _deno_path().is_file():
        return {"deno": {"path": str(_deno_path())}}
    for name in ("deno", "node", "bun"):
        found = shutil.which(name)
        if found:
            return {name: {"path": found}}
    return {}


def install_deno(get: Callable[[str], bytes]) -> Path:
    """Download Deno once (Windows x64 build). `get` returns the bytes of a URL."""
    if sys.platform != "win32":
        raise AppError("research.js_runtime_missing")
    try:
        data = get(DENO_URL)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            member = next(n for n in archive.namelist() if n.lower().endswith("deno.exe"))
            target = _deno_path()
            target.write_bytes(archive.read(member))
    except AppError:
        raise
    except Exception as exc:
        log.exception("Could not download Deno")
        raise AppError("research.js_runtime_missing") from exc
    return target


def _ydl_options(**extra: Any) -> dict[str, Any]:
    from taleport.video.media import ffmpeg_exe

    options: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_exe(),
        "socket_timeout": 30,
        "retries": 3,
        "logger": _QuietLogger(),
    }
    runtime = find_js_runtime()
    if runtime:
        options["js_runtimes"] = runtime
    options.update(extra)
    return options


class _QuietLogger:
    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        log.debug("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.info("yt-dlp: %s", msg)


def _info(raw: dict[str, Any], url: str) -> VideoInfo:
    return VideoInfo(
        title=str(raw.get("title") or "")[:300],
        url=str(raw.get("webpage_url") or raw.get("url") or url),
        channel=str(raw.get("channel") or raw.get("uploader") or "")[:200],
        duration=float(raw.get("duration") or 0),
        views=raw.get("view_count"),
        meta={
            "site": raw.get("extractor_key") or raw.get("ie_key") or "",
            "upload_date": raw.get("upload_date") or "",
        },
    )


def download_audio(
    url: str, folder: Path, ensure_runtime: Callable[[], None] | None = None
) -> tuple[Path, VideoInfo]:
    """Download the best audio track of `url` into `folder`. Raises AppError with a code the
    interface explains (private video, unsupported site, too long, ...)."""
    import yt_dlp

    if is_youtube(url) and not find_js_runtime() and ensure_runtime:
        ensure_runtime()
    folder.mkdir(parents=True, exist_ok=True)
    options = _ydl_options(
        format="bestaudio/best",
        outtmpl=str(folder / "audio.%(ext)s"),
        match_filter=_not_too_long,
    )
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            raw = ydl.extract_info(url, download=True)
    except AppError:
        raise
    except Exception as exc:
        raise _explain(exc) from exc
    if not raw:
        raise AppError("research.video_unavailable")
    if raw.get("_type") == "playlist":
        raise AppError("research.video_playlist")
    files = [f for f in folder.iterdir() if f.is_file() and f.stem == "audio"]
    if not files:
        if (raw.get("duration") or 0) > MAX_DURATION_SECONDS:
            raise AppError("research.video_too_long", hours=MAX_DURATION_SECONDS // 3600)
        raise AppError("research.video_unavailable")
    return files[0], _info(raw, url)


def _not_too_long(info: dict[str, Any], *, incomplete: bool = False) -> str | None:
    if (info.get("duration") or 0) > MAX_DURATION_SECONDS:
        return "too long"
    return None


def _explain(exc: Exception) -> AppError:
    text = str(exc).lower()
    if "private" in text or "sign in" in text or "login" in text or "cookies" in text:
        return AppError("research.video_private")
    if "unsupported url" in text:
        return AppError("research.video_unsupported")
    if "javascript" in text or "js runtime" in text or "challenge" in text:
        return AppError("research.js_runtime_missing")
    if "unavailable" in text or "removed" in text or "404" in text:
        return AppError("research.video_unavailable")
    log.warning("Video download failed: %s", exc)
    return AppError("research.video_download_failed")


def search_youtube(query: str, count: int = SEARCH_RESULTS) -> list[VideoInfo]:
    """Video suggestions for a query (titles, channels, links), without downloading."""
    import yt_dlp

    options = _ydl_options(extract_flat="in_playlist", skip_download=True)
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            raw = ydl.extract_info(f"ytsearch{count}:{query}", download=False) or {}
    except Exception:
        log.warning("YouTube search failed for %r", query, exc_info=True)
        return []
    found = []
    for entry in raw.get("entries") or []:
        if not entry or not entry.get("id"):
            continue
        info = _info(entry, f"https://www.youtube.com/watch?v={entry['id']}")
        if not info.url.startswith("http"):
            info.url = f"https://www.youtube.com/watch?v={entry['id']}"
        if info.duration and info.duration > MAX_DURATION_SECONDS:
            continue
        found.append(info)
    return found
