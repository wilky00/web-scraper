# ABOUTME: robots.txt fetching, in-memory domain cache, and compliance checking.
# ABOUTME: Allows all when robots.txt is missing or unreachable (fail-open).
from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog

logger = structlog.get_logger()


class RobotsCache:
    """Fetches and caches robots.txt per domain; checks URL allowance.

    Pass ``http_client`` in tests to inject a mock client and avoid live HTTP.
    In production (``http_client=None``) a new client is created per fetch and
    closed immediately — robots.txt is fetched at most once per domain per job.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._user_agent = user_agent
        self._http_client = http_client
        self._timeout = timeout
        self._cache: dict[str, RobotFileParser] = {}

    async def is_allowed(self, url: str) -> bool:
        """Return True if the URL is allowed by the domain's robots.txt."""
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return True

        base = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"

        if base not in self._cache:
            self._cache[base] = await self._fetch(base)

        return self._cache[base].can_fetch(self._user_agent, url)

    def clear(self) -> None:
        """Discard all cached robots.txt entries."""
        self._cache.clear()

    async def _fetch(self, base_url: str) -> RobotFileParser:
        robots_url = f"{base_url}/robots.txt"
        parser = RobotFileParser()

        owns_client = self._http_client is None
        client = self._http_client or httpx.AsyncClient(timeout=self._timeout)

        try:
            try:
                response = await client.get(robots_url)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                    logger.debug("robots.fetched", url=robots_url)
                else:
                    # 404 or other non-200 → no restrictions; parse empty to mark as checked
                    parser.parse([])
                    logger.debug("robots.not_found", url=robots_url, status=response.status_code)
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                # Network failure → fail-open (allow all)
                parser.parse([])
                logger.warning("robots.fetch_error", url=robots_url, error=str(exc))
        finally:
            if owns_client:
                await client.aclose()

        return parser
