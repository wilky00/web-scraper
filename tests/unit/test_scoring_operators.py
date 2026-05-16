# ABOUTME: Unit tests for evaluate_operator — covers all 12 Operator values.
# ABOUTME: Each operator gets at least one pass and one fail case, plus edge cases.
from __future__ import annotations

import pytest

from app.config.criteria import Operator
from app.scoring.operators import evaluate_operator

# ── exists ────────────────────────────────────────────────────────────────────


def test_exists_none_returns_false() -> None:
    assert evaluate_operator(Operator.exists, None, None) is False


def test_exists_non_empty_string_returns_true() -> None:
    assert evaluate_operator(Operator.exists, "hello", None) is True


def test_exists_empty_string_returns_false() -> None:
    assert evaluate_operator(Operator.exists, "", None) is False


def test_exists_whitespace_only_returns_false() -> None:
    assert evaluate_operator(Operator.exists, "   ", None) is False


def test_exists_zero_returns_true() -> None:
    # 0 is not None and "0".strip() != ""
    assert evaluate_operator(Operator.exists, 0, None) is True


# ── not_exists ────────────────────────────────────────────────────────────────


def test_not_exists_none_returns_true() -> None:
    assert evaluate_operator(Operator.not_exists, None, None) is True


def test_not_exists_non_empty_returns_false() -> None:
    assert evaluate_operator(Operator.not_exists, "x", None) is False


def test_not_exists_empty_string_returns_true() -> None:
    assert evaluate_operator(Operator.not_exists, "", None) is True


# ── equals ────────────────────────────────────────────────────────────────────


def test_equals_case_insensitive_match() -> None:
    assert evaluate_operator(Operator.equals, "Hello", "hello") is True


def test_equals_different_values_returns_false() -> None:
    assert evaluate_operator(Operator.equals, "hello", "world") is False


def test_equals_numeric_match() -> None:
    assert evaluate_operator(Operator.equals, 200, "200") is True


def test_equals_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.equals, None, "hello") is False


# ── not_equals ────────────────────────────────────────────────────────────────


def test_not_equals_different_values_returns_true() -> None:
    assert evaluate_operator(Operator.not_equals, "hello", "world") is True


def test_not_equals_same_value_returns_false() -> None:
    assert evaluate_operator(Operator.not_equals, "hello", "hello") is False


def test_not_equals_case_insensitive() -> None:
    assert evaluate_operator(Operator.not_equals, "Hello", "hello") is False


def test_not_equals_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.not_equals, None, "hello") is False


# ── contains ─────────────────────────────────────────────────────────────────


def test_contains_substring_present_returns_true() -> None:
    assert evaluate_operator(Operator.contains, "hello world", "world") is True


def test_contains_substring_absent_returns_false() -> None:
    assert evaluate_operator(Operator.contains, "hello world", "foo") is False


def test_contains_case_insensitive() -> None:
    assert evaluate_operator(Operator.contains, "Hello World", "hello") is True


def test_contains_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.contains, None, "hello") is False


# ── contains_any ─────────────────────────────────────────────────────────────


def test_contains_any_first_item_matches() -> None:
    assert evaluate_operator(Operator.contains_any, "hello world", ["world", "foo"]) is True


def test_contains_any_second_item_matches() -> None:
    assert evaluate_operator(Operator.contains_any, "hello world", ["foo", "world"]) is True


def test_contains_any_no_match_returns_false() -> None:
    assert evaluate_operator(Operator.contains_any, "hello world", ["abc", "xyz"]) is False


def test_contains_any_case_insensitive() -> None:
    assert evaluate_operator(Operator.contains_any, "Hello World", ["WORLD"]) is True


def test_contains_any_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.contains_any, None, ["foo"]) is False


# ── greater_than_or_equal ─────────────────────────────────────────────────────


def test_gte_greater_value_returns_true() -> None:
    assert evaluate_operator(Operator.greater_than_or_equal, 5.0, 3.0) is True


def test_gte_equal_value_returns_true() -> None:
    assert evaluate_operator(Operator.greater_than_or_equal, 3.0, 3.0) is True


def test_gte_lesser_value_returns_false() -> None:
    assert evaluate_operator(Operator.greater_than_or_equal, 2.0, 3.0) is False


def test_gte_non_numeric_returns_false() -> None:
    assert evaluate_operator(Operator.greater_than_or_equal, "abc", 3.0) is False


def test_gte_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.greater_than_or_equal, None, 3.0) is False


def test_gte_string_numeric_coercion() -> None:
    assert evaluate_operator(Operator.greater_than_or_equal, "5", 3.0) is True


# ── less_than_or_equal ────────────────────────────────────────────────────────


def test_lte_lesser_value_returns_true() -> None:
    assert evaluate_operator(Operator.less_than_or_equal, 2.0, 3.0) is True


def test_lte_equal_value_returns_true() -> None:
    assert evaluate_operator(Operator.less_than_or_equal, 3.0, 3.0) is True


def test_lte_greater_value_returns_false() -> None:
    assert evaluate_operator(Operator.less_than_or_equal, 5.0, 3.0) is False


def test_lte_non_numeric_returns_false() -> None:
    assert evaluate_operator(Operator.less_than_or_equal, "abc", 3.0) is False


def test_lte_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.less_than_or_equal, None, 3.0) is False


# ── in ────────────────────────────────────────────────────────────────────────


def test_in_value_present_returns_true() -> None:
    assert evaluate_operator(Operator.in_, "hello", ["hello", "world"]) is True


def test_in_value_absent_returns_false() -> None:
    assert evaluate_operator(Operator.in_, "missing", ["hello", "world"]) is False


def test_in_case_insensitive() -> None:
    assert evaluate_operator(Operator.in_, "HELLO", ["hello", "world"]) is True


def test_in_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.in_, None, ["hello"]) is False


# ── not_in ────────────────────────────────────────────────────────────────────


def test_not_in_absent_value_returns_true() -> None:
    assert evaluate_operator(Operator.not_in, "missing", ["hello", "world"]) is True


def test_not_in_present_value_returns_false() -> None:
    assert evaluate_operator(Operator.not_in, "hello", ["hello", "world"]) is False


def test_not_in_case_insensitive() -> None:
    assert evaluate_operator(Operator.not_in, "HELLO", ["hello"]) is False


def test_not_in_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.not_in, None, ["hello"]) is False


# ── domain_matches ────────────────────────────────────────────────────────────


def test_domain_matches_full_url_with_www() -> None:
    assert (
        evaluate_operator(
            Operator.domain_matches, "https://www.example.com/path?q=1", "example.com"
        )
        is True
    )


def test_domain_matches_different_domain_returns_false() -> None:
    assert evaluate_operator(Operator.domain_matches, "https://other.com", "example.com") is False


def test_domain_matches_bare_domain_no_scheme() -> None:
    assert evaluate_operator(Operator.domain_matches, "example.com", "example.com") is True


def test_domain_matches_rule_with_www() -> None:
    assert (
        evaluate_operator(Operator.domain_matches, "https://example.com", "www.example.com") is True
    )


def test_domain_matches_with_port_strips_port() -> None:
    assert (
        evaluate_operator(Operator.domain_matches, "https://example.com:8080/path", "example.com")
        is True
    )


def test_domain_matches_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.domain_matches, None, "example.com") is False


# ── matches_regex ─────────────────────────────────────────────────────────────


def test_matches_regex_digit_pattern_match() -> None:
    assert evaluate_operator(Operator.matches_regex, "abc1234", r"\d{4}") is True


def test_matches_regex_no_match_returns_false() -> None:
    assert evaluate_operator(Operator.matches_regex, "abcdef", r"\d{4}") is False


def test_matches_regex_email_pattern() -> None:
    assert (
        evaluate_operator(Operator.matches_regex, "user@example.com", r"^[\w.+-]+@[\w-]+\.\w+$")
        is True
    )


def test_matches_regex_none_metric_returns_false() -> None:
    assert evaluate_operator(Operator.matches_regex, None, r"\d+") is False


# ── None metric — all non-exists operators return False ───────────────────────


@pytest.mark.parametrize(
    "op",
    [
        Operator.equals,
        Operator.not_equals,
        Operator.contains,
        Operator.contains_any,
        Operator.greater_than_or_equal,
        Operator.less_than_or_equal,
        Operator.in_,
        Operator.not_in,
        Operator.domain_matches,
        Operator.matches_regex,
    ],
)
def test_none_metric_returns_false_for_all_non_exists_operators(op: Operator) -> None:
    rule_val: object
    if op in (Operator.contains_any, Operator.in_, Operator.not_in):
        rule_val = ["x"]
    else:
        rule_val = "x"
    assert evaluate_operator(op, None, rule_val) is False
