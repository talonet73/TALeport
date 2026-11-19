"""Built-in window problems: writable data folder, Chrome window, automatic switch to Chrome."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from taleport import main as app_main
from taleport.api.context import AppContext
from taleport.browser_shell import BrowserShell, browser_command
from taleport.core.paths import first_writable


class FakeProcess:
    def __init__(self, seconds: float = 0) -> None:
        self.seconds = seconds

    def wait(self) -> int:
        time.sleep(self.seconds)
        return 0


def test_unwritable_folder_is_skipped(tmp_path: Path) -> None:
    blocked = tmp_path / "webview"
    blocked.write_text("a file where a folder should be")  # mkdir fails like a denied folder
    assert first_writable(blocked, tmp_path / "webview2") == tmp_path / "webview2"
    assert first_writable(tmp_path / "ok") == tmp_path / "ok"


def test_unwritable_webview2_subfolder_is_skipped(tmp_path: Path, monkeypatch) -> None:
    good = tmp_path / "webview"
    (good / "EBWebView").mkdir(parents=True)
    real_write = Path.write_bytes

    def denied(self: Path, data: bytes) -> int:
        if self.parent.name == "EBWebView":
            raise PermissionError("access denied")
        return real_write(self, data)

    monkeypatch.setattr(Path, "write_bytes", denied)
    assert first_writable(good, tmp_path / "webview2") == tmp_path / "webview2"


def test_browser_command_opens_an_app_window_with_its_own_profile(tmp_path: Path) -> None:
    command = browser_command(Path("chrome.exe"), "http://127.0.0.1:5/#t=x", tmp_path)
    assert command[0] == "chrome.exe"
    assert "--app=http://127.0.0.1:5/#t=x" in command
    assert f"--user-data-dir={tmp_path}" in command


def test_browser_shell_launches_chrome_or_falls_back(tmp_path: Path) -> None:
    launched: list[list[str]] = []
    opened: list[str] = []
    shell = BrowserShell(
        "http://u",
        tmp_path,
        finder=lambda: Path("chrome.exe"),
        launcher=lambda cmd: launched.append(cmd) or FakeProcess(),
        open_default=opened.append,
    )
    shell.focus()
    assert launched and launched[0][1] == "--app=http://u" and not opened

    BrowserShell("http://u", tmp_path, finder=lambda: None, open_default=opened.append).focus()

    def broken(_cmd: list[str]):
        raise OSError("cannot start")

    BrowserShell(
        "http://u", tmp_path, finder=lambda: Path("c.exe"), launcher=broken,
        open_default=opened.append,
    ).focus()  # fmt: skip
    assert opened == ["http://u", "http://u"]


def test_closing_the_browser_window_is_reported_only_after_real_use(tmp_path: Path, monkeypatch):
    closed: list[bool] = []
    clock = iter([0.0, 10.0])
    monkeypatch.setattr("taleport.browser_shell.time.monotonic", lambda: next(clock))
    shell = BrowserShell(
        "http://u", tmp_path, on_closed=lambda: closed.append(True),
        finder=lambda: Path("chrome.exe"), launcher=lambda _c: FakeProcess(),
    )  # fmt: skip
    shell.focus()
    for _ in range(50):
        if closed:
            break
        time.sleep(0.02)
    assert closed == [True]


def test_ui_ready_route(client: TestClient, ctx: AppContext) -> None:
    assert not ctx.ui_ready.is_set()
    assert client.post("/api/app/ready").status_code == 204
    assert ctx.ui_ready.is_set()


def test_new_settings_have_safe_defaults(ctx: AppContext) -> None:
    settings = ctx.settings.get()
    assert settings.window_mode == "auto" and settings.webview_failed is False
    assert ctx.settings.update({"window_mode": "chrome"}).window_mode == "chrome"


class FakeWindow:
    def __init__(self) -> None:
        self.hidden = False

    def hide(self) -> None:
        self.hidden = True

    def quit(self) -> None:
        pass


@pytest.fixture
def desktop(ctx: AppContext, tmp_path: Path, monkeypatch) -> app_main._Desktop:
    monkeypatch.setenv("TALEPORT_DATA_DIR", str(tmp_path))
    desktop = app_main._Desktop(ctx, "http://u/#t=x", dev=False)
    desktop.opened = []  # type: ignore[attr-defined]
    desktop.browser.focus = lambda: desktop.opened.append(True)  # type: ignore[method-assign]
    desktop.window = FakeWindow()  # type: ignore[assignment]
    desktop.focus = lambda: None
    return desktop


def test_window_that_never_loads_switches_to_chrome(desktop, ctx, monkeypatch) -> None:
    monkeypatch.setattr(app_main, "WINDOW_READY_TIMEOUT", 0.05)
    desktop.watch_window()
    for _ in range(50):
        if desktop.opened:
            break
        time.sleep(0.02)
    assert desktop.opened == [True]
    assert desktop.window.hidden
    assert ctx.settings.get().webview_failed  # next start goes straight to Chrome
    desktop.focus()  # tray "Open" / second launch now reopens Chrome
    assert desktop.opened == [True, True]


def test_window_that_loads_stays(desktop, ctx, monkeypatch) -> None:
    monkeypatch.setattr(app_main, "WINDOW_READY_TIMEOUT", 0.2)
    ctx.ui_ready.set()
    desktop.watch_window()
    time.sleep(0.3)
    assert desktop.opened == [] and not ctx.settings.get().webview_failed


def test_choosing_the_window_again_retries_the_built_in_one(ctx: AppContext) -> None:
    class NoScheduler:
        def reschedule(self, _time: str) -> None:
            pass

    app_main._wire_settings(ctx, NoScheduler(), [])  # type: ignore[arg-type]
    ctx.settings.update({"webview_failed": True})
    ctx.settings.update({"window_mode": "chrome"})
    assert ctx.settings.get().webview_failed is False


def test_quitting_closes_the_browser_window_it_opened(tmp_path: Path) -> None:
    class LiveProcess(FakeProcess):
        terminated = False

        def wait(self) -> int:
            while not self.terminated:
                time.sleep(0.01)
            return 0

        def poll(self):
            return 0 if self.terminated else None

        def terminate(self) -> None:
            self.terminated = True

    process = LiveProcess()
    shell = BrowserShell(
        "http://u", tmp_path, on_closed=lambda: None,
        finder=lambda: Path("chrome.exe"), launcher=lambda _c: process,
    )  # fmt: skip
    shell.focus()
    shell.close()
    assert process.terminated


def test_browser_lookup_works_on_this_system() -> None:
    """Runs the real lookup (registry and Program Files on Windows) without opening anything."""
    from taleport.browser_shell import find_browser

    found = find_browser()
    assert found is None or found.is_file()
