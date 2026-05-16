# ABOUTME: Web routes for the exports list, HTMX status polling fragment, and file download proxy.
# ABOUTME: GET /exports/{id}/download streams the file through FastAPI — storage URL never exposed.
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.audit import Export
from app.models.user import User
from app.services import storage
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


async def _get_csrf(request: Request, session_cookie: str | None) -> str:
    if not session_cookie:
        return ""
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if session_data is None:
        return ""
    return session_data.get("csrf_token", "")


def _export_to_dict(e: Export) -> dict[str, Any]:
    return {
        "id": str(e.id),
        "format": e.format,
        "status": e.status,
        "row_count": e.row_count,
        "error": e.error,
        "created_at": e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "—",
    }


@router.get("/exports", response_class=HTMLResponse)
async def exports_list(
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(select(Export).order_by(Export.created_at.desc()).limit(50))
        exports = [_export_to_dict(e) for e in result.scalars().all()]

    return templates.TemplateResponse(
        request,
        "exports/list.html",
        {"user": user, "csrf_token": csrf_token, "exports": exports},
    )


@router.get("/exports/{export_id}/status", response_class=HTMLResponse)
async def export_status_fragment(
    export_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    try:
        parsed_id = uuid.UUID(export_id)
    except ValueError:
        return Response("Invalid ID", status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        export: Export | None = await db.get(Export, parsed_id)

    if export is None:
        return Response("Not found", status_code=404)

    return templates.TemplateResponse(
        request,
        "exports/_status.html",
        {"export": _export_to_dict(export)},
    )


@router.get("/exports/{export_id}/download")
async def export_download(
    export_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    try:
        parsed_id = uuid.UUID(export_id)
    except ValueError:
        return Response("Invalid ID", status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        export: Export | None = await db.get(Export, parsed_id)

    if export is None or export.status != "ready" or not export.s3_key:
        return Response("Export not ready or not found", status_code=404)

    settings: Settings = request.app.state.settings
    try:
        data = await asyncio.to_thread(storage.download_bytes, export.s3_key, settings)
    except storage.StorageNotFoundError:
        return Response("File not found in storage", status_code=404)
    except storage.StorageError:
        logger.exception("export.download_failed", export_id=export_id)
        return Response("Storage error", status_code=500)

    content_type = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if export.format == "xlsx"
        else "text/csv"
    )
    filename = f"records-export.{export.format}"

    return Response(
        content=data,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
