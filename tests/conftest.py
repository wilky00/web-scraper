# ABOUTME: Shared pytest fixtures for the test suite.
# ABOUTME: Provides mock app state (DB engine, Redis, Settings) and an async HTTP test client.
from __future__ import annotations

import os

# Set required env vars before any app code is imported so Settings() works in tests.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only-!!")
os.environ.setdefault("API_TOKEN_SECRET", "test-api-token-secret-for-testing")

from unittest.mock import AsyncMock, MagicMock  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app  # noqa: E402
from app.settings import Settings  # noqa: E402


@pytest.fixture
def mock_engine() -> MagicMock:
    """SQLAlchemy async engine stub that responds to SELECT 1 without a real DB."""
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    conn.execute = AsyncMock()

    engine = MagicMock()
    engine.connect.return_value = conn
    return engine


@pytest.fixture
def mock_redis() -> AsyncMock:
    """Redis async client stub."""
    client: AsyncMock = AsyncMock()
    client.ping = AsyncMock(return_value=True)
    client.incr = AsyncMock(return_value=1)
    client.expire = AsyncMock(return_value=True)
    client.set = AsyncMock(return_value=True)
    client.get = AsyncMock(return_value=None)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture(autouse=False)
def set_app_state(mock_engine: MagicMock, mock_redis: AsyncMock) -> None:
    """Injects mock engine, redis, and settings into app.state, bypassing the lifespan."""
    app.state.engine = mock_engine
    app.state.redis = mock_redis
    app.state.settings = Settings()
    yield
    del app.state.engine
    del app.state.redis
    del app.state.settings


@pytest.fixture
async def client(set_app_state: None) -> AsyncClient:
    """Async HTTP client wired to the FastAPI app (no real network)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
