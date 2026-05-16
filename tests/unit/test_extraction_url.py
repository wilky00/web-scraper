# ABOUTME: Unit tests for extract_website_url() with og:url, canonical link, and base_url fallback.
# ABOUTME: Verifies priority ordering and source_type attribution.
from __future__ import annotations

from app.extraction.url import extract_website_url

SOURCE_URL = "https://example.com/about"
BASE_URL = "https://example.com/"


class TestExtractWebsiteUrl:
    def test_og_url_priority(self) -> None:
        html = '<meta property="og:url" content="https://og.example.com/">'
        result = extract_website_url(html, BASE_URL, SOURCE_URL)
        assert result is not None
        assert result.value == "https://og.example.com/"
        assert result.source_type == "og_tag"

    def test_canonical_link_fallback(self) -> None:
        html = '<link rel="canonical" href="https://canonical.example.com/">'
        result = extract_website_url(html, BASE_URL, SOURCE_URL)
        assert result is not None
        assert result.value == "https://canonical.example.com/"
        assert result.source_type == "canonical_link"

    def test_og_takes_priority_over_canonical(self) -> None:
        html = """
        <meta property="og:url" content="https://og.example.com/">
        <link rel="canonical" href="https://canonical.example.com/">
        """
        result = extract_website_url(html, BASE_URL, SOURCE_URL)
        assert result is not None
        assert result.value == "https://og.example.com/"

    def test_base_url_fallback(self) -> None:
        html = "<p>No URL meta tags here.</p>"
        result = extract_website_url(html, BASE_URL, SOURCE_URL)
        assert result is not None
        assert result.value == BASE_URL
        assert result.source_type == "base_url"

    def test_relative_og_url_ignored(self) -> None:
        html = '<meta property="og:url" content="/relative-path">'
        result = extract_website_url(html, BASE_URL, SOURCE_URL)
        assert result is not None
        # relative og:url is ignored, falls back to base_url
        assert result.source_type != "og_tag"

    def test_source_url_stored(self) -> None:
        html = '<meta property="og:url" content="https://og.example.com/">'
        result = extract_website_url(html, BASE_URL, SOURCE_URL)
        assert result is not None
        assert result.source_url == SOURCE_URL

    def test_no_base_url_returns_none(self) -> None:
        html = "<p>No URL info.</p>"
        result = extract_website_url(html, "", SOURCE_URL)
        assert result is None

    def test_relative_canonical_ignored(self) -> None:
        html = '<link rel="canonical" href="/relative">'
        result = extract_website_url(html, BASE_URL, SOURCE_URL)
        assert result is not None
        assert result.source_type == "base_url"
