""" "Edit with AI" on a draft, and Gemini-ready image prompts."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from taleport.ai import prompts
from taleport.api.context import AppContext, build_context
from taleport.core.errors import AppError
from taleport.db.database import Database
from tests.conftest import TEST_TOKEN
from tests.test_ai import FakeProvider, _analysed_topic
from tests.test_generator import LINKEDIN, _posts


@pytest.fixture
def fake() -> FakeProvider:
    return FakeProvider([])


@pytest.fixture
def gen_ctx(db: Database, fake: FakeProvider) -> AppContext:
    return build_context(
        db, TEST_TOKEN, collectors_factory=lambda: [], ai_provider_factory=lambda *a: fake
    )


def _draft(gen_ctx: AppContext, fake) -> dict:
    _analysed_topic(gen_ctx)
    theme = gen_ctx.analysis.today_overview()["topics"][0]["themes"][0]
    fake.answers.append(_posts(LINKEDIN))
    return gen_ctx.generator.generate_from_theme(theme["id"], ["linkedin"], ["it"], mode="openai")[
        "drafts"
    ][0]


def test_revise_rewrites_the_draft_in_place(gen_ctx: AppContext, fake) -> None:
    draft = _draft(gen_ctx, fake)
    fake.answers.append(_posts({
        **LINKEDIN, "hook": "", "text": "Versione corta. Voi cosa ne pensate?",
        "sources_used": [], "image_prompt": "Create an image: a short chart, 1:1",
    }))  # fmt: skip

    revised = gen_ctx.generator.revise(draft["id"], "più corto con una domanda", "openai")["draft"]

    assert revised["id"] == draft["id"] and revised["text"].startswith(
        "Versione corta. Voi cosa ne pensate?"
    )
    assert revised["sources"] == draft["sources"]  # kept when the answer lists none
    assert revised["image_prompt"].startswith("Create an image:")
    user = fake.calls[-1][1]
    assert "più corto con una domanda" in user and "Lo sapevi?" in user  # request + current post
    assert "[1]" in user  # the post's sources are passed for facts


def test_revise_uses_the_hand_edited_text(gen_ctx: AppContext, fake) -> None:
    draft = _draft(gen_ctx, fake)
    gen_ctx.generator.update_text(draft["id"], "Il mio testo scritto a mano.")
    fake.answers.append(_posts({**LINKEDIN, "text": "Testo rivisto."}))
    gen_ctx.generator.revise(draft["id"], "più ironico", "openai")
    assert "Il mio testo scritto a mano." in fake.calls[-1][1]


def test_revise_via_chat_and_errors(gen_ctx: AppContext, fake) -> None:
    draft = _draft(gen_ctx, fake)
    out = gen_ctx.generator.revise(draft["id"], "aggiungi emoji", "chat")
    assert "aggiungi emoji" in out["handoff"]["prompt"]

    pasted = _posts({**LINKEDIN, "text": "Con emoji 🎉"})
    assert (
        gen_ctx.generator.parse_revise(draft["id"], pasted)["draft"]["text"].count("Con emoji 🎉")
        == 1
    )

    with pytest.raises(AppError) as info:
        gen_ctx.generator.revise(draft["id"], "   ", "openai")
    assert info.value.code == "generator.revision_empty"
    with pytest.raises(AppError) as info:  # an answer for another platform
        gen_ctx.generator.parse_revise(draft["id"], _posts({**LINKEDIN, "platform": "tiktok"}))
    assert info.value.code == "generator.no_posts"


def test_revise_api(client: TestClient) -> None:
    missing = client.post("/api/drafts/999/revise", json={"request": "x", "mode": "chat"})
    assert missing.status_code == 404
    assert client.post("/api/drafts/1/revise", json={"request": ""}).status_code in (400, 422)


@pytest.mark.parametrize("language", ["it", "en", "es"])
def test_image_prompts_are_gemini_ready_in_every_template(language: str) -> None:
    for name in ("post_generation", "long_content", "reference_posts", "post_revision"):
        system = prompts.render(name, language).system
        assert "Gemini" in system and "Create an image:" in system and "4:5" in system, name
    revision = prompts.render(
        "post_revision", language, platform="instagram", post_language="it", post=json.dumps({})
    )
    assert "instagram" in revision.user
