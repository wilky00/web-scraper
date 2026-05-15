# ABOUTME: Auth form-submission endpoints: POST /auth/login and POST /auth/logout.
# ABOUTME: Login validates CSRF, rate-limits by IP, verifies credentials, and sets a session cookie.
from __future__ import annotations

import secrets
from pathlib import Path

import structlog
from fastapi import APIRouter, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.csrf import generate_form_csrf, verify_form_csrf
from app.auth.hashing import verify_password
from app.auth.rate_limit import check_login_rate_limit
from app.auth.session import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_session,
    delete_session,
    get_session,
    set_session_cookie,
    sign_session_id,
)
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger()

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


def _render_login(
    request: Request, error: str = "", email_value: str = "", status_code: int = 200
) -> Response:
    settings: Settings = request.app.state.settings
    form_token, cookie_value = generate_form_csrf(settings.secret_key)
    resp = templates.TemplateResponse(
        request,
        "login.html",
        {"csrf_token": form_token, "error": error, "email_value": email_value},
        status_code=status_code,
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


@router.post("/auth/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    login_csrf_cookie: str | None = Cookie(default=None, alias="login_csrf"),
) -> Response:
    settings: Settings = request.app.state.settings

    csrf_valid = login_csrf_cookie and verify_form_csrf(
        csrf_token, login_csrf_cookie, settings.secret_key
    )
    if not csrf_valid:
        logger.warning("auth.login.csrf_failed", email=email)
        return _render_login(request, error="Invalid form submission. Please try again.")

    ip = (request.client.host if request.client else None) or "unknown"
    if not await check_login_rate_limit(request.app.state.redis, ip):
        logger.warning("auth.login.rate_limited", ip=ip)
        return _render_login(
            request,
            error="Too many login attempts. Please wait a moment before trying again.",
            email_value=email,
            status_code=429,
        )

    async with AsyncSession(request.app.state.engine) as db:
        result = await db.execute(select(User).where(User.email == email.lower().strip()))
        user = result.scalar_one_or_none()

    if user is None or user.hashed_password is None:
        logger.info("auth.login.invalid_credentials", email=email)
        return _render_login(
            request, error="Invalid email or password.", email_value=email, status_code=401
        )

    if not verify_password(password, user.hashed_password):
        logger.info("auth.login.invalid_credentials", email=email)
        return _render_login(
            request, error="Invalid email or password.", email_value=email, status_code=401
        )

    if not user.is_active or user.deleted_at is not None:
        logger.warning("auth.login.inactive_account", email=email)
        return _render_login(
            request, error="Account is inactive.", email_value=email, status_code=403
        )

    session_id, _ = await create_session(request.app.state.redis, str(user.id))
    signed = sign_session_id(session_id, settings.secret_key)

    redirect = RedirectResponse(url="/", status_code=303)
    set_session_cookie(redirect, signed, secure=(settings.environment == "production"))
    redirect.delete_cookie("login_csrf")
    logger.info("auth.login.success", email=email, user_id=str(user.id))
    return redirect


@router.post("/auth/logout")
async def logout(
    request: Request,
    csrf_token: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> RedirectResponse:
    settings: Settings = request.app.state.settings

    if session_cookie:
        session_data = await get_session(
            request.app.state.redis, session_cookie, settings.secret_key
        )
        if session_data:
            expected = session_data.get("csrf_token", "")
            if not csrf_token or not secrets.compare_digest(csrf_token, expected):
                # Log mismatch but always log out — forced logout beats leaving sessions open
                logger.warning("auth.logout.csrf_mismatch")
        await delete_session(request.app.state.redis, session_cookie, settings.secret_key)

    redirect = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(redirect)
    return redirect
