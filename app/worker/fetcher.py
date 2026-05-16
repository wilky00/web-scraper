# ABOUTME: Playwright-based async page fetcher for the crawl worker.
# ABOUTME: PageFetcher is an async context manager; FetchResult is the returned data container.
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from types import TracebackType

import structlog
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError

from app.config.models import CrawlConfig
from app.crawl.canonicalize import canonicalize

logger = structlog.get_logger(__name__)


@dataclass
class FetchResult:
    url: str
    canonical_url: str
    status_code: int | None
    html: str
    content_type: str
    depth: int
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None and self.status_code is not None


class PageFetcher:
    def __init__(self, config: CrawlConfig) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._last_fetch_time: float = 0.0

    async def __aenter__(self) -> PageFetcher:
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def fetch(self, url: str, depth: int = 0) -> FetchResult:
        if self._browser is None:
            raise RuntimeError("PageFetcher must be used as an async context manager")

        canonical = canonicalize(url)

        # Enforce inter-request delay against the previous fetch
        if self._config.delay_between_requests_ms > 0 and self._last_fetch_time > 0:
            elapsed_ms = (time.monotonic() - self._last_fetch_time) * 1000
            remaining_ms = self._config.delay_between_requests_ms - elapsed_ms
            if remaining_ms > 0:
                await asyncio.sleep(remaining_ms / 1000)

        context: BrowserContext = await self._browser.new_context(
            user_agent=self._config.user_agent
        )
        try:
            page = await context.new_page()
            try:
                response = await page.goto(url, timeout=self._config.timeout_seconds * 1000)
                self._last_fetch_time = time.monotonic()

                if response is None:
                    return FetchResult(
                        url=url,
                        canonical_url=canonical,
                        status_code=None,
                        html="",
                        content_type="",
                        depth=depth,
                        error="Navigation returned no response",
                    )

                status_code = response.status
                content_type = response.headers.get("content-type", "")
                html = await page.content()

                logger.info("page.fetched", url=url, status=status_code, depth=depth)
                return FetchResult(
                    url=url,
                    canonical_url=canonical,
                    status_code=status_code,
                    html=html,
                    content_type=content_type,
                    depth=depth,
                )
            except PlaywrightError as exc:
                self._last_fetch_time = time.monotonic()
                error_msg = str(exc)
                logger.warning("page.fetch_error", url=url, error=error_msg)
                return FetchResult(
                    url=url,
                    canonical_url=canonical,
                    status_code=None,
                    html="",
                    content_type="",
                    depth=depth,
                    error=error_msg,
                )
            finally:
                await page.close()
        finally:
            await context.close()
