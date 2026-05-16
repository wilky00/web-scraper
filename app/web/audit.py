# ABOUTME: Web route for the audit log browse page (GET /audit-log).
# ABOUTME: Filters: action, resource_type, user_id, date_from, date_to; 50 entries/page pagination.
from __future__ import annotations

import math
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.audit import RecordAuditLog
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

PAGE_SIZE = 50


async def _get_csrf(request: Request, session_cookie: str | None) -> str:
    if not session_cookie:
        return ""
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if session_data is None:
        return ""
    return session_data.get("csrf_token", "")


@router.get("/audit-log", response_class=HTMLResponse)
async def audit_log(
    request: Request,
    user: User = Depends(require_operator),
    action: str = Query(default=""),
    resource_type: str = Query(default=""),
    user_id: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    page: int = Query(default=1, ge=1),
) -> HTMLResponse:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    query = select(RecordAuditLog)

    if action.strip():
        query = query.where(RecordAuditLog.action == action.strip())
    if resource_type.strip():
        query = query.where(RecordAuditLog.resource_type == resource_type.strip())
    if user_id.strip():
        try:
            uid = uuid.UUID(user_id.strip())
            query = query.where(RecordAuditLog.user_id == uid)
        except ValueError:
            pass
    if date_from.strip():
        try:
            dt = datetime.combine(
                date.fromisoformat(date_from.strip()), datetime.min.time(), tzinfo=UTC
            )
            query = query.where(RecordAuditLog.created_at >= dt)
        except ValueError:
            pass
    if date_to.strip():
        try:
            dt = datetime.combine(
                date.fromisoformat(date_to.strip()), datetime.max.time(), tzinfo=UTC
            )
            query = query.where(RecordAuditLog.created_at <= dt)
        except ValueError:
            pass

    query = query.order_by(RecordAuditLog.created_at.desc())

    filters: dict[str, Any] = {
        "action": action,
        "resource_type": resource_type,
        "user_id": user_id,
        "date_from": date_from,
        "date_to": date_to,
    }

    async with AsyncSession(request.app.state.engine) as db:
        # Count total for pagination
        count_query = select(RecordAuditLog.id).order_by(None)
        if action.strip():
            count_query = count_query.where(RecordAuditLog.action == action.strip())
        if resource_type.strip():
            count_query = count_query.where(RecordAuditLog.resource_type == resource_type.strip())
        if user_id.strip():
            try:
                uid = uuid.UUID(user_id.strip())
                count_query = count_query.where(RecordAuditLog.user_id == uid)
            except ValueError:
                pass
        if date_from.strip():
            try:
                dt = datetime.combine(
                    date.fromisoformat(date_from.strip()), datetime.min.time(), tzinfo=UTC
                )
                count_query = count_query.where(RecordAuditLog.created_at >= dt)
            except ValueError:
                pass
        if date_to.strip():
            try:
                dt = datetime.combine(
                    date.fromisoformat(date_to.strip()), datetime.max.time(), tzinfo=UTC
                )
                count_query = count_query.where(RecordAuditLog.created_at <= dt)
            except ValueError:
                pass

        count_result = await db.execute(count_query)
        total = len(count_result.scalars().all())

        offset = (page - 1) * PAGE_SIZE
        page_query = query.offset(offset).limit(PAGE_SIZE)
        result = await db.execute(page_query)
        entries = list(result.scalars().all())

        # Resolve user emails in one pass
        user_ids = {e.user_id for e in entries if e.user_id is not None}
        email_map: dict[uuid.UUID, str] = {}
        if user_ids:
            users_result = await db.execute(select(User).where(User.id.in_(list(user_ids))))
            for u in users_result.scalars().all():
                email_map[u.id] = u.email

    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    # Build query string for pagination links (preserves filters)
    filter_qs = urlencode({k: v for k, v in filters.items() if v})

    return templates.TemplateResponse(
        request,
        "audit/list.html",
        {
            "user": user,
            "csrf_token": csrf_token,
            "entries": entries,
            "email_map": email_map,
            "filters": filters,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "filter_qs": filter_qs,
        },
    )
