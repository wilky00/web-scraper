# ABOUTME: RawSearchResult model — stores raw connector API responses before processing.
# ABOUTME: Processed flag tracks whether the record has been turned into a BusinessRecord.
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RawSearchResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "raw_search_results"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    def __repr__(self) -> str:
        return (
            f"<RawSearchResult id={self.id} connector={self.connector_type!r}"
            f" processed={self.processed}>"
        )
