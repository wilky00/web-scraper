# ABOUTME: FixtureConnector — reads *.json files from a directory, yields ConnectorResult objects.
# ABOUTME: Used for tests, demos, and local dev without live API credentials.
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog

from app.connectors.base import ConnectorBase, ConnectorResult

logger = structlog.get_logger()


class FixtureConnector(ConnectorBase):
    """Yields pre-recorded search results from JSON fixture files.

    Each JSON file must contain either a JSON array of result objects or a
    single result object.  Files are read in sorted filename order for
    deterministic test output.
    """

    connector_type = "fixture"

    def __init__(self, fixture_dir: str | Path) -> None:
        self._fixture_dir = Path(fixture_dir)

    async def discover(self, job_config: dict[str, Any]) -> AsyncIterator[ConnectorResult]:
        if not self._fixture_dir.exists():
            logger.warning(
                "fixture_connector.dir_not_found",
                fixture_dir=str(self._fixture_dir),
            )
            return

        fixture_files = sorted(self._fixture_dir.glob("*.json"))
        if not fixture_files:
            logger.info(
                "fixture_connector.no_files",
                fixture_dir=str(self._fixture_dir),
            )
            return

        for path in fixture_files:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "fixture_connector.file_error",
                    path=str(path),
                    error=str(exc),
                )
                continue

            records: list[dict[str, Any]] = raw if isinstance(raw, list) else [raw]
            for record in records:
                if not isinstance(record, dict):
                    logger.warning(
                        "fixture_connector.invalid_record",
                        path=str(path),
                        record=record,
                    )
                    continue
                yield ConnectorResult(
                    connector_type=self.connector_type,
                    raw_data=record,
                )
