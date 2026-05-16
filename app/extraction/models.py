# ABOUTME: Data models for the extraction package.
# ABOUTME: ExtractedField carries a normalized value plus full source attribution.
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExtractedField:
    value: str
    source_url: str
    source_type: str
    raw_value: str


@dataclass
class ExtractionResult:
    name: ExtractedField | None = field(default=None)
    website: ExtractedField | None = field(default=None)
    emails: list[ExtractedField] = field(default_factory=list)
    phones: list[ExtractedField] = field(default_factory=list)
    address: ExtractedField | None = field(default=None)
