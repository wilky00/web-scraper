# ABOUTME: Central FastAPI auth dependency. All protected routes depend on require_operator().
# ABOUTME: Raises NotAuthenticatedException on missing/invalid session; handler redirects to /login.
from __future__ import annotations

import uuid

import structlog
from fastapi import Cookie, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import SESSION_COOKIE, get_session
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger()


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
