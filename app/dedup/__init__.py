# ABOUTME: Public API for the deduplication module.
# ABOUTME: Exports RecordData, SourceData, and DeduplicationEngine for use across the app.
from __future__ import annotations

from app.dedup.engine import DeduplicationEngine, RecordData, SourceData

__all__ = ["DeduplicationEngine", "RecordData", "SourceData"]
