# ABOUTME: Central FastAPI auth dependencies. require_operator() uses session cookies;
# ABOUTME: require_api_token(scope) uses Bearer tokens for machine-client REST endpoints.
from __future__ import annotations

import hashlib
import hmac
import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import Cookie, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import SESSION_COOKIE, get_session
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger()

_VALID_SCOPES = {"records:read", "records:write"}


class NotAuthenticatedException(Exception):
    """Raised by require_operator() when the request has no valid session."""


async def require_operator(
    request: Request,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> User:
    """FastAPI dependency. Returns the active operator User or raises NotAuthenticatedException."""
    if not session_cookie:
        raise NotAuthenticatedException()

    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if not session_data:
        raise NotAuthenticatedException()

    try:
        user_id = uuid.UUID(session_data["user_id"])
    except (ValueError, KeyError):
        raise NotAuthenticatedException() from None

    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if not user or not user.is_active or user.deleted_at is not None:
        logger.warning("auth.require_operator.invalid_user", user_id=str(user_id))
        raise NotAuthenticatedException()

    return user


def require_api_token(scope: str) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory for Bearer-token-protected endpoints.

    Usage::

        _dep = require_api_token("records:read")

        @router.get("/api/records")
        async def list_records(user: User = Depends(_dep)):
            ...
    """

    async def _dep(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> User:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

        raw_token = authorization.removeprefix("Bearer ")
        settings: Settings = request.app.state.settings
        token_hash = hmac.new(
            settings.api_token_secret.encode(), raw_token.encode(), hashlib.sha256
        ).hexdigest()

        async with AsyncSession(request.app.state.engine) as db:
            result = await db.execute(select(User).where(User.api_key_hash == token_hash))
            user = result.scalar_one_or_none()

        if user is None or not user.is_active or user.deleted_at is not None:
            raise HTTPException(status_code=401, detail="Invalid API token")

        if scope not in (user.api_key_scopes or []):
            raise HTTPException(status_code=403, detail="Insufficient token scope")

        return user

    return _dep
