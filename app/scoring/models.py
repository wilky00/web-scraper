# ABOUTME: Result dataclasses for the scoring engine.
# ABOUTME: RuleResult captures per-rule evaluation; ScoringResult aggregates the full score.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RuleResult:
    rule_label: str  # from Rule.label, or metric if label is empty
    metric: str  # e.g. "extraction.email"
    operator: str  # e.g. "exists"
    value: Any  # the rule's expected value (None for exists/not_exists)
    passed: bool


@dataclass
class ScoringResult:
    match_score: float  # 0.0–100.0
    excluded: bool
    excluded_by: list[RuleResult]  # exclude rules that triggered (usually empty or 1)
    passed_must_have: list[RuleResult]
    failed_must_have: list[RuleResult]
    matched_rules: list[RuleResult]  # should_have + weighted_rules that passed
    failed_rules: list[RuleResult]  # should_have + weighted_rules that failed
    meets_minimum: bool  # match_score >= scoring.minimum_score (or True if scoring disabled)
