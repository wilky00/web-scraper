# ABOUTME: Web routes for criteria management — list, new editor, and existing editor pages.
# ABOUTME: All pages require auth; CSRF token is pulled from session for form protection.
from __future__ import annotations

import uuid
from pathlib import Path

import structlog
import yaml
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.criteria import CriteriaGroup, CriteriaVersion
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger()

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


async def _get_csrf(request: Request, session_cookie: str | None) -> str:
    """Extract the CSRF token from the current session, or return empty string."""
    if not session_cookie:
        return ""
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if session_data is None:
        return ""
    return session_data.get("csrf_token", "")


# ---------------------------------------------------------------------------
# GET /criteria  (criteria list)
# ---------------------------------------------------------------------------


@router.get("/criteria", response_class=HTMLResponse)
async def criteria_list(
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        groups_result = await db.execute(
            select(CriteriaGroup).order_by(CriteriaGroup.display_name)
        )
        groups = list(groups_result.scalars().all())

        # Get version counts per group
        counts_result = await db.execute(
            select(CriteriaVersion.group_id, func.count().label("version_count"))
            .group_by(CriteriaVersion.group_id)
        )
        version_counts = {str(row.group_id): row.version_count for row in counts_result}

    groups_data = [
        {
            "id": str(g.id),
            "name": g.name,
            "display_name": g.display_name,
            "description": g.description,
            "tags": g.tags,
            "is_active": g.is_active,
            "version_count": version_counts.get(str(g.id), 0),
            "created_at": (
                g.created_at.isoformat() if hasattr(g, "created_at") and g.created_at else ""
            ),
        }
        for g in groups
    ]

    return templates.TemplateResponse(
        request,
        "criteria/list.html",
        {"groups": groups_data, "csrf_token": csrf_token, "user": user},
    )


# ---------------------------------------------------------------------------
# GET /criteria/new  (blank editor)
# ---------------------------------------------------------------------------


@router.get("/criteria/new", response_class=HTMLResponse)
async def criteria_new(
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    placeholder = (
        "metadata:\n"
        "  name: my-criteria\n"
        "  display_name: My Criteria\n"
        "  description: ''\n"
        "  tags: []\n"
        "source:\n"
        "  connector: fixture\n"
        "  max_results: 60\n"
    )

    return templates.TemplateResponse(
        request,
        "criteria/editor.html",
        {
            "group": None,
            "yaml_text": placeholder,
            "versions": [],
            "errors": [],
            "csrf_token": csrf_token,
            "user": user,
        },
    )


# ---------------------------------------------------------------------------
# GET /criteria/{group_id}  (editor with existing criteria)
# ---------------------------------------------------------------------------


@router.get("/criteria/{group_id}", response_class=HTMLResponse)
async def criteria_editor(
    request: Request,
    group_id: uuid.UUID,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        group_result = await db.execute(
            select(CriteriaGroup).where(CriteriaGroup.id == group_id)
        )
        group = group_result.scalar_one_or_none()

        if group is None:
            return RedirectResponse(url="/criteria", status_code=303)

        versions_result = await db.execute(
            select(CriteriaVersion)
            .where(CriteriaVersion.group_id == group_id)
            .order_by(CriteriaVersion.version.desc())
        )
        versions = list(versions_result.scalars().all())

    latest = versions[0] if versions else None
    yaml_text = (
        yaml.dump(
            latest.config_snapshot,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        if latest
        else ""
    )

    return templates.TemplateResponse(
        request,
        "criteria/editor.html",
        {
            "group": group,
            "yaml_text": yaml_text,
            "versions": versions,
            "errors": [],
            "csrf_token": csrf_token,
            "user": user,
        },
    )
