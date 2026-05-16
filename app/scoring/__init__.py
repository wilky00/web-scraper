# ABOUTME: Scoring package — deterministic rule evaluation and match score calculation.
# ABOUTME: All public symbols exported here; ScoringEngine is the main entry point.
from __future__ import annotations

from app.scoring.engine import ScoringEngine
from app.scoring.models import RuleResult, ScoringResult

__all__ = ["RuleResult", "ScoringResult", "ScoringEngine"]
