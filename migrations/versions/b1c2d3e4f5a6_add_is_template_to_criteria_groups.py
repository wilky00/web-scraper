# ABOUTME: Migration to add is_template boolean column to criteria_groups.
# ABOUTME: Seeded example templates are marked is_template=True by the seeder at startup.

"""add_is_template_to_criteria_groups

Revision ID: b1c2d3e4f5a6
Revises: a9c69ca6be9b
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a9c69ca6be9b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "criteria_groups",
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("criteria_groups", "is_template")
