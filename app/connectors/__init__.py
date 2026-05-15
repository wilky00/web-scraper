# ABOUTME: Connectors package — connector abstraction, fixture connector, and registry.
# ABOUTME: Import ConnectorBase, ConnectorResult, FixtureConnector, and ConnectorRegistry from here.
from __future__ import annotations

from app.connectors.base import ConnectorBase, ConnectorResult
from app.connectors.fixture import FixtureConnector
from app.connectors.registry import ConnectorRegistry

__all__ = ["ConnectorBase", "ConnectorResult", "FixtureConnector", "ConnectorRegistry"]
