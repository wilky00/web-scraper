# ABOUTME: API integration tests for /login, /auth/login, /auth/logout, and auth redirect.
# ABOUTME: Uses mock DB session and mock Redis — no real services required.
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.csrf import generate_form_csrf
from app.auth.hashing import hash_password
from app.auth.session import SESSION_COOKIE, sign_session_id
from app.main import app
from app.models.user import User
from app.settings import Settings

_SECRET = Settings().secret_key
_EMAIL = "admin@test.com"
_PASSWORD = "testpassword123"


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = _EMAIL
    user.hashed_password = hash_password(_PASSWORD)
    user.role = "operator"
    user.is_active = True
    user.deleted_at = None
    return user


@pytest.fixture
def mock_redis_auth() -> AsyncMock:
    client: AsyncMock = AsyncMock()
    client.incr = AsyncMock(return_value=1)
    client.expire = AsyncMock(return_value=True)
    client.set = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.delete = AsyncMock(return_value=1)
    return client


def _make_db_mock(user: MagicMock | None) -> AsyncMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = user

    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock(return_value=result)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _set_state(mock_redis: AsyncMock) -> MagicMock:
    engine = MagicMock()
    app.state.engine = engine
    app.state.redis = mock_redis
    app.state.settings = Settings()
    return engine


def _clear_state() -> None:
    for attr in ("engine", "redis", "settings"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# GET /login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_login_returns_200(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/login")
    finally:
        _clear_state()
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_get_login_sets_csrf_cookie(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/login")
    finally:
        _clear_state()
    assert "login_csrf" in resp.cookies


@pytest.mark.asyncio
async def test_get_login_contains_form_fields(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/login")
    finally:
        _clear_state()
    body = resp.text
    assert 'name="email"' in body
    assert 'name="password"' in body
    assert 'name="csrf_token"' in body


# ---------------------------------------------------------------------------
# POST /auth/login — success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_valid_credentials_redirects(
    mock_user: MagicMock, mock_redis_auth: AsyncMock
) -> None:
    _set_state(mock_redis_auth)
    db_session = _make_db_mock(mock_user)
    form_token, cookie_value = generate_form_csrf(_SECRET)

    try:
        with patch("app.api.auth.AsyncSession", return_value=db_session):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    "/auth/login",
                    data={"email": _EMAIL, "password": _PASSWORD, "csrf_token": form_token},
                    cookies={"login_csrf": cookie_value},
                )
    finally:
        _clear_state()

    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert SESSION_COOKIE in resp.cookies


@pytest.mark.asyncio
async def test_login_sets_httponly_session_cookie(
    mock_user: MagicMock, mock_redis_auth: AsyncMock
) -> None:
    _set_state(mock_redis_auth)
    db_session = _make_db_mock(mock_user)
    form_token, cookie_value = generate_form_csrf(_SECRET)

    try:
        with patch("app.api.auth.AsyncSession", return_value=db_session):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                follow_redirects=False,
            ) as c:
                resp = await c.post(
                    "/auth/login",
                    data={"email": _EMAIL, "password": _PASSWORD, "csrf_token": form_token},
                    cookies={"login_csrf": cookie_value},
                )
    finally:
        _clear_state()

    assert resp.status_code == 303
    set_cookie_header = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie_header


# ---------------------------------------------------------------------------
# POST /auth/login — failure paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_wrong_password_returns_error(
    mock_user: MagicMock, mock_redis_auth: AsyncMock
) -> None:
    _set_state(mock_redis_auth)
    db_session = _make_db_mock(mock_user)
    form_token, cookie_value = generate_form_csrf(_SECRET)

    try:
        with patch("app.api.auth.AsyncSession", return_value=db_session):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/auth/login",
                    data={"email": _EMAIL, "password": "wrongpassword", "csrf_token": form_token},
                    cookies={"login_csrf": cookie_value},
                )
    finally:
        _clear_state()

    assert resp.status_code == 401
    assert "Invalid email or password" in resp.text


@pytest.mark.asyncio
async def test_login_unknown_email_returns_error(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)
    db_session = _make_db_mock(None)  # user not found
    form_token, cookie_value = generate_form_csrf(_SECRET)

    try:
        with patch("app.api.auth.AsyncSession", return_value=db_session):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    "/auth/login",
                    data={
                        "email": "nobody@test.com",
                        "password": "anything",
                        "csrf_token": form_token,
                    },
                    cookies={"login_csrf": cookie_value},
                )
    finally:
        _clear_state()

    assert resp.status_code == 401
    assert "Invalid email or password" in resp.text


@pytest.mark.asyncio
async def test_login_missing_csrf_cookie_returns_error(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/auth/login",
                data={"email": _EMAIL, "password": _PASSWORD, "csrf_token": "anything"},
            )
    finally:
        _clear_state()

    assert resp.status_code == 200
    assert "Invalid form submission" in resp.text


@pytest.mark.asyncio
async def test_login_tampered_csrf_returns_error(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)
    form_token, cookie_value = generate_form_csrf(_SECRET)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/auth/login",
                data={"email": _EMAIL, "password": _PASSWORD, "csrf_token": form_token},
                cookies={"login_csrf": cookie_value[:-4] + "xxxx"},
            )
    finally:
        _clear_state()

    assert resp.status_code == 200
    assert "Invalid form submission" in resp.text


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_session_cookie(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)

    session_id = "fake-session-id"
    signed = sign_session_id(session_id, _SECRET)
    mock_redis_auth.get = AsyncMock(
        return_value=json.dumps({"user_id": str(uuid.uuid4()), "csrf_token": "tok"})
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as c:
            resp = await c.post(
                "/auth/logout",
                data={"csrf_token": "tok"},
                cookies={SESSION_COOKIE: signed},
            )
    finally:
        _clear_state()

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    set_cookie = resp.headers.get("set-cookie", "")
    assert SESSION_COOKIE in set_cookie
    # Cookie should be cleared (max-age=0 or empty value)
    assert 'session_id=""' in set_cookie or "max-age=0" in set_cookie.lower()


# ---------------------------------------------------------------------------
# Unauthenticated redirect
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_request_redirects_to_login(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as c:
            resp = await c.get("/")
    finally:
        _clear_state()

    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rate_limit_blocks_excessive_attempts(mock_redis_auth: AsyncMock) -> None:
    _set_state(mock_redis_auth)
    mock_redis_auth.incr = AsyncMock(return_value=11)
    form_token, cookie_value = generate_form_csrf(_SECRET)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/auth/login",
                data={"email": _EMAIL, "password": _PASSWORD, "csrf_token": form_token},
                cookies={"login_csrf": cookie_value},
            )
    finally:
        _clear_state()

    assert resp.status_code == 429
    assert "Too many login attempts" in resp.text
