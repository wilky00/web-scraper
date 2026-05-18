# ABOUTME: Web routes for the records list, detail, and edit-form partial pages.
# ABOUTME: List supports server-side filter/sort/pagination; edit partial is HTMX-swapped inline.
from __future__ import annotations

import asyncio
import math
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.crawl import CrawlPage
from app.models.record import BusinessRecord, RecordSource
from app.models.user import User
from app.services import storage
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

PAGE_SIZE = 25

_SORT_COLUMNS: dict[str, Any] = {
    "name": BusinessRecord.name,
    "match_score": BusinessRecord.match_score,
    "status": BusinessRecord.status,
    "created_at": BusinessRecord.created_at,
}


async def _get_csrf(request: Request, session_cookie: str | None) -> str:
    if not session_cookie:
        return ""
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if session_data is None:
        return ""
    return session_data.get("csrf_token", "")


def _record_to_dict(r: BusinessRecord) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "id_short": str(r.id)[:8],
        "name": r.name,
        "website": r.website,
        "email": r.email,
        "phone": r.phone,
        "address": r.address,
        "location_city": r.location_city,
        "location_state": r.location_state,
        "location_country": r.location_country,
        "match_score": float(r.match_score) if r.match_score is not None else None,
        "status": r.status,
        "job_id": str(r.job_id) if r.job_id else None,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "—",
    }


def _build_sort_url(filters: dict[str, str], col: str) -> str:
    current_sort = filters["sort"]
    current_order = filters["order"]
    new_order = "asc" if (current_sort == col and current_order == "desc") else "desc"
    params = {k: v for k, v in filters.items() if v and k not in ("sort", "order", "page")}
    params["sort"] = col
    params["order"] = new_order
    return f"/records?{urlencode(params)}"


def _page_url(filters: dict[str, str], page: int) -> str:
    params = {k: v for k, v in filters.items() if v}
    params["page"] = str(page)
    return f"/records?{urlencode(params)}"


@router.get("/records", response_class=HTMLResponse)
async def records_list(
    request: Request,
    q: str = Query(default=""),
    status: str = Query(default=""),
    score_min: str = Query(default=""),
    score_max: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    if sort not in _SORT_COLUMNS:
        sort = "created_at"
    if order not in ("asc", "desc"):
        order = "desc"

    base_query = select(BusinessRecord)

    if q.strip():
        base_query = base_query.where(BusinessRecord.name.ilike(f"%{q.strip()}%"))
    if status.strip():
        base_query = base_query.where(BusinessRecord.status == status.strip())
    if score_min.strip():
        try:
            base_query = base_query.where(BusinessRecord.match_score >= Decimal(score_min.strip()))
        except InvalidOperation:
            pass
    if score_max.strip():
        try:
            base_query = base_query.where(BusinessRecord.match_score <= Decimal(score_max.strip()))
        except InvalidOperation:
            pass
    if date_from.strip():
        try:
            dt_from = datetime.combine(
                date.fromisoformat(date_from.strip()),
                datetime.min.time(),
                tzinfo=UTC,
            )
            base_query = base_query.where(BusinessRecord.created_at >= dt_from)
        except ValueError:
            pass
    if date_to.strip():
        try:
            dt_to = datetime.combine(
                date.fromisoformat(date_to.strip()),
                datetime.max.time(),
                tzinfo=UTC,
            )
            base_query = base_query.where(BusinessRecord.created_at <= dt_to)
        except ValueError:
            pass

    sort_col = _SORT_COLUMNS[sort]

    async with AsyncSession(request.app.state.engine) as db:
        count_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
        total = count_result.scalar() or 0

        paged_query = base_query
        if order == "asc":
            paged_query = paged_query.order_by(sort_col.asc())
        else:
            paged_query = paged_query.order_by(sort_col.desc())
        paged_query = paged_query.offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)

        records = list((await db.execute(paged_query)).scalars().all())

    total_pages = max(1, math.ceil(total / PAGE_SIZE))

    filters = {
        "q": q,
        "status": status,
        "score_min": score_min,
        "score_max": score_max,
        "date_from": date_from,
        "date_to": date_to,
        "sort": sort,
        "order": order,
    }
    sort_links = {col: _build_sort_url(filters, col) for col in _SORT_COLUMNS}

    return templates.TemplateResponse(
        request,
        "records/list.html",
        {
            "records": [_record_to_dict(r) for r in records],
            "filters": filters,
            "sort_links": sort_links,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "prev_url": _page_url(filters, page - 1) if page > 1 else None,
            "next_url": _page_url(filters, page + 1) if page < total_pages else None,
            "csrf_token": csrf_token,
            "user": user,
        },
    )


@router.get("/records/{record_id}", response_class=HTMLResponse)
async def record_detail(
    record_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    try:
        parsed_id = uuid.UUID(record_id)
    except ValueError:
        return HTMLResponse("Record not found", status_code=404)

    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        record: BusinessRecord | None = await db.get(BusinessRecord, parsed_id)
        if record is None:
            return HTMLResponse("Record not found", status_code=404)

        sources_result = await db.execute(
            select(RecordSource)
            .where(RecordSource.record_id == parsed_id)
            .order_by(RecordSource.field.asc())
        )
        sources = list(sources_result.scalars().all())

        # Check whether a screenshot was captured for this record's page
        has_screenshot = False
        if record.website and record.job_id:
            ss_result = await db.execute(
                select(CrawlPage.screenshot_path)
                .where(CrawlPage.job_id == record.job_id)
                .where(CrawlPage.url == record.website)
                .where(CrawlPage.screenshot_path.isnot(None))
                .order_by(CrawlPage.created_at.desc())
                .limit(1)
            )
            has_screenshot = ss_result.scalar_one_or_none() is not None

    sources_data = [
        {
            "field": s.field,
            "source_url": s.source_url,
            "source_type": s.source_type,
            "raw_value": s.raw_value,
        }
        for s in sources
    ]

    return templates.TemplateResponse(
        request,
        "records/detail.html",
        {
            "record": _record_to_dict(record),
            "sources": sources_data,
            "rule_results": record.rule_results or {},
            "has_screenshot": has_screenshot,
            "csrf_token": csrf_token,
            "user": user,
        },
    )


@router.get("/records/{record_id}/edit", response_class=HTMLResponse)
async def record_edit_partial(
    record_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    """HTMX partial — returns the inline edit form swapped into #record-fields."""
    try:
        parsed_id = uuid.UUID(record_id)
    except ValueError:
        return HTMLResponse("Record not found", status_code=404)

    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        record: BusinessRecord | None = await db.get(BusinessRecord, parsed_id)
        if record is None:
            return HTMLResponse("Record not found", status_code=404)

    return templates.TemplateResponse(
        request,
        "records/_edit_form.html",
        {"record": _record_to_dict(record), "csrf_token": csrf_token},
    )


@router.get("/records/{record_id}/screenshot")
async def record_screenshot(
    record_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    """Serve the screenshot for a record's crawled website page."""
    try:
        parsed_id = uuid.UUID(record_id)
    except ValueError:
        return HTMLResponse("Not found", status_code=404)

    settings: Settings = request.app.state.settings
    if not settings.s3_endpoint_url:
        return HTMLResponse("Storage not configured", status_code=404)

    async with AsyncSession(request.app.state.engine) as db:
        record: BusinessRecord | None = await db.get(BusinessRecord, parsed_id)
        if record is None or not record.website or not record.job_id:
            return HTMLResponse("Not found", status_code=404)

        ss_result = await db.execute(
            select(CrawlPage.screenshot_path)
            .where(CrawlPage.job_id == record.job_id)
            .where(CrawlPage.url == record.website)
            .where(CrawlPage.screenshot_path.isnot(None))
            .order_by(CrawlPage.created_at.desc())
            .limit(1)
        )
        screenshot_key = ss_result.scalar_one_or_none()

    if not screenshot_key:
        return HTMLResponse("Not found", status_code=404)

    try:
        image_bytes = await asyncio.to_thread(storage.download_bytes, screenshot_key, settings)
    except storage.StorageNotFoundError:
        return HTMLResponse("Not found", status_code=404)
    except storage.StorageError:
        logger.warning("record_screenshot.download_failed", record_id=record_id, key=screenshot_key)
        return HTMLResponse("Storage error", status_code=502)

    return Response(content=image_bytes, media_type="image/png")
