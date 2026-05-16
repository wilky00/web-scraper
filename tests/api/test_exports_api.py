# ABOUTME: API tests for export creation, status polling, and download proxy endpoints.
# ABOUTME: Overrides require_operator via dependency_overrides to isolate from auth.
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.exports import require_operator
from app.auth.session import SESSION_COOKIE, sign_session_id
from app.main import app
from app.models.audit import Export
from app.models.user import User
from app.settings import Settings

_SECRET = Settings().secret_key
_SESSION_CSRF = "test-csrf-exports"
_SESSION_ID = "test-session-id-exports"


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
def mock_redis_exports() -> AsyncMock:
    client: AsyncMock = AsyncMock()
    client.get = AsyncMock(
        return_value=json.dumps({"user_id": str(uuid.uuid4()), "csrf_token": _SESSION_CSRF})
    )
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def mock_engine_exports() -> MagicMock:
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
    mock_user: MagicMock, mock_engine_exports: MagicMock, mock_redis_exports: AsyncMock
) -> AsyncClient:
    app.dependency_overrides[require_operator] = lambda: mock_user
    app.state.engine = mock_engine_exports
    app.state.redis = mock_redis_exports
    app.state.settings = Settings()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    del app.state.engine
    del app.state.redis
    del app.state.settings


def _make_export(
    export_id: uuid.UUID | None = None,
    status: str = "pending",
    fmt: str = "csv",
    s3_key: str | None = None,
    row_count: int | None = None,
    error: str | None = None,
) -> MagicMock:
    e = MagicMock(spec=Export)
    e.id = export_id or uuid.uuid4()
    e.format = fmt
    e.status = status
    e.s3_key = s3_key
    e.row_count = row_count
    e.error = error
    e.created_at = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
    e.user_id = uuid.uuid4()
    e.filter_params = {}
    return e


# ---------------------------------------------------------------------------
# POST /api/exports — create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_export_redirects_to_exports_list(
    client: AsyncClient, signed_cookie: str
) -> None:
    with (
        patch("app.api.exports.AsyncSession") as mock_session_cls,
        patch("app.api.exports.asyncio.to_thread", new=AsyncMock()),
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        export_obj = _make_export()
        mock_session.get = AsyncMock(return_value=export_obj)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()

        def session_factory(*args, **kwargs):
            return mock_session

        mock_session_cls.side_effect = session_factory

        resp = await client.post(
            "/api/exports",
            data={"csrf_token": _SESSION_CSRF, "format": "csv"},
            cookies={SESSION_COOKIE: signed_cookie},
            follow_redirects=False,
        )

    assert resp.status_code == 201
    assert resp.headers.get("hx-redirect") == "/exports"


@pytest.mark.asyncio
async def test_create_export_invalid_format_returns_422(
    client: AsyncClient, signed_cookie: str
) -> None:
    resp = await client.post(
        "/api/exports",
        data={"csrf_token": _SESSION_CSRF, "format": "pdf"},
        cookies={SESSION_COOKIE: signed_cookie},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_export_missing_csrf_returns_403(
    client: AsyncClient, signed_cookie: str
) -> None:
    resp = await client.post(
        "/api/exports",
        data={"format": "csv"},
        cookies={SESSION_COOKIE: signed_cookie},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_export_unauthenticated_redirects(signed_cookie: str) -> None:
    app_without_override = app
    async with AsyncClient(
        transport=ASGITransport(app=app_without_override), base_url="http://test"
    ) as ac:
        resp = await ac.post(
            "/api/exports",
            data={"csrf_token": _SESSION_CSRF, "format": "csv"},
            follow_redirects=False,
        )
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# GET /api/exports/{id} — status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_export_status_returns_json(client: AsyncClient) -> None:
    export_id = uuid.uuid4()
    export = _make_export(export_id=export_id, status="ready", fmt="csv", row_count=10)

    with patch("app.api.exports.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = AsyncMock(return_value=export)
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get(f"/api/exports/{export_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["format"] == "csv"
    assert data["row_count"] == 10


@pytest.mark.asyncio
async def test_get_export_status_not_found(client: AsyncClient) -> None:
    with patch("app.api.exports.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = AsyncMock(return_value=None)
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get(f"/api/exports/{uuid.uuid4()}")

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_export_status_invalid_id(client: AsyncClient) -> None:
    resp = await client.get("/api/exports/not-a-uuid")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /exports/{id}/download — proxy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_export_streams_file(client: AsyncClient) -> None:
    export_id = uuid.uuid4()
    export = _make_export(
        export_id=export_id,
        status="ready",
        fmt="csv",
        s3_key=f"exports/{export_id}.csv",
    )

    with (
        patch("app.web.exports.AsyncSession") as mock_session_cls,
        patch("app.web.exports.asyncio.to_thread", new=AsyncMock(return_value=b"id,name\n1,Acme")),
    ):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = AsyncMock(return_value=export)
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get(f"/exports/{export_id}/download")

    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert b"Acme" in resp.content


@pytest.mark.asyncio
async def test_download_export_not_ready_returns_404(client: AsyncClient) -> None:
    export_id = uuid.uuid4()
    export = _make_export(export_id=export_id, status="pending")

    with patch("app.web.exports.AsyncSession") as mock_session_cls:
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get = AsyncMock(return_value=export)
        mock_session_cls.side_effect = lambda *a, **kw: mock_session

        resp = await client.get(f"/exports/{export_id}/download")

    assert resp.status_code == 404
