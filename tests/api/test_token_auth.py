# ABOUTME: Tests for API token management (generate/revoke) and Bearer-token-protected
# ABOUTME: GET endpoints: GET /api/records and GET /api/records/{id}.
from __future__ import annotations

import hashlib
import hmac
import uuid
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.records import _require_records_read
from app.auth.permissions import require_operator
from app.main import app
from app.models.connector import Connector
from app.models.record import BusinessRecord
from app.models.user import User
from app.settings import Settings

# Matches conftest.py os.environ.setdefault("API_TOKEN_SECRET", ...)
_TOKEN_SECRET = "test-api-token-secret-for-testing"


def _hash_token(token: str) -> str:
    return hmac.new(_TOKEN_SECRET.encode(), token.encode(), hashlib.sha256).hexdigest()


def _set_state(mock_redis: AsyncMock) -> None:
    app.state.engine = MagicMock()
    app.state.redis = mock_redis
    app.state.settings = Settings()


def _clear_state() -> None:
    for attr in ("engine", "redis", "settings"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


def _make_record(**kwargs: Any) -> MagicMock:
    r = MagicMock(spec=BusinessRecord)
    r.id = kwargs.get("id", uuid.uuid4())
    r.name = kwargs.get("name", "Acme Corp")
    r.website = kwargs.get("website", "https://acme.example.com")
    r.email = kwargs.get("email", "info@acme.example.com")
    r.phone = kwargs.get("phone", "5551234567")
    r.address = kwargs.get("address", "123 Main St")
    r.location_city = kwargs.get("location_city", "Springfield")
    r.location_state = kwargs.get("location_state", "IL")
    r.location_country = kwargs.get("location_country", "US")
    r.match_score = kwargs.get("match_score", Decimal("85.0"))
    r.status = kwargs.get("status", "active")
    r.job_id = kwargs.get("job_id", None)
    r.created_at = None
    r.rule_results = kwargs.get("rule_results", {})
    return r


def _make_api_db_mock(get_return: Any = None) -> AsyncMock:
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=get_return)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def _make_list_db_mock(records: list[MagicMock], total: int) -> AsyncMock:
    call_n: dict[str, int] = {"n": 0}

    count_result = MagicMock()
    count_result.scalar.return_value = total

    records_result = MagicMock()
    records_result.scalars.return_value.all.return_value = records

    async def _execute(*args: Any, **kwargs: Any) -> MagicMock:
        call_n["n"] += 1
        return count_result if call_n["n"] == 1 else records_result

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = _execute
    return session


def _make_detail_db_mock(record: MagicMock | None, sources: list[Any] | None = None) -> AsyncMock:
    sources_result = MagicMock()
    sources_result.scalars.return_value.all.return_value = sources or []

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=record)
    session.execute = AsyncMock(return_value=sources_result)
    return session


# ── Token generation (POST /api/auth/token) ───────────────────────────────────


@pytest.mark.asyncio
async def test_generate_token_success(mock_redis: AsyncMock) -> None:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    app.dependency_overrides[require_operator] = lambda: user
    _set_state(mock_redis)

    db_mock = _make_api_db_mock(get_return=MagicMock(spec=User))
    try:
        with patch("app.api.auth.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/api/auth/token", json={"scopes": ["records:read"]})
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 201
    body = resp.json()
    assert "token" in body
    assert body["scopes"] == ["records:read"]
    assert len(body["token"]) > 20


@pytest.mark.asyncio
async def test_generate_token_multiple_scopes(mock_redis: AsyncMock) -> None:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    app.dependency_overrides[require_operator] = lambda: user
    _set_state(mock_redis)

    db_mock = _make_api_db_mock(get_return=MagicMock(spec=User))
    try:
        with patch("app.api.auth.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/auth/token",
                    json={"scopes": ["records:read", "records:write"]},
                )
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 201
    assert set(resp.json()["scopes"]) == {"records:read", "records:write"}


@pytest.mark.asyncio
async def test_generate_token_empty_scopes(mock_redis: AsyncMock) -> None:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    app.dependency_overrides[require_operator] = lambda: user
    _set_state(mock_redis)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/auth/token", json={"scopes": []})
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_token_invalid_scope(mock_redis: AsyncMock) -> None:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    app.dependency_overrides[require_operator] = lambda: user
    _set_state(mock_redis)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/auth/token", json={"scopes": ["admin:all"]})
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 422
    assert "admin:all" in resp.json()["error"]


@pytest.mark.asyncio
async def test_generate_token_unauthenticated(mock_redis: AsyncMock) -> None:
    _set_state(mock_redis)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/auth/token",
                json={"scopes": ["records:read"]},
                follow_redirects=False,
            )
    finally:
        _clear_state()

    assert resp.status_code == 303


# ── Token revocation (DELETE /api/auth/token) ─────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_token_success(mock_redis: AsyncMock) -> None:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.api_key_hash = "somehash"
    app.dependency_overrides[require_operator] = lambda: user
    _set_state(mock_redis)

    db_mock = _make_api_db_mock(get_return=MagicMock(spec=User))
    try:
        with patch("app.api.auth.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete("/api/auth/token")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_revoke_token_none_exists(mock_redis: AsyncMock) -> None:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.api_key_hash = None
    app.dependency_overrides[require_operator] = lambda: user
    _set_state(mock_redis)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/auth/token")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_token_unauthenticated(mock_redis: AsyncMock) -> None:
    _set_state(mock_redis)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.delete("/api/auth/token", follow_redirects=False)
    finally:
        _clear_state()

    assert resp.status_code == 303


# ── GET /api/records (Bearer token auth) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_api_list_records_success(mock_redis: AsyncMock) -> None:
    records = [_make_record(name="Foo Inc"), _make_record(name="Bar LLC")]
    app.dependency_overrides[_require_records_read] = lambda: MagicMock(spec=User)
    _set_state(mock_redis)

    db_mock = _make_list_db_mock(records, total=2)
    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/records")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 2
    assert body["pagination"]["total"] == 2
    assert body["pagination"]["page"] == 1
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_api_list_records_empty(mock_redis: AsyncMock) -> None:
    app.dependency_overrides[_require_records_read] = lambda: MagicMock(spec=User)
    _set_state(mock_redis)

    db_mock = _make_list_db_mock([], total=0)
    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/records")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["pagination"]["total"] == 0


@pytest.mark.asyncio
async def test_api_list_records_missing_auth(mock_redis: AsyncMock) -> None:
    _set_state(mock_redis)
    # No Authorization header — checked before DB is hit
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/records")
    finally:
        _clear_state()

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_list_records_invalid_bearer_prefix(mock_redis: AsyncMock) -> None:
    _set_state(mock_redis)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/records", headers={"Authorization": "Token abc123"})
    finally:
        _clear_state()

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_list_records_invalid_token(mock_redis: AsyncMock) -> None:
    _set_state(mock_redis)

    # Token hash not found in DB → 401
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    auth_session = AsyncMock()
    auth_session.__aenter__ = AsyncMock(return_value=auth_session)
    auth_session.__aexit__ = AsyncMock(return_value=None)
    auth_session.execute = AsyncMock(return_value=mock_result)

    try:
        with patch("app.auth.permissions.AsyncSession", return_value=auth_session):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/records", headers={"Authorization": "Bearer invalidtoken"}
                )
    finally:
        _clear_state()

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_list_records_wrong_scope(mock_redis: AsyncMock) -> None:
    _set_state(mock_redis)

    # User has records:write but not records:read → 403
    user = MagicMock(spec=User)
    user.is_active = True
    user.deleted_at = None
    user.api_key_scopes = ["records:write"]

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    auth_session = AsyncMock()
    auth_session.__aenter__ = AsyncMock(return_value=auth_session)
    auth_session.__aexit__ = AsyncMock(return_value=None)
    auth_session.execute = AsyncMock(return_value=mock_result)

    try:
        with patch("app.auth.permissions.AsyncSession", return_value=auth_session):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/records", headers={"Authorization": "Bearer sometoken"}
                )
    finally:
        _clear_state()

    assert resp.status_code == 403


# ── GET /api/records/{id} (Bearer token auth) ─────────────────────────────────


@pytest.mark.asyncio
async def test_api_get_record_success(mock_redis: AsyncMock) -> None:
    record = _make_record(name="Acme Corp")
    app.dependency_overrides[_require_records_read] = lambda: MagicMock(spec=User)
    _set_state(mock_redis)

    db_mock = _make_detail_db_mock(record, sources=[])
    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/records/{record.id}")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["name"] == "Acme Corp"
    assert "sources" in body["data"]
    assert "rule_results" in body["data"]
    assert body["errors"] == []


@pytest.mark.asyncio
async def test_api_get_record_not_found(mock_redis: AsyncMock) -> None:
    app.dependency_overrides[_require_records_read] = lambda: MagicMock(spec=User)
    _set_state(mock_redis)

    db_mock = _make_api_db_mock(get_return=None)
    try:
        with patch("app.api.records.AsyncSession", return_value=db_mock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/api/records/{uuid.uuid4()}")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 404
    body = resp.json()
    assert body["data"] is None
    assert len(body["errors"]) > 0


@pytest.mark.asyncio
async def test_api_get_record_invalid_id(mock_redis: AsyncMock) -> None:
    app.dependency_overrides[_require_records_read] = lambda: MagicMock(spec=User)
    _set_state(mock_redis)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/records/not-a-uuid")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 422
    assert resp.json()["data"] is None


@pytest.mark.asyncio
async def test_api_get_record_unauthorized(mock_redis: AsyncMock) -> None:
    _set_state(mock_redis)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(f"/api/records/{uuid.uuid4()}")
    finally:
        _clear_state()

    assert resp.status_code == 401


# ── GET /api/connectors (session auth) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_list_connectors_success(mock_redis: AsyncMock) -> None:
    app.dependency_overrides[require_operator] = lambda: MagicMock(spec=User)
    _set_state(mock_redis)

    conn = MagicMock(spec=Connector)
    conn.id = uuid.uuid4()
    conn.name = "fixture"
    conn.connector_type = "fixture"
    conn.enabled = True

    conn_result = MagicMock()
    conn_result.scalars.return_value.all.return_value = [conn]
    conn_session = AsyncMock()
    conn_session.__aenter__ = AsyncMock(return_value=conn_session)
    conn_session.__aexit__ = AsyncMock(return_value=None)
    conn_session.execute = AsyncMock(return_value=conn_result)

    try:
        with patch("app.api.connectors.AsyncSession", return_value=conn_session):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/connectors")
    finally:
        app.dependency_overrides.clear()
        _clear_state()

    assert resp.status_code == 200
    body = resp.json()
    assert "connectors" in body
    assert body["connectors"][0]["name"] == "fixture"


@pytest.mark.asyncio
async def test_api_list_connectors_unauthenticated(mock_redis: AsyncMock) -> None:
    _set_state(mock_redis)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/connectors", follow_redirects=False)
    finally:
        _clear_state()

    assert resp.status_code == 303
