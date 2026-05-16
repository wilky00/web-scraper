# ABOUTME: Records API — HTMX-driven create/update/delete (session auth) and
# ABOUTME: machine-readable GET list + detail endpoints (Bearer token auth, JSON envelope).
from __future__ import annotations

import math
import secrets
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_api_token, require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.audit import RecordAuditLog
from app.models.record import BusinessRecord, RecordSource
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()

_EDITABLE_STATUSES = {"active", "excluded", "deleted"}
PAGE_SIZE = 25

_SORT_COLUMNS: dict[str, Any] = {
    "name": BusinessRecord.name,
    "match_score": BusinessRecord.match_score,
    "status": BusinessRecord.status,
    "created_at": BusinessRecord.created_at,
}

# Module-level dependency instances — stored so tests can override via dependency_overrides.
_require_records_read = require_api_token("records:read")


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


def _clean(value: str) -> str | None:
    v = value.strip()
    return v if v else None


@router.post("/api/records", status_code=201)
async def create_record(
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    name: str = Form(default=""),
    website: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    address: str = Form(default=""),
    location_city: str = Form(default=""),
    location_state: str = Form(default=""),
    location_country: str = Form(default=""),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    record_name = _clean(name)
    if not record_name:
        return JSONResponse({"error": "Name is required"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        record = BusinessRecord(
            name=record_name,
            website=_clean(website),
            email=_clean(email),
            phone=_clean(phone),
            address=_clean(address),
            location_city=_clean(location_city),
            location_state=_clean(location_state),
            location_country=_clean(location_country),
            status="active",
        )
        db.add(record)
        await db.flush()

        audit = RecordAuditLog(
            user_id=user.id,
            action="create",
            resource_type="business_record",
            resource_id=str(record.id),
            diff={"name": record_name, "source": "manual"},
        )
        db.add(audit)
        await db.commit()
        record_id = record.id

    logger.info("record.created", record_id=str(record_id), user_id=str(user.id))
    return Response(status_code=201, headers={"HX-Redirect": f"/records/{record_id}"})


@router.post("/api/records/{record_id}")
async def update_record(
    record_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    name: str = Form(default=""),
    website: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    address: str = Form(default=""),
    location_city: str = Form(default=""),
    location_state: str = Form(default=""),
    location_country: str = Form(default=""),
    status: str = Form(default="active"),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_id = uuid.UUID(record_id)
    except ValueError:
        return JSONResponse({"error": "Invalid record ID"}, status_code=422)

    if status not in _EDITABLE_STATUSES:
        return JSONResponse({"error": f"Invalid status '{status}'"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        record: BusinessRecord | None = await db.get(BusinessRecord, parsed_id)
        if record is None:
            return JSONResponse({"error": "Record not found"}, status_code=404)

        before = {
            "name": record.name,
            "website": record.website,
            "email": record.email,
            "phone": record.phone,
            "address": record.address,
            "location_city": record.location_city,
            "location_state": record.location_state,
            "location_country": record.location_country,
            "status": record.status,
        }
        record.name = _clean(name) or record.name
        record.website = _clean(website)
        record.email = _clean(email)
        record.phone = _clean(phone)
        record.address = _clean(address)
        record.location_city = _clean(location_city)
        record.location_state = _clean(location_state)
        record.location_country = _clean(location_country)
        record.status = status

        after = {
            "name": record.name,
            "website": record.website,
            "email": record.email,
            "phone": record.phone,
            "address": record.address,
            "location_city": record.location_city,
            "location_state": record.location_state,
            "location_country": record.location_country,
            "status": record.status,
        }
        db.add(
            RecordAuditLog(
                user_id=user.id,
                action="update",
                resource_type="business_record",
                resource_id=str(parsed_id),
                diff={"before": before, "after": after},
            )
        )
        await db.commit()

    logger.info("record.updated", record_id=record_id, user_id=str(user.id))
    return Response(status_code=200, headers={"HX-Redirect": f"/records/{record_id}"})


@router.post("/api/records/{record_id}/delete")
async def delete_record(
    record_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_id = uuid.UUID(record_id)
    except ValueError:
        return JSONResponse({"error": "Invalid record ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        record: BusinessRecord | None = await db.get(BusinessRecord, parsed_id)
        if record is None:
            return JSONResponse({"error": "Record not found"}, status_code=404)
        if record.status == "deleted":
            return JSONResponse({"error": "Record is already deleted"}, status_code=409)

        previous_status = record.status
        record.status = "deleted"
        db.add(
            RecordAuditLog(
                user_id=user.id,
                action="delete",
                resource_type="business_record",
                resource_id=str(parsed_id),
                diff={"previous_status": previous_status},
            )
        )
        await db.commit()

    logger.info("record.deleted", record_id=record_id, user_id=str(user.id))
    return Response(status_code=200, headers={"HX-Redirect": "/records"})


# ── Machine-readable REST endpoints (Bearer token auth) ──────────────────────


def _record_to_dict(r: BusinessRecord) -> dict[str, Any]:
    return {
        "id": str(r.id),
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
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/api/records")
async def api_list_records(
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
    user: User = Depends(_require_records_read),
) -> JSONResponse:
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
                date.fromisoformat(date_from.strip()), datetime.min.time(), tzinfo=UTC
            )
            base_query = base_query.where(BusinessRecord.created_at >= dt_from)
        except ValueError:
            pass
    if date_to.strip():
        try:
            dt_to = datetime.combine(
                date.fromisoformat(date_to.strip()), datetime.max.time(), tzinfo=UTC
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

    return JSONResponse(
        {
            "data": [_record_to_dict(r) for r in records],
            "pagination": {
                "page": page,
                "page_size": PAGE_SIZE,
                "total": total,
                "total_pages": total_pages,
            },
            "errors": [],
        }
    )


@router.get("/api/records/{record_id}")
async def api_get_record(
    record_id: str,
    request: Request,
    user: User = Depends(_require_records_read),
) -> JSONResponse:
    try:
        parsed_id = uuid.UUID(record_id)
    except ValueError:
        return JSONResponse({"data": None, "errors": ["Invalid record ID"]}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        record: BusinessRecord | None = await db.get(BusinessRecord, parsed_id)
        if record is None:
            return JSONResponse({"data": None, "errors": ["Record not found"]}, status_code=404)

        sources_result = await db.execute(
            select(RecordSource)
            .where(RecordSource.record_id == parsed_id)
            .order_by(RecordSource.field.asc())
        )
        sources = list(sources_result.scalars().all())

    return JSONResponse(
        {
            "data": {
                **_record_to_dict(record),
                "rule_results": record.rule_results or {},
                "sources": [
                    {
                        "field": s.field,
                        "source_url": s.source_url,
                        "source_type": s.source_type,
                        "raw_value": s.raw_value,
                    }
                    for s in sources
                ],
            },
            "errors": [],
        }
    )
