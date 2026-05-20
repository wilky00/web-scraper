# ABOUTME: Web route for the settings readout page (GET /settings).
# ABOUTME: Renders app.state.config as read-only YAML; secrets are redacted before display.
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.pricing import fetch_model_pricing
from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.user import User
from app.settings import Settings

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

_SECRET_KEYWORDS = ("key", "secret", "password", "token", "credential")


def _redact(obj: Any) -> Any:
    """Recursively redact dict values whose key names suggest secret material."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            key_lower = str(k).lower()
            if any(kw in key_lower for kw in _SECRET_KEYWORDS):
                result[k] = "[REDACTED]"
            else:
                result[k] = _redact(v)
        return result
    if isinstance(obj, list):
        return [_redact(item) for item in obj]
    return obj


async def _get_csrf(request: Request, session_cookie: str | None) -> str:
    if not session_cookie:
        return ""
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if session_data is None:
        return ""
    return session_data.get("csrf_token", "")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user: User = Depends(require_operator),
) -> HTMLResponse:
    session_cookie = request.cookies.get(SESSION_COOKIE)
    csrf_token = await _get_csrf(request, session_cookie)

    config = getattr(request.app.state, "config", None)
    config_sections: dict[str, str] = {}

    if config is not None:
        for section_name in ("app", "connectors", "crawl", "retention"):
            section = getattr(config, section_name, None)
            if section is not None:
                raw = section.model_dump() if hasattr(section, "model_dump") else {}
                redacted = _redact(raw)
                config_sections[section_name] = yaml.dump(
                    redacted, default_flow_style=False, sort_keys=True
                )

    async with AsyncSession(request.app.state.engine) as db:
        users_result = await db.execute(
            select(User).where(User.deleted_at.is_(None)).order_by(User.created_at)
        )
        users_list = [
            {
                "id": str(u.id),
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else "—",
            }
            for u in users_result.scalars()
        ]

    ai_config = getattr(getattr(request.app.state, "config", None), "ai", None)
    model_pricing: list[dict] = []
    if ai_config is not None:
        model_pricing = await fetch_model_pricing(request.app.state.redis, ai_config)

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "user": user,
            "csrf_token": csrf_token,
            "config_sections": config_sections,
            "has_api_token": user.api_key_hash is not None,
            "users_list": users_list,
            "model_pricing": model_pricing,
            "ai_provider": ai_config.provider if ai_config else None,
        },
    )
