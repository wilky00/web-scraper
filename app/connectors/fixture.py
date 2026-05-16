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

    def extract_fields(self, raw_data: dict[str, Any]) -> dict[str, str | None]:
        """Map fixture / Google-Places-style raw_data to standard field names."""
        address = raw_data.get("formatted_address") or raw_data.get("address") or None
        city: str | None = None
        state: str | None = None
        if address:
            parts = [p.strip() for p in address.split(",")]
            # "Street, City, ST Zip" — city is the second-to-last comma-part
            if len(parts) >= 2:
                city = parts[-2].strip() or None
            if parts:
                state_zip = parts[-1].strip().split()
                if state_zip:
                    state = state_zip[0] or None
        phone = raw_data.get("phone") or raw_data.get("formatted_phone_number") or None
        return {
            "name": raw_data.get("name") or None,
            "website": raw_data.get("website") or raw_data.get("url") or None,
            "email": raw_data.get("email") or None,
            "phone": phone,
            "address": address,
            "location_city": city,
            "location_state": state,
        }

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
