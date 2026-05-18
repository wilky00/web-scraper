# ABOUTME: FastAPI application factory. Defines lifespan, middleware, and router registration.
# ABOUTME: Health endpoint at GET /health checks live DB and Redis connectivity.
from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.api.ai import router as api_ai_router
from app.api.auth import router as api_auth_router
from app.api.connectors import router as api_connectors_router
from app.api.criteria import router as api_criteria_router
from app.api.exports import router as api_exports_router
from app.api.jobs import router as api_jobs_router
from app.api.projects import router as api_projects_router
from app.api.records import router as api_records_router
from app.auth.oidc import load_oidc_discovery
from app.auth.oidc import sso_enabled as _oidc_sso_enabled
from app.auth.permissions import NotAuthenticatedException
from app.auth.seed import seed_operator
from app.config.loader import ConfigLoadError, load_all_configs
from app.connectors.seed import seed_connectors
from app.criteria.seed import seed_example_criteria
from app.models.user import User
from app.settings import Settings
from app.web.audit import router as web_audit_router
from app.web.auth import router as web_auth_router
from app.web.criteria import router as web_criteria_router
from app.web.dashboard import router as web_dashboard_router
from app.web.exports import router as web_exports_router
from app.web.jobs import router as web_jobs_router
from app.web.projects import router as web_projects_router
from app.web.records import router as web_records_router
from app.web.settings_page import router as web_settings_router

_env = os.getenv("ENVIRONMENT", "local")

logger = structlog.get_logger()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Settings are loaded lazily here so importing app.main never fails
    # due to missing env vars (important for test collection without a .env file).
    settings = Settings()
    app.state.settings = settings
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

    await seed_operator(
        app.state.engine, settings.seed_operator_email, settings.seed_operator_password
    )

    async with AsyncSession(app.state.engine) as _db:
        _seed_user = (await _db.execute(select(User).limit(1))).scalar_one_or_none()
    await seed_example_criteria(app.state.engine, _seed_user.id if _seed_user else None)
    await seed_connectors(app.state.engine, app.state.config.connectors.connectors)

    if app.state.config.ai and not app.state.config.ai.models:
        import json as _json

        from app.ai.client import fetch_models as _fetch_models
        from app.api.ai import _AI_MODELS_CACHE_KEY, _AI_MODELS_CACHE_TTL

        try:
            _ai_models = await _fetch_models(app.state.config.ai.base_url, settings.ai_api_key)
            if _ai_models:
                await app.state.redis.set(
                    _AI_MODELS_CACHE_KEY, _json.dumps(_ai_models), ex=_AI_MODELS_CACHE_TTL
                )
                logger.info("startup.ai_models_cached", count=len(_ai_models))
        except Exception:
            logger.warning(
                "startup.ai_models_fetch_failed",
                hint="models will be fetched on first request",
            )

    app.state.oidc_discovery = None
    if _oidc_sso_enabled(settings, app.state.config.app):
        app.state.oidc_discovery = await load_oidc_discovery(settings)
        if app.state.oidc_discovery is None:
            logger.warning(
                "startup.oidc_discovery_failed",
                hint="SSO enabled but discovery unavailable — SSO button hidden",
            )
        else:
            logger.info("startup.oidc_ready")

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
    docs_url="/docs" if _env != "production" else None,
    redoc_url=None,
)


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(
    request: Request, exc: NotAuthenticatedException
) -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Only wrap /api/ paths in the envelope; let FastAPI handle HTML pages normally
    if request.url.path.startswith("/api/"):
        errors = [str(e.get("msg", e)) for e in exc.errors()]
        return JSONResponse({"data": None, "errors": errors}, status_code=422)
    return JSONResponse({"detail": exc.errors()}, status_code=422)


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    if request.url.path.startswith("/api/"):
        return JSONResponse({"data": None, "errors": ["Internal server error"]}, status_code=500)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(web_auth_router)
app.include_router(web_dashboard_router)
app.include_router(web_audit_router)
app.include_router(web_criteria_router)
app.include_router(web_exports_router)
app.include_router(web_jobs_router)
app.include_router(web_projects_router)
app.include_router(web_records_router)
app.include_router(web_settings_router)
app.include_router(api_ai_router)
app.include_router(api_auth_router)
app.include_router(api_connectors_router)
app.include_router(api_criteria_router)
app.include_router(api_exports_router)
app.include_router(api_jobs_router)
app.include_router(api_projects_router)
app.include_router(api_records_router)


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
