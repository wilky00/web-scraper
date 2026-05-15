# ABOUTME: RecordAuditLog and Export models.
# ABOUTME: Audit log is append-only. Exports track generated files stored in S3/MinIO.
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class RecordAuditLog(UUIDPrimaryKeyMixin, Base):
    """Append-only log of all user actions that mutate application state."""

    __tablename__ = "record_audit_log"

    # Explicit created_at only — audit entries are never updated
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Actions: create | update | delete | export | job_start | job_pause |
    #          job_resume | job_cancel | criteria_save | login | logout
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # JSON diff or relevant payload (never contains secrets)
    diff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:
        return (
            f"<RecordAuditLog id={self.id} action={self.action!r} resource={self.resource_type!r}>"
        )


class Export(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "exports"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # csv | xlsx
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    # Serialized filter/sort params used to generate this export
    filter_params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # S3/MinIO object key — null until upload completes
    s3_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # pending | processing | ready | failed
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Export id={self.id} format={self.format!r} status={self.status!r}>"
