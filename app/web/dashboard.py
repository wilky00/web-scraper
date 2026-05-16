# ABOUTME: Dashboard page (GET /). Shows recent jobs + record counts by status.
# ABOUTME: Requires a valid session; unauthenticated requests trigger redirect to /login.
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
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

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(require_operator),
) -> HTMLResponse:
    settings: Settings = request.app.state.settings
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = ""
    if session_cookie:
        session_data = await get_session(
            request.app.state.redis, session_cookie, settings.secret_key
        )
        if session_data:
            csrf_token = session_data.get("csrf_token", "")

    async with AsyncSession(request.app.state.engine) as db:
        # Record counts grouped by status
        counts_result = await db.execute(
            select(BusinessRecord.status, func.count(BusinessRecord.id)).group_by(
                BusinessRecord.status
            )
        )
        record_counts: dict[str, int] = {row[0]: row[1] for row in counts_result.all()}

        # Recent 5 jobs with connector + criteria names via joined subqueries
        jobs_result = await db.execute(
            select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(5)
        )
        recent_jobs = list(jobs_result.scalars().all())

        # Resolve connector and criteria names
        connector_ids = {j.connector_id for j in recent_jobs}
        criteria_ids = {j.criteria_version_id for j in recent_jobs}

        connector_names: dict[uuid.UUID, str] = {}
        criteria_names: dict[uuid.UUID, str] = {}

        if connector_ids:
            conn_result = await db.execute(
                select(Connector).where(Connector.id.in_(list(connector_ids)))
            )
            for c in conn_result.scalars().all():
                connector_names[c.id] = c.name

        if criteria_ids:
            cv_result = await db.execute(
                select(CriteriaVersion).where(CriteriaVersion.id.in_(list(criteria_ids)))
            )
            cv_list = list(cv_result.scalars().all())
            group_ids = {cv.group_id for cv in cv_list}

            if group_ids:
                grp_result = await db.execute(
                    select(CriteriaGroup).where(CriteriaGroup.id.in_(list(group_ids)))
                )
                group_map = {g.id: g for g in grp_result.scalars().all()}
                for cv in cv_list:
                    grp = group_map.get(cv.group_id)
                    criteria_names[cv.id] = grp.display_name if grp else "—"

    total_records = sum(record_counts.values())

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "csrf_token": csrf_token,
            "record_counts": record_counts,
            "total_records": total_records,
            "recent_jobs": recent_jobs,
            "connector_names": connector_names,
            "criteria_names": criteria_names,
        },
    )
