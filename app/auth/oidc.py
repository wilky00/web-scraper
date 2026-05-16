# ABOUTME: Authentik OIDC integration: discovery loading, state management,
# ABOUTME: token exchange, userinfo fetch, and user find-or-provision logic.
from __future__ import annotations

import secrets
from typing import Any

import httpx
import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.models import AppConfig
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger()

_STATE_TTL = 600  # 10 minutes
_STATE_PREFIX = "oidc_state:"


def sso_enabled(settings: Settings, config: AppConfig) -> bool:
    """Return True only when SSO flag is on and all three Authentik secrets are configured."""
    return (
        config.features.sso_enabled
        and bool(settings.authentik_client_id)
        and bool(settings.authentik_client_secret)
        and bool(settings.authentik_base_url)
    )


async def load_oidc_discovery(settings: Settings) -> dict[str, Any] | None:
    """Fetch the OIDC discovery document from Authentik. Returns None on any error."""
    if not settings.authentik_base_url:
        return None
    discovery_url = (
        f"{settings.authentik_base_url}/application/o/"
        f"{settings.authentik_app_slug}/.well-known/openid-configuration"
    )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(discovery_url)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            logger.info("oidc.discovery_loaded", slug=settings.authentik_app_slug)
            return data
    except Exception as exc:
        logger.warning("oidc.discovery_failed", error=str(exc))
        return None


async def create_oidc_state(redis: Redis, state: str) -> None:
    """Store a single-use OIDC state token in Redis with a 10-minute TTL."""
    await redis.set(f"{_STATE_PREFIX}{state}", "1", ex=_STATE_TTL)


async def verify_oidc_state(redis: Redis, state: str) -> bool:
    """Consume and verify a state token. Returns True exactly once per valid token."""
    deleted: int = await redis.delete(f"{_STATE_PREFIX}{state}")
    return bool(deleted)


async def exchange_code_for_tokens(
    settings: Settings,
    discovery: dict[str, Any],
    code: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """Exchange an authorization code for tokens via the Authentik token endpoint."""
    token_endpoint: str = discovery["token_endpoint"]
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.authentik_client_id,
                "client_secret": settings.authentik_client_secret,
            },
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


async def fetch_userinfo(discovery: dict[str, Any], access_token: str) -> dict[str, Any]:
    """Fetch the user profile from the OIDC userinfo endpoint."""
    userinfo_endpoint: str = discovery["userinfo_endpoint"]
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result


async def find_or_provision_sso_user(db: AsyncSession, userinfo: dict[str, Any]) -> User:
    """Find an existing user or create one from OIDC userinfo.

    Lookup order:
    1. sso_sub match → return existing user (fast path for returning SSO users)
    2. email match → link sso_sub to existing local user and return
    3. neither match → create a new operator user with the SSO subject
    """
    sub: str = userinfo["sub"]
    email: str = userinfo.get("email", "").lower().strip()

    result = await db.execute(select(User).where(User.sso_sub == sub))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    if email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is not None:
            user.sso_sub = sub
            await db.commit()
            logger.info("oidc.user_linked", user_id=str(user.id))
            return user

    if not email:
        raise ValueError(f"OIDC userinfo missing email claim for sub={sub!r}")

    new_user = User(
        email=email,
        role="operator",
        is_active=True,
        sso_sub=sub,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    logger.info("oidc.user_provisioned", user_id=str(new_user.id))
    return new_user


def generate_state() -> str:
    """Generate a cryptographically random OIDC state token."""
    return secrets.token_urlsafe(32)
