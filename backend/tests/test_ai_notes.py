"""Floating "AI notes" box: extra instructions reach every prompt of the request."""

from __future__ import annotations

import json
from urllib.parse import quote

from fastapi.testclient import TestClient

from taleport.ai import extra, prompts
from taleport.ai.structured import run_structured
from taleport.voices.schemas import VoiceAnalysis
from tests.test_ai import FakeProvider

NOTES = "Tono ironico, cita sempre la Curva Sud e chiudi con «Daje Roma!» 💛❤️"
LONG_TEXT = "La Roma ha vinto il derby con un gol di Dybala al novantesimo minuto. " * 12


def test_no_notes_leaves_prompts_unchanged() -> None:
    plain = prompts.render("voice_analysis", "it", documents="testo")
    assert "Indicazioni aggiuntive" not in plain.user


def test_notes_are_appended_to_every_prompt_in_the_ui_language() -> None:
    with extra.using(NOTES):
        it = prompts.render("voice_analysis", "it", documents="testo")
        en = prompts.render("post_generation", "en")
    assert it.user.endswith(f"<<<\n{NOTES}\n>>>")
    assert "Indicazioni aggiuntive dell'utente" in it.user
    assert "Additional instructions from the user" in en.user
    assert NOTES in prompts.as_single_text(it)  # "Open in chat" carries them too
    assert extra.current() == ""  # gone after the request


def test_notes_are_cleaned_and_capped() -> None:
    assert extra.clean("  ciao\x00\r\nmondo  ") == "ciao\nmondo"
    assert len(extra.clean("x" * 5000)) == extra.MAX_EXTRA_CHARS
    assert extra.from_header(quote(NOTES)) == NOTES
    assert extra.from_header(None) == extra.from_header("") == ""


def test_notes_stay_in_corrective_retries() -> None:
    fake = FakeProvider(["non json", json.dumps({"name": "X", "guide": "g" * 30})])
    with extra.using(NOTES):
        prompt = prompts.render("voice_analysis", "it", documents="testo")
    run_structured(fake, prompt, VoiceAnalysis, lambda _: None)
    assert len(fake.calls) == 2
    assert all(NOTES in user for _, user in fake.calls)


def test_header_reaches_the_prompt_through_the_api(client: TestClient) -> None:
    body = {"content": LONG_TEXT, "count": 1, "platforms": ["instagram"], "language": "it"}
    headers = {extra.HEADER: quote(NOTES)}

    with_notes = client.post("/api/generator/long", json={**body, "mode": "chat"}, headers=headers)
    without = client.post("/api/generator/long", json={**body, "mode": "chat"})

    assert with_notes.status_code == 200, with_notes.text
    assert NOTES in with_notes.json()["handoff"]["prompt"]
    assert NOTES not in without.json()["handoff"]["prompt"]
