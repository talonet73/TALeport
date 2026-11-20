"""The research article as a Word document (python-docx, already bundled for reading)."""

from __future__ import annotations

import io
from typing import Any

SOURCES_TITLE = {"it": "Fonti", "en": "Sources", "es": "Fuentes"}


def article_docx(article: dict[str, Any], sources: list[dict[str, Any]], lang: str) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading(article.get("title") or "", level=0)
    if article.get("subtitle"):
        doc.add_paragraph().add_run(article["subtitle"]).italic = True
    for block in (article.get("intro") or "").split("\n\n"):
        if block.strip():
            doc.add_paragraph(block.strip())
    for section in article.get("sections") or []:
        if section.get("heading"):
            doc.add_heading(section["heading"], level=1)
        for paragraph in section.get("paragraphs") or []:
            doc.add_paragraph(paragraph)
    for block in (article.get("conclusion") or "").split("\n\n"):
        if block.strip():
            doc.add_paragraph(block.strip())
    used = set(article.get("sources_used") or [])
    listed = [s for s in sources if not used or s.get("n") in used]
    if listed:
        doc.add_heading(SOURCES_TITLE.get(lang, "Sources"), level=2)
        for source in listed:
            text = source.get("title") or source.get("url") or ""
            if source.get("url") and source.get("url") != text:
                text += f" — {source['url']}"
            doc.add_paragraph(text, style="List Bullet")
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()
