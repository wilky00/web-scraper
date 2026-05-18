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
from app.models.job import CrawlJob, CrawlJobEvent
from app.models.project import Project
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
        project_count = (
            await db.execute(select(func.count()).select_from(Project))
        ).scalar() or 0

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

        # Last 5 failed jobs
        failed_result = await db.execute(
            select(CrawlJob)
            .where(CrawlJob.status == "failed")
            .order_by(CrawlJob.created_at.desc())
            .limit(5)
        )
        failed_jobs_orm = list(failed_result.scalars().all())

        # Resolve connector and criteria names (union of recent + failed jobs)
        all_jobs = recent_jobs + failed_jobs_orm
        connector_ids = {j.connector_id for j in all_jobs}
        criteria_ids = {j.criteria_version_id for j in all_jobs}

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

        # For each failed job, get the latest event message as the failure reason
        failed_jobs: list[dict[str, object]] = []
        for j in failed_jobs_orm:
            evt = (
                await db.execute(
                    select(CrawlJobEvent)
                    .where(CrawlJobEvent.job_id == j.id)
                    .order_by(CrawlJobEvent.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            failed_jobs.append(
                {
                    "id": str(j.id),
                    "id_short": str(j.id)[:8],
                    "connector_name": connector_names.get(j.connector_id, "—"),
                    "criteria_name": criteria_names.get(j.criteria_version_id, "—"),
                    "created_at": j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else "—",
                    "error": evt.message if evt else "Unknown error",
                }
            )

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
            "failed_jobs": failed_jobs,
            "project_count": project_count,
        },
    )
