# ABOUTME: Async job orchestrator — connector → crawl → extract → score → dedup → store pipeline.
# ABOUTME: run_job() is the main entry point; crawl helpers (robots, limits, filters) wired here.
from __future__ import annotations

import uuid
from dataclasses import asdict
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.criteria import CriteriaConfig
from app.config.models import CrawlConfig
from app.connectors.base import ConnectorBase
from app.crawl.filter import is_content_type_blocked, is_path_blocked
from app.crawl.limits import PageLimitTracker
from app.crawl.robots import RobotsCache
from app.dedup.engine import DeduplicationEngine, RecordData
from app.extraction.models import ExtractionResult
from app.extraction.runner import run_extraction
from app.models.job import CrawlJob
from app.models.raw_result import RawSearchResult
from app.models.record import BusinessRecord, RecordSource
from app.scoring.engine import ScoringEngine
from app.worker.fetcher import FetchResult, PageFetcher
from app.worker.persist import log_crawl_event, persist_crawl_page

logger = structlog.get_logger(__name__)


async def run_job(
    job_id: uuid.UUID,
    session: AsyncSession,
    *,
    connector: ConnectorBase,
    criteria: CriteriaConfig,
    crawl_config: CrawlConfig | None = None,
    fetcher: PageFetcher | None = None,
) -> None:
    """Run a complete crawl job end-to-end.

    State machine: queued → running → completed | completed_with_errors | failed.
    Per-record errors are caught and counted; fatal errors (connector failure, DB error)
    transition the job to 'failed'.
    """
    log = logger.bind(job_id=str(job_id))

    job: CrawlJob | None = await session.get(CrawlJob, job_id)
    if job is None:
        log.error("orchestrator.job_not_found")
        return

    job.status = "running"
    await session.flush()
    await log_crawl_event(session, job_id, "job_started", "Job started")
    await session.commit()
    log.info("orchestrator.job_started")

    error_count = 0

    try:
        limit_tracker: PageLimitTracker | None = None
        robots_cache: RobotsCache | None = None
        if fetcher and crawl_config:
            limit_tracker = PageLimitTracker(
                crawl_config.max_pages_per_job,
                crawl_config.max_pages_per_domain,
            )
            robots_cache = RobotsCache(crawl_config.user_agent)

        record_ids: list[uuid.UUID] = []

        async for conn_result in connector.discover(job.config_snapshot or {}):
            raw = RawSearchResult(
                job_id=job_id,
                connector_type=conn_result.connector_type,
                raw_data=conn_result.raw_data,
                processed=False,
            )
            session.add(raw)
            await session.flush()

            connector_fields = connector.extract_fields(conn_result.raw_data)
            website_url = connector_fields.get("website")

            fetch_result: FetchResult | None = None
            extraction: ExtractionResult | None = None

            if fetcher and website_url:
                fetch_result = await _try_crawl(
                    session,
                    job_id,
                    website_url,
                    fetcher=fetcher,
                    limit_tracker=limit_tracker,
                    robots_cache=robots_cache,
                    crawl_config=crawl_config,
                    log=log,
                )
                if fetch_result and fetch_result.success:
                    extraction = run_extraction(fetch_result.html, website_url, website_url)

            record = _build_record(job_id, connector_fields, extraction)
            session.add(record)
            await session.flush()
            record_ids.append(record.id)

            _add_sources(session, record, connector_fields, extraction, conn_result.connector_type)

            metrics = _build_metrics(
                extraction, connector_fields, fetch_result, conn_result.connector_type
            )
            scoring = ScoringEngine.score(metrics, criteria)
            record.match_score = Decimal(str(scoring.match_score))
            record.rule_results = asdict(scoring)

            raw.processed = True
            await log_crawl_event(
                session,
                job_id,
                "record_stored",
                f"Stored record: {record.name or 'unnamed'}",
                {"record_id": str(record.id)},
            )
            await session.commit()

            # Check between records for externally-requested pause or cancel.
            await session.refresh(job)
            if job.status == "cancel_requested":
                job.status = "cancelled"
                await log_crawl_event(session, job_id, "job_cancelled", "Job cancelled by user")
                await session.commit()
                return
            elif job.status == "paused":
                await log_crawl_event(session, job_id, "job_paused", "Job paused by user")
                await session.commit()
                return

        await log_crawl_event(
            session,
            job_id,
            "connector_complete",
            f"Connector complete — {len(record_ids)} records",
        )
        await session.commit()

        if len(record_ids) >= 2:
            await _run_dedup(session, job_id, log)

        job.status = "completed" if error_count == 0 else "completed_with_errors"
        await log_crawl_event(
            session,
            job_id,
            "job_complete",
            f"Job complete — {len(record_ids)} records, {error_count} errors",
        )
        await session.commit()
        log.info("orchestrator.job_complete", records=len(record_ids), errors=error_count)

    except Exception as exc:
        log.exception("orchestrator.fatal_error", error=str(exc))
        job.status = "failed"
        await log_crawl_event(session, job_id, "job_failed", f"Job failed: {exc}")
        await session.commit()
        raise


# ── Crawl helper ──────────────────────────────────────────────────────────────


async def _try_crawl(
    session: AsyncSession,
    job_id: uuid.UUID,
    url: str,
    *,
    fetcher: PageFetcher,
    limit_tracker: PageLimitTracker | None,
    robots_cache: RobotsCache | None,
    crawl_config: CrawlConfig | None,
    log: Any,
) -> FetchResult | None:
    """Attempt to crawl a URL. Returns FetchResult or None if skipped/failed."""
    if limit_tracker and not limit_tracker.is_within_limits(url):
        log.info("orchestrator.crawl_skipped.limits", url=url)
        await log_crawl_event(session, job_id, "crawl_skipped", f"Page limits reached: {url}")
        return None

    if robots_cache and not await robots_cache.is_allowed(url):
        log.info("orchestrator.crawl_skipped.robots", url=url)
        await log_crawl_event(session, job_id, "crawl_skipped", f"Blocked by robots.txt: {url}")
        return None

    blocked_patterns: list[str] = crawl_config.blocked_path_patterns if crawl_config else []
    if is_path_blocked(url, blocked_patterns):
        log.info("orchestrator.crawl_skipped.path", url=url)
        await log_crawl_event(session, job_id, "crawl_skipped", f"Blocked path: {url}")
        return None

    try:
        fetch_result = await fetcher.fetch(url)
    except Exception as exc:
        log.warning("orchestrator.crawl_error", url=url, error=str(exc))
        await log_crawl_event(session, job_id, "crawl_error", f"Fetch failed for {url}: {exc}")
        return None

    blocked_content_types: list[str] = crawl_config.blocked_content_types if crawl_config else []
    if is_content_type_blocked(fetch_result.content_type, blocked_content_types):
        log.info("orchestrator.crawl_skipped.content_type", url=url)
        await log_crawl_event(session, job_id, "crawl_skipped", f"Blocked content type: {url}")
        return fetch_result

    await persist_crawl_page(session, job_id, fetch_result)
    if limit_tracker:
        limit_tracker.record_crawled(url)

    await log_crawl_event(
        session,
        job_id,
        "page_crawled",
        f"Crawled: {url}",
        {"status_code": fetch_result.status_code, "depth": fetch_result.depth},
    )
    return fetch_result


# ── Record builders ───────────────────────────────────────────────────────────


def _build_record(
    job_id: uuid.UUID,
    connector_fields: dict[str, str | None],
    extraction: ExtractionResult | None,
) -> BusinessRecord:
    """Merge connector fields and extraction results into a BusinessRecord.

    Extraction takes priority for fields it found; connector provides the fallback.
    """
    name = (
        extraction.name.value if extraction and extraction.name else None
    ) or connector_fields.get("name")
    website = (
        extraction.website.value if extraction and extraction.website else None
    ) or connector_fields.get("website")
    email = (
        extraction.emails[0].value if extraction and extraction.emails else None
    ) or connector_fields.get("email")
    phone = (
        extraction.phones[0].value if extraction and extraction.phones else None
    ) or connector_fields.get("phone")
    address = (
        extraction.address.value if extraction and extraction.address else None
    ) or connector_fields.get("address")
    return BusinessRecord(
        job_id=job_id,
        name=name,
        website=website,
        email=email,
        phone=phone,
        address=address,
        location_city=connector_fields.get("location_city"),
        location_state=connector_fields.get("location_state"),
        status="active",
    )


def _add_sources(
    session: AsyncSession,
    record: BusinessRecord,
    connector_fields: dict[str, str | None],
    extraction: ExtractionResult | None,
    connector_type: str,
) -> None:
    """Add RecordSource rows preserving full field attribution."""
    record_id = record.id

    for field_name, cf_key in [
        ("name", "name"),
        ("website", "website"),
        ("email", "email"),
        ("phone", "phone"),
        ("address", "address"),
        ("location_city", "location_city"),
        ("location_state", "location_state"),
    ]:
        value = connector_fields.get(cf_key)
        if value:
            session.add(
                RecordSource(
                    record_id=record_id,
                    field=field_name,
                    source_url=None,
                    source_type="connector",
                    raw_value=value,
                )
            )

    if extraction is None:
        return

    if extraction.name:
        session.add(
            RecordSource(
                record_id=record_id,
                field="name",
                source_url=extraction.name.source_url,
                source_type=extraction.name.source_type,
                raw_value=extraction.name.raw_value,
            )
        )
    if extraction.website:
        session.add(
            RecordSource(
                record_id=record_id,
                field="website",
                source_url=extraction.website.source_url,
                source_type=extraction.website.source_type,
                raw_value=extraction.website.raw_value,
            )
        )
    for ef in extraction.emails:
        session.add(
            RecordSource(
                record_id=record_id,
                field="email",
                source_url=ef.source_url,
                source_type=ef.source_type,
                raw_value=ef.raw_value,
            )
        )
    for ef in extraction.phones:
        session.add(
            RecordSource(
                record_id=record_id,
                field="phone",
                source_url=ef.source_url,
                source_type=ef.source_type,
                raw_value=ef.raw_value,
            )
        )
    if extraction.address:
        session.add(
            RecordSource(
                record_id=record_id,
                field="address",
                source_url=extraction.address.source_url,
                source_type=extraction.address.source_type,
                raw_value=extraction.address.raw_value,
            )
        )


def _build_metrics(
    extraction: ExtractionResult | None,
    connector_fields: dict[str, str | None],
    fetch_result: FetchResult | None,
    connector_type: str,
) -> dict[str, Any]:
    """Build the metrics dict for ScoringEngine.score()."""
    metrics: dict[str, Any] = {"source.connector_type": connector_type}

    if extraction:
        if extraction.name:
            metrics["extraction.name"] = extraction.name.value
        if extraction.emails:
            metrics["extraction.email"] = extraction.emails[0].value
        if extraction.phones:
            metrics["extraction.phone"] = extraction.phones[0].value
        if extraction.address:
            metrics["extraction.address"] = extraction.address.value
        if extraction.website:
            metrics["extraction.website"] = extraction.website.value

    # Connector provides fallback for any metric not found in extraction
    for cf_key, metric_key in [
        ("name", "extraction.name"),
        ("email", "extraction.email"),
        ("phone", "extraction.phone"),
        ("address", "extraction.address"),
        ("website", "extraction.website"),
    ]:
        if metric_key not in metrics and connector_fields.get(cf_key):
            metrics[metric_key] = connector_fields[cf_key]

    if fetch_result:
        if fetch_result.status_code is not None:
            metrics["crawl.status_code"] = fetch_result.status_code
        metrics["crawl.depth"] = fetch_result.depth

    return metrics


# ── Deduplication ─────────────────────────────────────────────────────────────


async def _run_dedup(
    session: AsyncSession,
    job_id: uuid.UUID,
    log: Any,
) -> None:
    """Identify and mark duplicate BusinessRecords for this job."""
    stmt = select(BusinessRecord).where(
        BusinessRecord.job_id == job_id,
        BusinessRecord.status == "active",
    )
    result = await session.execute(stmt)
    orm_records = list(result.scalars())

    if len(orm_records) < 2:
        return

    record_data_list = [_orm_to_record_data(r) for r in orm_records]
    id_to_orm: dict[Any, BusinessRecord] = {r.id: r for r in orm_records}

    engine = DeduplicationEngine()
    groups = engine.find_duplicates(record_data_list)
    engine.merge_duplicates(groups)

    duplicate_count = 0
    for rd in record_data_list:
        if rd.status == "duplicate":
            orm_rec = id_to_orm.get(rd.id)
            if orm_rec:
                orm_rec.status = "duplicate"
                orm_rec.canonical_record_id = rd.canonical_record_id
            duplicate_count += 1

    if duplicate_count > 0:
        # Transfer RecordSource rows from losers to winners
        for group in groups:
            winner_id = group[0].id
            for loser_rd in group[1:]:
                await session.execute(
                    sa_update(RecordSource)
                    .where(RecordSource.record_id == loser_rd.id)
                    .values(record_id=winner_id)
                )
        await session.commit()
        log.info("orchestrator.dedup_complete", duplicates=duplicate_count)


def _orm_to_record_data(record: BusinessRecord) -> RecordData:
    return RecordData(
        id=record.id,
        name=record.name,
        website=record.website,
        email=record.email,
        phone=record.phone,
        location_city=record.location_city,
        location_state=record.location_state,
        status=record.status,
        canonical_record_id=record.canonical_record_id,
    )
