# ABOUTME: Integration tests for PageFetcher using real Playwright against a local HTTP server.
# ABOUTME: Requires `playwright install chromium` to have been run in the test environment.
from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

import pytest

from app.config.models import CrawlConfig
from app.worker.fetcher import PageFetcher

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "html"

pytestmark = pytest.mark.skipif(
    not (Path.home() / ".cache" / "ms-playwright").exists()
    and not (Path.home() / "Library" / "Caches" / "ms-playwright").exists(),
    reason="Playwright browsers not installed — run: playwright install chromium",
)


@pytest.fixture(scope="module")
def static_server() -> str:
    """Start a local HTTP server serving html fixtures. Returns the base URL."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(FIXTURES_DIR),
    )
    # Suppress request logging from the test server
    handler.log_message = lambda *args: None  # type: ignore[method-assign]
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


@pytest.fixture
def crawl_config() -> CrawlConfig:
    return CrawlConfig.model_validate(
        {"user_agent": "TestCrawler/1.0", "timeout_seconds": 15, "delay_between_requests_ms": 0}
    )


class TestPageFetcherIntegration:
    async def test_fetch_simple_html_returns_200(
        self, static_server: str, crawl_config: CrawlConfig
    ) -> None:
        async with PageFetcher(crawl_config) as fetcher:
            result = await fetcher.fetch(f"{static_server}/simple.html")
        assert result.status_code == 200
        assert result.error is None

    async def test_fetch_simple_html_contains_expected_text(
        self, static_server: str, crawl_config: CrawlConfig
    ) -> None:
        async with PageFetcher(crawl_config) as fetcher:
            result = await fetcher.fetch(f"{static_server}/simple.html")
        assert "Hello, Crawler" in result.html

    async def test_fetch_html_has_content_type(
        self, static_server: str, crawl_config: CrawlConfig
    ) -> None:
        async with PageFetcher(crawl_config) as fetcher:
            result = await fetcher.fetch(f"{static_server}/simple.html")
        assert "text/html" in result.content_type

    async def test_fetch_preserves_depth(
        self, static_server: str, crawl_config: CrawlConfig
    ) -> None:
        async with PageFetcher(crawl_config) as fetcher:
            result = await fetcher.fetch(f"{static_server}/simple.html", depth=2)
        assert result.depth == 2

    async def test_fetch_sets_canonical_url(
        self, static_server: str, crawl_config: CrawlConfig
    ) -> None:
        async with PageFetcher(crawl_config) as fetcher:
            url = f"{static_server}/simple.html"
            result = await fetcher.fetch(url)
        assert result.canonical_url == result.url

    async def test_fetch_missing_page_returns_result(
        self, static_server: str, crawl_config: CrawlConfig
    ) -> None:
        async with PageFetcher(crawl_config) as fetcher:
            result = await fetcher.fetch(f"{static_server}/nonexistent.html")
        # 404 from simple HTTP server is still a valid response (not an error)
        assert result.status_code == 404
        assert result.error is None

    async def test_fetch_with_links_page(
        self, static_server: str, crawl_config: CrawlConfig
    ) -> None:
        async with PageFetcher(crawl_config) as fetcher:
            result = await fetcher.fetch(f"{static_server}/with_links.html")
        assert result.status_code == 200
        assert "Links Test Page" in result.html
