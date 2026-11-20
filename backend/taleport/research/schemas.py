"""What the AI answers during a research: plan, source digest, dossier, article.

Small local models often rename keys or wrap lists: the validators accept the common
variants so a usable answer is not thrown away.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

SECTIONS = ("notions", "rules", "examples", "experiences", "mistakes", "quotes")
_SECTION_ALIASES = {
    "notions": ("notions", "nozioni", "concepts", "concetti", "nociones", "conceptos"),
    "rules": ("rules", "regole", "reglas", "principles", "principi"),
    "examples": ("examples", "esempi", "ejemplos", "case_studies", "casi"),
    "experiences": ("experiences", "esperienze", "experiencias", "stories"),
    "mistakes": ("mistakes", "errori", "errores", "pitfalls", "errors"),
    "quotes": ("quotes", "citazioni", "citas"),
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_text(v) for v in value)
    if isinstance(value, dict):
        return _text(value.get("text") or value.get("testo") or " ".join(map(str, value.values())))
    return str(value).strip()


def _list(value: Any) -> list:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [part.strip(" -•") for part in value.splitlines() if part.strip(" -•")]
    return [value]


def _numbers(value: Any) -> list[int]:
    out = []
    for v in _list(value):
        try:
            out.append(int(str(v).strip("[] ")))
        except ValueError:
            continue
    return out[:10]


class ResearchPlan(BaseModel):
    title: str = ""
    questions: list[str] = Field(default_factory=list)
    keywords: dict[str, list[str]] = Field(default_factory=dict)
    wikipedia: dict[str, list[str]] = Field(default_factory=dict)
    reddit_queries: list[str] = Field(default_factory=list)
    youtube_queries: list[str] = Field(default_factory=list)
    content_types: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("plan"), dict):
            data = data["plan"]
        if isinstance(data, dict):
            aliases = {"domande": "questions", "preguntas": "questions", "titolo": "title"}
            data = {aliases.get(k, k): v for k, v in data.items()}
        return data

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, value: Any) -> str:
        return _text(value)[:160]

    @field_validator(
        "questions", "reddit_queries", "youtube_queries", "content_types", mode="before"
    )
    @classmethod
    def _strings(cls, value: Any) -> list[str]:
        return [t for t in (_text(v)[:200] for v in _list(value)) if t][:12]

    @field_validator("keywords", "wikipedia", mode="before")
    @classmethod
    def _by_language(cls, value: Any) -> dict[str, list[str]]:
        if isinstance(value, list):  # no languages given: assume the first one later
            value = {"": value}
        if not isinstance(value, dict):
            return {}
        return {
            str(lang).lower()[:5]: [t for t in (_text(v)[:80] for v in _list(words)) if t][:10]
            for lang, words in value.items()
        }

    @model_validator(mode="after")
    def _needs_something(self) -> ResearchPlan:
        if not (self.questions or self.keywords or self.wikipedia or self.youtube_queries):
            raise ValueError("empty plan")
        return self


class Point(BaseModel):
    kind: str = "notion"
    text: str
    time: str = ""

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"text": data}
        return data

    @field_validator("text", "kind", "time", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> str:
        return _text(value)[:1200]


class SourceDigest(BaseModel):
    summary: str = ""
    points: list[Point] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"points": data}
        if isinstance(data, dict):
            aliases = {"riassunto": "summary", "resumen": "summary", "punti": "points",
                       "puntos": "points", "key_points": "points"}  # fmt: skip
            return {aliases.get(k, k): v for k, v in data.items()}
        return data

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, value: Any) -> str:
        return _text(value)[:2000]

    @field_validator("points", mode="before")
    @classmethod
    def _points(cls, value: Any) -> list:
        return _list(value)[:30]

    @model_validator(mode="after")
    def _not_empty(self) -> SourceDigest:
        if not (self.summary or self.points):
            raise ValueError("empty digest")
        return self


class DossierItem(BaseModel):
    text: str
    sources: list[int] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"text": data}
        if isinstance(data, dict):
            if "fonti" in data and "sources" not in data:
                data = {**data, "sources": data["fonti"]}
            if "text" not in data:
                data = {**data, "text": data.get("testo") or data.get("texto") or ""}
        return data

    @field_validator("text", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> str:
        return _text(value)[:1500]

    @field_validator("sources", mode="before")
    @classmethod
    def _source_numbers(cls, value: Any) -> list[int]:
        return _numbers(value)


class Dossier(BaseModel):
    title: str = ""
    summary: str = ""
    notions: list[DossierItem] = Field(default_factory=list)
    rules: list[DossierItem] = Field(default_factory=list)
    examples: list[DossierItem] = Field(default_factory=list)
    experiences: list[DossierItem] = Field(default_factory=list)
    mistakes: list[DossierItem] = Field(default_factory=list)
    quotes: list[DossierItem] = Field(default_factory=list)
    ai_knowledge: list[DossierItem] = Field(default_factory=list)  # no source: marked apart
    gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        if isinstance(data.get("dossier"), dict):
            data = data["dossier"]
        sections = data.get("sections") or data.get("sezioni")
        if isinstance(sections, dict):
            data = {**data, **sections}
        out: dict[str, Any] = dict(data)
        for section, names in _SECTION_ALIASES.items():
            for name in names:
                if name in data and section not in out:
                    out[section] = data[name]
        renamed = (
            ("riassunto", "summary"),
            ("titolo", "title"),
            ("conoscenza_generale", "ai_knowledge"),
            ("lacune", "gaps"),
        )
        for key, target in renamed:
            if key in data and target not in out:
                out[target] = data[key]
        return out

    @field_validator("title", "summary", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> str:
        return _text(value)[:3000]

    @field_validator(*SECTIONS, "ai_knowledge", mode="before")
    @classmethod
    def _items(cls, value: Any) -> list:
        return _list(value)[:25]

    @field_validator("gaps", mode="before")
    @classmethod
    def _gaps(cls, value: Any) -> list[str]:
        return [t for t in (_text(v)[:300] for v in _list(value)) if t][:10]

    @model_validator(mode="after")
    def _not_empty(self) -> Dossier:
        if not any(getattr(self, s) for s in SECTIONS):
            raise ValueError("empty dossier")
        return self


class WebSource(BaseModel):
    title: str = ""
    url: str = ""
    author: str = ""
    points: list[str] = Field(default_factory=list)

    @field_validator("title", "url", "author", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> str:
        return _text(value)[:500]

    @field_validator("points", mode="before")
    @classmethod
    def _points(cls, value: Any) -> list[str]:
        return [t for t in (_text(v)[:1200] for v in _list(value)) if t][:15]


class WebResearch(BaseModel):
    sources: list[WebSource]

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"sources": data}
        if isinstance(data, dict) and "sources" not in data:
            for key in ("fonti", "fuentes", "results", "risultati"):
                if key in data:
                    return {"sources": data[key]}
        return data

    @model_validator(mode="after")
    def _useful(self) -> WebResearch:
        self.sources = [s for s in self.sources if s.points and (s.url or s.title)][:15]
        if not self.sources:
            raise ValueError("no sources")
        return self


class ArticleSection(BaseModel):
    heading: str = ""
    paragraphs: list[str] = Field(default_factory=list)

    @field_validator("heading", mode="before")
    @classmethod
    def _heading(cls, value: Any) -> str:
        return _text(value)[:200]

    @field_validator("paragraphs", mode="before")
    @classmethod
    def _paragraphs(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            value = [p for p in value.split("\n\n")]
        return [t for t in (_text(v) for v in _list(value)) if t][:12]


class Article(BaseModel):
    title: str
    subtitle: str = ""
    intro: str = ""
    sections: list[ArticleSection]
    conclusion: str = ""
    sources_used: list[int] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _unwrap(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("article"), dict):
            return data["article"]
        return data

    @field_validator("title", "subtitle", "intro", "conclusion", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> str:
        return _text(value) if not isinstance(value, list) else "\n\n".join(map(_text, value))

    @field_validator("sources_used", mode="before")
    @classmethod
    def _source_numbers(cls, value: Any) -> list[int]:
        return _numbers(value)

    @model_validator(mode="after")
    def _not_empty(self) -> Article:
        self.sections = [s for s in self.sections if s.paragraphs]
        if not self.title or not self.sections:
            raise ValueError("empty article")
        return self
