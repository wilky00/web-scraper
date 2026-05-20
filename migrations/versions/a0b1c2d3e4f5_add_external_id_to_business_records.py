# ABOUTME: Migration to add external_id to business_records.
# ABOUTME: Stores stable connector-provided identifiers (e.g. Google Place ID) for cross-job dedup.

"""add_external_id_to_business_records

Revision ID: a0b1c2d3e4f5
Revises: f5a6b7c8d9e0
Create Date: 2026-05-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "business_records",
        sa.Column("external_id", sa.String(512), nullable=True),
    )
    # Regular index for fast lookups
    op.create_index("ix_business_records_external_id", "business_records", ["external_id"])
    # Partial unique index: prevents two active records with the same external_id,
    # while allowing multiple NULLs (connectors that don't provide an external_id).
    op.execute(
        "CREATE UNIQUE INDEX uq_business_records_external_id "
        "ON business_records (external_id) WHERE external_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_business_records_external_id")
    op.drop_index("ix_business_records_external_id", table_name="business_records")
    op.drop_column("business_records", "external_id")
