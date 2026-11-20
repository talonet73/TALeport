"""Evergreen sources for a research: Wikipedia articles and Reddit discussions.

Wikipedia: the public MediaWiki API (search, then the plain-text article). Reddit: the public
search RSS feed sorted by relevance over all time, so it returns experiences and advice
rather than the latest news. User names are never kept.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import feedparser

from taleport.collectors.base import CollectorError
from taleport.collectors.http import HttpClient
from taleport.collectors.text import excerpt, or_query

log = logging.getLogger(__name__)

WIKI_RESULTS_PER_TERM = 2
WIKI_MAX_ARTICLES = 6
WIKI_MAX_CHARS = 9000
REDDIT_MAX_POSTS = 12
_SUBMITTED_BY = re.compile(r"submitted by.*$", re.IGNORECASE | re.DOTALL)
_WIKI_LANGS = {"it", "en", "es", "fr", "de", "pt"}


@dataclass
class FoundText:
    kind: str
    title: str
    url: str
    content: str
    language: str | None = None


def wikipedia(http: HttpClient, terms: dict[str, list[str]]) -> list[FoundText]:
    found: list[FoundText] = []
    seen: set[str] = set()
    for lang, words in terms.items():
        if lang not in _WIKI_LANGS:
            continue
        api = f"https://{lang}.wikipedia.org/w/api.php"
        for term in words:
            if len(found) >= WIKI_MAX_ARTICLES:
                return found
            try:
                hits = http.get(api, params={
                    "action": "query", "list": "search", "srsearch": term, "format": "json",
                    "srlimit": WIKI_RESULTS_PER_TERM, "srprop": "",
                }).json().get("query", {}).get("search", [])  # fmt: skip
            except (CollectorError, ValueError):
                log.info("Wikipedia search failed for %r", term, exc_info=True)
                continue
            for hit in hits:
                title = hit.get("title", "")
                key = f"{lang}:{title}"
                if not title or key in seen or len(found) >= WIKI_MAX_ARTICLES:
                    continue
                seen.add(key)
                text = _wiki_text(http, api, title)
                if len(text) > 300:
                    url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    found.append(FoundText("wikipedia", title, url, text, lang))
    return found


def _wiki_text(http: HttpClient, api: str, title: str) -> str:
    try:
        pages = http.get(api, params={
            "action": "query", "prop": "extracts", "explaintext": 1, "titles": title,
            "format": "json", "redirects": 1,
        }).json().get("query", {}).get("pages", {})  # fmt: skip
    except (CollectorError, ValueError):
        return ""
    for page in pages.values():
        text = page.get("extract") or ""
        # Drop the reference sections at the end ("Note", "Bibliografia", "References", ...).
        text = re.split(r"\n==+ *(Note|Bibliografia|Voci correlate|Collegamenti esterni|"
                        r"References|See also|External links|Referencias|Véase también|"
                        r"Enlaces externos) *==+", text)[0]  # fmt: skip
        return text.strip()[:WIKI_MAX_CHARS]
    return ""


def _short_query(text: str) -> str:
    """'r/socialmedia - tips for social media strategists' -> 'tips for social media
    strategists': AI plans sometimes write subreddit names and long sentences."""
    text = re.sub(r"\br/\w+\s*[-:–]?\s*", "", text).strip(" -:–\"'")
    return " ".join(text.split()[:6])


def reddit(http: HttpClient, queries: list[str]) -> list[FoundText]:
    terms = [t for t in (_short_query(q) for q in queries[:4]) if t]
    if not terms:
        return []
    response = None
    # Relevance over all time finds experiences and advice; the "new" sort is the form the
    # trend scan uses and is the fallback when Reddit refuses the first one.
    for sort, period in (("relevance", "all"), ("new", "year")):
        try:
            response = http.get(
                "https://www.reddit.com/search.rss",
                params={"q": or_query(terms), "sort": sort, "t": period, "limit": REDDIT_MAX_POSTS},
            )
        except CollectorError:
            log.info("Reddit search unavailable", exc_info=True)
            return []
        log.info("Reddit search (%s) answered %s", sort, response.status_code)
        if response.status_code != 404:
            break
    if response is None or response.status_code >= 400:
        return []
    feed = feedparser.parse(response.content)
    found = []
    for entry in feed.entries[:REDDIT_MAX_POSTS]:
        summary = entry.get("summary") or ""
        body = _SUBMITTED_BY.sub("", re.sub(r"<[^>]+>", " ", summary))
        body = excerpt(re.sub(r"\s+", " ", body), 3000)
        title = entry.get("title") or ""
        if title:
            found.append(FoundText("reddit", title, entry.get("link") or "", body or title))
    return found
