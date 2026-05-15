# ABOUTME: Dashboard page (GET /). Stub for Phase 2 — exists to validate auth redirect behavior.
# ABOUTME: Requires a valid session; unauthenticated requests trigger redirect to /login.
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
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

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "csrf_token": csrf_token},
    )
