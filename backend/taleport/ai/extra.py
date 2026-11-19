"""Extra instructions from the floating "AI notes" box.

The box lives in the interface: when it is switched on, every API request carries its text in
the `X-TALeport-Extra` header (URL-encoded, so any language fits in an HTTP header). The
request middleware stores it here for the duration of the request and `prompts.render` adds it
to every prompt, so it reaches whichever AI is selected, including "Open in chat".
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import unquote

HEADER = "X-TALeport-Extra"
MAX_EXTRA_CHARS = 1500
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_current: ContextVar[str] = ContextVar("taleport_ai_extra", default="")


def clean(text: str) -> str:
    text = _CONTROL.sub("", text.replace("\r\n", "\n")).strip()
    return text[:MAX_EXTRA_CHARS].strip()


def from_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return clean(unquote(value, errors="replace"))
    except (TypeError, ValueError):
        return ""


def current() -> str:
    return _current.get()


def set_current(text: str) -> object:
    """Set for the running request; returns the token for `reset`."""
    return _current.set(clean(text))


def reset(token: object) -> None:
    _current.reset(token)  # type: ignore[arg-type]


@contextmanager
def using(text: str) -> Iterator[None]:
    token = _current.set(clean(text))
    try:
        yield
    finally:
        _current.reset(token)
