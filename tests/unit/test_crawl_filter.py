# ABOUTME: Unit tests for crawl URL path filtering and binary content-type detection.
from __future__ import annotations

from app.crawl.filter import is_content_type_blocked, is_path_blocked


class TestIsPathBlocked:
    def test_exact_match_blocked(self) -> None:
        assert is_path_blocked("https://example.com/login", ["/login"]) is True

    def test_prefix_match_with_slash_blocked(self) -> None:
        assert is_path_blocked("https://example.com/admin/users", ["/admin"]) is True

    def test_prefix_deep_path_blocked(self) -> None:
        assert is_path_blocked("https://example.com/wp-admin/edit.php", ["/wp-admin"]) is True

    def test_path_not_blocked_by_similar_prefix(self) -> None:
        # /admin should not block /administrator
        assert is_path_blocked("https://example.com/administrator", ["/admin"]) is False

    def test_unrelated_path_not_blocked(self) -> None:
        assert is_path_blocked("https://example.com/about", ["/login", "/admin"]) is False

    def test_empty_patterns_allows_all(self) -> None:
        assert is_path_blocked("https://example.com/login", []) is False

    def test_multiple_patterns_first_match(self) -> None:
        assert (
            is_path_blocked("https://example.com/checkout", ["/login", "/checkout", "/admin"])
            is True
        )

    def test_glob_pattern_wildcard(self) -> None:
        assert is_path_blocked("https://example.com/wp-admin/post.php", ["/wp-admin/*"]) is True

    def test_glob_pattern_no_match(self) -> None:
        assert is_path_blocked("https://example.com/about", ["/wp-admin/*"]) is False

    def test_trailing_slash_on_pattern_still_matches(self) -> None:
        # /admin/ pattern treated as prefix /admin → matches /admin/page
        assert is_path_blocked("https://example.com/admin/page", ["/admin/"]) is True

    def test_root_path_not_blocked_by_non_root_pattern(self) -> None:
        assert is_path_blocked("https://example.com/", ["/login"]) is False

    def test_query_string_ignored_path_still_matches(self) -> None:
        assert is_path_blocked("https://example.com/login?next=/dashboard", ["/login"]) is True


class TestIsContentTypeBlocked:
    def test_exact_blocked_type(self) -> None:
        assert is_content_type_blocked("application/pdf", ["application/pdf"]) is True

    def test_prefix_blocked_image(self) -> None:
        assert is_content_type_blocked("image/png", ["image/"]) is True

    def test_prefix_blocked_image_jpeg(self) -> None:
        assert is_content_type_blocked("image/jpeg", ["image/"]) is True

    def test_prefix_blocked_audio(self) -> None:
        assert is_content_type_blocked("audio/mpeg", ["audio/"]) is True

    def test_prefix_blocked_video(self) -> None:
        assert is_content_type_blocked("video/mp4", ["video/"]) is True

    def test_allowed_html(self) -> None:
        assert is_content_type_blocked("text/html", ["image/", "application/pdf"]) is False

    def test_allowed_json(self) -> None:
        assert is_content_type_blocked("application/json", ["application/pdf", "image/"]) is False

    def test_parameters_stripped(self) -> None:
        assert is_content_type_blocked("image/png; charset=utf-8", ["image/"]) is True

    def test_case_insensitive(self) -> None:
        assert is_content_type_blocked("IMAGE/PNG", ["image/"]) is True

    def test_empty_prefixes_allows_all(self) -> None:
        assert is_content_type_blocked("application/pdf", []) is False

    def test_zip_blocked(self) -> None:
        assert is_content_type_blocked("application/zip", ["application/zip"]) is True

    def test_octet_stream_blocked(self) -> None:
        assert (
            is_content_type_blocked("application/octet-stream", ["application/octet-stream"])
            is True
        )
