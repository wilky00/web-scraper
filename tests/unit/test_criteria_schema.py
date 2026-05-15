# ABOUTME: Unit tests for the criteria YAML Pydantic schema and validate_criteria_yaml().
# ABOUTME: Covers all operators, all metric namespaces, and structured error output.
from __future__ import annotations

import pytest

from app.config.criteria import Operator, validate_criteria_yaml

# ---------------------------------------------------------------------------
# Shared YAML fixtures (inline strings — keeps tests self-contained)
# ---------------------------------------------------------------------------

_VALID_MINIMAL = """\
metadata:
  name: test-criteria
  display_name: Test Criteria
source:
  connector: google_places
  query_fields:
    - field: type
      value: bakery
"""

_VALID_FULL = """\
metadata:
  name: bakeries-nashville
  display_name: Bakeries near Nashville
  description: Find bakeries within 30 miles
  tags: [bakery, food, nashville]
source:
  connector: google_places
  max_results: 60
  query_fields:
    - field: type
      value: bakery
    - field: location
      value: "Nashville, TN"
crawl:
  enabled: true
  max_depth: 2
  include_url_patterns: [".*menu.*"]
  exclude_url_patterns: ["/order"]
extraction:
  fields:
    - name: email
    - name: phone
      source_priority: [html, connector]
rules:
  must_have:
    - metric: extraction.email
      operator: exists
      label: Has email
  exclude:
    - metric: source.rating
      operator: less_than_or_equal
      value: 2.0
  should_have:
    - metric: crawl.status_code
      operator: equals
      value: 200
scoring:
  enabled: true
  minimum_score: 30.0
  weighted_rules:
    - metric: extraction.phone
      operator: exists
      weight: 2.0
dedup:
  primary_key: domain
  secondary_keys: [email, phone]
output:
  display_fields: [name, email, phone, address]
  store_fields: [name, email, phone, address, match_score]
  export_fields: [name, email, phone, address, website]
"""

_INVALID_OPERATOR = """\
metadata:
  name: test
  display_name: Test
source:
  connector: google_places
rules:
  must_have:
    - metric: extraction.email
      operator: fuzzy_match
"""

_INVALID_NAMESPACE = """\
metadata:
  name: test
  display_name: Test
source:
  connector: google_places
rules:
  must_have:
    - metric: bad_namespace.email
      operator: exists
"""

_INVALID_MISSING_METADATA = """\
source:
  connector: google_places
"""

_INVALID_MISSING_SOURCE = """\
metadata:
  name: test
  display_name: Test
"""

_INVALID_SYNTAX = """\
metadata:
  name: test
  display_name: [
    unclosed bracket
"""

_INVALID_SCORE_OUT_OF_RANGE = """\
metadata:
  name: test
  display_name: Test
source:
  connector: google_places
scoring:
  minimum_score: 150.0
"""

_INVALID_METRIC_NAMESPACE_ONLY = """\
metadata:
  name: test
  display_name: Test
source:
  connector: google_places
rules:
  must_have:
    - metric: extraction.
      operator: exists
"""


# ---------------------------------------------------------------------------
# validate_criteria_yaml — success paths
# ---------------------------------------------------------------------------


class TestValidateCriteriaYamlSuccess:
    def test_minimal_valid_returns_config(self) -> None:
        config, errors = validate_criteria_yaml(_VALID_MINIMAL)
        assert errors == []
        assert config is not None
        assert config.metadata.name == "test-criteria"
        assert config.source.connector == "google_places"

    def test_full_valid_parses_all_sections(self) -> None:
        config, errors = validate_criteria_yaml(_VALID_FULL)
        assert errors == []
        assert config is not None
        assert config.metadata.tags == ["bakery", "food", "nashville"]
        assert config.crawl.max_depth == 2
        assert len(config.rules.must_have) == 1
        assert config.rules.must_have[0].operator == Operator.exists
        assert config.rules.must_have[0].label == "Has email"
        assert len(config.rules.exclude) == 1
        assert config.rules.exclude[0].operator == Operator.less_than_or_equal
        assert config.scoring.minimum_score == 30.0
        assert len(config.scoring.weighted_rules) == 1
        assert config.scoring.weighted_rules[0].weight == 2.0
        assert config.dedup.primary_key == "domain"
        assert config.dedup.secondary_keys == ["email", "phone"]
        assert "name" in config.output.display_fields

    def test_defaults_applied_for_optional_sections(self) -> None:
        config, errors = validate_criteria_yaml(_VALID_MINIMAL)
        assert config is not None
        assert config.crawl.enabled is True
        assert config.crawl.max_depth == 3
        assert config.extraction.fields == []
        assert config.rules.must_have == []
        assert config.scoring.enabled is True
        assert config.scoring.minimum_score == 0.0
        assert config.dedup.primary_key == "domain"


# ---------------------------------------------------------------------------
# validate_criteria_yaml — all operators accepted
# ---------------------------------------------------------------------------


class TestAllOperators:
    @pytest.mark.parametrize("operator", [op.value for op in Operator])
    def test_operator_accepted(self, operator: str) -> None:
        yaml_text = f"""\
metadata:
  name: test
  display_name: Test
source:
  connector: google_places
rules:
  must_have:
    - metric: extraction.email
      operator: {operator}
"""
        config, errors = validate_criteria_yaml(yaml_text)
        assert errors == [], f"Operator '{operator}' failed: {errors}"
        assert config is not None
        assert config.rules.must_have[0].operator.value == operator


# ---------------------------------------------------------------------------
# validate_criteria_yaml — all namespaces accepted
# ---------------------------------------------------------------------------


class TestAllNamespaces:
    @pytest.mark.parametrize("namespace", ["source", "crawl", "html", "links", "extraction"])
    def test_namespace_accepted(self, namespace: str) -> None:
        yaml_text = f"""\
metadata:
  name: test
  display_name: Test
source:
  connector: google_places
rules:
  must_have:
    - metric: {namespace}.field_name
      operator: exists
"""
        config, errors = validate_criteria_yaml(yaml_text)
        assert errors == [], f"Namespace '{namespace}' failed: {errors}"


# ---------------------------------------------------------------------------
# validate_criteria_yaml — error paths
# ---------------------------------------------------------------------------


class TestValidateCriteriaYamlErrors:
    def test_unknown_operator_returns_error(self) -> None:
        config, errors = validate_criteria_yaml(_INVALID_OPERATOR)
        assert config is None
        assert len(errors) > 0
        # Error should reference the invalid operator value or the field
        assert any("operator" in e.lower() or "fuzzy_match" in e for e in errors)

    def test_invalid_namespace_returns_error(self) -> None:
        config, errors = validate_criteria_yaml(_INVALID_NAMESPACE)
        assert config is None
        assert len(errors) > 0
        assert any("bad_namespace" in e for e in errors)

    def test_missing_metadata_returns_error(self) -> None:
        config, errors = validate_criteria_yaml(_INVALID_MISSING_METADATA)
        assert config is None
        assert any("metadata" in e for e in errors)

    def test_missing_source_returns_error(self) -> None:
        config, errors = validate_criteria_yaml(_INVALID_MISSING_SOURCE)
        assert config is None
        assert any("source" in e for e in errors)

    def test_yaml_syntax_error_returns_single_error(self) -> None:
        config, errors = validate_criteria_yaml(_INVALID_SYNTAX)
        assert config is None
        assert len(errors) == 1
        assert "syntax" in errors[0].lower()

    def test_score_out_of_range_returns_error(self) -> None:
        config, errors = validate_criteria_yaml(_INVALID_SCORE_OUT_OF_RANGE)
        assert config is None
        assert any("minimum_score" in e or "scoring" in e for e in errors)

    def test_metric_namespace_only_no_field_returns_error(self) -> None:
        config, errors = validate_criteria_yaml(_INVALID_METRIC_NAMESPACE_ONLY)
        assert config is None
        assert len(errors) > 0

    def test_empty_string_returns_error(self) -> None:
        config, errors = validate_criteria_yaml("")
        assert config is None
        assert len(errors) > 0

    def test_non_mapping_yaml_returns_error(self) -> None:
        config, errors = validate_criteria_yaml("- just a list\n- not a mapping\n")
        assert config is None
        assert len(errors) > 0

    def test_errors_are_strings(self) -> None:
        config, errors = validate_criteria_yaml(_INVALID_OPERATOR)
        assert config is None
        for err in errors:
            assert isinstance(err, str)
            assert len(err) > 0


# ---------------------------------------------------------------------------
# CriteriaConfig — direct model construction
# ---------------------------------------------------------------------------


class TestCriteriaConfigModel:
    def test_operator_enum_in_value(self) -> None:
        # 'in' is a Python keyword — verify it round-trips via the enum value
        config, errors = validate_criteria_yaml(
            """\
metadata:
  name: test
  display_name: Test
source:
  connector: google_places
rules:
  must_have:
    - metric: source.type
      operator: "in"
      value: [bakery, cafe]
"""
        )
        assert errors == []
        assert config is not None
        assert config.rules.must_have[0].operator == Operator.in_
        assert config.rules.must_have[0].operator.value == "in"
