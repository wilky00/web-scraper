# ABOUTME: Criteria API endpoints — validate YAML, create criteria groups, save immutable versions.
# ABOUTME: All mutating endpoints write an audit log entry. Validate is read-only (no audit needed).
from __future__ import annotations

import secrets
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.config.criteria import validate_criteria_yaml
from app.models.audit import RecordAuditLog
from app.models.criteria import CriteriaGroup, CriteriaVersion
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger()

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _validation_html(errors: list[str]) -> str:
    """Return an HTML fragment for the HTMX validation result panel."""
    if not errors:
        return (
            '<div class="rounded-md bg-green-50 dark:bg-green-900/20 border border-green-200'
            ' dark:border-green-800 p-4">'
            '<p class="text-sm font-medium text-green-800 dark:text-green-300">'
            "Valid YAML — ready to save.</p></div>"
        )
    items = "".join(f'<li class="font-mono text-xs break-all">{err}</li>' for err in errors)
    return (
        '<div class="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200'
        ' dark:border-red-800 p-4">'
        '<p class="text-sm font-medium text-red-800 dark:text-red-300 mb-2">Validation errors</p>'
        f'<ul class="text-sm text-red-700 dark:text-red-400 list-disc list-inside space-y-1">'
        f"{items}</ul>"
        "</div>"
    )


async def _check_csrf(
    request: Request,
    form_csrf: str,
    session_cookie: str | None,
) -> bool:
    """Return True if form CSRF token matches the session CSRF token."""
    if not session_cookie:
        return False
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if not session_data:
        return False
    expected = session_data.get("csrf_token", "")
    return bool(expected) and secrets.compare_digest(form_csrf, expected)


def _render_editor(
    request: Request,
    *,
    group: CriteriaGroup | None = None,
    yaml_text: str = "",
    versions: list[CriteriaVersion] | None = None,
    errors: list[str] | None = None,
    csrf_token: str = "",
    user: User,
    ai_enabled: bool = False,
    status_code: int = 200,
) -> Response:
    return templates.TemplateResponse(
        request,
        "criteria/editor.html",
        {
            "group": group,
            "yaml_text": yaml_text,
            "versions": versions or [],
            "errors": errors or [],
            "csrf_token": csrf_token,
            "user": user,
            "ai_enabled": ai_enabled,
        },
        status_code=status_code,
    )


# ---------------------------------------------------------------------------
# POST /api/criteria/validate
# ---------------------------------------------------------------------------


@router.post("/api/criteria/validate", response_class=HTMLResponse)
async def validate_criteria(
    yaml_text: str = Form(...),
    user: User = Depends(require_operator),
) -> HTMLResponse:
    _, errors = validate_criteria_yaml(yaml_text)
    return HTMLResponse(content=_validation_html(errors))


# ---------------------------------------------------------------------------
# POST /api/criteria  (create group + version 1)
# ---------------------------------------------------------------------------


@router.post("/api/criteria")
async def create_criteria(
    request: Request,
    yaml_text: str = Form(...),
    csrf_token: str = Form(...),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        logger.warning("criteria.create.csrf_failed", user_id=str(user.id))
        settings: Settings = request.app.state.settings
        session_data = (
            await get_session(request.app.state.redis, session_cookie, settings.secret_key)
            if session_cookie
            else None
        )
        real_csrf = session_data.get("csrf_token", "") if session_data else ""
        return _render_editor(
            request,
            yaml_text=yaml_text,
            errors=["Invalid form submission. Please try again."],
            csrf_token=real_csrf,
            user=user,
            status_code=400,
        )

    config, errors = validate_criteria_yaml(yaml_text)
    if errors or config is None:
        settings2: Settings = request.app.state.settings
        session_data2 = (
            await get_session(request.app.state.redis, session_cookie, settings2.secret_key)
            if session_cookie
            else None
        )
        real_csrf2 = session_data2.get("csrf_token", "") if session_data2 else ""
        return _render_editor(
            request,
            yaml_text=yaml_text,
            errors=errors,
            csrf_token=real_csrf2,
            user=user,
            status_code=422,
        )

    snapshot = config.model_dump()
    try:
        async with AsyncSession(request.app.state.engine) as db:
            group = CriteriaGroup(
                name=config.metadata.name,
                display_name=config.metadata.display_name,
                description=config.metadata.description,
                tags=config.metadata.tags,
                is_active=True,
            )
            db.add(group)
            await db.flush()

            # Capture IDs before commit — commit expires all ORM attributes and
            # accessing them on a detached object after session close raises
            # DetachedInstanceError.
            group_id = group.id

            version = CriteriaVersion(
                group_id=group_id,
                version=1,
                config_snapshot=snapshot,
                is_active=True,
                created_by=user.id,
            )
            db.add(version)
            version_id = version.id

            audit = RecordAuditLog(
                user_id=user.id,
                action="criteria_save",
                resource_type="criteria_version",
                resource_id=str(version_id),
                diff={"group_id": str(group_id), "version": 1, "name": config.metadata.name},
            )
            db.add(audit)
            await db.commit()
    except IntegrityError:
        settings3: Settings = request.app.state.settings
        session_data3 = (
            await get_session(request.app.state.redis, session_cookie, settings3.secret_key)
            if session_cookie
            else None
        )
        real_csrf3 = session_data3.get("csrf_token", "") if session_data3 else ""
        return _render_editor(
            request,
            yaml_text=yaml_text,
            errors=[
                f"A criteria named '{config.metadata.name}' already exists. Use a unique name."
            ],
            csrf_token=real_csrf3,
            user=user,
            status_code=409,
        )

    logger.info(
        "criteria.created",
        group_id=str(group_id),
        name=config.metadata.name,
        user_id=str(user.id),
    )
    return RedirectResponse(url=f"/criteria/{group_id}", status_code=303)


# ---------------------------------------------------------------------------
# POST /api/criteria/{group_id}/versions  (save new immutable version)
# ---------------------------------------------------------------------------


@router.post("/api/criteria/{group_id}/versions")
async def save_criteria_version(
    request: Request,
    group_id: uuid.UUID,
    yaml_text: str = Form(...),
    csrf_token: str = Form(...),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    settings: Settings = request.app.state.settings

    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(select(CriteriaGroup).where(CriteriaGroup.id == group_id))
        group = result.scalar_one_or_none()

    if not await _check_csrf(request, csrf_token, session_cookie):
        logger.warning("criteria.save_version.csrf_failed", user_id=str(user.id))
        session_data = (
            await get_session(request.app.state.redis, session_cookie, settings.secret_key)
            if session_cookie
            else None
        )
        real_csrf = session_data.get("csrf_token", "") if session_data else ""
        return _render_editor(
            request,
            group=group,
            yaml_text=yaml_text,
            errors=["Invalid form submission. Please try again."],
            csrf_token=real_csrf,
            user=user,
            status_code=400,
        )

    if group is None:
        return _render_editor(
            request,
            yaml_text=yaml_text,
            errors=["Criteria group not found."],
            csrf_token=csrf_token,
            user=user,
            status_code=404,
        )

    config, errors = validate_criteria_yaml(yaml_text)
    if errors or config is None:
        session_data2 = (
            await get_session(request.app.state.redis, session_cookie, settings.secret_key)
            if session_cookie
            else None
        )
        real_csrf2 = session_data2.get("csrf_token", "") if session_data2 else ""
        async with AsyncSession(request.app.state.engine) as db2:
            v_result = await db2.execute(
                select(CriteriaVersion)
                .where(CriteriaVersion.group_id == group_id)
                .order_by(CriteriaVersion.version.desc())
            )
            versions = list(v_result.scalars().all())
        return _render_editor(
            request,
            group=group,
            yaml_text=yaml_text,
            versions=versions,
            errors=errors,
            csrf_token=real_csrf2,
            user=user,
            status_code=422,
        )

    snapshot = config.model_dump()
    async with AsyncSession(request.app.state.engine) as db3:
        count_result = await db3.execute(
            select(func.count())
            .select_from(CriteriaVersion)
            .where(CriteriaVersion.group_id == group_id)
        )
        next_version = (count_result.scalar() or 0) + 1

        version = CriteriaVersion(
            group_id=group_id,
            version=next_version,
            config_snapshot=snapshot,
            is_active=True,
            created_by=user.id,
        )
        db3.add(version)

        audit = RecordAuditLog(
            user_id=user.id,
            action="criteria_save",
            resource_type="criteria_version",
            resource_id=str(version.id),
            diff={
                "group_id": str(group_id),
                "version": next_version,
                "name": config.metadata.name,
            },
        )
        db3.add(audit)

        group.display_name = config.metadata.display_name
        group.description = config.metadata.description
        group.tags = config.metadata.tags
        db3.add(group)

        await db3.commit()

    logger.info(
        "criteria.version_saved",
        group_id=str(group_id),
        version=next_version,
        user_id=str(user.id),
    )
    return RedirectResponse(url=f"/criteria/{group_id}", status_code=303)


# ---------------------------------------------------------------------------
# GET /api/criteria/{group_id}/versions  (version history HTMX partial)
# ---------------------------------------------------------------------------


@router.get("/api/criteria/{group_id}/versions", response_class=HTMLResponse)
async def list_criteria_versions(
    request: Request,
    group_id: uuid.UUID,
    user: User = Depends(require_operator),
) -> HTMLResponse:
    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(
            select(CriteriaVersion)
            .where(CriteriaVersion.group_id == group_id)
            .order_by(CriteriaVersion.version.desc())
        )
        versions = list(result.scalars().all())

    return templates.TemplateResponse(
        request,
        "criteria/version_history.html",
        {"versions": versions, "group_id": group_id},
    )
