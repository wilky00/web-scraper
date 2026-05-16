# ABOUTME: Records API endpoints — create, update (inline edit), and soft-delete business records.
# ABOUTME: All mutating endpoints require CSRF validation and write audit log entries.
from __future__ import annotations

import secrets
import uuid

import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.audit import RecordAuditLog
from app.models.record import BusinessRecord
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()

_EDITABLE_STATUSES = {"active", "excluded", "deleted"}


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
