# ABOUTME: Ephemeral test runner — mini-crawl (max 3 results) with no DB persistence.
# ABOUTME: Results stored in Redis under test:{test_id} with a 15-minute TTL.
from __future__ import annotations

import asyncio
import json
import uuid
from decimal import Decimal
from typing import Any

import redis
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config.criteria import CriteriaConfig
from app.config.loader import load_all_configs
from app.config.models import CrawlConfig
from app.connectors.registry import ConnectorRegistry
from app.extraction.runner import run_extraction
from app.models.connector import Connector
from app.models.criteria import CriteriaVersion
from app.scoring.engine import ScoringEngine
from app.settings import Settings
from app.worker.fetcher import PageFetcher

logger = structlog.get_logger(__name__)

_REDIS_TTL = 900  # 15 minutes


def run_test_job(
    test_id: str,
    criteria_version_id_str: str,
    connector_id_str: str,
    config_overrides: dict[str, Any],
) -> None:
    """RQ entry point for an ephemeral test crawl. No DB writes; results land in Redis."""
    settings = Settings()
    r = redis.from_url(settings.redis_url)
    log = logger.bind(test_id=test_id)

    try:
        r.set(
            f"test:{test_id}",
            json.dumps({"status": "running", "results": [], "error": None}),
            ex=_REDIS_TTL,
        )
        results = asyncio.run(
            _async_test_main(
                settings, criteria_version_id_str, connector_id_str, config_overrides, log
            )
        )
        r.set(
            f"test:{test_id}",
            json.dumps({"status": "done", "results": results, "error": None}),
            ex=_REDIS_TTL,
        )
        log.info("test_runner.done", result_count=len(results))
    except Exception as exc:
        log.exception("test_runner.failed", error=str(exc))
        r.set(
            f"test:{test_id}",
            json.dumps({"status": "error", "results": [], "error": str(exc)}),
            ex=_REDIS_TTL,
        )
    finally:
        r.close()


async def _async_test_main(
    settings: Settings,
    criteria_version_id_str: str,
    connector_id_str: str,
    config_overrides: dict[str, Any],
    log: Any,
) -> list[dict[str, Any]]:
    configs = load_all_configs(settings.config_dir)
    registry = ConnectorRegistry(configs.connectors.connectors)

    engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=2)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            connector_id = uuid.UUID(connector_id_str)
            connector_orm: Connector | None = await session.get(Connector, connector_id)
            if connector_orm is None:
                raise ValueError(f"Connector {connector_id_str!r} not found")

            try:
                connector = registry.get(connector_orm.name)
            except KeyError:
                raise ValueError(f"Connector '{connector_orm.name}' is not registered") from None

            criteria_version_id = uuid.UUID(criteria_version_id_str)
            criteria_version: CriteriaVersion | None = await session.get(
                CriteriaVersion, criteria_version_id
            )
            if criteria_version is None:
                raise ValueError(f"CriteriaVersion {criteria_version_id_str!r} not found")

            criteria = CriteriaConfig.model_validate(criteria_version.config_snapshot)

            # Apply allowed config overrides
            crawl_config: CrawlConfig = configs.crawl
            allowed_keys = {"max_pages_per_job", "delay_between_requests_ms", "max_depth"}
            filtered = {k: v for k, v in config_overrides.items() if k in allowed_keys}
            if filtered:
                crawl_config = crawl_config.model_copy(update=filtered)

            discover_config: dict[str, Any] = {
                "criteria": criteria_version.config_snapshot,
                "connector": connector_orm.config_snapshot,
            }

            results: list[dict[str, Any]] = []

            async with PageFetcher(crawl_config) as fetcher:
                count = 0
                async for conn_result in connector.discover(discover_config):
                    if count >= 3:
                        break
                    count += 1

                    connector_fields = connector.extract_fields(conn_result.raw_data)
                    website_url: str | None = connector_fields.get("website")

                    fetch_result = None
                    extraction = None

                    if website_url:
                        try:
                            fetch_result = await fetcher.fetch(website_url)
                            if fetch_result and fetch_result.success and fetch_result.html:
                                extraction = run_extraction(
                                    fetch_result.html, website_url, website_url
                                )
                        except Exception as exc:
                            log.warning("test_runner.fetch_error", url=website_url, error=str(exc))

                    metrics = _build_metrics(
                        extraction, connector_fields, fetch_result, conn_result.connector_type
                    )
                    scoring = ScoringEngine.score(metrics, criteria)

                    name = (
                        extraction.name.value if extraction and extraction.name else None
                    ) or connector_fields.get("name")
                    email = (
                        extraction.emails[0].value if extraction and extraction.emails else None
                    ) or connector_fields.get("email")
                    phone = (
                        extraction.phones[0].value if extraction and extraction.phones else None
                    ) or connector_fields.get("phone")
                    address = (
                        extraction.address.value if extraction and extraction.address else None
                    ) or connector_fields.get("address")
                    website = (
                        extraction.website.value if extraction and extraction.website else None
                    ) or website_url

                    results.append(
                        {
                            "name": name,
                            "website": website,
                            "email": email,
                            "phone": phone,
                            "address": address,
                            "match_score": float(Decimal(str(scoring.match_score))),
                        }
                    )

        return results
    finally:
        await engine.dispose()


def _build_metrics(
    extraction: Any,
    connector_fields: dict[str, str | None],
    fetch_result: Any,
    connector_type: str,
) -> dict[str, Any]:
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
