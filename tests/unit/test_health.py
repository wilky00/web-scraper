# ABOUTME: Unit tests for the GET /health endpoint.
# ABOUTME: Uses mock engine and redis — no real DB or Redis required.
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_200_when_all_ok(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_503_when_db_fails(
    mock_engine: MagicMock, mock_redis: AsyncMock
) -> None:
    conn = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)
    conn.execute = AsyncMock(side_effect=Exception("DB connection refused"))
    mock_engine.connect.return_value = conn

    app.state.engine = mock_engine
    app.state.redis = mock_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/health")
    finally:
        del app.state.engine
        del app.state.redis

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"
    assert body["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_returns_503_when_redis_fails(
    mock_engine: MagicMock, mock_redis: AsyncMock
) -> None:
    mock_redis.ping = AsyncMock(side_effect=Exception("Redis connection refused"))
    app.state.engine = mock_engine
    app.state.redis = mock_redis
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            response = await c.get("/health")
    finally:
        del app.state.engine
        del app.state.redis

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "ok"
    assert body["redis"] == "error"


@pytest.mark.asyncio
async def test_health_returns_503_before_startup() -> None:
    """If app state isn't initialized (lifespan hasn't run), endpoint returns 503 starting."""
    for attr in ("engine", "redis"):
        if hasattr(app.state, attr):
            delattr(app.state, attr)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "starting"
