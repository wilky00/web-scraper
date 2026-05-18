# ABOUTME: CrawlPage model — one row per URL visited during a crawl job.
# ABOUTME: raw_html_path points to S3/MinIO key; null when raw HTML storage is disabled.
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CrawlPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "crawl_pages"

    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawl_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # S3/MinIO key for stored raw HTML (null = not stored or retention expired)
    raw_html_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # S3/MinIO key for page screenshot (null = not captured or retention expired)
    screenshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Extraction result summary stored alongside the page
    extracted_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<CrawlPage id={self.id} url={self.url!r} status={self.status_code}>"
