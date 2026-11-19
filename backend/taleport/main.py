"""Entry point: local API, scheduler, tray icon and desktop window."""

from __future__ import annotations

import argparse
import logging
import secrets
import threading
from collections.abc import Callable

from taleport import __version__
from taleport.api.app import create_app
from taleport.api.context import AppContext, build_context
from taleport.autostart import set_autostart
from taleport.core.errors import AppError
from taleport.core.logging_setup import setup_logging
from taleport.core.maintenance import cleanup
from taleport.core.paths import bundle_root, db_path, instance_file
from taleport.core.settings import AppSettings
from taleport.db.database import Database
from taleport.scan.scheduler import ScanScheduler
from taleport.server import ApiServer
from taleport.single_instance import (
    SingleInstance,
    focus_running_instance,
    remove_instance_file,
    write_instance_file,
)

log = logging.getLogger("taleport")

DEV_API_PORT = 8765
DEV_UI_URL = "http://localhost:5173"
WINDOW_READY_TIMEOUT = 25  # seconds for the interface to load in the built-in window


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="taleport")
    parser.add_argument(
        "--dev", action="store_true", help="UI from the Vite dev server, fixed API port"
    )
    parser.add_argument(
        "--no-window", action="store_true", help="run the API only and print the UI URL"
    )
    parser.add_argument("--minimized", action="store_true", help="start hidden in the tray")
    parser.add_argument("--port", type=int, default=None, help="API port (default: random)")
    return parser.parse_args(argv)


def _wire_settings(ctx: AppContext, scheduler: ScanScheduler, on_language: list) -> None:
    def on_change(old: AppSettings, new: AppSettings) -> None:
        if old.scan_time != new.scan_time:
            scheduler.reschedule(new.scan_time)
        if old.start_with_windows != new.start_with_windows:
            set_autostart(new.start_with_windows)
        if old.language != new.language:
            for callback in on_language:
                callback()
        if old.window_mode != new.window_mode and new.webview_failed:
            ctx.settings.update({"webview_failed": False})  # the user chose again: retry

    ctx.settings.add_listener(on_change)


def _start_scan_from_shell(ctx: AppContext) -> None:
    try:
        ctx.scans.start("manual")
    except AppError as exc:
        log.info("Scan not started: %s", exc.code)


def _housekeeping(ctx: AppContext) -> None:
    """Startup chores off the main thread: old data clean-up, daily update check."""
    try:
        cleanup(ctx.db, ctx.settings.get().retention_months)
        ctx.updates.check_if_due()
    except Exception:
        log.exception("Startup housekeeping failed")


class _Desktop:
    """The visible part of the app: built-in window or browser window, tray icon, quitting."""

    def __init__(self, ctx: AppContext, ui_url: str, dev: bool) -> None:
        from taleport.browser_shell import BrowserShell
        from taleport.core.paths import browser_profile_dir

        self.ctx = ctx
        self.dev = dev
        self.stop = threading.Event()
        self.window = None
        self.browser = BrowserShell(ui_url, browser_profile_dir(), on_closed=self._browser_closed)
        self.focus: Callable[[], None] = self.browser.focus

    def _browser_closed(self) -> None:
        if not self.ctx.settings.get().close_to_tray:
            self.quit()

    def quit(self) -> None:
        self.stop.set()
        self.browser.close()
        if self.window is not None:
            self.window.quit()

    def switch_to_browser(self, reason: str) -> None:
        """The built-in window did not work: continue in Chrome, also at the next starts."""
        if self.focus == self.browser.focus:
            return
        log.warning("Built-in window unavailable (%s): opening TALeport in the browser", reason)
        try:
            self.ctx.settings.update({"webview_failed": True})
        except Exception:
            log.exception("Could not remember the browser fallback")
        if self.window is not None:
            try:
                self.window.hide()
            except Exception:
                log.debug("Could not hide the built-in window", exc_info=True)
        self.focus = self.browser.focus
        self.browser.focus()

    def watch_window(self) -> None:
        """If the interface has not loaded in the built-in window after a while, use Chrome."""

        def check() -> None:
            if not self.ctx.ui_ready.wait(WINDOW_READY_TIMEOUT) and not self.stop.is_set():
                self.switch_to_browser("no answer from the interface")

        threading.Thread(target=check, name="window-watchdog", daemon=True).start()

    def wait_in_tray(self) -> None:
        while not self.stop.wait(1):
            pass


def _run_desktop(ctx: AppContext, args: argparse.Namespace, ui_url: str, on_language: list):
    from taleport.tray import Tray

    desktop = _Desktop(ctx, ui_url, args.dev)
    settings = ctx.settings.get()
    use_browser = settings.window_mode == "chrome" or settings.webview_failed
    ctx.on_focus = lambda: desktop.focus()
    tray = Tray(
        bundle_root() / "assets" / "brand" / "taleport.ico",
        language=lambda: ctx.settings.get().language,
        on_open=lambda: desktop.focus(),
        on_scan=lambda: threading.Thread(
            target=_start_scan_from_shell, args=(ctx,), daemon=True
        ).start(),
        on_quit=desktop.quit,
    )
    on_language.append(tray.refresh)
    tray.start()
    ctx.notifications.toaster = tray.notify

    if not use_browser:
        try:
            from taleport.window import AppWindow

            window = AppWindow(
                ui_url,
                hidden=args.minimized,
                close_to_tray=lambda: ctx.settings.get().close_to_tray,
            )
            desktop.window = window
            desktop.focus = window.focus
            if args.minimized:
                first_focus = window.focus

                def focus_and_watch() -> None:
                    desktop.focus = first_focus
                    first_focus()
                    desktop.watch_window()

                desktop.focus = focus_and_watch
            else:
                desktop.watch_window()
            window.run(debug=args.dev)
            if not desktop.stop.is_set() and desktop.focus == desktop.browser.focus:
                desktop.wait_in_tray()  # the window was replaced by the browser
            return tray
        except Exception as exc:
            log.exception("The built-in window could not start")
            desktop.window = None
            desktop.switch_to_browser(type(exc).__name__)
            desktop.wait_in_tray()
            return tray

    log.info("Opening the interface in the browser (setting: %s)", settings.window_mode)
    if not args.minimized:
        desktop.browser.focus()
    desktop.wait_in_tray()
    return tray


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    setup_logging(logging.DEBUG if args.dev else logging.INFO)
    log.info("Starting TALeport %s", __version__)

    instance = SingleInstance()
    if not instance.acquire():
        log.info("Another instance is running; focusing it")
        focus_running_instance(instance_file())
        return 0

    db = Database(db_path())
    log.info("Database schema version %d", db.migrate())

    ctx = build_context(db, secrets.token_urlsafe(32))
    ctx.scans.mark_interrupted()
    ctx.videos.resume()
    settings = ctx.settings.get()

    scheduler = ScanScheduler(ctx.scans)
    scheduler.start(settings.scan_time)
    ctx.next_scan_at = scheduler.next_run_at
    on_language: list = []
    _wire_settings(ctx, scheduler, on_language)
    set_autostart(settings.start_with_windows)  # keep the registry in sync (e.g. after a move)
    scheduler.catch_up_if_needed(settings.scan_time)
    threading.Thread(target=_housekeeping, args=(ctx,), name="housekeeping", daemon=True).start()

    port = args.port if args.port is not None else (DEV_API_PORT if args.dev else 0)
    server = ApiServer(create_app(ctx), port=port)
    server.start()
    write_instance_file(instance_file(), server.port, ctx.token)
    log.info("API listening on %s", server.url)

    ui_url = f"{DEV_UI_URL if args.dev else server.url}/#t={ctx.token}"
    tray = None
    try:
        if args.no_window:
            print(f"TALeport UI: {ui_url}", flush=True)
            server.wait()
        else:
            tray = _run_desktop(ctx, args, ui_url, on_language)
    except KeyboardInterrupt:
        pass
    finally:
        if tray:
            tray.stop()
        ctx.scans.cancel()
        scheduler.shutdown()
        server.stop()
        remove_instance_file(instance_file())
        log.info("TALeport stopped")
    return 0
