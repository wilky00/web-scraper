# ABOUTME: Projects API — create/list projects and manage project-scoped API keys.
# ABOUTME: All endpoints use session auth (operators only); keys are hashed with HMAC-SHA256.
from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.criteria import CriteriaGroup
from app.models.job import CrawlJob
from app.models.project import Project, ProjectApiKey
from app.models.record import BusinessRecord
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()

_VALID_SCOPES: set[str] = {"records:read", "records:write"}


async def _check_csrf(request: Request, form_csrf: str, session_cookie: str | None) -> bool:
    if not session_cookie:
        return False
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if not session_data:
        return False
    expected = session_data.get("csrf_token", "")
    return bool(expected) and secrets.compare_digest(form_csrf, expected)


def _project_to_dict(p: Project, job_count: int = 0, key_count: int = 0) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "job_count": job_count,
        "key_count": key_count,
    }


@router.get("/api/projects")
async def list_projects(
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(select(Project).order_by(Project.created_at.desc()))
        projects = list(result.scalars().all())

        project_data = []
        for p in projects:
            job_count_result = await db.execute(
                select(func.count()).select_from(CrawlJob).where(CrawlJob.project_id == p.id)
            )
            job_count = job_count_result.scalar() or 0

            key_count_result = await db.execute(
                select(func.count())
                .select_from(ProjectApiKey)
                .where(
                    ProjectApiKey.project_id == p.id,
                    ProjectApiKey.revoked_at.is_(None),
                )
            )
            key_count = key_count_result.scalar() or 0
            project_data.append(_project_to_dict(p, job_count, key_count))

    return JSONResponse({"data": project_data, "errors": []})


@router.post("/api/projects", status_code=201)
async def create_project(
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    name: str = Form(default=""),
    description: str = Form(default=""),
    user: User = Depends(require_operator),
) -> JSONResponse:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    name = name.strip()
    if not name:
        return JSONResponse({"error": "Project name is required"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        project = Project(
            name=name,
            description=description.strip() or None,
            created_by=user.id,
        )
        db.add(project)
        await db.commit()
        await db.refresh(project)
        project_id = project.id

    logger.info("project.created", project_id=str(project_id), user_id=str(user.id))
    return JSONResponse(
        {"data": _project_to_dict(project), "errors": []},
        status_code=201,
        headers={"HX-Redirect": "/projects"},
    )


@router.post("/api/projects/{project_id}/keys", status_code=201)
async def create_project_key(
    project_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    label: str = Form(default=""),
    scopes: list[str] = Form(default=[]),
    user: User = Depends(require_operator),
) -> JSONResponse:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_project_id = uuid.UUID(project_id)
    except ValueError:
        return JSONResponse({"error": "Invalid project ID"}, status_code=422)

    label = label.strip()
    if not label:
        return JSONResponse({"error": "Key label is required"}, status_code=422)

    invalid = sorted(set(scopes) - _VALID_SCOPES)
    if invalid:
        return JSONResponse({"error": f"Invalid scopes: {invalid}"}, status_code=422)
    if not scopes:
        return JSONResponse({"error": "At least one scope is required"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        project: Project | None = await db.get(Project, parsed_project_id)
        if project is None:
            return JSONResponse({"error": "Project not found"}, status_code=404)

        settings: Settings = request.app.state.settings
        plaintext = secrets.token_urlsafe(32)
        key_hash = hmac.new(
            settings.api_token_secret.encode(), plaintext.encode(), hashlib.sha256
        ).hexdigest()

        proj_key = ProjectApiKey(
            project_id=parsed_project_id,
            label=label,
            key_hash=key_hash,
            scopes=scopes,
        )
        db.add(proj_key)
        await db.commit()
        await db.refresh(proj_key)
        key_id = proj_key.id

    logger.info("project_key.created", project_id=project_id, key_id=str(key_id))
    return JSONResponse(
        {
            "data": {
                "id": str(key_id),
                "label": label,
                "scopes": scopes,
                "token": plaintext,
            },
            "errors": [],
        },
        status_code=201,
    )


@router.delete("/api/projects/{project_id}/keys/{key_id}")
async def revoke_project_key(
    project_id: str,
    key_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_project_id = uuid.UUID(project_id)
        parsed_key_id = uuid.UUID(key_id)
    except ValueError:
        return JSONResponse({"error": "Invalid ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        proj_key: ProjectApiKey | None = await db.get(ProjectApiKey, parsed_key_id)
        if proj_key is None or proj_key.project_id != parsed_project_id:
            return JSONResponse({"error": "Key not found"}, status_code=404)

        proj_key.revoked_at = datetime.now(tz=UTC)
        await db.commit()

    logger.info("project_key.revoked", project_id=project_id, key_id=key_id)
    return Response(status_code=204)


@router.patch("/api/projects/{project_id}")
async def update_project(
    project_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    name: str = Form(default=""),
    description: str = Form(default=""),
    user: User = Depends(require_operator),
) -> JSONResponse:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_project_id = uuid.UUID(project_id)
    except ValueError:
        return JSONResponse({"error": "Invalid project ID"}, status_code=422)

    name = name.strip()
    if not name:
        return JSONResponse({"error": "Project name is required"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        project: Project | None = await db.get(Project, parsed_project_id)
        if project is None:
            return JSONResponse({"error": "Project not found"}, status_code=404)

        if project.name == "Default" and name != "Default":
            return JSONResponse({"error": "Cannot rename the Default project"}, status_code=409)

        project.name = name
        project.description = description.strip() or None
        await db.commit()
        await db.refresh(project)

    logger.info("project.updated", project_id=project_id, user_id=str(user.id))
    return JSONResponse({"data": _project_to_dict(project), "errors": []})


@router.delete("/api/projects/{project_id}")
async def delete_project(
    project_id: str,
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> Response:
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_project_id = uuid.UUID(project_id)
    except ValueError:
        return JSONResponse({"error": "Invalid project ID"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        project: Project | None = await db.get(Project, parsed_project_id)
        if project is None:
            return JSONResponse({"error": "Project not found"}, status_code=404)

        if project.name == "Default":
            return JSONResponse({"error": "Cannot delete the Default project"}, status_code=409)

        # Soft-delete all records whose jobs belong to this project
        job_ids_result = await db.execute(
            select(CrawlJob.id).where(CrawlJob.project_id == parsed_project_id)
        )
        job_ids = [row[0] for row in job_ids_result.all()]

        if job_ids:
            records_result = await db.execute(
                select(BusinessRecord).where(BusinessRecord.job_id.in_(job_ids))
            )
            for record in records_result.scalars():
                record.status = "deleted"

            # Unscope the jobs (keep them, just remove project association)
            jobs_result = await db.execute(
                select(CrawlJob).where(CrawlJob.project_id == parsed_project_id)
            )
            for job in jobs_result.scalars():
                job.project_id = None

        # Unscope any criteria groups tagged to this project
        groups_result = await db.execute(
            select(CriteriaGroup).where(CriteriaGroup.project_id == parsed_project_id)
        )
        for group in groups_result.scalars():
            group.project_id = None

        await db.delete(project)
        await db.commit()

    logger.info("project.deleted", project_id=project_id, user_id=str(user.id))
    return Response(status_code=204)


@router.post("/api/projects/{project_id}/move-jobs")
async def move_project_jobs(
    project_id: str,
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=422)

    session_cookie = request.cookies.get(SESSION_COOKIE)
    if not await _check_csrf(request, body.get("csrf_token", ""), session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    try:
        parsed_source_id = uuid.UUID(project_id)
        parsed_target_id = uuid.UUID(body.get("target_project_id", ""))
    except (ValueError, AttributeError):
        return JSONResponse({"error": "Invalid project ID"}, status_code=422)

    if parsed_source_id == parsed_target_id:
        return JSONResponse({"error": "Source and target projects must differ"}, status_code=422)

    async with AsyncSession(request.app.state.engine) as db:
        source: Project | None = await db.get(Project, parsed_source_id)
        target: Project | None = await db.get(Project, parsed_target_id)
        if source is None or target is None:
            return JSONResponse({"error": "Project not found"}, status_code=404)

        jobs_result = await db.execute(
            select(CrawlJob).where(CrawlJob.project_id == parsed_source_id)
        )
        moved = 0
        for job in jobs_result.scalars():
            job.project_id = parsed_target_id
            moved += 1

        await db.commit()

    logger.info(
        "project.jobs_moved",
        source_id=project_id,
        target_id=str(parsed_target_id),
        moved=moved,
        user_id=str(user.id),
    )
    return JSONResponse({"moved": moved, "errors": []})
