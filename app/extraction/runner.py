# ABOUTME: ExtractionRunner — calls all field extractors on a page and returns unified result.
# ABOUTME: Pure function; takes HTML string + metadata, performs no I/O.
from __future__ import annotations

from app.extraction.address import extract_address
from app.extraction.email import extract_emails
from app.extraction.models import ExtractionResult
from app.extraction.name import extract_company_name
from app.extraction.phone import extract_phones
from app.extraction.url import extract_website_url


def run_extraction(html: str, source_url: str, base_url: str) -> ExtractionResult:
    return ExtractionResult(
        name=extract_company_name(html, source_url),
        website=extract_website_url(html, base_url, source_url),
        emails=extract_emails(html, source_url),
        phones=extract_phones(html, source_url),
        address=extract_address(html, source_url),
    )
