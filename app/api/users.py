# ABOUTME: API endpoints for user management — list users and toggle active status.
# ABOUTME: Operator-only; uses session auth + CSRF protection.
from __future__ import annotations

import secrets
import uuid

import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()


async def _check_csrf(
    request: Request,
    form_csrf: str,
    session_cookie: str | None,
) -> bool:
    if not session_cookie:
        return False
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if not session_data:
        return False
    expected = session_data.get("csrf_token", "")
    return bool(expected) and secrets.compare_digest(form_csrf, expected)


@router.get("/api/users")
async def list_users(
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(
            select(User).where(User.deleted_at.is_(None)).order_by(User.created_at)
        )
        users = list(result.scalars().all())

    return JSONResponse(
        [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "—",
            }
            for u in users
        ]
    )


@router.patch("/api/users/{user_id}/active")
async def toggle_user_active(
    user_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    active: bool = Form(...),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    current_user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_id = uuid.UUID(user_id)
    except ValueError:
        return JSONResponse({"error": "Invalid user ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        target: User | None = await db.get(User, parsed_id)
        if target is None or target.deleted_at is not None:
            return JSONResponse({"error": "User not found"}, status_code=404)

        target.is_active = active
        await db.commit()

    logger.info(
        "user.active_toggled",
        target_id=str(parsed_id),
        active=active,
        by=str(current_user.id),
    )
    return JSONResponse({"id": str(parsed_id), "is_active": active})
