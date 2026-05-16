# ABOUTME: Unit tests for the job orchestrator — verifies pipeline logic with mocked session.
# ABOUTME: No real DB or network required; covers run_job(), helper functions, and dedup.
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.criteria import CriteriaConfig
from app.connectors.base import ConnectorBase, ConnectorResult
from app.extraction.models import ExtractedField, ExtractionResult
from app.jobs.orchestrator import (
    _add_sources,
    _build_metrics,
    _build_record,
    _orm_to_record_data,
    run_job,
)
from app.models.job import CrawlJob
from app.models.record import BusinessRecord, RecordSource

# ── Fixtures ──────────────────────────────────────────────────────────────────

_MINIMAL_CRITERIA_YAML = """
metadata:
  name: test-criteria
  display_name: Test Criteria
  description: For unit testing
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


def _minimal_criteria() -> CriteriaConfig:
    from app.config.criteria import validate_criteria_yaml

    cfg, errors = validate_criteria_yaml(_MINIMAL_CRITERIA_YAML)
    assert not errors
    assert cfg is not None
    return cfg


def _make_job(job_id: uuid.UUID) -> CrawlJob:
    job = CrawlJob()
    job.id = job_id
    job.status = "queued"
    job.config_snapshot = {}
    job.connector_id = uuid.uuid4()
    job.criteria_version_id = uuid.uuid4()
    return job


class _FakeConnector(ConnectorBase):
    connector_type = "fixture"

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self._results = results

    def extract_fields(self, raw_data: dict[str, Any]) -> dict[str, str | None]:
        return {
            "name": raw_data.get("name"),
            "website": raw_data.get("website"),
            "email": raw_data.get("email"),
            "phone": raw_data.get("phone"),
            "address": raw_data.get("address"),
            "location_city": raw_data.get("location_city"),
            "location_state": raw_data.get("location_state"),
        }

    async def discover(self, job_config: dict[str, Any]) -> AsyncIterator[ConnectorResult]:
        for r in self._results:
            yield ConnectorResult(connector_type=self.connector_type, raw_data=r)


def _make_session(job: CrawlJob | None = None) -> AsyncMock:
    session = AsyncMock()
    session.get = AsyncMock(return_value=job)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    # execute() returns an object with scalars() that returns an iterable
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value = iter([])
    session.execute = AsyncMock(return_value=mock_execute_result)
    return session


# ── _build_record tests ───────────────────────────────────────────────────────


def test_build_record_connector_only() -> None:
    job_id = uuid.uuid4()
    fields: dict[str, str | None] = {
        "name": "Acme Co",
        "website": "https://acme.com",
        "email": "info@acme.com",
        "phone": "5125550101",
        "address": "123 Main St",
        "location_city": "Austin",
        "location_state": "TX",
    }
    record = _build_record(job_id, fields, None)
    assert record.name == "Acme Co"
    assert record.website == "https://acme.com"
    assert record.email == "info@acme.com"
    assert record.phone == "5125550101"
    assert record.location_city == "Austin"
    assert record.location_state == "TX"
    assert record.status == "active"


def test_build_record_extraction_overrides_connector() -> None:
    job_id = uuid.uuid4()
    fields: dict[str, str | None] = {
        "name": "Old Name",
        "email": "old@example.com",
        "website": None,
        "phone": None,
        "address": None,
        "location_city": "Austin",
        "location_state": "TX",
    }
    extraction = ExtractionResult(
        name=ExtractedField(
            value="New Name From HTML",
            source_url="https://x.com",
            source_type="og_tag",
            raw_value="New Name From HTML",
        ),
        emails=[
            ExtractedField(
                value="new@example.com",
                source_url="https://x.com",
                source_type="mailto_link",
                raw_value="new@example.com",
            )
        ],
    )
    record = _build_record(job_id, fields, extraction)
    assert record.name == "New Name From HTML"
    assert record.email == "new@example.com"
    assert record.location_city == "Austin"  # comes from connector only


# ── _build_metrics tests ──────────────────────────────────────────────────────


def test_build_metrics_connector_only() -> None:
    fields: dict[str, str | None] = {
        "name": "Acme",
        "email": "info@acme.com",
        "phone": "5125550101",
        "address": "123 Main",
        "website": "https://acme.com",
    }
    m = _build_metrics(None, fields, None, "fixture")
    assert m["extraction.name"] == "Acme"
    assert m["extraction.email"] == "info@acme.com"
    assert m["source.connector_type"] == "fixture"
    assert "crawl.status_code" not in m


def test_build_metrics_extraction_overrides_connector() -> None:
    fields: dict[str, str | None] = {"name": "Old Name", "email": "old@example.com"}
    extraction = ExtractionResult(
        name=ExtractedField(
            value="New Name", source_url="x", source_type="json_ld", raw_value="New Name"
        ),
        emails=[
            ExtractedField(
                value="new@example.com",
                source_url="x",
                source_type="mailto_link",
                raw_value="new@example.com",
            )
        ],
    )
    m = _build_metrics(extraction, fields, None, "fixture")
    assert m["extraction.name"] == "New Name"
    assert m["extraction.email"] == "new@example.com"


def test_build_metrics_fetch_result_adds_crawl_keys() -> None:
    from app.worker.fetcher import FetchResult

    fetch = FetchResult(
        url="https://a.com",
        canonical_url="https://a.com",
        status_code=200,
        html="",
        content_type="text/html",
        depth=0,
    )
    m = _build_metrics(None, {}, fetch, "fixture")
    assert m["crawl.status_code"] == 200
    assert m["crawl.depth"] == 0


# ── _add_sources tests ────────────────────────────────────────────────────────


def test_add_sources_connector_only(tmp_path: Any) -> None:
    session = MagicMock()
    session.add = MagicMock()
    record = BusinessRecord(job_id=uuid.uuid4())
    record.id = uuid.uuid4()
    fields: dict[str, str | None] = {
        "name": "Acme",
        "website": "https://acme.com",
        "email": None,
        "phone": None,
        "address": None,
        "location_city": None,
        "location_state": None,
    }
    _add_sources(session, record, fields, None, "fixture")
    added = [call.args[0] for call in session.add.call_args_list]
    assert len(added) == 2  # name + website only (others are None)
    assert all(isinstance(a, RecordSource) for a in added)
    assert all(a.source_type == "connector" for a in added)


def test_add_sources_extraction_sources_added() -> None:
    session = MagicMock()
    session.add = MagicMock()
    record = BusinessRecord(job_id=uuid.uuid4())
    record.id = uuid.uuid4()
    extraction = ExtractionResult(
        emails=[
            ExtractedField(
                value="a@b.com",
                source_url="https://x.com",
                source_type="mailto_link",
                raw_value="a@b.com",
            )
        ],
    )
    _add_sources(session, record, {}, extraction, "fixture")
    added = [call.args[0] for call in session.add.call_args_list]
    email_sources = [a for a in added if a.field == "email"]
    assert len(email_sources) == 1
    assert email_sources[0].source_type == "mailto_link"


# ── _orm_to_record_data tests ─────────────────────────────────────────────────


def test_orm_to_record_data() -> None:
    rec = BusinessRecord()
    rec.id = uuid.uuid4()
    rec.name = "Test Co"
    rec.website = "https://test.com"
    rec.email = "t@t.com"
    rec.phone = "5125550101"
    rec.location_city = "Austin"
    rec.location_state = "TX"
    rec.status = "active"
    rec.canonical_record_id = None
    rd = _orm_to_record_data(rec)
    assert rd.id == rec.id
    assert rd.name == "Test Co"
    assert rd.status == "active"


# ── run_job tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_job_happy_path_no_fetcher() -> None:
    """run_job with one connector result and no fetcher completes successfully."""
    job_id = uuid.uuid4()
    job = _make_job(job_id)
    session = _make_session(job)

    connector = _FakeConnector(
        [{"name": "Acme", "website": "https://acme.com", "email": "info@acme.com"}]
    )
    criteria = _minimal_criteria()

    # Capture all adds
    added: list[Any] = []
    session.add.side_effect = lambda obj: added.append(obj)

    # Patch flush to set IDs on BusinessRecord (simulate DB auto-id)
    async def fake_flush() -> None:
        for obj in added:
            if isinstance(obj, (BusinessRecord, RecordSource)) and not hasattr(obj, "id"):
                obj.id = uuid.uuid4()
            elif isinstance(obj, BusinessRecord) and obj.id is None:
                obj.id = uuid.uuid4()

    session.flush.side_effect = fake_flush

    await run_job(job_id, session, connector=connector, criteria=criteria)

    assert job.status == "completed"
    business_records = [a for a in added if isinstance(a, BusinessRecord)]
    assert len(business_records) == 1
    assert business_records[0].name == "Acme"
    assert session.commit.called


@pytest.mark.asyncio
async def test_run_job_job_not_found() -> None:
    """run_job returns early without error if job does not exist."""
    session = _make_session(None)
    connector = _FakeConnector([])
    criteria = _minimal_criteria()
    # Should not raise
    await run_job(uuid.uuid4(), session, connector=connector, criteria=criteria)
    assert not session.commit.called


@pytest.mark.asyncio
async def test_run_job_connector_error_marks_failed() -> None:
    """run_job transitions job to 'failed' if connector.discover() raises."""
    job_id = uuid.uuid4()
    job = _make_job(job_id)
    session = _make_session(job)

    class _ErrorConnector(ConnectorBase):
        connector_type = "fixture"

        async def discover(self, job_config: dict[str, Any]) -> AsyncIterator[ConnectorResult]:
            raise RuntimeError("connector exploded")
            yield  # pragma: no cover

    criteria = _minimal_criteria()
    with pytest.raises(RuntimeError, match="connector exploded"):
        await run_job(job_id, session, connector=_ErrorConnector(), criteria=criteria)

    assert job.status == "failed"


@pytest.mark.asyncio
async def test_run_job_multiple_records_stored() -> None:
    """run_job stores one BusinessRecord per connector result."""
    job_id = uuid.uuid4()
    job = _make_job(job_id)
    session = _make_session(job)

    connector = _FakeConnector(
        [
            {"name": "Alpha", "website": "https://alpha.com"},
            {"name": "Beta", "website": "https://beta.com"},
            {"name": "Gamma", "website": "https://gamma.com"},
        ]
    )
    criteria = _minimal_criteria()

    added: list[Any] = []
    session.add.side_effect = lambda obj: added.append(obj)

    async def fake_flush() -> None:
        for obj in added:
            if isinstance(obj, BusinessRecord) and obj.id is None:
                obj.id = uuid.uuid4()

    session.flush.side_effect = fake_flush

    await run_job(job_id, session, connector=connector, criteria=criteria)

    business_records = [a for a in added if isinstance(a, BusinessRecord)]
    assert len(business_records) == 3
    names = {r.name for r in business_records}
    assert names == {"Alpha", "Beta", "Gamma"}


@pytest.mark.asyncio
async def test_run_job_cancel_requested_transitions_to_cancelled() -> None:
    """run_job transitions to 'cancelled' when cancel_requested is detected after a record."""
    job_id = uuid.uuid4()
    job = _make_job(job_id)
    session = _make_session(job)

    connector = _FakeConnector(
        [
            {"name": "Alpha", "website": "https://alpha.com"},
            {"name": "Beta", "website": "https://beta.com"},
        ]
    )
    criteria = _minimal_criteria()

    added: list[Any] = []
    session.add.side_effect = lambda obj: added.append(obj)

    async def fake_flush() -> None:
        for obj in added:
            if isinstance(obj, BusinessRecord) and obj.id is None:
                obj.id = uuid.uuid4()

    session.flush.side_effect = fake_flush

    # Simulate: first refresh after a record commit sees cancel_requested
    refresh_count = [0]

    async def fake_refresh(obj: Any) -> None:
        refresh_count[0] += 1
        if isinstance(obj, type(job)) and refresh_count[0] >= 1:
            obj.status = "cancel_requested"

    session.refresh = AsyncMock(side_effect=fake_refresh)

    await run_job(job_id, session, connector=connector, criteria=criteria)

    assert job.status == "cancelled"
    # Only the first record should be stored (cancel fires after first refresh)
    business_records = [a for a in added if isinstance(a, BusinessRecord)]
    assert len(business_records) == 1
    assert business_records[0].name == "Alpha"


@pytest.mark.asyncio
async def test_run_job_paused_stops_gracefully() -> None:
    """run_job exits gracefully and leaves status as 'paused' when paused externally."""
    job_id = uuid.uuid4()
    job = _make_job(job_id)
    session = _make_session(job)

    connector = _FakeConnector(
        [
            {"name": "Alpha", "website": "https://alpha.com"},
            {"name": "Beta", "website": "https://beta.com"},
        ]
    )
    criteria = _minimal_criteria()

    added: list[Any] = []
    session.add.side_effect = lambda obj: added.append(obj)

    async def fake_flush() -> None:
        for obj in added:
            if isinstance(obj, BusinessRecord) and obj.id is None:
                obj.id = uuid.uuid4()

    session.flush.side_effect = fake_flush

    refresh_count = [0]

    async def fake_refresh(obj: Any) -> None:
        refresh_count[0] += 1
        if isinstance(obj, type(job)) and refresh_count[0] >= 1:
            obj.status = "paused"

    session.refresh = AsyncMock(side_effect=fake_refresh)

    await run_job(job_id, session, connector=connector, criteria=criteria)

    assert job.status == "paused"
    business_records = [a for a in added if isinstance(a, BusinessRecord)]
    assert len(business_records) == 1  # Only one record before pause
    assert business_records[0].name == "Alpha"
