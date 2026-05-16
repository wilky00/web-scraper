# ABOUTME: Export API endpoints — create export tasks and poll status by ID.
# ABOUTME: POST /api/exports enqueues an RQ export task; GET /api/exports/{id} returns JSON status.
from __future__ import annotations

import asyncio
import secrets
import uuid

import redis as sync_redis
import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import JSONResponse, Response
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.audit import Export
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()

_VALID_FORMATS = {"csv", "xlsx"}


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


def _enqueue_export(redis_url: str, export_id: uuid.UUID) -> None:
    conn = sync_redis.from_url(redis_url)
    try:
        q = Queue(connection=conn)
        q.enqueue("app.jobs.export_task.run_export", str(export_id))
    finally:
        conn.close()


@router.post("/api/exports", status_code=201)
async def create_export(
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    format: str = Form(default="csv"),
    q: str = Form(default=""),
    status: str = Form(default=""),
    score_min: str = Form(default=""),
    score_max: str = Form(default=""),
    date_from: str = Form(default=""),
    date_to: str = Form(default=""),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    if format not in _VALID_FORMATS:
        return JSONResponse({"error": f"Invalid format '{format}'"}, status_code=422)

    filter_params = {
        "q": q.strip(),
        "status": status.strip(),
        "score_min": score_min.strip(),
        "score_max": score_max.strip(),
        "date_from": date_from.strip(),
        "date_to": date_to.strip(),
    }

    async with AsyncSession(request.app.state.engine) as db:
        export = Export(
            user_id=user.id,
            format=format,
            filter_params=filter_params,
            status="pending",
        )
        db.add(export)
        await db.commit()
        export_id = export.id

    settings: Settings = request.app.state.settings
    await asyncio.to_thread(_enqueue_export, settings.redis_url, export_id)

    logger.info("export.created", export_id=str(export_id), format=format, user_id=str(user.id))
    return Response(status_code=201, headers={"HX-Redirect": "/exports"})


@router.get("/api/exports/{export_id}")
async def get_export_status(
    export_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    try:
        parsed_id = uuid.UUID(export_id)
    except ValueError:
        return JSONResponse({"error": "Invalid export ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        export: Export | None = await db.get(Export, parsed_id)

    if export is None:
        return JSONResponse({"error": "Export not found"}, status_code=404)

    return JSONResponse(
        {
            "id": str(export.id),
            "format": export.format,
            "status": export.status,
            "row_count": export.row_count,
            "error": export.error,
            "created_at": export.created_at.isoformat() if export.created_at else None,
        }
    )
