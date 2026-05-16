# ABOUTME: Jobs API endpoints — create and enqueue crawl jobs, retrieve job status.
# ABOUTME: POST /api/jobs creates a CrawlJob row and enqueues run_crawl_job via RQ.
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import redis
import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from rq import Queue
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.models.connector import Connector
from app.models.criteria import CriteriaVersion
from app.models.job import CrawlJob
from app.models.user import User
from app.settings import Settings

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
