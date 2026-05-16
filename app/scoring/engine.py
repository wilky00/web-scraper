# ABOUTME: ScoringEngine — evaluates CriteriaConfig rules against a metrics dict.
# ABOUTME: Deterministic, stateless; returns a ScoringResult with full rule-level detail.
from __future__ import annotations

from typing import Any

from app.config.criteria import CriteriaConfig, Rule
from app.scoring.models import RuleResult, ScoringResult
from app.scoring.operators import evaluate_operator


class ScoringEngine:
    @staticmethod
    def score(metrics: dict[str, Any], criteria: CriteriaConfig) -> ScoringResult:
        """Score a record against the given criteria configuration.

        Evaluation order: exclude → must_have → scoring (should_have + weighted_rules).
        Returns a fully populated ScoringResult.
        """
        # ── 1. EXCLUDE pass ──────────────────────────────────────────────────
        excluded_by: list[RuleResult] = []
        for rule in criteria.rules.exclude:
            metric_val = metrics.get(rule.metric)
            passed = evaluate_operator(rule.operator, metric_val, rule.value)
            if passed:
                excluded_by.append(ScoringEngine._make_rule_result(rule, passed=True))

        if excluded_by:
            return ScoringResult(
                match_score=0.0,
                excluded=True,
                excluded_by=excluded_by,
                passed_must_have=[],
                failed_must_have=[],
                matched_rules=[],
                failed_rules=[],
                meets_minimum=False,
            )

        # ── 2. MUST-HAVE pass ────────────────────────────────────────────────
        passed_must_have: list[RuleResult] = []
        failed_must_have: list[RuleResult] = []
        for rule in criteria.rules.must_have:
            metric_val = metrics.get(rule.metric)
            passed = evaluate_operator(rule.operator, metric_val, rule.value)
            result = ScoringEngine._make_rule_result(rule, passed=passed)
            if passed:
                passed_must_have.append(result)
            else:
                failed_must_have.append(result)

        if failed_must_have:
            return ScoringResult(
                match_score=0.0,
                excluded=False,
                excluded_by=[],
                passed_must_have=passed_must_have,
                failed_must_have=failed_must_have,
                matched_rules=[],
                failed_rules=[],
                meets_minimum=False,
            )

        # ── 3. SCORING pass ──────────────────────────────────────────────────
        if not criteria.scoring.enabled:
            return ScoringResult(
                match_score=100.0,
                excluded=False,
                excluded_by=[],
                passed_must_have=passed_must_have,
                failed_must_have=[],
                matched_rules=[],
                failed_rules=[],
                meets_minimum=True,
            )

        scorable_rules = criteria.rules.should_have + criteria.scoring.weighted_rules
        matched_rules: list[RuleResult] = []
        failed_rules: list[RuleResult] = []

        for rule in scorable_rules:
            metric_val = metrics.get(rule.metric)
            passed = evaluate_operator(rule.operator, metric_val, rule.value)
            result = ScoringEngine._make_rule_result(rule, passed=passed)
            if passed:
                matched_rules.append(result)
            else:
                failed_rules.append(result)

        max_score = sum(rule.weight for rule in scorable_rules)
        if max_score == 0.0:
            match_score = 100.0
        else:
            earned_score = sum(
                rule.weight
                for rule in scorable_rules
                if evaluate_operator(rule.operator, metrics.get(rule.metric), rule.value)
            )
            match_score = round((earned_score / max_score) * 100.0, 2)

        meets_minimum = match_score >= criteria.scoring.minimum_score

        return ScoringResult(
            match_score=match_score,
            excluded=False,
            excluded_by=[],
            passed_must_have=passed_must_have,
            failed_must_have=[],
            matched_rules=matched_rules,
            failed_rules=failed_rules,
            meets_minimum=meets_minimum,
        )

    @staticmethod
    def _make_rule_result(rule: Rule, passed: bool) -> RuleResult:
        rule_label = rule.label if rule.label else rule.metric
        return RuleResult(
            rule_label=rule_label,
            metric=rule.metric,
            operator=str(rule.operator),
            value=rule.value,
            passed=passed,
        )
