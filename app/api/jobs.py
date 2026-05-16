# ABOUTME: Jobs API endpoints — create, enqueue, and control crawl jobs.
# ABOUTME: Includes cancel/pause/resume endpoints used by the job detail UI via HTMX.
from __future__ import annotations

import asyncio
import secrets
import uuid
from typing import Any

import redis
import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import JSONResponse, Response
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.connector import Connector
from app.models.criteria import CriteriaVersion
from app.models.job import CrawlJob
from app.models.user import User
from app.settings import Settings
from app.worker.persist import log_crawl_event

logger = structlog.get_logger(__name__)

router = APIRouter()


def _enqueue_rq(redis_url: str, job_id: uuid.UUID) -> str:
    """Enqueue run_crawl_job on the default RQ queue. Sync — call via asyncio.to_thread."""
    conn = redis.from_url(redis_url)
    try:
        q = Queue(connection=conn)
        rq_job = q.enqueue("app.jobs.tasks.run_crawl_job", str(job_id))
        return rq_job.id
    finally:
        conn.close()


@router.post("/api/jobs", status_code=201)
async def create_job(
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    body: dict[str, Any] = await request.json()
    connector_id_str = body.get("connector_id")
    criteria_version_id_str = body.get("criteria_version_id")

    if not connector_id_str or not criteria_version_id_str:
        return JSONResponse(
            {"error": "connector_id and criteria_version_id are required"}, status_code=422
        )

    try:
        connector_id = uuid.UUID(connector_id_str)
        criteria_version_id = uuid.UUID(criteria_version_id_str)
    except ValueError:
        return JSONResponse({"error": "Invalid UUID format"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        connector: Connector | None = await db.get(Connector, connector_id)
        if connector is None:
            return JSONResponse({"error": "Connector not found"}, status_code=404)

        criteria_version: CriteriaVersion | None = await db.get(
            CriteriaVersion, criteria_version_id
        )
        if criteria_version is None:
            return JSONResponse({"error": "CriteriaVersion not found"}, status_code=404)

        crawl_job = CrawlJob(
            connector_id=connector_id,
            criteria_version_id=criteria_version_id,
            status="queued",
            config_snapshot={
                "criteria": criteria_version.config_snapshot,
                "connector": connector.config_snapshot,
            },
            created_by=user.id,
        )
        db.add(crawl_job)
        await db.flush()
        job_id = crawl_job.id
        await db.commit()

    settings: Settings = request.app.state.settings
    try:
        rq_job_id = await asyncio.to_thread(_enqueue_rq, settings.redis_url, job_id)
        logger.info("job.enqueued", job_id=str(job_id), rq_job_id=rq_job_id)
    except Exception as exc:
        logger.error("job.enqueue_failed", job_id=str(job_id), error=str(exc))
        return JSONResponse(
            {"job_id": str(job_id), "status": "queued", "warning": "RQ enqueue failed"},
            status_code=201,
        )

    return JSONResponse(
        {"job_id": str(job_id), "status": "queued", "rq_job_id": rq_job_id},
        status_code=201,
    )


@router.get("/api/jobs/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    try:
        parsed_id = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse({"error": "Invalid job ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        job: CrawlJob | None = await db.get(CrawlJob, parsed_id)
        if job is None:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        return JSONResponse(
            {
                "job_id": str(job.id),
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "connector_id": str(job.connector_id),
                "criteria_version_id": str(job.criteria_version_id),
            }
        )


# ── Job controls (pause / resume / cancel) ───────────────────────────────────


async def _check_csrf(
    request: Request,
    form_csrf: str,
    session_cookie: str | None,
) -> bool:
    """Return True if the form CSRF token matches the session CSRF token."""
    if not session_cookie:
        return False
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if not session_data:
        return False
    expected = session_data.get("csrf_token", "")
    return bool(expected) and secrets.compare_digest(form_csrf, expected)


@router.post("/api/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    """Request cancellation of a queued, running, or paused job."""
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_id = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse({"error": "Invalid job ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        job: CrawlJob | None = await db.get(CrawlJob, parsed_id)
        if job is None:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        if job.status not in ("queued", "running", "paused"):
            return JSONResponse(
                {"error": f"Cannot cancel a job with status '{job.status}'"}, status_code=409
            )
        job.status = "cancel_requested"
        await log_crawl_event(db, parsed_id, "cancel_requested", "Cancellation requested by user")
        await db.commit()

    logger.info("job.cancel_requested", job_id=job_id, user_id=str(user.id))
    return Response(status_code=200, headers={"HX-Redirect": f"/jobs/{job_id}"})


@router.post("/api/jobs/{job_id}/pause")
async def pause_job(
    job_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    """Request that a running job pause after its current record."""
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_id = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse({"error": "Invalid job ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        job: CrawlJob | None = await db.get(CrawlJob, parsed_id)
        if job is None:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        if job.status != "running":
            return JSONResponse(
                {"error": f"Cannot pause a job with status '{job.status}'"}, status_code=409
            )
        job.status = "paused"
        await log_crawl_event(db, parsed_id, "pause_requested", "Pause requested by user")
        await db.commit()

    logger.info("job.pause_requested", job_id=job_id, user_id=str(user.id))
    return Response(status_code=200, headers={"HX-Redirect": f"/jobs/{job_id}"})


@router.post("/api/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    """Re-enqueue a paused job to run from the beginning."""
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_id = uuid.UUID(job_id)
    except ValueError:
        return JSONResponse({"error": "Invalid job ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        job: CrawlJob | None = await db.get(CrawlJob, parsed_id)
        if job is None:
            return JSONResponse({"error": "Job not found"}, status_code=404)
        if job.status != "paused":
            return JSONResponse(
                {"error": f"Cannot resume a job with status '{job.status}'"}, status_code=409
            )
        job.status = "queued"
        await log_crawl_event(db, parsed_id, "job_resumed", "Job resumed by user")
        await db.commit()

    settings: Settings = request.app.state.settings
    try:
        rq_job_id = await asyncio.to_thread(_enqueue_rq, settings.redis_url, parsed_id)
        logger.info("job.resumed", job_id=job_id, rq_job_id=rq_job_id, user_id=str(user.id))
    except Exception as exc:
        logger.error("job.resume_enqueue_failed", job_id=job_id, error=str(exc))

    return Response(status_code=200, headers={"HX-Redirect": f"/jobs/{job_id}"})
