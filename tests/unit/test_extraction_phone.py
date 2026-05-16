# ABOUTME: Unit tests for extract_phones() — tel links and regex text extraction.
# ABOUTME: Covers normalization to 10-digit strings and source_type attribution.
from __future__ import annotations

from app.extraction.phone import extract_phones

URL = "https://example.com/page"


class TestExtractPhones:
    def test_finds_tel_link(self) -> None:
        html = '<a href="tel:+16155550100">Call us</a>'
        results = extract_phones(html, URL)
        assert len(results) == 1

    def test_tel_link_source_type(self) -> None:
        html = '<a href="tel:+16155550100">Call us</a>'
        results = extract_phones(html, URL)
        assert results[0].source_type == "tel_link"

    def test_normalizes_to_10_digits(self) -> None:
        html = '<a href="tel:+16155550100">Call</a>'
        results = extract_phones(html, URL)
        assert results[0].value == "6155550100"

    def test_strips_country_code_1(self) -> None:
        html = '<a href="tel:16155550100">Call</a>'
        results = extract_phones(html, URL)
        assert results[0].value == "6155550100"

    def test_finds_phone_in_plain_text(self) -> None:
        html = "<p>Call us at (615) 555-0177 anytime.</p>"
        results = extract_phones(html, URL)
        assert any(r.value == "6155550177" for r in results)

    def test_regex_text_source_type(self) -> None:
        html = "<p>Phone: 615-555-0188</p>"
        results = extract_phones(html, URL)
        text_results = [r for r in results if r.source_type == "regex_text"]
        assert len(text_results) == 1

    def test_deduplicates_same_phone(self) -> None:
        html = '<a href="tel:6155550100">Call</a><p>(615) 555-0100</p>'
        results = extract_phones(html, URL)
        values = [r.value for r in results]
        assert values.count("6155550100") == 1

    def test_no_phones_returns_empty(self) -> None:
        html = "<p>No phone number here.</p>"
        results = extract_phones(html, URL)
        assert results == []

    def test_source_url_stored(self) -> None:
        html = '<a href="tel:6155550100">Call</a>'
        results = extract_phones(html, URL)
        assert results[0].source_url == URL

    def test_multiple_distinct_phones(self) -> None:
        html = (
            '<a href="tel:6155550201">(615) 555-0201</a><a href="tel:6155550202">(615) 555-0202</a>'
        )
        results = extract_phones(html, URL)
        values = {r.value for r in results}
        assert "6155550201" in values
        assert "6155550202" in values
