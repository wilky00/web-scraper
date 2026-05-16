# ABOUTME: Unit tests for extract_emails() — mailto links and regex text extraction.
# ABOUTME: Covers deduplication, source_type attribution, and edge cases.
from __future__ import annotations

from app.extraction.email import extract_emails

URL = "https://example.com/page"


class TestExtractEmails:
    def test_finds_mailto_link(self) -> None:
        html = '<a href="mailto:info@example.com">Contact</a>'
        results = extract_emails(html, URL)
        assert len(results) == 1
        assert results[0].value == "info@example.com"

    def test_mailto_source_type(self) -> None:
        html = '<a href="mailto:info@example.com">Contact</a>'
        results = extract_emails(html, URL)
        assert results[0].source_type == "mailto_link"

    def test_finds_email_in_plain_text(self) -> None:
        html = "<p>Email us at text@example.com for help.</p>"
        results = extract_emails(html, URL)
        assert any(r.value == "text@example.com" for r in results)

    def test_regex_text_source_type(self) -> None:
        html = "<p>Contact: text@example.com</p>"
        results = extract_emails(html, URL)
        text_results = [r for r in results if r.source_type == "regex_text"]
        assert len(text_results) == 1

    def test_deduplicates_same_email(self) -> None:
        html = '<a href="mailto:dup@example.com">link</a><p>dup@example.com</p>'
        results = extract_emails(html, URL)
        values = [r.value for r in results]
        assert values.count("dup@example.com") == 1

    def test_mailto_takes_priority_over_text(self) -> None:
        # When the same email appears as mailto link and in text, mailto comes first
        html = '<a href="mailto:same@example.com">link</a><p>same@example.com</p>'
        results = extract_emails(html, URL)
        assert results[0].source_type == "mailto_link"

    def test_no_emails_returns_empty(self) -> None:
        html = "<p>No contact info here.</p>"
        results = extract_emails(html, URL)
        assert results == []

    def test_lowercases_email_value(self) -> None:
        html = '<a href="mailto:Info@Example.COM">Contact</a>'
        results = extract_emails(html, URL)
        assert results[0].value == "info@example.com"

    def test_strips_mailto_query_params(self) -> None:
        html = '<a href="mailto:info@example.com?subject=Hello">Contact</a>'
        results = extract_emails(html, URL)
        assert results[0].value == "info@example.com"

    def test_source_url_stored(self) -> None:
        html = '<a href="mailto:x@example.com">x</a>'
        results = extract_emails(html, URL)
        assert results[0].source_url == URL

    def test_multiple_distinct_emails(self) -> None:
        html = '<a href="mailto:a@example.com">a</a><a href="mailto:b@example.com">b</a>'
        results = extract_emails(html, URL)
        values = {r.value for r in results}
        assert "a@example.com" in values
        assert "b@example.com" in values

    def test_ignores_email_in_script_tag(self) -> None:
        html = "<p>Hi</p><script>var e = 'noscript@example.com';</script>"
        results = extract_emails(html, URL)
        assert not any(r.value == "noscript@example.com" for r in results)
