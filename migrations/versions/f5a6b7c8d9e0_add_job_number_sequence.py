# ABOUTME: Migration to add job_number — a human-readable sequential identifier for CrawlJobs.
# ABOUTME: Uses a PostgreSQL sequence so existing rows are backfilled and new rows auto-increment.

"""add_job_number_sequence

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-05-20

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE crawl_jobs_job_number_seq START 1")
    op.add_column(
        "crawl_jobs",
        sa.Column(
            "job_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("nextval('crawl_jobs_job_number_seq')"),
        ),
    )
    op.create_unique_constraint("uq_crawl_jobs_job_number", "crawl_jobs", ["job_number"])


def downgrade() -> None:
    op.drop_constraint("uq_crawl_jobs_job_number", "crawl_jobs", type_="unique")
    op.drop_column("crawl_jobs", "job_number")
    op.execute("DROP SEQUENCE crawl_jobs_job_number_seq")
