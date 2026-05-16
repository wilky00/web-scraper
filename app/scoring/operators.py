# ABOUTME: Operator evaluation logic for the scoring engine.
# ABOUTME: evaluate_operator() dispatches to the correct comparison for each Operator value.
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.config.criteria import Operator


def evaluate_operator(op: Operator, metric_val: Any, rule_val: Any) -> bool:
    """Evaluate a single rule operator against a metric value.

    Returns True if the condition passes, False otherwise.
    Never raises for None or type mismatch — returns False instead.
    """
    if op == Operator.exists:
        return metric_val is not None and str(metric_val).strip() != ""

    if op == Operator.not_exists:
        return metric_val is None or str(metric_val).strip() == ""

    # All remaining operators return False when metric_val is None
    if metric_val is None:
        return False

    if op == Operator.equals:
        return str(metric_val).lower() == str(rule_val).lower()

    if op == Operator.not_equals:
        return str(metric_val).lower() != str(rule_val).lower()

    if op == Operator.contains:
        return str(rule_val).lower() in str(metric_val).lower()

    if op == Operator.contains_any:
        metric_lower = str(metric_val).lower()
        return any(str(v).lower() in metric_lower for v in rule_val)

    if op == Operator.greater_than_or_equal:
        try:
            return float(metric_val) >= float(rule_val)
        except (ValueError, TypeError):
            return False

    if op == Operator.less_than_or_equal:
        try:
            return float(metric_val) <= float(rule_val)
        except (ValueError, TypeError):
            return False

    if op == Operator.in_:
        return str(metric_val).lower() in [str(v).lower() for v in rule_val]

    if op == Operator.not_in:
        return str(metric_val).lower() not in [str(v).lower() for v in rule_val]

    if op == Operator.domain_matches:
        metric_str = str(metric_val)
        parsed = urlparse(metric_str)
        # If no scheme, urlparse puts everything in path; treat whole value as domain
        if parsed.netloc:
            domain = parsed.netloc
        else:
            domain = metric_str
        # Strip port if present
        domain = domain.split(":")[0]
        # Strip leading www.
        if domain.lower().startswith("www."):
            domain = domain[4:]
        rule_domain = str(rule_val).lower()
        if rule_domain.startswith("www."):
            rule_domain = rule_domain[4:]
        return domain.lower() == rule_domain

    if op == Operator.matches_regex:
        return bool(re.search(str(rule_val), str(metric_val)))

    return False
