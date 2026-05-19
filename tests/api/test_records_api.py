# ABOUTME: API + web integration tests for records management endpoints.
# ABOUTME: Overrides require_operator via dependency_overrides to isolate records logic from auth.
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, sign_session_id
from app.main import app
from app.models.record import BusinessRecord
from app.models.user import User
from app.settings import Settings

_SECRET = Settings().secret_key
_SESSION_CSRF = "test-csrf-for-records"
_SESSION_ID = "test-session-id-records"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "operator@test.com"
    user.role = "operator"
    user.is_active = True
    user.deleted_at = None
    return user


@pytest.fixture
def mock_redis_records() -> AsyncMock:
    client: AsyncMock = AsyncMock()
    client.get = AsyncMock(
        return_value=json.dumps({"user_id": str(uuid.uuid4()), "csrf_token": _SESSION_CSRF})
    )
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def signed_session() -> str:
    return sign_session_id(_SESSION_ID, _SECRET)


def _make_mock_record(**kwargs: object) -> MagicMock:
    r = MagicMock(spec=BusinessRecord)
    r.id = kwargs.get("id", uuid.uuid4())
    r.name = kwargs.get("name", "Test Business")
    r.website = kwargs.get("website", "https://example.com")
    r.email = kwargs.get("email", "test@example.com")
    r.phone = kwargs.get("phone", "5551234567")
    r.address = kwargs.get("address", "123 Main St")
    r.location_city = kwargs.get("location_city", "Testville")
    r.location_state = kwargs.get("location_state", "FL")
    r.location_country = kwargs.get("location_country", "US")
    r.match_score = kwargs.get("match_score", Decimal("85.50"))
    r.status = kwargs.get("status", "active")
    r.job_id = kwargs.get("job_id", None)
    r.rule_results = kwargs.get("rule_results", {})
    r.created_at = kwargs.get("created_at", datetime(2026, 5, 16, 10, 0, 0, tzinfo=UTC))
    return r


def _make_list_db_mock(records: list[MagicMock], total: int | None = None) -> AsyncMock:
    """Two execute calls: count query then records query."""
    call_n = {"n": 0}

    count_result = MagicMock()
    count_result.scalar.return_value = total if total is not None else len(records)

    records_result = MagicMock()
    records_result.scalars.return_value.all.return_value = records

    async def _execute(*args: object, **kwargs: object) -> MagicMock:
        call_n["n"] += 1
        return count_result if call_n["n"] == 1 else records_result

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = _execute
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_detail_db_mock(
    record: MagicMock | None,
    sources: list[MagicMock] | None = None,
) -> AsyncMock:
    """get() returns record; execute() returns sources."""
    sources_result = MagicMock()
    sources_result.scalars.return_value.all.return_value = sources or []

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=record)
    session.execute = AsyncMock(return_value=sources_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_api_db_mock(record: MagicMock | None = None) -> AsyncMock:
    """get() returns record; supports add/flush/commit."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=record)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _set_state(mock_redis: AsyncMock) -> None:
    app.state.engine = MagicMock()
    app.state.redis = mock_redis
    app.state.settings = Settings()


def _clear_state() -> None:
    for attr in ("engine", "redis", "settings"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# GET /records  (list page)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_records_list_renders_empty(
    mock_user: MagicMock, mock_redis_records: AsyncMock
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_list_db_mock([])

    try:
        with patch("app.web.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/records")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "Records" in resp.text
    assert "No records found" in resp.text


@pytest.mark.asyncio
async def test_records_list_renders_records(
    mock_user: MagicMock, mock_redis_records: AsyncMock
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    record = _make_mock_record()
    db_mock = _make_list_db_mock([record])

    try:
        with patch("app.web.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/records")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "Test Business" in resp.text
    assert "active" in resp.text


@pytest.mark.asyncio
async def test_records_list_requires_auth(mock_redis_records: AsyncMock) -> None:
    _set_state(mock_redis_records)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as c:
            resp = await c.get("/records")
    finally:
        _clear_state()

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_records_list_filter_by_status(
    mock_user: MagicMock, mock_redis_records: AsyncMock
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_list_db_mock([])

    try:
        with patch("app.web.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get("/records?status=active&q=test")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    # Filter values should be reflected in the form
    assert 'value="test"' in resp.text
    assert "selected" in resp.text


# ---------------------------------------------------------------------------
# GET /records/{id}  (detail page)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_detail_renders(mock_user: MagicMock, mock_redis_records: AsyncMock) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    record = _make_mock_record()
    db_mock = _make_detail_db_mock(record)

    try:
        with patch("app.web.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/records/{record.id}")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "Test Business" in resp.text
    assert "Record Fields" in resp.text
    assert "Edit" in resp.text


@pytest.mark.asyncio
async def test_record_detail_not_found(mock_user: MagicMock, mock_redis_records: AsyncMock) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_detail_db_mock(None)

    try:
        with patch("app.web.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/records/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /records/{id}/edit  (edit partial)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_edit_partial_renders(
    mock_user: MagicMock, mock_redis_records: AsyncMock
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    record = _make_mock_record()
    db_mock = _make_api_db_mock(record)

    try:
        with patch("app.web.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.get(f"/records/{record.id}/edit")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "fetch(" in resp.text  # Alpine.js fetch replaces hx-post
    assert "Save" in resp.text
    assert "Test Business" in resp.text


# ---------------------------------------------------------------------------
# POST /api/records  (create)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_record_success(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_api_db_mock()

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    "/api/records",
                    data={"name": "New Business", "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 201
    assert "HX-Redirect" in resp.headers
    assert "/records/" in resp.headers["HX-Redirect"]


@pytest.mark.asyncio
async def test_create_record_missing_name_returns_422(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_api_db_mock()

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/records",
                    data={"name": "   ", "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 422
    assert "Name is required" in resp.text


@pytest.mark.asyncio
async def test_create_record_csrf_failure_returns_403(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_api_db_mock()

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/api/records",
                    data={"name": "Test", "csrf_token": "wrong-token"},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/records/{id}  (update)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_record_success(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    record = _make_mock_record()
    db_mock = _make_api_db_mock(record)

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    f"/api/records/{record.id}",
                    data={
                        "name": "Updated Name",
                        "status": "active",
                        "csrf_token": _SESSION_CSRF,
                    },
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert "HX-Redirect" in resp.headers
    assert str(record.id) in resp.headers["HX-Redirect"]


@pytest.mark.asyncio
async def test_update_record_not_found(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_api_db_mock(None)

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/records/{uuid.uuid4()}",
                    data={"name": "X", "status": "active", "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_record_invalid_status_returns_422(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    record = _make_mock_record()
    db_mock = _make_api_db_mock(record)

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/records/{record.id}",
                    data={"name": "X", "status": "bad_status", "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/records/{id}/delete  (soft delete)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_record_success(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    record = _make_mock_record(status="active")
    db_mock = _make_api_db_mock(record)

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    f"/api/records/{record.id}/delete",
                    data={"csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert resp.headers.get("HX-Redirect") == "/records"


@pytest.mark.asyncio
async def test_delete_already_deleted_returns_409(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    record = _make_mock_record(status="deleted")
    db_mock = _make_api_db_mock(record)

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/records/{record.id}/delete",
                    data={"csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 409
    assert "already deleted" in resp.text


@pytest.mark.asyncio
async def test_delete_record_not_found(
    mock_user: MagicMock, mock_redis_records: AsyncMock, signed_session: str
) -> None:
    _set_state(mock_redis_records)
    app.dependency_overrides[require_operator] = lambda: mock_user
    db_mock = _make_api_db_mock(None)

    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/api/records/{uuid.uuid4()}/delete",
                    data={"csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_session},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 404
