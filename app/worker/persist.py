# ABOUTME: DB persistence helpers for the crawl worker.
# ABOUTME: persist_crawl_page() writes a CrawlPage row and optionally uploads raw HTML to S3.
from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawlPage
from app.models.job import CrawlJobEvent
from app.services import storage

if TYPE_CHECKING:
    from app.settings import Settings
    from app.worker.fetcher import FetchResult

logger = structlog.get_logger(__name__)


async def persist_crawl_page(
    session: AsyncSession,
    job_id: uuid.UUID,
    result: FetchResult,
    settings: Settings | None = None,
) -> CrawlPage:
    raw_html_path: str | None = None

    if settings and settings.s3_endpoint_url and result.html:
        key = storage.generate_html_key(job_id, result.url)
        try:
            await asyncio.to_thread(
                storage.upload_bytes,
                result.html.encode("utf-8"),
                key,
                "text/html",
                settings,
            )
            raw_html_path = key
        except storage.StorageError:
            logger.warning("crawl_page.html_upload_failed", url=result.url, job_id=str(job_id))

    page = CrawlPage(
        job_id=job_id,
        url=result.url,
        canonical_url=result.canonical_url,
        status_code=result.status_code,
        crawl_depth=result.depth,
        raw_html_path=raw_html_path,
        extracted_fields={},
        error=result.error,
    )
    session.add(page)
    await session.flush()
    logger.info("crawl_page.saved", url=result.url, job_id=str(job_id))
    return page


async def log_crawl_event(
    session: AsyncSession,
    job_id: uuid.UUID,
    event_type: str,
    message: str,
    data: dict[str, Any] | None = None,
) -> CrawlJobEvent:
    event = CrawlJobEvent(
        job_id=job_id,
        event_type=event_type,
        message=message,
        event_data=data or {},
    )
    session.add(event)
    await session.flush()
    return event
