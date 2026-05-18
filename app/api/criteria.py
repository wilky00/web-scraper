# ABOUTME: Criteria API endpoints — validate YAML, create criteria groups, save immutable versions.
# ABOUTME: All mutating endpoints write an audit log entry. Validate is read-only (no audit needed).
from __future__ import annotations

import copy
import html as _html
import re
import secrets
import uuid
from pathlib import Path

import structlog
import yaml
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
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
from app.web.criteria import _ai_enabled

logger = structlog.get_logger()

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _validation_html(
    errors: list[str],
    *,
    parse_error_line: int | None = None,
    ai_hint: bool = False,
) -> str:
    """Return an HTML fragment for the HTMX validation result panel."""
    if not errors:
        return (
            '<div class="rounded-md bg-green-50 dark:bg-green-900/20 border border-green-200'
            " dark:border-green-800 p-4\">"
            '<p class="text-sm font-medium text-green-800 dark:text-green-300">'
            "Valid YAML — ready to save.</p></div>"
        )

    if parse_error_line is not None:
        # YAML syntax error — include line marker and an AI tip.
        line_marker = f'<span data-error-line="{parse_error_line}" class="hidden"></span>'
        detail_html = "".join(
            f'<p class="font-mono text-xs text-red-600 dark:text-red-400 break-all mt-1">'
            f"{_html.escape(err)}</p>"
            for err in errors
        )
        hint_html = (
            '<p class="mt-3 text-xs text-red-500 dark:text-red-400 italic">'
            "Tip: Paste your YAML into the AI Assistant below — it can help fix syntax errors."
            "</p>"
            if ai_hint
            else ""
        )
        return (
            '<div class="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200'
            f' dark:border-red-800 p-4">{line_marker}'
            '<p class="text-sm font-medium text-red-800 dark:text-red-300">'
            f"YAML syntax error on line {parse_error_line}</p>"
            f"{detail_html}{hint_html}</div>"
        )

    # Logic / Pydantic validation errors — field path in code, message as text.
    def _err_item(err: str) -> str:
        if ": " in err:
            path, msg = err.split(": ", 1)
            code_cls = "font-mono text-xs bg-red-100 dark:bg-red-900/40 px-1 rounded shrink-0"
            span_cls = "text-xs text-red-700 dark:text-red-400"
            return (
                '<li class="flex flex-wrap gap-x-2 items-baseline">'
                f'<code class="{code_cls}">{_html.escape(path)}</code>'
                f'<span class="{span_cls}">{_html.escape(msg)}</span></li>'
            )
        return (
            f'<li class="font-mono text-xs text-red-700 dark:text-red-400 break-all">'
            f"{_html.escape(err)}</li>"
        )

    items = "".join(_err_item(e) for e in errors)
    return (
        '<div class="rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200'
        " dark:border-red-800 p-4\">"
        '<p class="text-sm font-medium text-red-800 dark:text-red-300 mb-2">Validation errors</p>'
        f'<ul class="space-y-1.5">{items}</ul>'
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
    normalize: bool = Form(default=False),
    user: User = Depends(require_operator),
) -> HTMLResponse:
    # Step 1: YAML parse — extract line/column from parse errors.
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = (mark.line + 1) if mark is not None else None
        col = (mark.column + 1) if mark is not None else None
        problem = getattr(exc, "problem", None) or str(exc)
        detail = f"column {col}: {problem}" if col else problem
        return HTMLResponse(content=_validation_html([detail], parse_error_line=line, ai_hint=True))

    if not isinstance(parsed, dict):
        return HTMLResponse(
            content=_validation_html(
                [f"Criteria YAML must be a mapping, got {type(parsed).__name__}"],
                ai_hint=True,
            )
        )

    # Step 2: normalize (reformat) when requested by the manual Validate button.
    # The server validates against the normalized form but does not push it back to the editor.
    yaml_to_validate = yaml_text
    if normalize:
        yaml_to_validate = yaml.dump(
            parsed, sort_keys=False, allow_unicode=True, default_flow_style=False
        )

    # Step 3: Pydantic logic validation.
    _, errors = validate_criteria_yaml(yaml_to_validate)
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
            ai_enabled=_ai_enabled(request),
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
            ai_enabled=_ai_enabled(request),
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
            ai_enabled=_ai_enabled(request),
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
            ai_enabled=_ai_enabled(request),
            status_code=400,
        )

    if group is None:
        return _render_editor(
            request,
            yaml_text=yaml_text,
            errors=["Criteria group not found."],
            csrf_token=csrf_token,
            user=user,
            ai_enabled=_ai_enabled(request),
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
            ai_enabled=_ai_enabled(request),
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


@router.get("/api/criteria/{group_id}/yaml")
async def get_criteria_yaml(
    request: Request,
    group_id: uuid.UUID,
    user: User = Depends(require_operator),
) -> Response:
    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(
            select(CriteriaVersion)
            .where(CriteriaVersion.group_id == group_id)
            .order_by(CriteriaVersion.version.desc())
            .limit(1)
        )
        version = result.scalar_one_or_none()
    if version is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    yaml_text = yaml.dump(
        version.config_snapshot,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    return JSONResponse({"yaml": yaml_text})


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


# ---------------------------------------------------------------------------
# POST /api/criteria/{group_id}/delete  (soft delete)
# ---------------------------------------------------------------------------


@router.post("/api/criteria/{group_id}/delete")
async def delete_criteria(
    request: Request,
    group_id: uuid.UUID,
    csrf_token: str = Form(...),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        logger.warning("criteria.delete.csrf_failed", user_id=str(user.id))
        return JSONResponse({"error": "Invalid form submission."}, status_code=400)

    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(select(CriteriaGroup).where(CriteriaGroup.id == group_id))
        group = result.scalar_one_or_none()

        if group is None:
            return JSONResponse({"error": "Not found."}, status_code=404)

        if group.is_template:
            return JSONResponse(
                {"error": "Cannot delete a built-in template — clone it instead."},
                status_code=422,
            )

        group.is_active = False
        audit = RecordAuditLog(
            user_id=user.id,
            action="criteria_delete",
            resource_type="criteria_group",
            resource_id=str(group_id),
            diff={"group_id": str(group_id), "name": group.name},
        )
        db.add(audit)
        await db.commit()

    logger.info("criteria.deleted", group_id=str(group_id), user_id=str(user.id))
    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# POST /api/criteria/{group_id}/clone  (copy latest version to new group)
# ---------------------------------------------------------------------------


@router.post("/api/criteria/{group_id}/clone")
async def clone_criteria(
    request: Request,
    group_id: uuid.UUID,
    csrf_token: str = Form(...),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        logger.warning("criteria.clone.csrf_failed", user_id=str(user.id))
        return JSONResponse({"error": "Invalid form submission."}, status_code=400)

    async with AsyncSession(request.app.state.engine) as db:
        group_result = await db.execute(select(CriteriaGroup).where(CriteriaGroup.id == group_id))
        group = group_result.scalar_one_or_none()
        if group is None:
            return JSONResponse({"error": "Not found."}, status_code=404)

        version_result = await db.execute(
            select(CriteriaVersion)
            .where(CriteriaVersion.group_id == group_id)
            .order_by(CriteriaVersion.version.desc())
            .limit(1)
        )
        latest = version_result.scalar_one_or_none()

    if latest is None:
        return JSONResponse({"error": "No version to clone."}, status_code=404)

    base_name = group.name + "-copy"
    base_display = group.display_name + " (Copy)"
    source_desc = group.description
    source_tags = list(group.tags or [])

    new_group_id: uuid.UUID | None = None
    for attempt in range(5):
        candidate_name = base_name if attempt == 0 else f"{base_name}-{attempt + 1}"
        snapshot = copy.deepcopy(latest.config_snapshot)
        if "metadata" in snapshot and isinstance(snapshot["metadata"], dict):
            snapshot["metadata"]["name"] = candidate_name

        # Pre-generate the UUID so it's available without relying on flush
        candidate_id = uuid.uuid4()
        try:
            async with AsyncSession(request.app.state.engine) as db2:
                new_group = CriteriaGroup(
                    id=candidate_id,
                    name=candidate_name,
                    display_name=base_display,
                    description=source_desc,
                    tags=source_tags,
                    is_active=True,
                    is_template=False,
                )
                db2.add(new_group)

                new_version = CriteriaVersion(
                    group_id=candidate_id,
                    version=1,
                    config_snapshot=snapshot,
                    is_active=True,
                    created_by=user.id,
                )
                db2.add(new_version)

                audit = RecordAuditLog(
                    user_id=user.id,
                    action="criteria_clone",
                    resource_type="criteria_group",
                    resource_id=str(candidate_id),
                    diff={"source_group_id": str(group_id), "new_name": candidate_name},
                )
                db2.add(audit)
                await db2.commit()
            new_group_id = candidate_id
            break
        except IntegrityError:
            continue

    if new_group_id is None:
        return JSONResponse(
            {
                "error": (
                    "Could not create a unique name for the clone. Try renaming the original first."
                )
            },
            status_code=409,
        )

    logger.info(
        "criteria.cloned",
        source_id=str(group_id),
        new_id=str(new_group_id),
        user_id=str(user.id),
    )
    return Response(status_code=200, headers={"HX-Redirect": f"/criteria/{new_group_id}"})


# ---------------------------------------------------------------------------
# GET /api/criteria/{group_id}/versions/{version_id}/yaml
# ---------------------------------------------------------------------------


@router.get("/api/criteria/{group_id}/versions/{version_id}/yaml")
async def get_version_yaml(
    request: Request,
    group_id: uuid.UUID,
    version_id: uuid.UUID,
    user: User = Depends(require_operator),
) -> Response:
    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(
            select(CriteriaVersion).where(
                CriteriaVersion.id == version_id,
                CriteriaVersion.group_id == group_id,
            )
        )
        version = result.scalar_one_or_none()
    if version is None:
        return JSONResponse({"error": "Not found"}, status_code=404)
    yaml_text = yaml.dump(
        version.config_snapshot,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    return JSONResponse({"yaml": yaml_text})


# ---------------------------------------------------------------------------
# POST /api/criteria/{group_id}/save-as
# ---------------------------------------------------------------------------


@router.post("/api/criteria/{group_id}/save-as")
async def save_as_criteria(
    request: Request,
    group_id: uuid.UUID,
    yaml_text: str = Form(...),
    new_display_name: str = Form(...),
    csrf_token: str = Form(...),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        logger.warning("criteria.save_as.csrf_failed", user_id=str(user.id))
        return JSONResponse({"error": "Invalid form submission."}, status_code=400)

    config, errors = validate_criteria_yaml(yaml_text)
    if errors or config is None:
        return _render_editor(
            request,
            yaml_text=yaml_text,
            errors=errors,
            csrf_token=csrf_token,
            user=user,
            ai_enabled=_ai_enabled(request),
            status_code=422,
        )

    new_name = re.sub(r"[^a-z0-9]+", "-", new_display_name.strip().lower()).strip("-")
    display_name = new_display_name.strip()
    snapshot = config.model_dump()
    if "metadata" in snapshot and isinstance(snapshot["metadata"], dict):
        snapshot["metadata"]["name"] = new_name
        snapshot["metadata"]["display_name"] = display_name

    new_group_id = uuid.uuid4()
    try:
        async with AsyncSession(request.app.state.engine) as db:
            new_group = CriteriaGroup(
                id=new_group_id,
                name=new_name,
                display_name=display_name,
                description=config.metadata.description,
                tags=config.metadata.tags,
                is_active=True,
                is_template=False,
            )
            db.add(new_group)
            version = CriteriaVersion(
                group_id=new_group_id,
                version=1,
                config_snapshot=snapshot,
                is_active=True,
                created_by=user.id,
            )
            db.add(version)
            audit = RecordAuditLog(
                user_id=user.id,
                action="criteria_save_as",
                resource_type="criteria_group",
                resource_id=str(new_group_id),
                diff={"source_group_id": str(group_id), "new_name": new_name},
            )
            db.add(audit)
            await db.commit()
    except IntegrityError:
        return _render_editor(
            request,
            yaml_text=yaml_text,
            errors=[f"A criteria named '{new_name}' already exists. Use a different name."],
            csrf_token=csrf_token,
            user=user,
            ai_enabled=_ai_enabled(request),
            status_code=409,
        )

    logger.info(
        "criteria.saved_as",
        new_group_id=str(new_group_id),
        name=new_name,
        source_group_id=str(group_id),
        user_id=str(user.id),
    )
    return RedirectResponse(url=f"/criteria/{new_group_id}", status_code=303)
