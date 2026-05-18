# ABOUTME: Adds project_id FK to criteria_groups so templates can be scoped to a project.
# ABOUTME: Nullable — existing groups remain unscoped (treated as the Default project).
"""add project scoping to criteria

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-05-18 08:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "criteria_groups",
        sa.Column(
            "project_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_criteria_groups_project_id",
        "criteria_groups",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_criteria_groups_project_id",
        "criteria_groups",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_criteria_groups_project_id", table_name="criteria_groups")
    op.drop_constraint("fk_criteria_groups_project_id", "criteria_groups", type_="foreignkey")
    op.drop_column("criteria_groups", "project_id")
