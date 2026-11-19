"""Filesystem locations used by the app."""

from __future__ import annotations

import logging
import os
import sys
import tempfile
import uuid
from pathlib import Path

from taleport import APP_NAME

log = logging.getLogger(__name__)


def data_dir() -> Path:
    """Per-user data folder (%LOCALAPPDATA%\\TALeport). TALEPORT_DATA_DIR overrides it (tests)."""
    override = os.environ.get("TALEPORT_DATA_DIR")
    if override:
        base = Path(override)
    else:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        base = Path(local) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def _subdir(name: str) -> Path:
    path = data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "taleport.db"


def logs_dir() -> Path:
    return _subdir("logs")


def exports_dir() -> Path:
    return _subdir("exports")


def branding_dir() -> Path:
    """User files for report covers (custom logo)."""
    return _subdir("branding")


def _writable(path: Path) -> bool:
    """True if this user can create and delete files in `path` (and in WebView2's own
    `EBWebView` subfolder, when it already exists)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        for folder in (path, path / "EBWebView"):
            if folder.is_dir():
                probe = folder / f".write-test-{uuid.uuid4().hex}"
                probe.write_bytes(b"ok")
                probe.unlink()
        return True
    except OSError as exc:
        log.warning("Folder not writable: %s (%s)", path, exc)
        return False


def first_writable(*candidates: Path) -> Path:
    for path in candidates:
        if _writable(path):
            return path
    return candidates[-1]


def webview_storage_dir() -> Path:
    """Data folder of the built-in window (Edge WebView2). If it cannot be written (left behind
    by another account, blocked by security software) a fresh folder is used instead."""
    return first_writable(
        data_dir() / "webview",
        data_dir() / "webview2",
        Path(tempfile.gettempdir()) / f"{APP_NAME}-webview",
    )


def browser_profile_dir() -> Path:
    """Profile of the Chrome/Edge app window (separate from the user's own browser profile)."""
    return first_writable(
        data_dir() / "browser", Path(tempfile.gettempdir()) / f"{APP_NAME}-browser"
    )


def instance_file() -> Path:
    """Port and session token of the running instance, used to focus it from a second launch."""
    return data_dir() / "instance.json"


def bundle_root() -> Path:
    """Root of bundled resources: PyInstaller's extraction dir when frozen, else the repo root."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[3]


def frontend_dist() -> Path:
    root = bundle_root()
    return root / "frontend" if getattr(sys, "frozen", False) else root / "frontend" / "dist"
