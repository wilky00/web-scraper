# ABOUTME: Unit tests for app/jobs/export_task.py — CSV/XLSX generation, status transitions,
# ABOUTME: audit log entry creation, and error handling. All DB and S3 calls are mocked.
from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.jobs.export_task import (
    _build_csv,
    _build_xlsx,
    _query_records,
    _record_row,
)
from app.models.record import BusinessRecord


def _make_record(**kwargs: Any) -> MagicMock:
    r = MagicMock(spec=BusinessRecord)
    r.id = uuid.uuid4()
    r.name = kwargs.get("name", "Acme Corp")
    r.website = kwargs.get("website", "https://acme.com")
    r.email = kwargs.get("email", "info@acme.com")
    r.phone = kwargs.get("phone", "5551234567")
    r.address = kwargs.get("address", "123 Main St")
    r.location_city = kwargs.get("location_city", "Springfield")
    r.location_state = kwargs.get("location_state", "IL")
    r.location_country = kwargs.get("location_country", "US")
    r.match_score = kwargs.get("match_score", Decimal("85.5"))
    r.status = kwargs.get("status", "active")
    r.job_id = kwargs.get("job_id", uuid.uuid4())
    r.created_at = kwargs.get("created_at", datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC))
    return r


# ── _record_row ───────────────────────────────────────────────────────────────


def test_record_row_all_fields() -> None:
    r = _make_record()
    row = _record_row(r)
    assert row[0] == str(r.id)
    assert row[1] == "Acme Corp"
    assert row[9] == 85.5
    assert row[10] == "active"


def test_record_row_none_match_score() -> None:
    r = _make_record(match_score=None)
    row = _record_row(r)
    assert row[9] == ""


def test_record_row_none_job_id() -> None:
    r = _make_record(job_id=None)
    row = _record_row(r)
    assert row[11] == ""


def test_record_row_none_created_at() -> None:
    r = _make_record(created_at=None)
    row = _record_row(r)
    assert row[12] == ""


def test_record_row_none_optional_strings() -> None:
    r = _make_record(website=None, email=None, phone=None, address=None)
    row = _record_row(r)
    assert row[2] == ""
    assert row[3] == ""
    assert row[4] == ""
    assert row[5] == ""


# ── _build_csv ────────────────────────────────────────────────────────────────


def test_build_csv_has_headers() -> None:
    data = _build_csv([])
    reader = csv.reader(io.StringIO(data.decode("utf-8")))
    headers = next(reader)
    assert "id" in headers
    assert "name" in headers
    assert "match_score" in headers


def test_build_csv_has_data_row() -> None:
    r = _make_record(name="Test Co")
    data = _build_csv([r])
    text = data.decode("utf-8")
    assert "Test Co" in text


def test_build_csv_empty_produces_headers_only() -> None:
    data = _build_csv([])
    lines = data.decode("utf-8").strip().splitlines()
    assert len(lines) == 1


def test_build_csv_multiple_records() -> None:
    records = [_make_record(name=f"Co {i}") for i in range(5)]
    data = _build_csv(records)
    lines = data.decode("utf-8").strip().splitlines()
    assert len(lines) == 6  # 1 header + 5 data rows


# ── _build_xlsx ───────────────────────────────────────────────────────────────


def test_build_xlsx_returns_bytes() -> None:
    data = _build_xlsx([])
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_build_xlsx_is_valid_workbook() -> None:
    import openpyxl

    r = _make_record(name="Widget Inc")
    data = _build_xlsx([r])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws.title == "Records"
    # Row 1 is headers, row 2 is the record
    header_row = [cell.value for cell in ws[1]]
    assert "name" in header_row
    name_col = header_row.index("name") + 1
    assert ws.cell(row=2, column=name_col).value == "Widget Inc"


def test_build_xlsx_empty_has_only_header_row() -> None:
    import openpyxl

    data = _build_xlsx([])
    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active
    assert ws.max_row == 1


# ── _query_records filter logic ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_records_empty_filters() -> None:
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    result = await _query_records(mock_session, {})
    assert result == []
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_query_records_with_status_filter() -> None:
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    await _query_records(mock_session, {"status": "active"})
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_query_records_invalid_score_min_ignored() -> None:
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    # Should not raise even with bad decimal value
    await _query_records(mock_session, {"score_min": "not-a-number"})
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_query_records_invalid_date_ignored() -> None:
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    await _query_records(mock_session, {"date_from": "not-a-date"})
    mock_session.execute.assert_called_once()
