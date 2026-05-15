# ABOUTME: Web UI route for the login page (GET /login).
# ABOUTME: Generates a CSRF token pair and sets the signed value as a cookie for the form.
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Cookie, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.auth.csrf import generate_form_csrf
from app.auth.session import SESSION_COOKIE, get_session
from app.settings import Settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    settings: Settings = request.app.state.settings

    if session_cookie:
        session_data = await get_session(
            request.app.state.redis, session_cookie, settings.secret_key
        )
        if session_data:
            return RedirectResponse(url="/", status_code=303)

    form_token, cookie_value = generate_form_csrf(settings.secret_key)
    resp = templates.TemplateResponse(
        request,
        "login.html",
        {"csrf_token": form_token, "error": "", "email_value": ""},
    )
    resp.set_cookie(
        "login_csrf",
        cookie_value,
        httponly=True,
        samesite="strict",
        max_age=3600,
        secure=(settings.environment == "production"),
    )
    return resp
