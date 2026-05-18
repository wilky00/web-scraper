# ABOUTME: Web routes for job list and detail pages.
# ABOUTME: Includes HTMX partial endpoint for live event log polling on the detail page.
from __future__ import annotations

import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.config.models import CrawlConfig
from app.models.connector import Connector
from app.models.criteria import CriteriaGroup, CriteriaVersion
from app.models.job import CrawlJob, CrawlJobEvent
from app.models.project import Project
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


@router.get("/jobs/new", response_class=HTMLResponse)
async def new_job_form(
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        # Active connectors
        conn_result = await db.execute(
            select(Connector).where(Connector.enabled).order_by(Connector.name)
        )
        connectors = [
            {
                "id": str(c.id),
                "name": c.name,
                "connector_type": c.connector_type,
                "projects": c.config_snapshot.get("projects", []) if c.config_snapshot else [],
            }
            for c in conn_result.scalars()
        ]

        # Latest active version per criteria group
        # Subquery: max version number per group among active versions
        max_ver_subq = (
            select(
                CriteriaVersion.group_id,
                func.max(CriteriaVersion.version).label("max_version"),
            )
            .where(CriteriaVersion.is_active)
            .group_by(CriteriaVersion.group_id)
            .subquery()
        )
        cv_alias = aliased(CriteriaVersion)
        latest_result = await db.execute(
            select(cv_alias).join(
                max_ver_subq,
                (cv_alias.group_id == max_ver_subq.c.group_id)
                & (cv_alias.version == max_ver_subq.c.max_version),
            )
        )
        latest_versions: dict[str, str] = {}
        version_configs: dict[str, dict] = {}
        for v in latest_result.scalars():
            gid = str(v.group_id)
            latest_versions[gid] = str(v.id)
            snap = v.config_snapshot or {}
            source = snap.get("source") or {}
            crawl_snap = snap.get("crawl") or {}
            version_configs[gid] = {
                "max_results": source.get("max_results"),
                "max_depth": crawl_snap.get("max_depth"),
                "delay_ms": crawl_snap.get("delay_ms"),
            }

        groups_result = await db.execute(
            select(CriteriaGroup)
            .where(CriteriaGroup.is_active)
            .order_by(CriteriaGroup.display_name)
        )
        criteria_groups = [
            {
                "id": str(g.id),
                "display_name": g.display_name,
                "description": g.description or "",
                "tags": g.tags or [],
                "latest_version_id": latest_versions.get(str(g.id), ""),
                "project_id": str(g.project_id) if g.project_id else "",
                "config": version_configs.get(str(g.id), {}),
            }
            for g in groups_result.scalars()
            if str(g.id) in latest_versions
        ]

        projects_result = await db.execute(select(Project).order_by(Project.name))
        projects = [{"id": str(p.id), "name": p.name} for p in projects_result.scalars()]

    default_project = next((p for p in projects if p["name"] == "Default"), None)
    if default_project:
        default_project_id = default_project["id"]
    else:
        default_project_id = projects[0]["id"] if projects else ""

    # Default crawl config values for the form
    app_crawl: CrawlConfig = request.app.state.config.crawl
    default_config = {
        "max_pages_per_job": app_crawl.max_pages_per_job,
        "delay_between_requests_ms": app_crawl.delay_between_requests_ms,
        "max_depth": app_crawl.max_depth,
    }

    return templates.TemplateResponse(
        request,
        "jobs/new.html",
        {
            "connectors": connectors,
            "criteria_groups": criteria_groups,
            "default_config": default_config,
            "csrf_token": csrf_token,
            "user": user,
            "projects": projects,
            "default_project_id": default_project_id,
        },
    )


@router.get("/jobs", response_class=HTMLResponse)
async def jobs_list(
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        jobs_result = await db.execute(select(CrawlJob).order_by(CrawlJob.created_at.desc()))
        jobs = list(jobs_result.scalars().all())

        # Load connector names
        connector_ids = {j.connector_id for j in jobs}
        connector_names: dict[str, str] = {}
        if connector_ids:
            conn_result = await db.execute(select(Connector).where(Connector.id.in_(connector_ids)))
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


# ── Job detail ────────────────────────────────────────────────────────────────


async def _load_job_detail(
    db: AsyncSession, parsed_id: uuid.UUID
) -> tuple[CrawlJob, dict[str, object], list[dict[str, object]]] | None:
    """Load job + related data for the detail page. Returns None if job not found."""
    job: CrawlJob | None = await db.get(CrawlJob, parsed_id)
    if job is None:
        return None

    connector_names: dict[str, str] = {}
    conn_result = await db.execute(select(Connector).where(Connector.id == job.connector_id))
    conn = conn_result.scalar_one_or_none()
    if conn:
        connector_names[str(job.connector_id)] = conn.name

    criteria_names: dict[str, str] = {}
    ver_result = await db.execute(
        select(CriteriaVersion).where(CriteriaVersion.id == job.criteria_version_id)
    )
    ver = ver_result.scalar_one_or_none()
    if ver:
        group_result = await db.execute(
            select(CriteriaGroup).where(CriteriaGroup.id == ver.group_id)
        )
        grp = group_result.scalar_one_or_none()
        if grp:
            criteria_names[str(job.criteria_version_id)] = grp.display_name

    counts_result = await db.execute(select(func.count()).where(BusinessRecord.job_id == parsed_id))
    record_count: int = counts_result.scalar() or 0

    events_result = await db.execute(
        select(CrawlJobEvent)
        .where(CrawlJobEvent.job_id == parsed_id)
        .order_by(CrawlJobEvent.created_at.asc())
    )
    raw_events = list(events_result.scalars())

    job_data: dict[str, object] = {
        "id": str(job.id),
        "id_short": str(job.id)[:8],
        "status": job.status,
        "connector_name": connector_names.get(str(job.connector_id), "—"),
        "criteria_name": criteria_names.get(str(job.criteria_version_id), "—"),
        "record_count": record_count,
        "created_at": job.created_at.strftime("%Y-%m-%d %H:%M") if job.created_at else "—",
    }
    events_data: list[dict[str, object]] = [
        {
            "event_type": e.event_type,
            "message": e.message,
            "created_at": e.created_at.strftime("%H:%M:%S") if e.created_at else "—",
        }
        for e in raw_events
    ]
    return job, job_data, events_data


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(
    job_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    try:
        parsed_id = uuid.UUID(job_id)
    except ValueError:
        return HTMLResponse("Job not found", status_code=404)

    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    async with AsyncSession(request.app.state.engine) as db:
        result = await _load_job_detail(db, parsed_id)

    if result is None:
        return HTMLResponse("Job not found", status_code=404)

    _, job_data, events_data = result
    return templates.TemplateResponse(
        request,
        "jobs/detail.html",
        {"job": job_data, "events": events_data, "csrf_token": csrf_token, "user": user},
    )


@router.get("/jobs/{job_id}/events", response_class=HTMLResponse)
async def job_events_partial(
    job_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> Response:
    """HTMX partial — returns the events polling container for live polling."""
    try:
        parsed_id = uuid.UUID(job_id)
    except ValueError:
        return HTMLResponse("", status_code=404)

    async with AsyncSession(request.app.state.engine) as db:
        result = await _load_job_detail(db, parsed_id)

    if result is None:
        return HTMLResponse("", status_code=404)

    _, job_data, events_data = result
    return templates.TemplateResponse(
        request,
        "jobs/_events_poll.html",
        {"job": job_data, "events": events_data},
    )
