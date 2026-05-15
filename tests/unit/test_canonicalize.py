# ABOUTME: Unit tests for URL canonicalization — scheme/host normalization, port
# ABOUTME: stripping, fragment removal, path resolution, and query sorting.
from __future__ import annotations

from app.crawl.canonicalize import canonicalize


class TestSchemeAndHost:
    def test_lowercases_scheme(self) -> None:
        assert canonicalize("HTTP://example.com/") == "http://example.com/"

    def test_lowercases_host(self) -> None:
        assert canonicalize("https://Example.COM/page") == "https://example.com/page"

    def test_lowercases_both(self) -> None:
        assert canonicalize("HTTPS://WWW.Example.Com/path") == "https://www.example.com/path"


class TestDefaultPortStripping:
    def test_strips_http_port_80(self) -> None:
        assert canonicalize("http://example.com:80/page") == "http://example.com/page"

    def test_strips_https_port_443(self) -> None:
        assert canonicalize("https://example.com:443/page") == "https://example.com/page"

    def test_preserves_non_default_http_port(self) -> None:
        result = canonicalize("http://example.com:8080/page")
        assert "8080" in result

    def test_preserves_non_default_https_port(self) -> None:
        result = canonicalize("https://example.com:8443/page")
        assert "8443" in result

    def test_does_not_strip_443_for_http(self) -> None:
        result = canonicalize("http://example.com:443/page")
        assert "443" in result

    def test_does_not_strip_80_for_https(self) -> None:
        result = canonicalize("https://example.com:80/page")
        assert "80" in result


class TestFragmentRemoval:
    def test_strips_fragment(self) -> None:
        assert canonicalize("https://example.com/page#section") == "https://example.com/page"

    def test_strips_fragment_with_query(self) -> None:
        result = canonicalize("https://example.com/page?q=1#top")
        assert "#" not in result
        assert "q=1" in result

    def test_empty_fragment_stripped(self) -> None:
        assert canonicalize("https://example.com/page#") == "https://example.com/page"


class TestPathResolution:
    def test_resolves_dot_segment(self) -> None:
        assert canonicalize("https://example.com/about/./team") == "https://example.com/about/team"

    def test_resolves_dotdot_segment(self) -> None:
        assert canonicalize("https://example.com/about/../contact") == "https://example.com/contact"

    def test_empty_path_becomes_root(self) -> None:
        assert canonicalize("https://example.com") == "https://example.com/"

    def test_trailing_slash_stripped_by_normpath(self) -> None:
        # normpath strips trailing slashes — this is intentional for deduplication
        result = canonicalize("https://example.com/about/")
        assert result == "https://example.com/about"

    def test_root_slash_preserved(self) -> None:
        assert canonicalize("https://example.com/") == "https://example.com/"


class TestQueryNormalization:
    def test_sorts_query_params(self) -> None:
        result = canonicalize("https://example.com/?z=1&a=2")
        assert result == "https://example.com/?a=2&z=1"

    def test_deduplicates_query_params_last_wins(self) -> None:
        result = canonicalize("https://example.com/?key=first&key=last")
        assert "key=last" in result
        assert "key=first" not in result

    def test_empty_query_no_question_mark(self) -> None:
        result = canonicalize("https://example.com/page?")
        assert "?" not in result

    def test_no_query_no_question_mark(self) -> None:
        result = canonicalize("https://example.com/page")
        assert "?" not in result

    def test_blank_value_preserved(self) -> None:
        result = canonicalize("https://example.com/?key=")
        assert "key=" in result


class TestEdgeCases:
    def test_relative_url_returned_unchanged(self) -> None:
        url = "/relative/path"
        assert canonicalize(url) == url

    def test_url_without_scheme_returned_unchanged(self) -> None:
        url = "example.com/page"
        assert canonicalize(url) == url

    def test_combined_normalization(self) -> None:
        url = "HTTP://Example.COM:80/about/../contact?z=3&a=1#top"
        result = canonicalize(url)
        assert result == "http://example.com/contact?a=1&z=3"
