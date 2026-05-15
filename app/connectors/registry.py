# ABOUTME: ConnectorRegistry — maps connector names from connectors.yml to connector instances.
# ABOUTME: API keys and secrets are injected from environment variables, never from config dicts.
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from app.connectors.base import ConnectorBase
from app.connectors.fixture import FixtureConnector
from app.connectors.google_places import GooglePlacesConnector

logger = structlog.get_logger()

_DEFAULT_FIXTURE_DIR = "tests/fixtures/connector_responses"


class UnknownConnectorError(KeyError):
    """Raised when a requested connector name is not registered."""


class ConnectorRegistry:
    """Builds and caches connector instances from a connectors.yml config dict.

    Usage::

        registry = ConnectorRegistry(config_dict)
        connector = registry.get("fixture")
        async for result in connector.discover(job_config):
            ...
    """

    def __init__(self, connectors_config: dict[str, Any]) -> None:
        self._config = connectors_config
        self._instances: dict[str, ConnectorBase] = {}
        self._build()

    def _build(self) -> None:
        for name, cfg in self._config.items():
            if not isinstance(cfg, dict):
                continue
            if not cfg.get("enabled", True):
                logger.info("connector_registry.disabled", connector=name)
                continue

            connector_type = cfg.get("connector_type", name)

            if connector_type == "fixture":
                fixture_dir = cfg.get("fixture_dir", _DEFAULT_FIXTURE_DIR)
                self._instances[name] = FixtureConnector(Path(fixture_dir))
                logger.info(
                    "connector_registry.registered",
                    connector=name,
                    type=connector_type,
                )
            elif connector_type == "google_places":
                self._instances[name] = GooglePlacesConnector(cfg)
                logger.info(
                    "connector_registry.registered",
                    connector=name,
                    type=connector_type,
                )
            else:
                logger.info(
                    "connector_registry.unknown_type",
                    connector=name,
                    type=connector_type,
                )

    def get(self, name: str) -> ConnectorBase:
        """Return the connector instance for the given config key name."""
        if name not in self._instances:
            raise UnknownConnectorError(
                f"No enabled connector named {name!r}. Available: {list(self._instances)}"
            )
        return self._instances[name]

    def available(self) -> list[str]:
        """Return the names of all enabled, registered connectors."""
        return list(self._instances)
