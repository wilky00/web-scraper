# ABOUTME: Unit tests for ScoringEngine.score() covering all rule evaluation paths.
# ABOUTME: Uses inline CriteriaConfig objects and JSON fixture files for metrics.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config.criteria import (
    CriteriaConfig,
    validate_criteria_yaml,
)
from app.scoring import ScoringEngine, ScoringResult

FIXTURES = Path(__file__).parent.parent / "fixtures" / "scoring"
CRITERIA_FIXTURES = Path(__file__).parent.parent / "fixtures" / "criteria"


def load_metrics(filename: str) -> dict[str, Any]:
    return json.loads((FIXTURES / filename).read_text())


def minimal_criteria(
    must_have: list[dict[str, Any]] | None = None,
    should_have: list[dict[str, Any]] | None = None,
    exclude: list[dict[str, Any]] | None = None,
    weighted_rules: list[dict[str, Any]] | None = None,
    scoring_enabled: bool = True,
    minimum_score: float = 0.0,
) -> CriteriaConfig:
    """Build a minimal CriteriaConfig for testing specific scenarios."""
    return CriteriaConfig.model_validate(
        {
            "metadata": {
                "name": "test",
                "display_name": "Test",
            },
            "source": {"connector": "google_places"},
            "rules": {
                "must_have": must_have or [],
                "should_have": should_have or [],
                "exclude": exclude or [],
            },
            "scoring": {
                "enabled": scoring_enabled,
                "minimum_score": minimum_score,
                "weighted_rules": weighted_rules or [],
            },
        }
    )


# ── 1. Excluded record ────────────────────────────────────────────────────────


def test_excluded_record_low_rating() -> None:
    metrics = load_metrics("low_rated.json")
    criteria = minimal_criteria(
        exclude=[{"metric": "source.rating", "operator": "less_than_or_equal", "value": 2.0}]
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.excluded is True
    assert result.match_score == 0.0
    assert result.meets_minimum is False
    assert len(result.excluded_by) == 1


# ── 2. Failed must-have ───────────────────────────────────────────────────────


def test_failed_must_have_missing_email() -> None:
    metrics = load_metrics("missing_email.json")
    criteria = minimal_criteria(must_have=[{"metric": "extraction.email", "operator": "exists"}])
    result = ScoringEngine.score(metrics, criteria)
    assert result.excluded is False
    assert result.match_score == 0.0
    assert result.meets_minimum is False
    assert len(result.failed_must_have) == 1
    assert result.failed_must_have[0].metric == "extraction.email"


# ── 3. Passed must-have, no scoring rules ─────────────────────────────────────


def test_passed_must_have_no_scoring_rules() -> None:
    metrics = load_metrics("basic_metrics.json")
    criteria = minimal_criteria(must_have=[{"metric": "extraction.email", "operator": "exists"}])
    result = ScoringEngine.score(metrics, criteria)
    assert result.match_score == 100.0
    assert result.meets_minimum is True
    assert len(result.passed_must_have) == 1


# ── 4. Weighted scoring — all pass ────────────────────────────────────────────


def test_weighted_scoring_all_pass() -> None:
    metrics = load_metrics("basic_metrics.json")
    criteria = minimal_criteria(
        weighted_rules=[
            {"metric": "extraction.phone", "operator": "exists", "weight": 2.0},
            {"metric": "extraction.address", "operator": "exists", "weight": 1.5},
        ]
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.match_score == 100.0
    assert len(result.matched_rules) == 2
    assert len(result.failed_rules) == 0


# ── 5. Weighted scoring — partial ─────────────────────────────────────────────


def test_weighted_scoring_partial() -> None:
    # phone is absent; address is present
    metrics: dict[str, Any] = {
        "extraction.address": "123 Main St",
    }
    criteria = minimal_criteria(
        weighted_rules=[
            {"metric": "extraction.phone", "operator": "exists", "weight": 2.0},
            {"metric": "extraction.address", "operator": "exists", "weight": 1.5},
        ]
    )
    result = ScoringEngine.score(metrics, criteria)
    expected = round((1.5 / 3.5) * 100.0, 2)
    assert result.match_score == expected
    assert len(result.matched_rules) == 1
    assert len(result.failed_rules) == 1


# ── 6. Minimum score met ──────────────────────────────────────────────────────


def test_minimum_score_met() -> None:
    metrics = load_metrics("basic_metrics.json")
    criteria = minimal_criteria(
        weighted_rules=[{"metric": "extraction.phone", "operator": "exists", "weight": 1.0}],
        minimum_score=50.0,
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.match_score == 100.0
    assert result.meets_minimum is True


# ── 7. Minimum score not met ──────────────────────────────────────────────────


def test_minimum_score_not_met() -> None:
    metrics: dict[str, Any] = {"extraction.address": "123 Main St"}
    criteria = minimal_criteria(
        weighted_rules=[
            {"metric": "extraction.phone", "operator": "exists", "weight": 2.0},
            {"metric": "extraction.address", "operator": "exists", "weight": 1.5},
        ],
        minimum_score=60.0,
    )
    result = ScoringEngine.score(metrics, criteria)
    # earned=1.5, max=3.5 → ~42.86%
    assert result.meets_minimum is False
    assert result.match_score < 60.0


# ── 8. Scoring disabled ───────────────────────────────────────────────────────


def test_scoring_disabled_returns_full_score() -> None:
    metrics = load_metrics("basic_metrics.json")
    criteria = minimal_criteria(
        weighted_rules=[{"metric": "extraction.phone", "operator": "exists", "weight": 1.0}],
        scoring_enabled=False,
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.match_score == 100.0
    assert result.meets_minimum is True


# ── 9. should_have contributes to score ───────────────────────────────────────


def test_should_have_contributes_to_score() -> None:
    metrics = load_metrics("basic_metrics.json")
    # crawl.status_code == 200, weight 1.0 (default)
    criteria = minimal_criteria(
        should_have=[{"metric": "crawl.status_code", "operator": "equals", "value": 200}]
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.match_score == 100.0
    assert len(result.matched_rules) == 1


# ── 10. should_have and weighted together ─────────────────────────────────────


def test_should_have_and_weighted_combined() -> None:
    metrics: dict[str, Any] = {
        "crawl.status_code": 200,
        "extraction.phone": "6155550101",
    }
    criteria = minimal_criteria(
        should_have=[{"metric": "crawl.status_code", "operator": "equals", "value": 200}],
        weighted_rules=[
            {"metric": "extraction.phone", "operator": "exists", "weight": 2.0},
            {"metric": "extraction.address", "operator": "exists", "weight": 1.5},
        ],
    )
    result = ScoringEngine.score(metrics, criteria)
    # max = 1.0 + 2.0 + 1.5 = 4.5, earned = 1.0 + 2.0 = 3.0
    expected = round((3.0 / 4.5) * 100.0, 2)
    assert result.match_score == expected
    assert len(result.matched_rules) == 2
    assert len(result.failed_rules) == 1


# ── 11. Exclude takes priority over must-have ─────────────────────────────────


def test_exclude_takes_priority_over_must_have() -> None:
    metrics = load_metrics("low_rated.json")
    criteria = minimal_criteria(
        exclude=[{"metric": "source.rating", "operator": "less_than_or_equal", "value": 2.0}],
        must_have=[{"metric": "extraction.email", "operator": "exists"}],
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.excluded is True
    assert result.match_score == 0.0
    # must_have was not evaluated — lists are empty
    assert result.passed_must_have == []
    assert result.failed_must_have == []


# ── 12. rule_label uses label field ──────────────────────────────────────────


def test_rule_label_uses_label_field() -> None:
    metrics = load_metrics("basic_metrics.json")
    criteria = minimal_criteria(
        must_have=[{"metric": "extraction.email", "operator": "exists", "label": "Has email"}]
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.passed_must_have[0].rule_label == "Has email"


# ── 13. rule_label falls back to metric ──────────────────────────────────────


def test_rule_label_falls_back_to_metric() -> None:
    metrics = load_metrics("basic_metrics.json")
    criteria = minimal_criteria(
        must_have=[{"metric": "extraction.email", "operator": "exists", "label": ""}]
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.passed_must_have[0].rule_label == "extraction.email"


# ── 14. Full criteria from valid_full.yml ─────────────────────────────────────


def test_full_criteria_from_fixture_basic_metrics_passes() -> None:
    yaml_text = (CRITERIA_FIXTURES / "valid_full.yml").read_text()
    criteria, errors = validate_criteria_yaml(yaml_text)
    assert criteria is not None, f"Criteria failed to load: {errors}"

    metrics = load_metrics("basic_metrics.json")
    result = ScoringEngine.score(metrics, criteria)

    # basic_metrics has email + website → must_have passes
    # rating 4.5 → not excluded (exclude is <=2.0)
    # should_have: status_code==200 → pass (weight 1.0)
    # weighted: phone exists (weight 2.0) → pass, address exists (weight 1.5) → pass
    # max=4.5, earned=4.5 → 100.0
    assert result.excluded is False
    assert result.failed_must_have == []
    assert result.match_score == 100.0
    assert result.meets_minimum is True  # minimum_score=30.0


# ── 15. Empty metrics dict + must_have exists rule ────────────────────────────


def test_empty_metrics_fails_must_have_exists() -> None:
    metrics: dict[str, Any] = {}
    criteria = minimal_criteria(must_have=[{"metric": "extraction.email", "operator": "exists"}])
    result = ScoringEngine.score(metrics, criteria)
    assert result.match_score == 0.0
    assert result.meets_minimum is False
    assert len(result.failed_must_have) == 1


# ── Bonus: no_website fixture — missing website fails must_have ───────────────


def test_no_website_fails_website_must_have() -> None:
    metrics = load_metrics("no_website.json")
    criteria = minimal_criteria(must_have=[{"metric": "extraction.website", "operator": "exists"}])
    result = ScoringEngine.score(metrics, criteria)
    assert result.match_score == 0.0
    assert len(result.failed_must_have) == 1


# ── Bonus: excluded_by collects all triggering rules ─────────────────────────


def test_multiple_exclude_rules_all_collected() -> None:
    metrics: dict[str, Any] = {
        "source.rating": 1.0,
        "crawl.status_code": 404,
    }
    criteria = minimal_criteria(
        exclude=[
            {"metric": "source.rating", "operator": "less_than_or_equal", "value": 2.0},
            {"metric": "crawl.status_code", "operator": "equals", "value": 404},
        ]
    )
    result = ScoringEngine.score(metrics, criteria)
    assert result.excluded is True
    assert len(result.excluded_by) == 2


# ── Bonus: ScoringResult fields are correct types ─────────────────────────────


def test_scoring_result_is_dataclass() -> None:
    metrics = load_metrics("basic_metrics.json")
    criteria = minimal_criteria()
    result = ScoringEngine.score(metrics, criteria)
    assert isinstance(result, ScoringResult)
    assert isinstance(result.match_score, float)
    assert isinstance(result.excluded, bool)
    assert isinstance(result.excluded_by, list)
    assert isinstance(result.matched_rules, list)
    assert isinstance(result.failed_rules, list)
