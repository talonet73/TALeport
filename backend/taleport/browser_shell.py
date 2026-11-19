"""TALeport in a browser window instead of the built-in one (Edge WebView2).

Used when the user picks "Google Chrome" in the settings, or automatically when the built-in
window cannot start (for example WebView2 cannot write its data folder on that PC).
Chrome opens in app mode (`--app`): a plain window without tabs or address bar, with its own
profile inside TALeport's data folder, so it never touches the user's normal Chrome.
If Chrome is missing, the Edge browser is used the same way, then the default browser.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

WINDOW_SIZE = "1440,900"
_CHROME = ("Google", "Chrome", "Application", "chrome.exe")
_EDGE = ("Microsoft", "Edge", "Application", "msedge.exe")


def _registry_app_path(exe: str) -> Path | None:
    if sys.platform != "win32":
        return None
    import winreg

    key_path = rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "")
        except OSError:
            continue
        path = Path(str(value).strip('"'))
        if path.is_file():
            return path
    return None


def _find(parts: tuple[str, ...]) -> Path | None:
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base and (Path(base).joinpath(*parts)).is_file():
            return Path(base).joinpath(*parts)
    return _registry_app_path(parts[-1])


def find_browser() -> Path | None:
    """Chrome first (the user's choice), then the Edge browser; None if neither is installed."""
    return _find(_CHROME) or _find(_EDGE)


def browser_command(exe: Path, url: str, profile_dir: Path) -> list[str]:
    return [
        str(exe),
        f"--app={url}",
        f"--user-data-dir={profile_dir}",
        f"--window-size={WINDOW_SIZE}",
        "--no-first-run",
        "--no-default-browser-check",
    ]


class BrowserShell:
    """Opens (or reopens) the UI in a browser app window. `focus` is safe to call repeatedly."""

    def __init__(
        self,
        url: str,
        profile_dir: Path,
        *,
        on_closed: Callable[[], None] | None = None,
        finder: Callable[[], Path | None] = find_browser,
        launcher: Callable[[list[str]], subprocess.Popen] | None = None,
        open_default: Callable[[str], object] = webbrowser.open,
    ) -> None:
        self._url = url
        self._profile_dir = profile_dir
        self._on_closed = on_closed
        self._finder = finder
        self._launch = launcher or (lambda cmd: subprocess.Popen(cmd, close_fds=True))
        self._open_default = open_default
        self._watching = False
        self._process: subprocess.Popen | None = None

    def focus(self) -> None:
        exe = self._finder()
        if exe is None:
            log.warning("No Chrome or Edge found: opening TALeport in the default browser")
            self._open_default(self._url)
            return
        log.info("Opening TALeport in %s", exe.name)
        try:
            process = self._launch(browser_command(exe, self._url, self._profile_dir))
        except OSError:
            log.exception("Could not start %s: opening the default browser", exe)
            self._open_default(self._url)
            return
        self._watch(process)

    def _watch(self, process: subprocess.Popen) -> None:
        """Tell the app when the window is closed (the first process owns the window; a later
        launch with the same profile only hands the request over and exits at once)."""
        if self._watching or self._on_closed is None:
            return
        self._watching = True
        self._process = process
        started = time.monotonic()

        def wait() -> None:
            process.wait()
            self._watching = False
            self._process = None
            if time.monotonic() - started > 5 and self._on_closed:
                self._on_closed()

        threading.Thread(target=wait, name="browser-window", daemon=True).start()

    def close(self) -> None:
        """When the app quits: close the window it opened (its own profile, never the user's)."""
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                log.debug("Could not close the browser window", exc_info=True)
