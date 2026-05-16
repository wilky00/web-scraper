"""add_api_token_to_users

Revision ID: a1b2c3d4e5f6
Revises: def32db42b5c
Create Date: 2026-05-16

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "def32db42b5c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("api_key_hash", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("api_key_scopes", postgresql.JSONB(), nullable=True))
    op.create_index("ix_users_api_key_hash", "users", ["api_key_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_api_key_hash", table_name="users")
    op.drop_column("users", "api_key_scopes")
    op.drop_column("users", "api_key_hash")
