# ABOUTME: ConnectorBase ABC and ConnectorResult schema.
# ABOUTME: Connectors implement discover(); job_id is added by the job runner on persistence.
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel


class ConnectorResult(BaseModel):
    """Data transfer object yielded by connectors before DB persistence.

    job_id is intentionally absent — it is set by the job runner when writing
    RawSearchResult rows so connectors remain independent of the job lifecycle.
    """

    connector_type: str
    raw_data: dict[str, Any]


class ConnectorBase(ABC):
    """Abstract base for all search connectors."""

    #: Matches the key used in connectors.yml and ConnectorRegistry.
    connector_type: str

    @abstractmethod
    async def discover(self, job_config: dict[str, Any]) -> AsyncIterator[ConnectorResult]:
        """Yield raw search results for the given job configuration.

        Implementations must be async generators (use ``yield`` inside an
        ``async def``).  The caller is responsible for persisting results and
        handling back-pressure.
        """
        # This satisfies mypy — subclasses override with a real async generator.
        raise NotImplementedError
        yield  # pragma: no cover — makes the return type AsyncIterator[ConnectorResult]
