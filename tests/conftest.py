# ABOUTME: Shared pytest fixtures for the test suite.
# ABOUTME: Provides mock app state (DB engine, Redis) and an async HTTP test client.
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


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
    return client


@pytest.fixture(autouse=False)
def set_app_state(mock_engine: MagicMock, mock_redis: AsyncMock) -> None:
    """Injects mock engine and redis into app.state, bypassing the lifespan."""
    app.state.engine = mock_engine
    app.state.redis = mock_redis
    yield
    # Clean up so tests don't bleed state into each other
    del app.state.engine
    del app.state.redis


@pytest.fixture
async def client(set_app_state: None) -> AsyncClient:
    """Async HTTP client wired to the FastAPI app (no real network)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
