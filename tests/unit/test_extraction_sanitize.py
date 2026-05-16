# ABOUTME: Unit tests for sanitize_html() bleach-based HTML sanitization.
# ABOUTME: Verifies that unsafe tags/attrs are stripped and safe content is preserved.
from __future__ import annotations

from app.extraction.sanitize import sanitize_html


class TestSanitizeHtml:
    def test_strips_script_tags(self) -> None:
        result = sanitize_html('<p>Hello</p><script>alert("xss")</script>')
        assert "<script>" not in result
        assert "alert" not in result

    def test_strips_style_tags(self) -> None:
        result = sanitize_html("<p>Hi</p><style>body { color: red; }</style>")
        assert "<style>" not in result

    def test_strips_onclick_attr(self) -> None:
        result = sanitize_html('<p onclick="evil()">Click me</p>')
        assert "onclick" not in result
        assert "Click me" in result

    def test_keeps_allowed_paragraph_tag(self) -> None:
        result = sanitize_html("<p>Hello world</p>")
        assert "<p>" in result
        assert "Hello world" in result

    def test_keeps_anchor_href(self) -> None:
        result = sanitize_html('<a href="https://example.com">Link</a>')
        assert 'href="https://example.com"' in result

    def test_strips_javascript_href(self) -> None:
        result = sanitize_html('<a href="javascript:void(0)">Bad</a>')
        assert "javascript:" not in result

    def test_plain_text_preserved(self) -> None:
        result = sanitize_html("<p>Simple text with no HTML concerns.</p>")
        assert "Simple text with no HTML concerns." in result

    def test_strips_html_comments(self) -> None:
        result = sanitize_html("<p>Hi</p><!-- hidden comment -->")
        assert "hidden comment" not in result

    def test_strips_iframe(self) -> None:
        result = sanitize_html('<iframe src="https://evil.com"></iframe>')
        assert "<iframe" not in result

    def test_empty_string_returns_empty(self) -> None:
        assert sanitize_html("") == ""
