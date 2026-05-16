# ABOUTME: Integration tests for job pause and cancel controls against a real PostgreSQL DB.
# ABOUTME: Monkeypatches session.refresh() to simulate external status changes mid-job.
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

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
from app.models.record import BusinessRecord
from app.models.user import User
from app.settings import Settings

_CRITERIA_YAML = """
metadata:
  name: test-controls-criteria
  display_name: Controls Test Criteria
  description: Used in job controls integration tests
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
async def test_criteria_version(db_session: AsyncSession, test_user: User) -> CriteriaVersion:
    cfg, errors = validate_criteria_yaml(_CRITERIA_YAML)
    assert not errors and cfg is not None
    group = CriteriaGroup(
        name="test-controls-criteria",
        display_name="Controls Test Criteria",
        description="Used in job controls integration tests",
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


def _make_cancel_after_n_commits(
    original_commit: Any, original_refresh: Any, job: CrawlJob, n: int, target_status: str
) -> tuple[Any, Any]:
    """Return patched commit/refresh that sets job.status after n commits."""
    commit_count = [0]

    async def patched_commit() -> None:
        commit_count[0] += 1
        await original_commit()

    async def patched_refresh(obj: object, **kwargs: object) -> None:
        await original_refresh(obj, **kwargs)  # type: ignore[arg-type]
        if isinstance(obj, CrawlJob) and obj.id == job.id and commit_count[0] >= n:
            obj.status = target_status

    return patched_commit, patched_refresh


@pytest.mark.asyncio
async def test_run_job_cancel_preserves_stored_records(
    db_session: AsyncSession,
    test_job: CrawlJob,
    test_criteria_version: CriteriaVersion,
) -> None:
    """Cancel stops the job; records stored before cancel remain intact."""
    from app.config.criteria import CriteriaConfig

    criteria = CriteriaConfig.model_validate(test_criteria_version.config_snapshot)
    connector = FixtureConnector(_FIXTURE_DIR)

    # Trigger cancel after commit #3 (job_started + record1 + record2)
    original_commit = db_session.commit
    original_refresh = db_session.refresh
    patched_commit, patched_refresh = _make_cancel_after_n_commits(
        original_commit, original_refresh, test_job, n=3, target_status="cancel_requested"
    )
    db_session.commit = patched_commit  # type: ignore[method-assign]
    db_session.refresh = patched_refresh  # type: ignore[method-assign]

    await run_job(test_job.id, db_session, connector=connector, criteria=criteria, fetcher=None)

    db_session.commit = original_commit  # type: ignore[method-assign]
    db_session.refresh = original_refresh  # type: ignore[method-assign]

    await db_session.refresh(test_job)
    assert test_job.status == "cancelled"

    br_result = await db_session.execute(
        select(BusinessRecord).where(BusinessRecord.job_id == test_job.id)
    )
    records = list(br_result.scalars())
    assert len(records) == 2
    assert all(r.status == "active" for r in records)

    evt_result = await db_session.execute(
        select(CrawlJobEvent).where(
            CrawlJobEvent.job_id == test_job.id,
            CrawlJobEvent.event_type == "job_cancelled",
        )
    )
    assert len(list(evt_result.scalars())) == 1


@pytest.mark.asyncio
async def test_run_job_pause_preserves_stored_records(
    db_session: AsyncSession,
    test_job: CrawlJob,
    test_criteria_version: CriteriaVersion,
) -> None:
    """Pause stops the job gracefully; records stored before pause remain intact."""
    from app.config.criteria import CriteriaConfig

    criteria = CriteriaConfig.model_validate(test_criteria_version.config_snapshot)
    connector = FixtureConnector(_FIXTURE_DIR)

    original_commit = db_session.commit
    original_refresh = db_session.refresh
    patched_commit, patched_refresh = _make_cancel_after_n_commits(
        original_commit, original_refresh, test_job, n=3, target_status="paused"
    )
    db_session.commit = patched_commit  # type: ignore[method-assign]
    db_session.refresh = patched_refresh  # type: ignore[method-assign]

    await run_job(test_job.id, db_session, connector=connector, criteria=criteria, fetcher=None)

    db_session.commit = original_commit  # type: ignore[method-assign]
    db_session.refresh = original_refresh  # type: ignore[method-assign]

    await db_session.refresh(test_job)
    assert test_job.status == "paused"

    br_result = await db_session.execute(
        select(BusinessRecord).where(BusinessRecord.job_id == test_job.id)
    )
    records = list(br_result.scalars())
    assert len(records) == 2
    assert all(r.status == "active" for r in records)

    evt_result = await db_session.execute(
        select(CrawlJobEvent).where(
            CrawlJobEvent.job_id == test_job.id,
            CrawlJobEvent.event_type == "job_paused",
        )
    )
    assert len(list(evt_result.scalars())) == 1
