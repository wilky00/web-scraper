# ABOUTME: Phone number extractor — finds numbers from tel links and page text.
# ABOUTME: Returns a deduplicated list of ExtractedField normalized to 10 digits.
from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag

from app.extraction.models import ExtractedField

_PHONE_RE = re.compile(
    r"(?:\+?1[\s.\-]?)?(?:\(\d{3}\)|\d{3})[\s.\-]?\d{3}[\s.\-]?\d{4}"
    r"(?:\s*(?:ext|x|ext\.)\s*\d{1,5})?"
)


def _normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    return digits


def extract_phones(html: str, source_url: str) -> list[ExtractedField]:
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    results: list[ExtractedField] = []

    for tag in soup.find_all("a", href=True):
        if not isinstance(tag, Tag):
            continue
        href = str(tag.get("href", ""))
        if href.lower().startswith("tel:"):
            raw = href[4:].strip()
            normalized = _normalize_phone(raw)
            if len(normalized) == 10 and normalized not in seen:
                seen.add(normalized)
                results.append(
                    ExtractedField(
                        value=normalized,
                        source_url=source_url,
                        source_type="tel_link",
                        raw_value=raw,
                    )
                )

    for script in soup(["script", "style"]):
        script.decompose()
    text = soup.get_text(" ")
    for match in _PHONE_RE.finditer(text):
        raw = match.group().strip()
        normalized = _normalize_phone(raw)
        if len(normalized) == 10 and normalized not in seen:
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
