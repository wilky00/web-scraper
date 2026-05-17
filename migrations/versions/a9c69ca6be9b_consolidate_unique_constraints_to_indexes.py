# ABOUTME: Migration to remove redundant UniqueConstraints and consolidate uniqueness
# ABOUTME: into indexes on connectors.name, criteria_groups.name, and users.email.

"""consolidate_unique_constraints_to_indexes

Revision ID: a9c69ca6be9b
Revises: a1b2c3d4e5f6
Create Date: 2026-05-17

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c69ca6be9b"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # connectors.name: drop redundant UniqueConstraint, replace non-unique index with unique index
    op.drop_constraint("connectors_name_key", "connectors", type_="unique")
    op.drop_index("ix_connectors_name", table_name="connectors")
    op.create_index("ix_connectors_name", "connectors", ["name"], unique=True)

    # criteria_groups.name: same consolidation
    op.drop_constraint("criteria_groups_name_key", "criteria_groups", type_="unique")
    op.drop_index("ix_criteria_groups_name", table_name="criteria_groups")
    op.create_index("ix_criteria_groups_name", "criteria_groups", ["name"], unique=True)

    # users.email: same consolidation
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    # users.email: restore separate UniqueConstraint + non-unique index
    op.drop_index("ix_users_email", table_name="users")
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_unique_constraint("users_email_key", "users", ["email"])

    # criteria_groups.name
    op.drop_index("ix_criteria_groups_name", table_name="criteria_groups")
    op.create_index("ix_criteria_groups_name", "criteria_groups", ["name"], unique=False)
    op.create_unique_constraint("criteria_groups_name_key", "criteria_groups", ["name"])

    # connectors.name
    op.drop_index("ix_connectors_name", table_name="connectors")
    op.create_index("ix_connectors_name", "connectors", ["name"], unique=False)
    op.create_unique_constraint("connectors_name_key", "connectors", ["name"])
