# ABOUTME: Migration to add screenshot_path column to crawl_pages.
# ABOUTME: Stores the S3/MinIO key for an optional page screenshot artifact.

"""add_screenshot_path_to_crawl_pages

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-18

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "crawl_pages",
        sa.Column("screenshot_path", sa.String(512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("crawl_pages", "screenshot_path")
