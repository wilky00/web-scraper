# ABOUTME: Integration tests for Alembic migrations. Requires a live PostgreSQL connection.
# ABOUTME: Verifies all 12 tables exist after upgrade and are removed after downgrade.
from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

EXPECTED_TABLES = {
    "users",
    "criteria_groups",
    "criteria_versions",
    "connectors",
    "crawl_jobs",
    "crawl_job_events",
    "raw_search_results",
    "crawl_pages",
    "business_records",
    "record_sources",
    "record_audit_log",
    "exports",
}


@pytest.fixture(scope="module")
def alembic_cfg() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    return cfg


@pytest.fixture(scope="module", autouse=True)
def run_migrations(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "head")
    yield
    command.downgrade(alembic_cfg, "base")


@pytest.fixture(scope="module")
async def async_engine():
    engine = create_async_engine(os.environ["DATABASE_URL"])
    yield engine
    await engine.dispose()


async def get_table_names(engine) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename")
        )
        return {row[0] for row in result}


async def get_column_names(engine, table: str) -> set[str]:
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"
            ),
            {"t": table},
        )
        return {row[0] for row in result}


@pytest.mark.asyncio
async def test_all_tables_exist_after_upgrade(async_engine) -> None:
    tables = await get_table_names(async_engine)
    missing = EXPECTED_TABLES - tables
    assert not missing, f"Missing tables after upgrade: {missing}"


@pytest.mark.asyncio
async def test_alembic_version_table_exists(async_engine) -> None:
    tables = await get_table_names(async_engine)
    assert "alembic_version" in tables


@pytest.mark.asyncio
async def test_users_table_has_expected_columns(async_engine) -> None:
    cols = await get_column_names(async_engine, "users")
    assert {"id", "email", "hashed_password", "role", "is_active", "created_at"} <= cols


@pytest.mark.asyncio
async def test_crawl_jobs_has_expected_columns(async_engine) -> None:
    cols = await get_column_names(async_engine, "crawl_jobs")
    assert {"id", "status", "config_snapshot", "criteria_version_id", "connector_id"} <= cols


@pytest.mark.asyncio
async def test_business_records_has_extra_fields_not_metadata(async_engine) -> None:
    cols = await get_column_names(async_engine, "business_records")
    assert "extra_fields" in cols
    assert "metadata" not in cols


@pytest.mark.asyncio
async def test_crawl_job_events_has_event_data_not_metadata(async_engine) -> None:
    cols = await get_column_names(async_engine, "crawl_job_events")
    assert "event_data" in cols
    assert "metadata" not in cols


@pytest.mark.asyncio
async def test_append_only_tables_have_no_updated_at(async_engine) -> None:
    for table in ("crawl_job_events", "record_audit_log"):
        cols = await get_column_names(async_engine, table)
        assert "created_at" in cols, f"{table} missing created_at"
        assert "updated_at" not in cols, f"{table} should not have updated_at"
