# ABOUTME: Criteria group and version models. Versions are immutable once saved.
# ABOUTME: config_snapshot stores the full validated YAML as JSON for reproducibility.
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CriteriaGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "criteria_groups"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    versions: Mapped[list[CriteriaVersion]] = relationship(
        "CriteriaVersion", back_populates="group", order_by="CriteriaVersion.version"
    )

    def __repr__(self) -> str:
        return f"<CriteriaGroup id={self.id} name={self.name!r}>"


class CriteriaVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "criteria_versions"

    group_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("criteria_groups.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # Full validated criteria config — never mutated after creation
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    group: Mapped[CriteriaGroup] = relationship("CriteriaGroup", back_populates="versions")

    def __repr__(self) -> str:
        return f"<CriteriaVersion id={self.id} group_id={self.group_id} v={self.version}>"
