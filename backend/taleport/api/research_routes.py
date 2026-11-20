"""Research from a goal: plan, sources (texts, videos, documents, web), dossier, article."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from taleport.api.context import AppContext

router = APIRouter()


def _ctx(request: Request) -> AppContext:
    return request.app.state.ctx


class NewResearch(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    languages: list[str] = Field(default_factory=lambda: ["it"], max_length=3)


class ResearchChanges(BaseModel):
    goal: str | None = Field(None, max_length=4000)
    title: str | None = Field(None, max_length=160)
    languages: list[str] | None = Field(None, max_length=3)
    plan: dict[str, Any] | None = None
    dossier: dict[str, Any] | None = None


class Mode(BaseModel):
    mode: str | None = None


class Pasted(BaseModel):
    text: str = Field(min_length=1, max_length=400_000)


class VideoLinks(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)


class Document(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    data_base64: str = Field(min_length=1)


class PastedText(BaseModel):
    title: str = Field("", max_length=300)
    text: str = Field(min_length=1, max_length=200_000)


class DossierRequest(BaseModel):
    mode: str | None = None
    ai_knowledge: bool = False


class ArticleRequest(BaseModel):
    language: Literal["it", "en", "es"] = "it"
    length: Literal["short", "medium", "long"] = "medium"
    tone: str = Field("", max_length=1500)
    mode: str | None = None


class ArticlePasted(BaseModel):
    text: str = Field(min_length=1, max_length=400_000)
    language: Literal["it", "en", "es"] = "it"


@router.get("/research")
def list_research(request: Request) -> list[dict[str, Any]]:
    return _ctx(request).research.list_projects()


@router.post("/research")
def create_research(request: Request, body: NewResearch) -> dict[str, Any]:
    return _ctx(request).research.create(body.goal, body.languages)


@router.get("/research/{project_id}")
def get_research(request: Request, project_id: int) -> dict[str, Any]:
    return _ctx(request).research.get(project_id)


@router.patch("/research/{project_id}")
def update_research(request: Request, project_id: int, body: ResearchChanges) -> dict[str, Any]:
    return _ctx(request).research.update(project_id, body.model_dump(exclude_unset=True))


@router.delete("/research/{project_id}", status_code=204)
def delete_research(request: Request, project_id: int) -> None:
    _ctx(request).research.delete(project_id)


@router.post("/research/{project_id}/plan")
def plan(request: Request, project_id: int, body: Mode) -> dict[str, Any]:
    return _ctx(request).research.plan(project_id, body.mode)


@router.post("/research/{project_id}/plan/parse")
def plan_parse(request: Request, project_id: int, body: Pasted) -> dict[str, Any]:
    return _ctx(request).research.parse_plan(project_id, body.text)


@router.post("/research/{project_id}/collect")
def collect(request: Request, project_id: int) -> dict[str, Any]:
    return _ctx(request).research.collect(project_id)


@router.post("/research/{project_id}/videos")
def add_videos(request: Request, project_id: int, body: VideoLinks) -> dict[str, Any]:
    return _ctx(request).research.add_videos(project_id, body.urls)


@router.post("/research/{project_id}/documents")
def add_document(request: Request, project_id: int, body: Document) -> dict[str, Any]:
    return _ctx(request).research.add_document(project_id, body.filename, body.data_base64)


@router.post("/research/{project_id}/texts")
def add_text(request: Request, project_id: int, body: PastedText) -> dict[str, Any]:
    return _ctx(request).research.add_text(project_id, body.title, body.text)


@router.post("/research/{project_id}/web")
def web(request: Request, project_id: int) -> dict[str, Any]:
    return _ctx(request).research.web_prompt(project_id)


@router.post("/research/{project_id}/web/parse")
def web_parse(request: Request, project_id: int, body: Pasted) -> dict[str, Any]:
    return _ctx(request).research.parse_web(project_id, body.text)


@router.get("/research/sources/{source_id}")
def get_source(request: Request, source_id: int) -> dict[str, Any]:
    return _ctx(request).research.source(source_id)


@router.delete("/research/sources/{source_id}")
def delete_source(request: Request, source_id: int) -> dict[str, Any]:
    return _ctx(request).research.delete_source(source_id)


@router.post("/research/sources/{source_id}/transcribe")
def transcribe_source(request: Request, source_id: int) -> dict[str, Any]:
    return _ctx(request).research.transcribe_suggestion(source_id)


@router.post("/research/sources/{source_id}/retry")
def retry_source(request: Request, source_id: int) -> dict[str, Any]:
    return _ctx(request).research.retry_source(source_id)


@router.post("/research/{project_id}/dossier")
def dossier(request: Request, project_id: int, body: DossierRequest) -> dict[str, Any]:
    return _ctx(request).research.build_dossier(project_id, body.mode, body.ai_knowledge)


@router.post("/research/{project_id}/dossier/parse")
def dossier_parse(request: Request, project_id: int, body: Pasted) -> dict[str, Any]:
    return _ctx(request).research.parse_dossier(project_id, body.text)


@router.get("/research/{project_id}/dossier/text")
def dossier_text(request: Request, project_id: int) -> dict[str, Any]:
    return _ctx(request).research.dossier_text(project_id)


@router.post("/research/{project_id}/article")
def article(request: Request, project_id: int, body: ArticleRequest) -> dict[str, Any]:
    return _ctx(request).research.write_article(
        project_id, body.language, body.length, body.tone, body.mode
    )


@router.post("/research/{project_id}/article/parse")
def article_parse(request: Request, project_id: int, body: ArticlePasted) -> dict[str, Any]:
    return _ctx(request).research.parse_article(project_id, body.text, body.language)


@router.post("/research/{project_id}/article/docx")
def article_docx(request: Request, project_id: int) -> dict[str, Any]:
    return _ctx(request).research.article_docx(project_id)
