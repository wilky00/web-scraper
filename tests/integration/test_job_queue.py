# ABOUTME: Integration tests for the job orchestrator against a real PostgreSQL database.
# ABOUTME: Uses FixtureConnector with static JSON; no Playwright (crawl step skipped).
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config.criteria import validate_criteria_yaml
from app.connectors.fixture import FixtureConnector
from app.jobs.orchestrator import run_job
from app.models.base import Base
from app.models.connector import Connector
from app.models.criteria import CriteriaGroup, CriteriaVersion
from app.models.job import CrawlJob, CrawlJobEvent
from app.models.raw_result import RawSearchResult
from app.models.record import BusinessRecord, RecordSource
from app.models.user import User
from app.settings import Settings

_CRITERIA_YAML = """
metadata:
  name: test-integration-criteria
  display_name: Integration Test Criteria
  description: Used in integration tests
source:
  connector: fixture
  max_results: 10
rules:
  exclude: []
  must_have: []
  should_have: []
scoring:
  enabled: false
  minimum_score: 0
  weighted_rules: []
"""

_FIXTURE_DIR = Path("tests/fixtures/connector_responses")


@pytest.fixture
async def db_session() -> AsyncSession:
    """Real async DB session against the test PostgreSQL database."""
    settings = Settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    finally:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"test-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed",
        role="operator",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def test_connector(db_session: AsyncSession) -> Connector:
    connector = Connector(
        name=f"fixture-{uuid.uuid4().hex[:8]}",
        connector_type="fixture",
        enabled=True,
        config_snapshot={"fixture_dir": str(_FIXTURE_DIR)},
    )
    db_session.add(connector)
    await db_session.flush()
    return connector


@pytest.fixture
async def test_criteria_version(
    db_session: AsyncSession, test_user: User
) -> CriteriaVersion:
    cfg, errors = validate_criteria_yaml(_CRITERIA_YAML)
    assert not errors and cfg is not None

    group = CriteriaGroup(
        name="test-integration-criteria",
        display_name="Integration Test Criteria",
        description="Used in integration tests",
        is_active=True,
    )
    db_session.add(group)
    await db_session.flush()

    version = CriteriaVersion(
        group_id=group.id,
        version=1,
        config_snapshot=cfg.model_dump(),
        is_active=True,
        created_by=test_user.id,
    )
    db_session.add(version)
    await db_session.flush()
    return version


@pytest.fixture
async def test_job(
    db_session: AsyncSession,
    test_user: User,
    test_connector: Connector,
    test_criteria_version: CriteriaVersion,
) -> CrawlJob:
    job = CrawlJob(
        connector_id=test_connector.id,
        criteria_version_id=test_criteria_version.id,
        status="queued",
        config_snapshot={},
        created_by=test_user.id,
    )
    db_session.add(job)
    await db_session.flush()
    return job


@pytest.mark.asyncio
async def test_run_job_complete(
    db_session: AsyncSession,
    test_job: CrawlJob,
    test_criteria_version: CriteriaVersion,
) -> None:
    """Full pipeline: fixture connector → score → dedup → job completes."""
    from app.config.criteria import CriteriaConfig

    criteria = CriteriaConfig.model_validate(test_criteria_version.config_snapshot)
    connector = FixtureConnector(_FIXTURE_DIR)

    await run_job(
        test_job.id,
        db_session,
        connector=connector,
        criteria=criteria,
        fetcher=None,  # skip crawl step
    )

    # Job reached completed status
    await db_session.refresh(test_job)
    assert test_job.status == "completed"

    # RawSearchResult rows created (valid_results.json has 3 entries)
    rsr_result = await db_session.execute(
        select(RawSearchResult).where(RawSearchResult.job_id == test_job.id)
    )
    raw_results = list(rsr_result.scalars())
    assert len(raw_results) >= 3
    assert all(r.processed for r in raw_results)

    # BusinessRecord rows created
    br_result = await db_session.execute(
        select(BusinessRecord).where(BusinessRecord.job_id == test_job.id)
    )
    records = list(br_result.scalars())
    assert len(records) >= 3

    # Each record has a name
    names = {r.name for r in records}
    assert "Acme Roofing Co." in names
    assert "Summit Storm Repair" in names

    # RecordSource rows created for each record
    for record in records:
        src_result = await db_session.execute(
            select(RecordSource).where(RecordSource.record_id == record.id)
        )
        sources = list(src_result.scalars())
        assert len(sources) >= 1

    # CrawlJobEvents logged
    evt_result = await db_session.execute(
        select(CrawlJobEvent).where(CrawlJobEvent.job_id == test_job.id)
    )
    events = list(evt_result.scalars())
    event_types = {e.event_type for e in events}
    assert "job_started" in event_types
    assert "connector_complete" in event_types
    assert "job_complete" in event_types


@pytest.mark.asyncio
async def test_run_job_scoring_stored(
    db_session: AsyncSession,
    test_job: CrawlJob,
    test_criteria_version: CriteriaVersion,
) -> None:
    """Scoring result is stored on each BusinessRecord."""
    from app.config.criteria import CriteriaConfig

    criteria = CriteriaConfig.model_validate(test_criteria_version.config_snapshot)
    connector = FixtureConnector(_FIXTURE_DIR)

    await run_job(test_job.id, db_session, connector=connector, criteria=criteria)

    br_result = await db_session.execute(
        select(BusinessRecord).where(BusinessRecord.job_id == test_job.id)
    )
    records = list(br_result.scalars())
    for record in records:
        assert record.match_score is not None
        assert isinstance(record.rule_results, dict)
        assert "match_score" in record.rule_results
