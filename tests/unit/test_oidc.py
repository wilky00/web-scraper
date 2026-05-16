# ABOUTME: Unit tests for app/auth/oidc.py — sso_enabled, state management,
# ABOUTME: discovery loading (soft-fail), and find_or_provision_sso_user (3 cases).
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.oidc import (
    create_oidc_state,
    find_or_provision_sso_user,
    load_oidc_discovery,
    sso_enabled,
    verify_oidc_state,
)
from app.config.models import AppConfig, FeaturesConfig
from app.models.user import User
from app.settings import Settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**overrides: str) -> Settings:
    base = {
        "DATABASE_URL": "postgresql+asyncpg://x:x@localhost/x",
        "SECRET_KEY": "test-secret",
        "API_TOKEN_SECRET": "test-api-secret",
        "AUTHENTIK_CLIENT_ID": "client-id",
        "AUTHENTIK_CLIENT_SECRET": "client-secret",
        "AUTHENTIK_BASE_URL": "https://auth.example.com",
    }
    base.update(overrides)
    import os

    with patch.dict(os.environ, base, clear=False):
        return Settings()


def _config(sso: bool = True) -> AppConfig:
    return AppConfig(
        base_url="http://localhost:8000",
        features=FeaturesConfig(sso_enabled=sso),
    )


# ---------------------------------------------------------------------------
# sso_enabled()
# ---------------------------------------------------------------------------


def test_sso_enabled_all_configured() -> None:
    assert sso_enabled(_settings(), _config(sso=True)) is True


def test_sso_enabled_flag_false() -> None:
    assert sso_enabled(_settings(), _config(sso=False)) is False


def test_sso_enabled_missing_client_id() -> None:
    assert sso_enabled(_settings(AUTHENTIK_CLIENT_ID=""), _config(sso=True)) is False


def test_sso_enabled_missing_client_secret() -> None:
    assert sso_enabled(_settings(AUTHENTIK_CLIENT_SECRET=""), _config(sso=True)) is False


def test_sso_enabled_missing_base_url() -> None:
    assert sso_enabled(_settings(AUTHENTIK_BASE_URL=""), _config(sso=True)) is False


# ---------------------------------------------------------------------------
# create_oidc_state / verify_oidc_state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_verify_state() -> None:
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock(return_value=1)
    await create_oidc_state(mock_redis, "state-abc")
    mock_redis.set.assert_called_once()
    assert "oidc_state:state-abc" in mock_redis.set.call_args[0][0]
    result = await verify_oidc_state(mock_redis, "state-abc")
    assert result is True


@pytest.mark.asyncio
async def test_verify_state_nonexistent() -> None:
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock(return_value=0)
    result = await verify_oidc_state(mock_redis, "no-such-state")
    assert result is False


@pytest.mark.asyncio
async def test_verify_state_one_time_use() -> None:
    mock_redis = AsyncMock()
    mock_redis.delete = AsyncMock(side_effect=[1, 0])
    first = await verify_oidc_state(mock_redis, "state-xyz")
    second = await verify_oidc_state(mock_redis, "state-xyz")
    assert first is True
    assert second is False


# ---------------------------------------------------------------------------
# load_oidc_discovery (soft-fail)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_discovery_missing_base_url() -> None:
    settings = _settings(AUTHENTIK_BASE_URL="")
    result = await load_oidc_discovery(settings)
    assert result is None


@pytest.mark.asyncio
async def test_load_discovery_network_error() -> None:
    import httpx

    settings = _settings()
    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectError("unreachable")):
        result = await load_oidc_discovery(settings)
    assert result is None


@pytest.mark.asyncio
async def test_load_discovery_non_200() -> None:
    import httpx

    settings = _settings()
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock()
    )
    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await load_oidc_discovery(settings)
    assert result is None


# ---------------------------------------------------------------------------
# find_or_provision_sso_user
# ---------------------------------------------------------------------------


def _mock_db(*return_values: User | None) -> AsyncMock:
    """Create a mock db with execute() returning each value in sequence."""
    db = AsyncMock()
    results = []
    for val in return_values:
        r = MagicMock()
        r.scalar_one_or_none.return_value = val
        results.append(r)
    db.execute = AsyncMock(side_effect=results)
    return db


@pytest.mark.asyncio
async def test_provision_returns_existing_sso_user() -> None:
    existing = MagicMock(spec=User)
    existing.id = "uuid-1"
    db = _mock_db(existing)
    user = await find_or_provision_sso_user(db, {"sub": "sub-1", "email": "a@example.com"})
    assert user is existing
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_provision_links_existing_local_user() -> None:
    existing = MagicMock(spec=User)
    existing.id = "uuid-2"
    existing.sso_sub = None
    db = _mock_db(None, existing)
    user = await find_or_provision_sso_user(db, {"sub": "new-sub", "email": "b@example.com"})
    assert user is existing
    assert existing.sso_sub == "new-sub"
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_provision_creates_new_user() -> None:
    db = _mock_db(None, None)
    db.refresh = AsyncMock()
    await find_or_provision_sso_user(db, {"sub": "brand-new", "email": "c@example.com"})
    db.add.assert_called_once()
    added: User = db.add.call_args[0][0]
    assert added.email == "c@example.com"
    assert added.sso_sub == "brand-new"
    assert added.role == "operator"
    db.commit.assert_called_once()
    db.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_provision_raises_on_missing_email() -> None:
    db = _mock_db(None)
    with pytest.raises(ValueError, match="missing email"):
        await find_or_provision_sso_user(db, {"sub": "no-email-sub"})
