# ABOUTME: Unit tests for extract_company_name() — JSON-LD, og:site_name, title, and h1 fallbacks.
# ABOUTME: Verifies priority ordering and source_type attribution.
from __future__ import annotations

from app.extraction.name import extract_company_name

URL = "https://example.com/"


class TestExtractCompanyName:
    def test_json_ld_organization_name(self) -> None:
        html = """<script type="application/ld+json">
        {"@type": "Organization", "name": "Acme Corp"}</script>"""
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "Acme Corp"
        assert result.source_type == "json_ld"

    def test_json_ld_local_business_name(self) -> None:
        html = """<script type="application/ld+json">
        {"@type": "LocalBusiness", "name": "Joe's Diner"}</script>"""
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "Joe's Diner"

    def test_json_ld_takes_priority_over_og(self) -> None:
        html = """
        <head>
          <meta property="og:site_name" content="OG Name">
          <script type="application/ld+json">
          {"@type": "Organization", "name": "LD Name"}</script>
        </head>"""
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "LD Name"

    def test_og_site_name(self) -> None:
        html = '<meta property="og:site_name" content="OG Company">'
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "OG Company"
        assert result.source_type == "og_tag"

    def test_og_takes_priority_over_title(self) -> None:
        html = """
        <head>
          <meta property="og:site_name" content="OG Name">
          <title>Title Name</title>
        </head>"""
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "OG Name"

    def test_title_tag(self) -> None:
        html = "<title>Simple Company</title>"
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "Simple Company"
        assert result.source_type == "html_title"

    def test_title_with_pipe_separator(self) -> None:
        html = "<title>Page Title | Company Name</title>"
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "Page Title"

    def test_title_with_dash_separator(self) -> None:
        html = "<title>Home - My Business</title>"
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "Home"

    def test_h1_fallback(self) -> None:
        html = "<body><h1>Heading Company</h1></body>"
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "Heading Company"
        assert result.source_type == "h1_heading"

    def test_no_name_returns_none(self) -> None:
        html = "<body><p>No name anywhere.</p></body>"
        result = extract_company_name(html, URL)
        assert result is None

    def test_json_ld_graph_array(self) -> None:
        html = """<script type="application/ld+json">
        {"@graph": [{"@type": "Organization", "name": "Graph Corp"}]}</script>"""
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.value == "Graph Corp"

    def test_source_url_stored(self) -> None:
        html = "<title>Test Co</title>"
        result = extract_company_name(html, URL)
        assert result is not None
        assert result.source_url == URL
