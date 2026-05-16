# ABOUTME: Address extractor — finds business address from JSON-LD or itemprop microdata.
# ABOUTME: Returns the first confident address as an ExtractedField, or None.
from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from app.extraction._json_ld import parse_json_ld_blocks
from app.extraction.models import ExtractedField

_ITEMPROP_PARTS = ("streetAddress", "addressLocality", "addressRegion", "postalCode")


def _address_from_ld(blocks: list[dict[str, object]]) -> str | None:
    for block in blocks:
        addr = block.get("address")
        if isinstance(addr, dict):
            if addr.get("@type") == "PostalAddress":
                parts = [
                    str(addr.get("streetAddress", "")),
                    str(addr.get("addressLocality", "")),
                    str(addr.get("addressRegion", "")),
                    str(addr.get("postalCode", "")),
                ]
                formatted = ", ".join(p for p in parts if p)
                if formatted:
                    return formatted
        elif isinstance(addr, str) and addr.strip():
            return addr.strip()
    return None


def _address_from_itemprop(soup: BeautifulSoup) -> str | None:
    addr_tag = soup.find(itemprop="address")
    if isinstance(addr_tag, Tag):
        text = addr_tag.get_text(separator=" ", strip=True)
        if text:
            return text

    parts: list[str] = []
    for prop in _ITEMPROP_PARTS:
        tag = soup.find(itemprop=prop)
        if isinstance(tag, Tag):
            text = tag.get_text(strip=True)
            if text:
                parts.append(text)
    return ", ".join(parts) if parts else None


def extract_address(html: str, source_url: str) -> ExtractedField | None:
    soup = BeautifulSoup(html, "lxml")

    ld_addr = _address_from_ld(parse_json_ld_blocks(soup))
    if ld_addr:
        return ExtractedField(
            value=ld_addr,
            source_url=source_url,
            source_type="json_ld",
            raw_value=ld_addr,
        )

    itemprop_addr = _address_from_itemprop(soup)
    if itemprop_addr:
        return ExtractedField(
            value=itemprop_addr,
            source_url=source_url,
            source_type="schema_org_itemprop",
            raw_value=itemprop_addr,
        )

    return None
