# ABOUTME: AI Assist API — POST /api/ai/chat for natural-language criteria authoring.
# ABOUTME: Requires operator auth + CSRF. Rate-limited to 20 req/5min per user.
from __future__ import annotations

import json
import secrets

import httpx
import structlog
from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import JSONResponse

from app.ai.chat import build_messages, extract_yaml_block
from app.ai.client import AIClientError, chat_complete
from app.ai.config import AIConfig
from app.ai.skills import load_skills
from app.auth.permissions import require_operator
from app.auth.session import SESSION_COOKIE, get_session
from app.models.user import User
from app.settings import Settings

logger = structlog.get_logger(__name__)

router = APIRouter()

_RATE_LIMIT_MAX = 20
_RATE_LIMIT_WINDOW = 300  # 5 minutes


async def _check_csrf(
    request: Request,
    form_csrf: str,
    session_cookie: str | None,
) -> bool:
    if not session_cookie:
        return False
    settings: Settings = request.app.state.settings
    session_data = await get_session(request.app.state.redis, session_cookie, settings.secret_key)
    if not session_data:
        return False
    expected = session_data.get("csrf_token", "")
    return bool(expected) and secrets.compare_digest(form_csrf, expected)


async def _check_rate_limit(redis: object, user_id: str) -> bool:
    """Return True if within limit, False if exceeded. Uses Redis INCR/EXPIRE."""
    import redis.asyncio as aioredis

    r: aioredis.Redis = redis  # type: ignore[assignment]
    key = f"ai_rate:{user_id}"
    count = await r.incr(key)
    if int(count) == 1:
        await r.expire(key, _RATE_LIMIT_WINDOW)
    return int(count) <= _RATE_LIMIT_MAX


@router.get("/api/ai/models")
async def ai_models(
    request: Request,
    user: User = Depends(require_operator),
) -> JSONResponse:
    ai_config: AIConfig | None = getattr(request.app.state.config, "ai", None)
    if ai_config is None:
        return JSONResponse({"error": "AI Assist is not configured"}, status_code=503)

    settings: Settings = request.app.state.settings
    url = ai_config.base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {settings.ai_api_key}"}

    models: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        models = sorted(item["id"] for item in data.get("data", []) if item.get("id"))
    except Exception:
        pass

    if not models:
        models = [ai_config.model]

    return JSONResponse({"models": models, "default": ai_config.model})


@router.post("/api/ai/chat")
async def ai_chat(
    request: Request,
    message: str = Form(default=""),
    current_yaml: str = Form(default=""),
    history: str = Form(default="[]"),
    csrf_token: str = Form(default=""),
    model: str = Form(default=""),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    user: User = Depends(require_operator),
) -> JSONResponse:
    # Check AI is configured
    ai_config: AIConfig | None = getattr(request.app.state.config, "ai", None)
    if ai_config is None:
        return JSONResponse({"error": "AI Assist is not configured"}, status_code=503)

    # CSRF
    if not await _check_csrf(request, csrf_token, session_cookie):
        return JSONResponse({"error": "Invalid CSRF token"}, status_code=403)

    # Rate limit
    if not await _check_rate_limit(request.app.state.redis, str(user.id)):
        return JSONResponse(
            {"error": "Rate limit exceeded. Please wait before sending more messages."},
            status_code=429,
        )

    # Validate message
    message = message.strip().replace("\x00", "")
    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=422)

    # Parse history
    try:
        history_list: list[dict[str, str]] = json.loads(history)
        if not isinstance(history_list, list):
            history_list = []
    except (json.JSONDecodeError, ValueError):
        history_list = []

    # Load skills and build messages
    settings: Settings = request.app.state.settings
    skill_content = load_skills(settings.config_dir, ai_config)
    messages = build_messages(message, current_yaml or None, history_list, skill_content)

    # Call AI
    model_override = model.strip() or None
    try:
        reply = await chat_complete(
            messages, ai_config, settings.ai_api_key, model_override=model_override
        )
    except AIClientError as exc:
        logger.warning("ai.chat.client_error", error=str(exc), user_id=str(user.id))
        return JSONResponse({"error": str(exc)}, status_code=502)

    suggested_yaml = extract_yaml_block(reply)

    logger.info(
        "ai.chat.completed",
        user_id=str(user.id),
        has_yaml=suggested_yaml is not None,
        model=model_override or ai_config.model,
    )

    return JSONResponse({"reply": reply, "suggested_yaml": suggested_yaml})
