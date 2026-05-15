# ABOUTME: Unit tests for RobotsCache — robots.txt fetching, caching, and
# ABOUTME: compliance checks. All HTTP calls mocked via injected httpx.AsyncClient.
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.crawl.robots import RobotsCache

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "robots"

_USER_AGENT = "WebScraper/1.0"


def _make_mock_client(status: int, body: str) -> AsyncMock:
    """Return a mock AsyncClient whose GET always returns the given response."""
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    async def _get(*args: Any, **kwargs: Any) -> MagicMock:
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.text = body
        return mock_response

    mock_client.get = _get  # type: ignore[method-assign]
    return mock_client


def _fixture(name: str) -> str:
    return (_FIXTURE_DIR / name).read_text()


# ---------------------------------------------------------------------------
# Allow-all robots.txt
# ---------------------------------------------------------------------------


class TestAllowAll:
    @pytest.mark.asyncio
    async def test_allows_root(self) -> None:
        client = _make_mock_client(200, _fixture("allow_all.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/") is True

    @pytest.mark.asyncio
    async def test_allows_deep_path(self) -> None:
        client = _make_mock_client(200, _fixture("allow_all.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/a/b/c") is True


# ---------------------------------------------------------------------------
# Disallow-all robots.txt
# ---------------------------------------------------------------------------


class TestDisallowAll:
    @pytest.mark.asyncio
    async def test_blocks_root(self) -> None:
        client = _make_mock_client(200, _fixture("disallow_all.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/") is False

    @pytest.mark.asyncio
    async def test_blocks_any_path(self) -> None:
        client = _make_mock_client(200, _fixture("disallow_all.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/about") is False


# ---------------------------------------------------------------------------
# Selective robots.txt
# ---------------------------------------------------------------------------


class TestSelective:
    @pytest.mark.asyncio
    async def test_blocks_disallowed_path(self) -> None:
        client = _make_mock_client(200, _fixture("selective.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/admin/users") is False

    @pytest.mark.asyncio
    async def test_blocks_private_path(self) -> None:
        client = _make_mock_client(200, _fixture("selective.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/private/docs") is False

    @pytest.mark.asyncio
    async def test_blocks_login(self) -> None:
        client = _make_mock_client(200, _fixture("selective.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/login") is False

    @pytest.mark.asyncio
    async def test_allows_public_path(self) -> None:
        client = _make_mock_client(200, _fixture("selective.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/about") is True

    @pytest.mark.asyncio
    async def test_allows_root(self) -> None:
        client = _make_mock_client(200, _fixture("selective.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/") is True


# ---------------------------------------------------------------------------
# Missing robots.txt (fail-open)
# ---------------------------------------------------------------------------


class TestMissingRobots:
    @pytest.mark.asyncio
    async def test_404_allows_all(self) -> None:
        client = _make_mock_client(404, "")
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/any/path") is True

    @pytest.mark.asyncio
    async def test_500_allows_all(self) -> None:
        client = _make_mock_client(500, "")
        cache = RobotsCache(_USER_AGENT, http_client=client)
        assert await cache.is_allowed("https://example.com/any/path") is True


# ---------------------------------------------------------------------------
# Network error (fail-open)
# ---------------------------------------------------------------------------


class TestNetworkError:
    @pytest.mark.asyncio
    async def test_request_error_allows_all(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def _get(*args: Any, **kwargs: Any) -> None:
            raise httpx.RequestError("connection refused")

        mock_client.get = _get  # type: ignore[method-assign]
        cache = RobotsCache(_USER_AGENT, http_client=mock_client)
        assert await cache.is_allowed("https://example.com/page") is True

    @pytest.mark.asyncio
    async def test_timeout_allows_all(self) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def _get(*args: Any, **kwargs: Any) -> None:
            raise httpx.TimeoutException("timed out")

        mock_client.get = _get  # type: ignore[method-assign]
        cache = RobotsCache(_USER_AGENT, http_client=mock_client)
        assert await cache.is_allowed("https://example.com/page") is True


# ---------------------------------------------------------------------------
# Caching behaviour
# ---------------------------------------------------------------------------


class TestCaching:
    @pytest.mark.asyncio
    async def test_fetches_robots_only_once_per_domain(self) -> None:
        call_count = 0

        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def _get(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.text = _fixture("allow_all.txt")
            return resp

        mock_client.get = _get  # type: ignore[method-assign]
        cache = RobotsCache(_USER_AGENT, http_client=mock_client)

        await cache.is_allowed("https://example.com/page1")
        await cache.is_allowed("https://example.com/page2")
        await cache.is_allowed("https://example.com/page3")

        assert call_count == 1

    @pytest.mark.asyncio
    async def test_fetches_separately_per_domain(self) -> None:
        call_count = 0

        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def _get(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.text = _fixture("allow_all.txt")
            return resp

        mock_client.get = _get  # type: ignore[method-assign]
        cache = RobotsCache(_USER_AGENT, http_client=mock_client)

        await cache.is_allowed("https://example.com/page")
        await cache.is_allowed("https://other.com/page")

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_clear_resets_cache(self) -> None:
        call_count = 0

        mock_client = AsyncMock(spec=httpx.AsyncClient)

        async def _get(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            resp.text = _fixture("allow_all.txt")
            return resp

        mock_client.get = _get  # type: ignore[method-assign]
        cache = RobotsCache(_USER_AGENT, http_client=mock_client)

        await cache.is_allowed("https://example.com/page")
        cache.clear()
        await cache.is_allowed("https://example.com/page")

        assert call_count == 2


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_url_without_scheme_is_allowed(self) -> None:
        client = _make_mock_client(200, _fixture("disallow_all.txt"))
        cache = RobotsCache(_USER_AGENT, http_client=client)
        # Unparseable URL — no scheme/netloc — treated as allowed
        assert await cache.is_allowed("/relative/path") is True
