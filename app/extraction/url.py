# ABOUTME: Website URL extractor — finds canonical URL from og:url, canonical link, or base URL.
# ABOUTME: Returns the best-guess canonical URL as an ExtractedField, or None.
from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from app.extraction.models import ExtractedField


def extract_website_url(html: str, base_url: str, source_url: str) -> ExtractedField | None:
    soup = BeautifulSoup(html, "lxml")

    og_tag = soup.find("meta", property="og:url")
    if isinstance(og_tag, Tag):
        content = og_tag.get("content")
        if isinstance(content, str) and content.strip().startswith("http"):
            return ExtractedField(
                value=content.strip(),
                source_url=source_url,
                source_type="og_tag",
                raw_value=content,
            )

    canonical = soup.find("link", rel="canonical")
    if isinstance(canonical, Tag):
        href = canonical.get("href")
        if isinstance(href, str) and href.strip().startswith("http"):
            return ExtractedField(
                value=href.strip(),
                source_url=source_url,
                source_type="canonical_link",
                raw_value=href,
            )

    if base_url.startswith("http"):
        return ExtractedField(
            value=base_url,
            source_url=source_url,
            source_type="base_url",
            raw_value=base_url,
        )

    return None
