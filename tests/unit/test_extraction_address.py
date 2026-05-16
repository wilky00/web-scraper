# ABOUTME: Unit tests for extract_address() with JSON-LD PostalAddress and itemprop fallback.
# ABOUTME: Verifies priority ordering and source_type attribution.
from __future__ import annotations

from app.extraction.address import extract_address

URL = "https://example.com/"


class TestExtractAddress:
    def test_json_ld_postal_address(self) -> None:
        html = """<script type="application/ld+json">
        {
          "@type": "LocalBusiness",
          "address": {
            "@type": "PostalAddress",
            "streetAddress": "123 Main St",
            "addressLocality": "Nashville",
            "addressRegion": "TN",
            "postalCode": "37201"
          }
        }</script>"""
        result = extract_address(html, URL)
        assert result is not None
        assert "123 Main St" in result.value
        assert "Nashville" in result.value
        assert result.source_type == "json_ld"

    def test_json_ld_address_string(self) -> None:
        html = """<script type="application/ld+json">
        {"@type": "Organization", "address": "456 Oak Lane, Memphis, TN"}</script>"""
        result = extract_address(html, URL)
        assert result is not None
        assert result.value == "456 Oak Lane, Memphis, TN"

    def test_json_ld_takes_priority_over_itemprop(self) -> None:
        html = """
        <script type="application/ld+json">
        {"@type": "Organization", "address": {"@type": "PostalAddress",
         "streetAddress": "LD Street", "addressLocality": "LD City",
         "addressRegion": "TN", "postalCode": "37000"}}</script>
        <span itemprop="streetAddress">Itemprop Street</span>
        """
        result = extract_address(html, URL)
        assert result is not None
        assert "LD Street" in result.value

    def test_itemprop_address_container(self) -> None:
        html = '<div itemprop="address">78 Ridge Road, Franklin, TN 37064</div>'
        result = extract_address(html, URL)
        assert result is not None
        assert result.source_type == "schema_org_itemprop"

    def test_itemprop_individual_parts(self) -> None:
        html = """
        <span itemprop="streetAddress">99 Elm St</span>
        <span itemprop="addressLocality">Murfreesboro</span>
        <span itemprop="addressRegion">TN</span>
        <span itemprop="postalCode">37130</span>
        """
        result = extract_address(html, URL)
        assert result is not None
        assert "99 Elm St" in result.value
        assert "Murfreesboro" in result.value

    def test_no_address_returns_none(self) -> None:
        html = "<p>No address information available.</p>"
        result = extract_address(html, URL)
        assert result is None

    def test_source_url_stored(self) -> None:
        html = '<span itemprop="streetAddress">1 Test Ave</span>'
        result = extract_address(html, URL)
        assert result is not None
        assert result.source_url == URL

    def test_json_ld_skips_missing_postal_parts(self) -> None:
        html = """<script type="application/ld+json">
        {"@type": "LocalBusiness", "address": {
          "@type": "PostalAddress",
          "addressLocality": "Nashville",
          "addressRegion": "TN"
        }}</script>"""
        result = extract_address(html, URL)
        assert result is not None
        assert "Nashville" in result.value
