# ABOUTME: Pydantic v2 schema for criteria YAML — the human-authored scrape/score templates.
# ABOUTME: validate_criteria_yaml() returns structured errors instead of raising exceptions.
from __future__ import annotations

from enum import StrEnum
from typing import Any

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class Operator(StrEnum):
    """All supported rule operators. Values match what appears in criteria YAML."""

    exists = "exists"
    not_exists = "not_exists"
    equals = "equals"
    not_equals = "not_equals"
    contains = "contains"
    contains_any = "contains_any"
    greater_than_or_equal = "greater_than_or_equal"
    less_than_or_equal = "less_than_or_equal"
    in_ = "in"  # 'in' is a Python keyword; YAML value is still "in"
    not_in = "not_in"
    domain_matches = "domain_matches"
    matches_regex = "matches_regex"


_VALID_NAMESPACES = frozenset(["source", "crawl", "html", "links", "extraction"])


class CriteriaMetadata(BaseModel):
    name: str
    display_name: str
    description: str = ""
    tags: list[str] = []
    project: str | None = None


class QueryField(BaseModel):
    field: str
    value: str


class SourceSection(BaseModel):
    connector: str
    max_results: int = Field(60, ge=1)
    query_fields: list[QueryField] = []


class CrawlSection(BaseModel):
    enabled: bool = True
    max_depth: int = Field(3, ge=0, le=10)
    max_pages_per_domain: int = Field(50, ge=1)
    timeout_seconds: int = Field(30, ge=1, le=300)
    delay_ms: int = Field(1000, ge=0)
    include_url_patterns: list[str] = []
    exclude_url_patterns: list[str] = []
    capture_screenshot: bool = False


class ExtractionField(BaseModel):
    name: str
    source_priority: list[str] = []
    filters: list[str] = []


class ExtractionSection(BaseModel):
    fields: list[ExtractionField] = []


class Rule(BaseModel):
    metric: str
    operator: Operator
    value: Any = None
    label: str = ""
    weight: float = Field(1.0, ge=0.0, le=100.0)

    @field_validator("metric")
    @classmethod
    def validate_metric_namespace(cls, v: str) -> str:
        parts = v.split(".", 1)
        if len(parts) < 2 or parts[0] not in _VALID_NAMESPACES or not parts[1]:
            valid = ", ".join(sorted(_VALID_NAMESPACES))
            raise ValueError(
                f"'{v}' must be '<namespace>.<field>' where namespace is one of: {valid}"
            )
        return v


class RulesSection(BaseModel):
    must_have: list[Rule] = []
    should_have: list[Rule] = []
    exclude: list[Rule] = []


class ScoringSection(BaseModel):
    enabled: bool = True
    minimum_score: float = Field(0.0, ge=0.0, le=100.0)
    weighted_rules: list[Rule] = []


class DedupSection(BaseModel):
    primary_key: str = "domain"
    secondary_keys: list[str] = []


class OutputSection(BaseModel):
    display_fields: list[str] = []
    store_fields: list[str] = []
    export_fields: list[str] = []


class CriteriaConfig(BaseModel):
    metadata: CriteriaMetadata
    source: SourceSection
    crawl: CrawlSection = CrawlSection()
    extraction: ExtractionSection = ExtractionSection()
    rules: RulesSection = RulesSection()
    scoring: ScoringSection = ScoringSection()
    dedup: DedupSection = DedupSection()
    output: OutputSection = OutputSection()


def validate_criteria_yaml(yaml_text: str) -> tuple[CriteriaConfig | None, list[str]]:
    """Parse and validate a criteria YAML string.

    Returns (CriteriaConfig, []) on success or (None, [error strings]) on any failure.
    Never raises — all errors are returned as readable strings for the UI.
    """
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return None, [f"YAML syntax error: {exc}"]

    if not isinstance(data, dict):
        return None, [f"Criteria YAML must be a mapping, got {type(data).__name__}"]

    try:
        config = CriteriaConfig.model_validate(data)
        return config, []
    except ValidationError as exc:
        errors: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err["loc"])
            msg = err["msg"]
            errors.append(f"{loc}: {msg}" if loc else msg)
        return None, errors
