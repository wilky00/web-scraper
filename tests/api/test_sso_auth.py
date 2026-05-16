# ABOUTME: API tests for OIDC SSO routes: GET /auth/oidc/login and GET /auth/oidc/callback.
# ABOUTME: Mocks token exchange and userinfo; never makes real Authentik calls.
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.loader import AppConfigs
from app.config.models import AppConfig, FeaturesConfig
from app.main import app
from app.models.user import User
from app.settings import Settings

_DISCOVERY = {
    "authorization_endpoint": "https://auth.example.com/application/o/web-scraper/authorize/",
    "token_endpoint": "https://auth.example.com/application/o/web-scraper/token/",
    "userinfo_endpoint": "https://auth.example.com/application/o/web-scraper/userinfo/",
}


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _sso_settings() -> Settings:
    overrides = {
        "AUTHENTIK_CLIENT_ID": "test-client-id",
        "AUTHENTIK_CLIENT_SECRET": "test-client-secret",
        "AUTHENTIK_BASE_URL": "https://auth.example.com",
    }
    with patch.dict(os.environ, overrides, clear=False):
        return Settings()


def _sso_configs() -> MagicMock:
    cfg = MagicMock(spec=AppConfigs)
    cfg.app = AppConfig(
        base_url="http://localhost:8000",
        features=FeaturesConfig(sso_enabled=True),
    )
    return cfg


def _make_redis(state_valid: bool = True) -> AsyncMock:
    r: AsyncMock = AsyncMock()
    r.set = AsyncMock(return_value=True)
    r.delete = AsyncMock(return_value=1 if state_valid else 0)
    return r


@pytest.fixture
def mock_sso_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "sso@example.com"
    user.role = "operator"
    user.is_active = True
    user.deleted_at = None
    return user


@pytest.fixture
async def sso_client() -> AsyncClient:
    app.state.settings = _sso_settings()
    app.state.config = _sso_configs()
    app.state.redis = _make_redis()
    app.state.oidc_discovery = _DISCOVERY
    app.state.engine = MagicMock()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    for attr in ("settings", "config", "redis", "oidc_discovery", "engine"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


@pytest.fixture
async def no_sso_client() -> AsyncClient:
    app.state.settings = Settings()
    cfg = MagicMock(spec=AppConfigs)
    cfg.app = AppConfig(
        base_url="http://localhost:8000",
        features=FeaturesConfig(sso_enabled=False),
    )
    app.state.config = cfg
    app.state.redis = _make_redis()
    app.state.oidc_discovery = None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    for attr in ("settings", "config", "redis", "oidc_discovery"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# GET /auth/oidc/login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oidc_login_redirects_to_authentik(sso_client: AsyncClient) -> None:
    resp = await sso_client.get("/auth/oidc/login", follow_redirects=False)
    assert resp.status_code == 302
    loc = resp.headers["location"]
    assert "auth.example.com" in loc
    assert "response_type=code" in loc
    assert "scope=openid+email+profile" in loc


@pytest.mark.asyncio
async def test_oidc_login_stores_state_in_redis(sso_client: AsyncClient) -> None:
    await sso_client.get("/auth/oidc/login", follow_redirects=False)
    app.state.redis.set.assert_called_once()
    key = app.state.redis.set.call_args[0][0]
    assert key.startswith("oidc_state:")


@pytest.mark.asyncio
async def test_oidc_login_returns_404_when_sso_disabled(no_sso_client: AsyncClient) -> None:
    resp = await no_sso_client.get("/auth/oidc/login", follow_redirects=False)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /auth/oidc/callback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oidc_callback_success_creates_session(
    sso_client: AsyncClient, mock_sso_user: MagicMock
) -> None:
    mock_db = AsyncMock()
    mock_ctx = MagicMock()
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
    mock_ctx.__aexit__ = AsyncMock(return_value=False)
    tok_patch = patch(
        "app.web.auth.exchange_code_for_tokens",
        new=AsyncMock(return_value={"access_token": "tok"}),
    )
    info_patch = patch(
        "app.web.auth.fetch_userinfo",
        new=AsyncMock(return_value={"sub": "s1", "email": "sso@example.com"}),
    )
    user_patch = patch(
        "app.web.auth.find_or_provision_sso_user",
        new=AsyncMock(return_value=mock_sso_user),
    )
    with patch("app.web.auth.AsyncSession", return_value=mock_ctx):
        with tok_patch, info_patch, user_patch:
            resp = await sso_client.get(
                "/auth/oidc/callback?code=authcode&state=valid-state",
                follow_redirects=False,
            )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    assert "session_id" in resp.cookies


@pytest.mark.asyncio
async def test_oidc_callback_invalid_state_redirects_to_login(sso_client: AsyncClient) -> None:
    app.state.redis = _make_redis(state_valid=False)
    resp = await sso_client.get(
        "/auth/oidc/callback?code=code&state=bad-state",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


@pytest.mark.asyncio
async def test_oidc_callback_provider_error_redirects_to_login(sso_client: AsyncClient) -> None:
    resp = await sso_client.get(
        "/auth/oidc/callback?error=access_denied",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


@pytest.mark.asyncio
async def test_oidc_callback_missing_params_redirects_to_login(sso_client: AsyncClient) -> None:
    resp = await sso_client.get("/auth/oidc/callback", follow_redirects=False)
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


@pytest.mark.asyncio
async def test_oidc_callback_returns_404_when_sso_disabled(no_sso_client: AsyncClient) -> None:
    resp = await no_sso_client.get("/auth/oidc/callback?code=x&state=y", follow_redirects=False)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_oidc_callback_token_exchange_failure_redirects(sso_client: AsyncClient) -> None:
    import httpx

    with patch(
        "app.web.auth.exchange_code_for_tokens",
        new=AsyncMock(side_effect=httpx.ConnectError("down")),
    ):
        resp = await sso_client.get(
            "/auth/oidc/callback?code=code&state=valid-state",
            follow_redirects=False,
        )
    assert resp.status_code == 303
    assert "/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Local login still works when SSO is enabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_login_page_renders_with_sso_button(sso_client: AsyncClient) -> None:
    resp = await sso_client.get("/login")
    assert resp.status_code == 200
    assert "Sign in with Authentik" in resp.text
    assert 'action="/auth/login"' in resp.text


@pytest.mark.asyncio
async def test_local_login_page_no_sso_button_when_disabled(no_sso_client: AsyncClient) -> None:
    resp = await no_sso_client.get("/login")
    assert resp.status_code == 200
    assert "Authentik" not in resp.text
    assert 'action="/auth/login"' in resp.text
