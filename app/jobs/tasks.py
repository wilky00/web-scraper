# ABOUTME: RQ task entry points for background job processing.
# ABOUTME: run_crawl_job() is the RQ entry point; creates its own DB session and PageFetcher.
from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config.criteria import CriteriaConfig
from app.config.loader import load_all_configs
from app.connectors.registry import ConnectorRegistry
from app.jobs.orchestrator import run_job
from app.models.connector import Connector
from app.models.criteria import CriteriaVersion
from app.models.job import CrawlJob
from app.settings import Settings
from app.worker.fetcher import PageFetcher

logger = structlog.get_logger(__name__)


def run_crawl_job(job_id_str: str) -> None:
    """RQ entry point — runs a single crawl job to completion.

    Called by the RQ worker process.  Creates its own DB engine and session;
    does NOT reuse the FastAPI app's connection pool.
    """
    asyncio.run(_async_main(job_id_str))


async def _async_main(job_id_str: str) -> None:
    log = logger.bind(job_id=job_id_str)
    settings = Settings()
    configs = load_all_configs(settings.config_dir)
    registry = ConnectorRegistry(configs.connectors.connectors)

    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=5)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            job_id = uuid.UUID(job_id_str)

            job: CrawlJob | None = await session.get(CrawlJob, job_id)
            if job is None:
                log.error("task.job_not_found")
                return

            connector_orm: Connector | None = await session.get(Connector, job.connector_id)
            if connector_orm is None:
                log.error("task.connector_not_found", connector_id=str(job.connector_id))
                return

            try:
                connector = registry.get(connector_orm.name)
            except KeyError:
                log.error("task.connector_not_registered", connector_name=connector_orm.name)
                return

            criteria_version: CriteriaVersion | None = await session.get(
                CriteriaVersion, job.criteria_version_id
            )
            if criteria_version is None:
                log.error(
                    "task.criteria_not_found", version_id=str(job.criteria_version_id)
                )
                return

            criteria = CriteriaConfig.model_validate(criteria_version.config_snapshot)

            async with PageFetcher(configs.crawl) as fetcher:
                await run_job(
                    job_id,
                    session,
                    connector=connector,
                    criteria=criteria,
                    crawl_config=configs.crawl,
                    fetcher=fetcher,
                )
    finally:
        await engine.dispose()
