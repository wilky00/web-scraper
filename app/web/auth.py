# ABOUTME: Web routes for authentication: GET /login page, GET /auth/oidc/login redirect,
# ABOUTME: and GET /auth/oidc/callback to complete the Authentik OIDC flow.
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.csrf import generate_form_csrf
from app.auth.oidc import (
    create_oidc_state,
    exchange_code_for_tokens,
    fetch_userinfo,
    find_or_provision_sso_user,
    generate_state,
    sso_enabled,
    verify_oidc_state,
)
from app.auth.session import (
    SESSION_COOKIE,
    create_session,
    get_session,
    set_session_cookie,
    sign_session_id,
)
from app.settings import Settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
logger = structlog.get_logger()


def _sso_active(request: Request) -> bool:
    """Return True when SSO is configured and the discovery document is available."""
    settings: Settings = request.app.state.settings
    config = request.app.state.config.app
    discovery = getattr(request.app.state, "oidc_discovery", None)
    return sso_enabled(settings, config) and discovery is not None


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
        {
            "csrf_token": form_token,
            "error": "",
            "email_value": "",
            "sso_enabled": _sso_active(request),
        },
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


@router.get("/auth/oidc/login")
async def oidc_login(request: Request) -> Response:
    if not _sso_active(request):
        raise HTTPException(status_code=404)

    settings: Settings = request.app.state.settings
    config = request.app.state.config.app
    discovery: dict[str, str] = request.app.state.oidc_discovery

    state = generate_state()
    await create_oidc_state(request.app.state.redis, state)

    redirect_uri = f"{config.base_url}/auth/oidc/callback"
    params = urlencode(
        {
            "response_type": "code",
            "client_id": settings.authentik_client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid email profile",
            "state": state,
        }
    )
    authorization_url = f"{discovery['authorization_endpoint']}?{params}"
    return RedirectResponse(url=authorization_url, status_code=302)


@router.get("/auth/oidc/callback")
async def oidc_callback(request: Request) -> Response:
    if not _sso_active(request):
        raise HTTPException(status_code=404)

    settings: Settings = request.app.state.settings
    config = request.app.state.config.app
    discovery: dict[str, str] = request.app.state.oidc_discovery

    error = request.query_params.get("error")
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    if error:
        logger.info("oidc.callback.provider_error", error=error)
        return RedirectResponse(url="/login", status_code=303)

    if not code or not state:
        logger.warning("oidc.callback.missing_params")
        return RedirectResponse(url="/login", status_code=303)

    if not await verify_oidc_state(request.app.state.redis, state):
        logger.warning("oidc.callback.invalid_state")
        return RedirectResponse(url="/login", status_code=303)

    redirect_uri = f"{config.base_url}/auth/oidc/callback"

    try:
        tokens = await exchange_code_for_tokens(settings, discovery, code, redirect_uri)
    except Exception:
        logger.exception("oidc.callback.token_exchange_failed")
        return RedirectResponse(url="/login", status_code=303)

    try:
        userinfo = await fetch_userinfo(discovery, tokens["access_token"])
    except Exception:
        logger.exception("oidc.callback.userinfo_failed")
        return RedirectResponse(url="/login", status_code=303)

    try:
        async with AsyncSession(request.app.state.engine) as db:
            user = await find_or_provision_sso_user(db, userinfo)
    except Exception:
        logger.exception("oidc.callback.provision_failed")
        return RedirectResponse(url="/login", status_code=303)

    if not user.is_active or user.deleted_at is not None:
        logger.warning("oidc.callback.inactive_user", user_id=str(user.id))
        return RedirectResponse(url="/login", status_code=303)

    session_id, _ = await create_session(request.app.state.redis, str(user.id))
    signed = sign_session_id(session_id, settings.secret_key)

    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, signed, secure=(settings.environment == "production"))
    logger.info("oidc.login_success", user_id=str(user.id))
    return response
