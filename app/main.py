# ABOUTME: FastAPI application factory. Defines lifespan, middleware, and router registration.
# ABOUTME: Health endpoint at GET /health checks live DB and Redis connectivity.
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config.loader import ConfigLoadError, load_all_configs
from app.settings import Settings

logger = structlog.get_logger()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Settings are loaded lazily here so importing app.main never fails
    # due to missing env vars (important for test collection without a .env file).
    settings = Settings()
    logger.info("startup.begin", environment=settings.environment)

    try:
        app.state.config = load_all_configs(settings.config_dir)
        logger.info("startup.config_loaded", config_dir=str(settings.config_dir))
    except ConfigLoadError as exc:
        logger.critical("startup.config_failed", error=str(exc))
        raise SystemExit(1) from exc

    app.state.engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )
    app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    logger.info("startup.complete")
    yield

    engine: AsyncEngine = app.state.engine
    await engine.dispose()
    await app.state.redis.aclose()
    logger.info("shutdown.complete")


app = FastAPI(
    title="Web Scraper",
    version="0.1.0",
    lifespan=lifespan,
    # Disable docs in production via config (Sprint 1.1)
    docs_url="/docs",
    redoc_url=None,
)


@app.get("/health", include_in_schema=False)
async def health(request: Request) -> JSONResponse:
    result: dict[str, Any] = {"status": "ok", "db": "unknown", "redis": "unknown"}
    http_status = 200

    engine: AsyncEngine | None = getattr(request.app.state, "engine", None)
    redis_client: aioredis.Redis | None = getattr(request.app.state, "redis", None)

    if engine is None or redis_client is None:
        return JSONResponse(
            {"status": "starting", "db": "not_ready", "redis": "not_ready"},
            status_code=503,
        )

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        result["db"] = "ok"
    except Exception:
        logger.exception("health.db_check_failed")
        result["db"] = "error"
        result["status"] = "degraded"
        http_status = 503

    try:
        await redis_client.ping()  # type: ignore[misc]  # redis types ping() as Awaitable|bool
        result["redis"] = "ok"
    except Exception:
        logger.exception("health.redis_check_failed")
        result["redis"] = "error"
        result["status"] = "degraded"
        http_status = 503

    return JSONResponse(result, status_code=http_status)
