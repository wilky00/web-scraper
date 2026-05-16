# ABOUTME: Tests for the GET /audit-log page — auth enforcement, filter params, and pagination.
# ABOUTME: Uses dependency_overrides to bypass auth and mocked DB sessions.
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.session import sign_session_id
from app.main import app
from app.models.audit import RecordAuditLog
from app.models.user import User
from app.settings import Settings
from app.web.audit import require_operator

_SECRET = Settings().secret_key
_SESSION_CSRF = "test-csrf-audit"
_SESSION_ID = "test-session-id-audit"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user() -> MagicMock:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.email = "operator@test.com"
    u.role = "operator"
    u.is_active = True
    u.deleted_at = None
    return u


@pytest.fixture
def mock_redis_audit() -> AsyncMock:
    client: AsyncMock = AsyncMock()
    client.get = AsyncMock(
        return_value=json.dumps({"user_id": str(uuid.uuid4()), "csrf_token": _SESSION_CSRF})
    )
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def mock_engine_audit() -> MagicMock:
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


@pytest.fixture
def signed_cookie() -> str:
    return sign_session_id(_SESSION_ID, _SECRET)


@pytest.fixture
async def client(
    mock_user: MagicMock, mock_engine_audit: MagicMock, mock_redis_audit: AsyncMock
) -> AsyncClient:
    app.dependency_overrides[require_operator] = lambda: mock_user
    app.state.engine = mock_engine_audit
    app.state.redis = mock_redis_audit
    app.state.settings = Settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    del app.state.engine
    del app.state.redis
    del app.state.settings


def _make_entry(
    action: str = "create",
    resource_type: str = "record",
    resource_id: str | None = None,
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    e = MagicMock(spec=RecordAuditLog)
    e.id = uuid.uuid4()
    e.action = action
    e.resource_type = resource_type
    e.resource_id = resource_id or str(uuid.uuid4())
    e.user_id = user_id
    e.created_at = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
    e.diff = {}
    return e


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_returns_200_authenticated(client: AsyncClient) -> None:
    with patch("app.web.audit.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        count_result = MagicMock()
        count_result.scalars.return_value.all.return_value = []
        page_result = MagicMock()
        page_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, page_result])
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get("/audit-log")

    assert resp.status_code == 200
    assert "Audit Log" in resp.text


@pytest.mark.asyncio
async def test_audit_log_unauthenticated_redirects() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/audit-log", follow_redirects=False)
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Filter by action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_filter_by_action(client: AsyncClient) -> None:
    entry = _make_entry(action="export")

    with patch("app.web.audit.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        count_result = MagicMock()
        count_result.scalars.return_value.all.return_value = [entry.id]
        page_result = MagicMock()
        page_result.scalars.return_value.all.return_value = [entry]
        # third call for user email resolution — no users
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, page_result, empty_result])
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get("/audit-log?action=export")

    assert resp.status_code == 200
    assert "export" in resp.text


# ---------------------------------------------------------------------------
# Filter by date range
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_filter_by_date_from(client: AsyncClient) -> None:
    with patch("app.web.audit.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=empty)
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get("/audit-log?date_from=2026-01-01")

    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_audit_log_filter_invalid_date_ignored(client: AsyncClient) -> None:
    with patch("app.web.audit.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=empty)
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        # Should not raise even with garbage date
        resp = await client.get("/audit-log?date_from=not-a-date")

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_log_pagination_page_2(client: AsyncClient) -> None:
    with patch("app.web.audit.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        # Return 75 ids in count (forces 2 pages at 50/page)
        count_result = MagicMock()
        count_result.scalars.return_value.all.return_value = [uuid.uuid4() for _ in range(75)]
        page_result = MagicMock()
        page_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(side_effect=[count_result, page_result])
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get("/audit-log?page=2")

    assert resp.status_code == 200
    assert "Page 2 of 2" in resp.text


@pytest.mark.asyncio
async def test_audit_log_shows_entry_count(client: AsyncClient) -> None:
    with patch("app.web.audit.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        count_result = MagicMock()
        count_result.scalars.return_value.all.return_value = [uuid.uuid4() for _ in range(3)]
        page_result = MagicMock()
        page_result.scalars.return_value.all.return_value = [_make_entry() for _ in range(3)]
        mock_session.execute = AsyncMock(side_effect=[count_result, page_result])
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get("/audit-log")

    assert resp.status_code == 200
    assert "3 entries" in resp.text
