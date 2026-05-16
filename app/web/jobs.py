# ABOUTME: Web routes for the job list page.
# ABOUTME: Requires auth; shows all crawl jobs ordered newest-first with status badges.
from __future__ import annotations

from pathlib import Path

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
from app.models.record import BusinessRecord
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger()

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


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_list(
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        jobs_result = await db.execute(
            select(CrawlJob).order_by(CrawlJob.created_at.desc())
        )
        jobs = list(jobs_result.scalars().all())

        # Load connector names
        connector_ids = {j.connector_id for j in jobs}
        connector_names: dict[str, str] = {}
        if connector_ids:
            conn_result = await db.execute(
                select(Connector).where(Connector.id.in_(connector_ids))
            )
            for c in conn_result.scalars():
                connector_names[str(c.id)] = c.name

        # Load criteria display names via criteria_version → criteria_group
        version_ids = {j.criteria_version_id for j in jobs}
        criteria_names: dict[str, str] = {}
        if version_ids:
            ver_result = await db.execute(
                select(CriteriaVersion).where(CriteriaVersion.id.in_(version_ids))
            )
            versions = list(ver_result.scalars())
            group_ids = {v.group_id for v in versions}
            group_result = await db.execute(
                select(CriteriaGroup).where(CriteriaGroup.id.in_(group_ids))
            )
            group_names = {str(g.id): g.display_name for g in group_result.scalars()}
            for v in versions:
                criteria_names[str(v.id)] = group_names.get(str(v.group_id), "—")

        # Record counts per job
        counts_result = await db.execute(
            select(BusinessRecord.job_id, func.count().label("cnt"))
            .where(BusinessRecord.job_id.in_([j.id for j in jobs]))
            .group_by(BusinessRecord.job_id)
        )
        record_counts: dict[str, int] = {str(row.job_id): row.cnt for row in counts_result}

    jobs_data = [
        {
            "id": str(j.id),
            "id_short": str(j.id)[:8],
            "status": j.status,
            "connector_name": connector_names.get(str(j.connector_id), "—"),
            "criteria_name": criteria_names.get(str(j.criteria_version_id), "—"),
            "record_count": record_counts.get(str(j.id), 0),
            "created_at": j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else "—",
        }
        for j in jobs
    ]

    return templates.TemplateResponse(
        request,
        "jobs/list.html",
        {"jobs": jobs_data, "csrf_token": csrf_token, "user": user},
    )
