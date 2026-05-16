# ABOUTME: Company name extractor — tries JSON-LD, Open Graph, title tag, then h1.
# ABOUTME: Returns the first confident match as an ExtractedField, or None.
from __future__ import annotations

from bs4 import BeautifulSoup, Tag

from app.extraction._json_ld import parse_json_ld_blocks
from app.extraction.models import ExtractedField

_ORG_TYPES: frozenset[str] = frozenset(
    {
        "Organization",
        "LocalBusiness",
        "Restaurant",
        "FoodEstablishment",
        "Store",
        "Hotel",
        "MedicalBusiness",
        "HealthAndBeautyBusiness",
        "ProfessionalService",
        "HomeAndConstructionBusiness",
        "LodgingBusiness",
        "AutomotiveBusiness",
    }
)

_TITLE_SEPARATORS = (" | ", " - ", " – ", " — ", " · ")


def _org_name_from_ld(blocks: list[dict[str, object]]) -> str | None:
    for block in blocks:
        block_type = block.get("@type", "")
        if isinstance(block_type, str):
            types: set[str] = {block_type}
        elif isinstance(block_type, list):
            types = {t for t in block_type if isinstance(t, str)}
        else:
            types = set()
        if types & _ORG_TYPES:
            name = block.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def extract_company_name(html: str, source_url: str) -> ExtractedField | None:
    soup = BeautifulSoup(html, "lxml")

    ld_name = _org_name_from_ld(parse_json_ld_blocks(soup))
    if ld_name:
        return ExtractedField(
            value=ld_name,
            source_url=source_url,
            source_type="json_ld",
            raw_value=ld_name,
        )

    og_tag = soup.find("meta", property="og:site_name")
    if isinstance(og_tag, Tag):
        content = og_tag.get("content")
        if isinstance(content, str) and content.strip():
            return ExtractedField(
                value=content.strip(),
                source_url=source_url,
                source_type="og_tag",
                raw_value=content,
            )

    title_tag = soup.find("title")
    if isinstance(title_tag, Tag):
        raw_title = title_tag.get_text(strip=True)
        text = raw_title
        for sep in _TITLE_SEPARATORS:
            if sep in text:
                text = text.split(sep)[0].strip()
                break
        if text:
            return ExtractedField(
                value=text,
                source_url=source_url,
                source_type="html_title",
                raw_value=raw_title,
            )

    h1_tag = soup.find("h1")
    if isinstance(h1_tag, Tag):
        text = h1_tag.get_text(strip=True)
        if text:
            return ExtractedField(
                value=text,
                source_url=source_url,
                source_type="h1_heading",
                raw_value=text,
            )

    return None
