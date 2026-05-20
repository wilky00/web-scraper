# ABOUTME: BusinessRecord and RecordSource models. Sources preserve attribution for every field.
# ABOUTME: rule_results stores the scoring breakdown (matched/failed/excluded rules + score).
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class BusinessRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "business_records"

    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Core extracted fields
    name: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_country: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Stable external identifier from the connector (e.g. Google Places place_id)
    external_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)

    # Scoring output
    match_score: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True
    )
    # Full scoring breakdown: {matched_rules, failed_rules, excluded_rules, evidence}
    rule_results: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Status: active | duplicate | excluded | deleted
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active", index=True)
    # Points to the canonical record when this record is a duplicate
    canonical_record_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("business_records.id", ondelete="SET NULL"), nullable=True
    )

    # Extra fields from criteria output config — renamed from `metadata` to avoid
    # collision with DeclarativeBase.metadata
    extra_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    sources: Mapped[list[RecordSource]] = relationship("RecordSource", back_populates="record")

    def __repr__(self) -> str:
        return f"<BusinessRecord id={self.id} name={self.name!r} status={self.status!r}>"


class RecordSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "record_sources"

    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("business_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Which field this source attribution belongs to (e.g. "email", "phone")
    field: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # connector | crawl | manual
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="crawl")
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    record: Mapped[BusinessRecord] = relationship("BusinessRecord", back_populates="sources")

    def __repr__(self) -> str:
        return f"<RecordSource id={self.id} field={self.field!r} type={self.source_type!r}>"
