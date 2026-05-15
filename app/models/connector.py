# ABOUTME: Connector model. Stores connector type, enabled flag, and non-secret config snapshot.
# ABOUTME: API keys and credentials are never stored here — they live in .env only.
from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Connector(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "connectors"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Non-secret options snapshot from connectors.yml at time of job creation
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<Connector id={self.id} name={self.name!r} type={self.connector_type!r}>"
