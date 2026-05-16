# ABOUTME: Email extractor — finds email addresses from mailto links and page text.
# ABOUTME: Returns a deduplicated list of ExtractedField with source attribution.
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from app.extraction.models import ExtractedField

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


def extract_emails(html: str, source_url: str) -> list[ExtractedField]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    results: list[ExtractedField] = []

    for tag in soup.find_all("a", href=True):
        if not isinstance(tag, Tag):
            continue
        href = str(tag.get("href", ""))
        if href.lower().startswith("mailto:"):
            raw = href[7:].split("?")[0].strip()
            normalized = raw.lower()
            if normalized and normalized not in seen and _EMAIL_RE.match(normalized):
                seen.add(normalized)
                results.append(
                    ExtractedField(
                        value=normalized,
                        source_url=source_url,
                        source_type="mailto_link",
                        raw_value=raw,
                    )
                )

    for script in soup(["script", "style"]):
        script.decompose()
    text = soup.get_text(" ")
    for match in _EMAIL_RE.finditer(text):
        raw = match.group()
        normalized = raw.lower()
        if normalized not in seen:
            seen.add(normalized)
            results.append(
                ExtractedField(
                    value=normalized,
                    source_url=source_url,
                    source_type="regex_text",
                    raw_value=raw,
                )
            )

    return results
