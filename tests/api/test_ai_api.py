# ABOUTME: API tests for POST /api/ai/chat — auth, CSRF, rate limit, and AI client mocking.
# ABOUTME: Overrides require_operator via dependency_overrides; never makes real AI API calls.
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.config import AIConfig
from app.api.ai import require_operator
from app.auth.session import SESSION_COOKIE, sign_session_id
from app.config.loader import AppConfigs
from app.main import app
from app.models.user import User
from app.settings import Settings

_SECRET = Settings().secret_key
_SESSION_CSRF = "test-csrf-ai"
_SESSION_ID = "test-session-ai"

_AI_CONFIG = AIConfig(
    provider="openrouter",
    base_url="https://openrouter.ai/api/v1",
    model="anthropic/claude-3-5-sonnet",
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_user() -> MagicMock:
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.email = "operator@test.com"
    user.role = "operator"
    return user


def _make_redis(csrf: str = _SESSION_CSRF, rate_count: int = 1) -> AsyncMock:
    r: AsyncMock = AsyncMock()
    r.get = AsyncMock(return_value=json.dumps({"user_id": str(uuid.uuid4()), "csrf_token": csrf}))
    r.incr = AsyncMock(return_value=rate_count)
    r.expire = AsyncMock(return_value=True)
    return r


def _make_configs(ai: AIConfig | None = _AI_CONFIG) -> MagicMock:
    cfg = MagicMock(spec=AppConfigs)
    cfg.ai = ai
    return cfg


@pytest.fixture
def signed_cookie() -> str:
    return sign_session_id(_SESSION_ID, _SECRET)


@pytest.fixture
async def client(mock_user: MagicMock) -> AsyncClient:
    app.dependency_overrides[require_operator] = lambda: mock_user
    app.state.redis = _make_redis()
    app.state.settings = Settings()
    app.state.config = _make_configs()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    for attr in ("redis", "settings", "config"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)


# ---------------------------------------------------------------------------
# POST /api/ai/chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_returns_reply(client: AsyncClient, signed_cookie: str) -> None:
    with patch("app.api.ai.chat_complete", new=AsyncMock(return_value="Here is your answer.")):
        with patch("app.api.ai.load_skills", return_value="skill content"):
            resp = await client.post(
                "/api/ai/chat",
                data={"message": "create a test criteria", "csrf_token": _SESSION_CSRF},
                cookies={SESSION_COOKIE: signed_cookie},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Here is your answer."
    assert body["suggested_yaml"] is None


@pytest.mark.asyncio
async def test_chat_extracts_yaml_from_reply(client: AsyncClient, signed_cookie: str) -> None:
    ai_reply = "Here you go:\n```yaml\nmetadata:\n  name: test\n```"
    with patch("app.api.ai.chat_complete", new=AsyncMock(return_value=ai_reply)):
        with patch("app.api.ai.load_skills", return_value=""):
            resp = await client.post(
                "/api/ai/chat",
                data={"message": "make a criteria", "csrf_token": _SESSION_CSRF},
                cookies={SESSION_COOKIE: signed_cookie},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["suggested_yaml"] == "metadata:\n  name: test"


@pytest.mark.asyncio
async def test_chat_returns_503_when_ai_not_configured(
    mock_user: MagicMock, signed_cookie: str
) -> None:
    app.dependency_overrides[require_operator] = lambda: mock_user
    app.state.redis = _make_redis()
    app.state.settings = Settings()
    app.state.config = _make_configs(ai=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/ai/chat",
            data={"message": "hello", "csrf_token": _SESSION_CSRF},
            cookies={SESSION_COOKIE: signed_cookie},
        )
    app.dependency_overrides.clear()
    for attr in ("redis", "settings", "config"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_chat_returns_403_on_invalid_csrf(client: AsyncClient, signed_cookie: str) -> None:
    resp = await client.post(
        "/api/ai/chat",
        data={"message": "hello", "csrf_token": "wrong-token"},
        cookies={SESSION_COOKIE: signed_cookie},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_chat_returns_422_on_empty_message(client: AsyncClient, signed_cookie: str) -> None:
    with patch("app.api.ai.chat_complete", new=AsyncMock(return_value="ok")):
        with patch("app.api.ai.load_skills", return_value=""):
            resp = await client.post(
                "/api/ai/chat",
                data={"message": "   ", "csrf_token": _SESSION_CSRF},
                cookies={SESSION_COOKIE: signed_cookie},
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_returns_429_when_rate_limited(mock_user: MagicMock, signed_cookie: str) -> None:
    app.dependency_overrides[require_operator] = lambda: mock_user
    app.state.redis = _make_redis(rate_count=21)  # over the 20 limit
    app.state.settings = Settings()
    app.state.config = _make_configs()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with patch("app.api.ai.chat_complete", new=AsyncMock(return_value="ok")):
            with patch("app.api.ai.load_skills", return_value=""):
                resp = await ac.post(
                    "/api/ai/chat",
                    data={"message": "hello", "csrf_token": _SESSION_CSRF},
                    cookies={SESSION_COOKIE: signed_cookie},
                )
    app.dependency_overrides.clear()
    for attr in ("redis", "settings", "config"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_chat_returns_502_on_ai_client_error(client: AsyncClient, signed_cookie: str) -> None:
    from app.ai.client import AIClientError

    with patch("app.api.ai.chat_complete", new=AsyncMock(side_effect=AIClientError("timeout"))):
        with patch("app.api.ai.load_skills", return_value=""):
            resp = await client.post(
                "/api/ai/chat",
                data={"message": "hello", "csrf_token": _SESSION_CSRF},
                cookies={SESSION_COOKIE: signed_cookie},
            )
    assert resp.status_code == 502


@pytest.mark.asyncio
async def test_chat_requires_authentication() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/ai/chat",
            data={"message": "hello", "csrf_token": "x"},
            follow_redirects=False,
        )
    # unauthenticated → NotAuthenticatedException → 303 redirect to /login
    assert resp.status_code == 303


@pytest.mark.asyncio
async def test_chat_passes_current_yaml_to_messages(
    client: AsyncClient, signed_cookie: str
) -> None:
    captured: list[list[dict]] = []

    async def fake_complete(messages, ai_config, api_key):
        captured.append(messages)
        return "response"

    with patch("app.api.ai.chat_complete", new=fake_complete):
        with patch("app.api.ai.load_skills", return_value=""):
            await client.post(
                "/api/ai/chat",
                data={
                    "message": "update it",
                    "current_yaml": "metadata:\n  name: existing",
                    "csrf_token": _SESSION_CSRF,
                },
                cookies={SESSION_COOKIE: signed_cookie},
            )

    assert captured
    system_content = captured[0][0]["content"]
    assert "metadata:" in system_content


@pytest.mark.asyncio
async def test_chat_passes_history_to_messages(client: AsyncClient, signed_cookie: str) -> None:
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
    ]
    captured: list[list[dict]] = []

    async def fake_complete(messages, ai_config, api_key):
        captured.append(messages)
        return "new response"

    with patch("app.api.ai.chat_complete", new=fake_complete):
        with patch("app.api.ai.load_skills", return_value=""):
            await client.post(
                "/api/ai/chat",
                data={
                    "message": "follow up",
                    "history": json.dumps(history),
                    "csrf_token": _SESSION_CSRF,
                },
                cookies={SESSION_COOKIE: signed_cookie},
            )

    assert captured
    contents = [m["content"] for m in captured[0]]
    assert "earlier question" in contents
    assert "earlier answer" in contents
