# ABOUTME: Connector seeding — syncs enabled connectors from connectors.yml into the DB.
# ABOUTME: Called from the FastAPI lifespan on every startup. Idempotent (upserts by name).
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models.connector import Connector

logger = structlog.get_logger()

_SECRET_KEYS = frozenset({"api_key", "secret", "password", "token", "credential"})


async def seed_connectors(engine: AsyncEngine, connectors_config: dict[str, Any]) -> None:
    """Upsert one Connector row per enabled entry in connectors.yml. Idempotent."""
    upserted = 0
    disabled = 0

    enabled_names: set[str] = set()

    for name, cfg in connectors_config.items():
        if not isinstance(cfg, dict):
            continue

        is_enabled = cfg.get("enabled", True)
        connector_type = cfg.get("connector_type", name)
        safe_cfg = {k: v for k, v in cfg.items() if k not in _SECRET_KEYS}

        async with AsyncSession(engine) as db:
            existing = (
                await db.execute(select(Connector).where(Connector.name == name))
            ).scalar_one_or_none()

            if existing:
                existing.enabled = bool(is_enabled)
                existing.connector_type = connector_type
                existing.config_snapshot = safe_cfg
            else:
                db.add(
                    Connector(
                        name=name,
                        connector_type=connector_type,
                        enabled=bool(is_enabled),
                        config_snapshot=safe_cfg,
                    )
                )
            await db.commit()
            upserted += 1

        if is_enabled:
            enabled_names.add(name)

    # Disable any DB connectors no longer present in config
    async with AsyncSession(engine) as db:
        all_result = await db.execute(select(Connector))
        for connector in all_result.scalars():
            if connector.name not in connectors_config:
                connector.enabled = False
                disabled += 1
        if disabled:
            await db.commit()

    if upserted or disabled:
        logger.info(
            "connectors.seed.complete",
            upserted=upserted,
            disabled=disabled,
            enabled=list(enabled_names),
        )
