# ABOUTME: CrawlJob and CrawlJobEvent models. Jobs store a full config snapshot for reproducibility.
# ABOUTME: Events are append-only — they have created_at but no updated_at.
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CrawlJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crawl_jobs"

    criteria_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("criteria_versions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    connector_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connectors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Lifecycle: queued | running | paused | cancel_requested | cancelled |
    #            completed | completed_with_errors | failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued", index=True)
    # Full snapshot of criteria + connector config at job start — makes jobs reproducible
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    rq_job_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    events: Mapped[list[CrawlJobEvent]] = relationship(
        "CrawlJobEvent", back_populates="job", order_by="CrawlJobEvent.created_at"
    )

    def __repr__(self) -> str:
        return f"<CrawlJob id={self.id} status={self.status!r}>"


class CrawlJobEvent(UUIDPrimaryKeyMixin, Base):
    """Append-only event log for a crawl job. No updated_at — events are never mutated."""

    __tablename__ = "crawl_job_events"

    # Explicit created_at without updated_at — this table is append-only
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Renamed from `metadata` to avoid collision with DeclarativeBase.metadata
    event_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    job: Mapped[CrawlJob] = relationship("CrawlJob", back_populates="events")

    def __repr__(self) -> str:
        return f"<CrawlJobEvent id={self.id} type={self.event_type!r}>"
