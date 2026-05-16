# ABOUTME: Unit tests for app/dedup/normalize.py pure normalization functions.
# ABOUTME: Covers domain, name, phone, and email normalization edge cases.
from __future__ import annotations

from app.dedup.normalize import (
    normalize_domain,
    normalize_email,
    normalize_name,
    normalize_phone,
)


class TestNormalizeDomain:
    def test_https_www_trailing_slash(self) -> None:
        assert normalize_domain("https://www.example.com/") == "example.com"

    def test_http_no_trailing_slash(self) -> None:
        assert normalize_domain("http://example.com") == "example.com"

    def test_bare_www(self) -> None:
        assert normalize_domain("www.example.com") == "example.com"

    def test_bare_domain(self) -> None:
        assert normalize_domain("example.com") == "example.com"

    def test_subdomain_preserved(self) -> None:
        assert normalize_domain("subdomain.example.com") == "subdomain.example.com"

    def test_none(self) -> None:
        assert normalize_domain(None) == ""

    def test_empty_string(self) -> None:
        assert normalize_domain("") == ""


class TestNormalizeName:
    def test_apostrophe_comma_llc(self) -> None:
        assert normalize_name("Joe's Bakery, LLC") == "joes bakery llc"

    def test_leading_trailing_and_internal_whitespace(self) -> None:
        assert normalize_name("  Green Valley   Roofing  ") == "green valley roofing"

    def test_ampersand_stripped(self) -> None:
        assert normalize_name("A&B Services") == "ab services"

    def test_none(self) -> None:
        assert normalize_name(None) == ""

    def test_empty_string(self) -> None:
        assert normalize_name("") == ""


class TestNormalizePhone:
    def test_dashes(self) -> None:
        assert normalize_phone("615-555-0101") == "6155550101"

    def test_parens_and_space(self) -> None:
        assert normalize_phone("(615) 555-0101") == "6155550101"

    def test_country_code_with_dashes(self) -> None:
        assert normalize_phone("1-615-555-0101") == "6155550101"

    def test_eleven_digits_leading_one(self) -> None:
        assert normalize_phone("16155550101") == "6155550101"

    def test_too_few_digits(self) -> None:
        assert normalize_phone("555-0101") == ""

    def test_none(self) -> None:
        assert normalize_phone(None) == ""


class TestNormalizeEmail:
    def test_uppercase(self) -> None:
        assert normalize_email("HELLO@Example.COM") == "hello@example.com"

    def test_leading_trailing_spaces(self) -> None:
        assert normalize_email("  hello@example.com  ") == "hello@example.com"

    def test_none(self) -> None:
        assert normalize_email(None) == ""
