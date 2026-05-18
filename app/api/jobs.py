# ABOUTME: Jobs API endpoints — create, enqueue, and control crawl jobs.
# ABOUTME: Includes cancel/pause/resume endpoints used by the job detail UI.
from __future__ import annotations

import asyncio
import copy
import json
import secrets
import uuid
from typing import Any

import redis
import structlog
from fastapi import APIRouter, Cookie, Depends, Request
from fastapi.responses import JSONResponse, Response
from rq import Queue
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.connector import Connector
from app.models.criteria import CriteriaVersion
from app.models.job import CrawlJob, CrawlJobEvent
from app.models.project import Project
from app.models.record import BusinessRecord
from app.models.user import User
from app.settings import Settings
from app.worker.persist import log_crawl_event

logger = structlog.get_logger(__name__)

router = APIRouter()


_TEST_REDIS_TTL = 900  # 15 minutes
_CRAWL_OVERRIDE_KEYS = {"max_pages_per_job", "delay_between_requests_ms", "max_depth"}


def _enqueue_rq(redis_url: str, job_id: uuid.UUID) -> str:
    """Enqueue run_crawl_job on the default RQ queue. Sync — call via asyncio.to_thread."""
    conn = redis.from_url(redis_url)
    try:
        q = Queue(connection=conn)
        rq_job = q.enqueue("app.jobs.tasks.run_crawl_job", str(job_id))
        return rq_job.id
    finally:
        conn.close()


def _enqueue_test_rq(
    redis_url: str,
    test_id: str,
    criteria_version_id: str,
    connector_id: str,
    config_overrides: dict[str, Any],
) -> str:
    """Enqueue run_test_job on the default RQ queue with a 90-second timeout."""
    conn = redis.from_url(redis_url)
    try:
        q = Queue(connection=conn)
        rq_job = q.enqueue(
            "app.jobs.test_runner.run_test_job",
            test_id,
            criteria_version_id,
            connector_id,
            config_overrides,
            job_timeout=90,
        )
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

    # Extract and validate optional config overrides
    raw_config: dict[str, Any] = body.get("config") or {}
    crawl_overrides: dict[str, Any] = {}
    for key in _CRAWL_OVERRIDE_KEYS:
        if key in raw_config:
            try:
                crawl_overrides[key] = int(raw_config[key])
            except (TypeError, ValueError):
                return JSONResponse({"error": f"config.{key} must be an integer"}, status_code=422)

    max_results_override: int | None = None
    if "max_results" in raw_config:
        try:
            max_results_override = int(raw_config["max_results"])
            if max_results_override < 1:
                raise ValueError
        except (TypeError, ValueError):
            return JSONResponse(
                {"error": "config.max_results must be a positive integer"}, status_code=422
            )

    project_id: uuid.UUID | None = None
    project_id_str = body.get("project_id")
    if project_id_str:
        try:
            project_id = uuid.UUID(project_id_str)
        except ValueError:
            return JSONResponse({"error": "Invalid project_id format"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        connector: Connector | None = await db.get(Connector, connector_id)
        if connector is None:
            return JSONResponse({"error": "Connector not found"}, status_code=404)

        criteria_version: CriteriaVersion | None = await db.get(
            CriteriaVersion, criteria_version_id
        )
        if criteria_version is None:
            return JSONResponse({"error": "CriteriaVersion not found"}, status_code=404)

        if project_id is not None:
            project: Project | None = await db.get(Project, project_id)
            if project is None:
                return JSONResponse({"error": "Project not found"}, status_code=404)

        criteria_snap: dict[str, Any] = copy.deepcopy(criteria_version.config_snapshot or {})
        if max_results_override is not None:
            source: dict[str, Any] = criteria_snap.setdefault("source", {})
            source["max_results"] = max_results_override

        config_snapshot: dict[str, Any] = {
            "criteria": criteria_snap,
            "connector": connector.config_snapshot,
        }
        if crawl_overrides:
            config_snapshot["crawl_overrides"] = crawl_overrides

        crawl_job = CrawlJob(
            connector_id=connector_id,
            criteria_version_id=criteria_version_id,
            status="queued",
            config_snapshot=config_snapshot,
            created_by=user.id,
            project_id=project_id,
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

        count_result = await db.execute(
            select(func.count()).where(BusinessRecord.job_id == parsed_id)
        )
        record_count: int = count_result.scalar() or 0

        events_result = await db.execute(
            select(CrawlJobEvent)
            .where(CrawlJobEvent.job_id == parsed_id)
            .order_by(CrawlJobEvent.created_at.asc())
        )
        raw_events = list(events_result.scalars())
        events_data = [
            {
                "event_type": e.event_type,
                "message": e.message,
                "created_at": e.created_at.strftime("%H:%M:%S") if e.created_at else "--",
            }
            for e in raw_events
        ]

        return JSONResponse(
            {
                "job_id": str(job.id),
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "connector_id": str(job.connector_id),
                "criteria_version_id": str(job.criteria_version_id),
                "record_count": record_count,
                "events": events_data,
            }
        )


# -- Job controls (pause / resume / cancel) -----------------------------------


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
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    """Request cancellation of a queued, running, or paused job."""
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass
    form_csrf = body.get("csrf_token", "")

    if not await _check_csrf(request, form_csrf, session_cookie):
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
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    """Request that a running job pause after its current record."""
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass
    form_csrf = body.get("csrf_token", "")

    if not await _check_csrf(request, form_csrf, session_cookie):
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
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    """Re-enqueue a paused job to run from the beginning."""
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass
    form_csrf = body.get("csrf_token", "")

    if not await _check_csrf(request, form_csrf, session_cookie):
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


# -- Test run endpoints -------------------------------------------------------


@router.post("/api/jobs/test", status_code=202)
async def create_test_run(
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    """Start an ephemeral 3-result test crawl. Results are stored in Redis for 15 minutes."""
    body: dict[str, Any] = await request.json()
    connector_id_str = body.get("connector_id")
    criteria_version_id_str = body.get("criteria_version_id")

    if not connector_id_str or not criteria_version_id_str:
        return JSONResponse(
            {"error": "connector_id and criteria_version_id are required"}, status_code=422
        )

    try:
        uuid.UUID(connector_id_str)
        uuid.UUID(criteria_version_id_str)
    except ValueError:
        return JSONResponse({"error": "Invalid UUID format"}, status_code=422)

    raw_config: dict[str, Any] = body.get("config") or {}
    config_overrides: dict[str, Any] = {}
    for key in _CRAWL_OVERRIDE_KEYS:
        if key in raw_config:
            try:
                config_overrides[key] = int(raw_config[key])
            except (TypeError, ValueError):
                return JSONResponse({"error": f"config.{key} must be an integer"}, status_code=422)

    test_id = str(uuid.uuid4())
    r = request.app.state.redis
    await r.set(
        f"test:{test_id}",
        json.dumps({"status": "queued", "results": [], "error": None}),
        ex=_TEST_REDIS_TTL,
    )

    settings: Settings = request.app.state.settings
    try:
        await asyncio.to_thread(
            _enqueue_test_rq,
            settings.redis_url,
            test_id,
            criteria_version_id_str,
            connector_id_str,
            config_overrides,
        )
        logger.info("test_run.enqueued", test_id=test_id)
    except Exception as exc:
        logger.error("test_run.enqueue_failed", test_id=test_id, error=str(exc))
        return JSONResponse(
            {"error": "Failed to enqueue test run — RQ unavailable"}, status_code=503
        )

    return JSONResponse({"test_id": test_id, "status": "queued"}, status_code=202)


@router.get("/api/jobs/test/{test_id}")
async def get_test_run(
    test_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    """Poll for the status and results of an ephemeral test run."""
    r = request.app.state.redis
    raw = await r.get(f"test:{test_id}")
    if raw is None:
        return JSONResponse({"error": "Test run not found or expired"}, status_code=404)

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return JSONResponse({"error": "Corrupted test run state"}, status_code=500)

    return JSONResponse(data)
