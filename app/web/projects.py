# ABOUTME: Web routes for project list, creation form, and detail page (jobs + API key management).
# ABOUTME: Project keys are generated/revoked via HTMX calling the /api/projects/ endpoints.
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.connector import Connector
from app.models.criteria import CriteriaGroup, CriteriaVersion
from app.models.job import CrawlJob
from app.models.project import Project, ProjectApiKey
from app.models.user import User
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


def _key_to_dict(k: ProjectApiKey) -> dict[str, Any]:
    return {
        "id": str(k.id),
        "label": k.label,
        "scopes": k.scopes,
        "created_at": k.created_at.strftime("%Y-%m-%d %H:%M") if k.created_at else "—",
        "revoked": k.revoked_at is not None,
    }


@router.get("/projects", response_class=HTMLResponse)
async def projects_list(
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(select(Project).order_by(Project.created_at.desc()))
        projects_orm = list(result.scalars().all())

        projects = []
        for p in projects_orm:
            jc = (
                await db.execute(
                    select(func.count()).select_from(CrawlJob).where(CrawlJob.project_id == p.id)
                )
            ).scalar() or 0
            kc = (
                await db.execute(
                    select(func.count())
                    .select_from(ProjectApiKey)
                    .where(
                        ProjectApiKey.project_id == p.id,
                        ProjectApiKey.revoked_at.is_(None),
                    )
                )
            ).scalar() or 0
            tc = (
                await db.execute(
                    select(func.count())
                    .select_from(CriteriaGroup)
                    .where(
                        CriteriaGroup.project_id == p.id,
                        CriteriaGroup.is_active.is_(True),
                    )
                )
            ).scalar() or 0
            projects.append(
                {
                    "id": str(p.id),
                    "name": p.name,
                    "description": p.description or "",
                    "created_at": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "—",
                    "job_count": jc,
                    "key_count": kc,
                    "template_count": tc,
                    "has_api_key": kc > 0,
                    "is_default": p.name == "Default",
                }
            )

    return templates.TemplateResponse(
        request,
        "projects/list.html",
        {"user": user, "csrf_token": csrf_token, "projects": projects},
    )


@router.get("/projects/new", response_class=HTMLResponse)
async def project_new(
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    return templates.TemplateResponse(
        request,
        "projects/new.html",
        {"user": user, "csrf_token": csrf_token},
    )


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(
    project_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    try:
        parsed_id = uuid.UUID(project_id)
    except ValueError:
        return HTMLResponse("Project not found", status_code=404)

    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        project: Project | None = await db.get(Project, parsed_id)
        if project is None:
            return HTMLResponse("Project not found", status_code=404)

        jobs_result = await db.execute(
            select(CrawlJob)
            .where(CrawlJob.project_id == parsed_id)
            .order_by(CrawlJob.created_at.desc())
            .limit(20)
        )
        jobs_orm = list(jobs_result.scalars().all())

        connector_ids = {j.connector_id for j in jobs_orm}
        criteria_ids = {j.criteria_version_id for j in jobs_orm}

        connector_names: dict[str, str] = {}
        if connector_ids:
            conn_result = await db.execute(select(Connector).where(Connector.id.in_(connector_ids)))
            for c in conn_result.scalars():
                connector_names[str(c.id)] = c.name

        criteria_names: dict[str, str] = {}
        if criteria_ids:
            crit_result = await db.execute(
                select(CriteriaVersion).where(CriteriaVersion.id.in_(criteria_ids))
            )
            for cv in crit_result.scalars():
                criteria_names[str(cv.id)] = f"v{cv.version}"

        jobs = [
            {
                "id": str(j.id),
                "id_short": str(j.id)[:8],
                "status": j.status,
                "connector_name": connector_names.get(str(j.connector_id), "—"),
                "criteria_name": criteria_names.get(str(j.criteria_version_id), "—"),
                "created_at": j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else "—",
            }
            for j in jobs_orm
        ]

        keys_result = await db.execute(
            select(ProjectApiKey)
            .where(ProjectApiKey.project_id == parsed_id)
            .order_by(ProjectApiKey.created_at.desc())
        )
        keys = [_key_to_dict(k) for k in keys_result.scalars().all()]

    return templates.TemplateResponse(
        request,
        "projects/detail.html",
        {
            "user": user,
            "csrf_token": csrf_token,
            "project": {
                "id": str(project.id),
                "name": project.name,
                "description": project.description,
                "created_at": (
                    project.created_at.strftime("%Y-%m-%d %H:%M") if project.created_at else "—"
                ),
            },
            "jobs": jobs,
            "keys": keys,
        },
    )
