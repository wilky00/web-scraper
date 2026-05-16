# ABOUTME: Unit tests for run_extraction() — the top-level extraction orchestrator.
# ABOUTME: Verifies that all extractors are called and results are combined correctly.
from __future__ import annotations

from pathlib import Path

from app.extraction.models import ExtractionResult
from app.extraction.runner import run_extraction

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html" / "extraction"
SOURCE_URL = "https://example.com/page"
BASE_URL = "https://example.com/"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestRunExtraction:
    def test_returns_extraction_result_instance(self) -> None:
        result = run_extraction("<html><body></body></html>", SOURCE_URL, BASE_URL)
        assert isinstance(result, ExtractionResult)

    def test_empty_page_all_none_or_empty(self) -> None:
        result = run_extraction(
            "<html><body><p>Nothing here.</p></body></html>", SOURCE_URL, BASE_URL
        )
        assert result.name is None
        assert result.website is not None  # base_url fallback
        assert result.emails == []
        assert result.phones == []
        assert result.address is None

    def test_base_url_used_for_website_fallback(self) -> None:
        result = run_extraction("<html><body></body></html>", SOURCE_URL, BASE_URL)
        assert result.website is not None
        assert result.website.value == BASE_URL

    def test_source_url_passed_to_all_fields(self) -> None:
        html = """
        <head><title>Test Co</title></head>
        <body>
          <a href="mailto:t@example.com">Email</a>
          <a href="tel:6155550100">Call</a>
        </body>
        """
        result = run_extraction(html, SOURCE_URL, BASE_URL)
        if result.name:
            assert result.name.source_url == SOURCE_URL
        assert all(e.source_url == SOURCE_URL for e in result.emails)
        assert all(p.source_url == SOURCE_URL for p in result.phones)

    def test_full_contact_fixture(self) -> None:
        html = read_fixture("full_contact.html")
        result = run_extraction(html, SOURCE_URL, BASE_URL)
        assert result.name is not None
        assert len(result.emails) >= 1
        assert len(result.phones) >= 1
        assert result.address is not None

    def test_json_ld_fixture(self) -> None:
        html = read_fixture("json_ld_local_business.html")
        result = run_extraction(html, SOURCE_URL, BASE_URL)
        assert result.name is not None
        assert result.name.value == "Green Thumb Garden Center"
        assert result.address is not None

    def test_no_contact_fixture(self) -> None:
        html = read_fixture("no_contact.html")
        result = run_extraction(html, SOURCE_URL, BASE_URL)
        assert result.emails == []
        assert result.phones == []
        assert result.address is None

    def test_malformed_html_does_not_raise(self) -> None:
        html = read_fixture("malformed.html")
        result = run_extraction(html, SOURCE_URL, BASE_URL)
        assert isinstance(result, ExtractionResult)

    def test_multiple_contacts_fixture(self) -> None:
        html = read_fixture("multiple_contacts.html")
        result = run_extraction(html, SOURCE_URL, BASE_URL)
        assert len(result.emails) == 2
        assert len(result.phones) == 2
