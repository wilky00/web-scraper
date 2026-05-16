# ABOUTME: DB persistence helpers for the crawl worker.
# ABOUTME: persist_crawl_page() writes a CrawlPage row; log_crawl_event() appends a CrawlJobEvent.
from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl import CrawlPage
from app.models.job import CrawlJobEvent
from app.worker.fetcher import FetchResult

logger = structlog.get_logger(__name__)


async def persist_crawl_page(
    session: AsyncSession,
    job_id: uuid.UUID,
    result: FetchResult,
) -> CrawlPage:
    page = CrawlPage(
        job_id=job_id,
        url=result.url,
        canonical_url=result.canonical_url,
        status_code=result.status_code,
        crawl_depth=result.depth,
        raw_html_path=None,  # MinIO upload deferred to Phase 8
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
