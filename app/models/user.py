# ABOUTME: User model. MVP supports a single `operator` role; role field is future-ready.
# ABOUTME: Passwords are stored hashed (bcrypt). SSO users have sso_sub populated.
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="operator")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Populated for SSO users; null for local-auth-only users
    sso_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Soft-delete support for audit trail
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # API token — one token per user; hash stored, plaintext never persisted
    api_key_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, index=True
    )
    api_key_scopes: Mapped[Any] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"
