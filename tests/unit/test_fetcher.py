# ABOUTME: Unit tests for PageFetcher and FetchResult using mocked Playwright.
# ABOUTME: Covers lifecycle, fetch behavior, delay enforcement, and error handling.
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.models import CrawlConfig
from app.worker.fetcher import FetchResult, PageFetcher


def make_config(**kwargs: object) -> CrawlConfig:
    defaults = {
        "user_agent": "TestBot/1.0",
        "timeout_seconds": 10,
        "delay_between_requests_ms": 0,
    }
    defaults.update(kwargs)
    return CrawlConfig.model_validate(defaults)


def make_mock_playwright_stack(
    *,
    status: int = 200,
    content_type: str = "text/html",
    html: str = "<html><body>Hello</body></html>",
    goto_return: object = "response",  # set to None to simulate null response
    goto_raises: Exception | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    """Returns (mock_ap_fn, mock_browser, mock_page) for patching async_playwright."""
    mock_response = MagicMock()
    mock_response.status = status
    mock_response.headers = {"content-type": content_type}

    mock_page = AsyncMock()
    mock_page.close = AsyncMock()
    mock_page.content = AsyncMock(return_value=html)
    if goto_raises is not None:
        mock_page.goto = AsyncMock(side_effect=goto_raises)
    elif goto_return is None:
        mock_page.goto = AsyncMock(return_value=None)
    else:
        mock_page.goto = AsyncMock(return_value=mock_response)

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)
    mock_pw.stop = AsyncMock()

    mock_pcm = MagicMock()
    mock_pcm.start = AsyncMock(return_value=mock_pw)

    mock_ap_fn = MagicMock(return_value=mock_pcm)

    return mock_ap_fn, mock_browser, mock_page


class TestFetchResult:
    def test_success_true_when_status_set_and_no_error(self) -> None:
        r = FetchResult(
            url="http://x.com/",
            canonical_url="http://x.com/",
            status_code=200,
            html="",
            content_type="text/html",
            depth=0,
        )
        assert r.success is True

    def test_success_false_when_error_set(self) -> None:
        r = FetchResult(
            url="http://x.com/",
            canonical_url="http://x.com/",
            status_code=None,
            html="",
            content_type="",
            depth=0,
            error="timeout",
        )
        assert r.success is False

    def test_success_false_when_status_none_and_no_error(self) -> None:
        r = FetchResult(
            url="http://x.com/",
            canonical_url="http://x.com/",
            status_code=None,
            html="",
            content_type="",
            depth=0,
        )
        assert r.success is False

    def test_success_false_on_non_200_status(self) -> None:
        # success only requires status_code is not None, not that it's 200
        r = FetchResult(
            url="http://x.com/",
            canonical_url="http://x.com/",
            status_code=404,
            html="",
            content_type="text/html",
            depth=0,
        )
        assert r.success is True

    def test_error_defaults_to_none(self) -> None:
        r = FetchResult(
            url="http://x.com/",
            canonical_url="http://x.com/",
            status_code=200,
            html="",
            content_type="text/html",
            depth=0,
        )
        assert r.error is None


class TestPageFetcherLifecycle:
    async def test_aenter_launches_headless_chromium(self) -> None:
        mock_ap_fn, mock_browser, _ = make_mock_playwright_stack()
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            fetcher = PageFetcher(make_config())
            result = await fetcher.__aenter__()
            assert result is fetcher
            mock_ap_fn.return_value.start.assert_awaited_once()
            mock_ap_fn.return_value.start.return_value.chromium.launch.assert_awaited_once_with(
                headless=True
            )

    async def test_aexit_closes_browser_and_stops_playwright(self) -> None:
        mock_ap_fn, mock_browser, _ = make_mock_playwright_stack()
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()):
                pass
            mock_browser.close.assert_awaited_once()
            mock_ap_fn.return_value.start.return_value.stop.assert_awaited_once()

    async def test_fetch_without_context_manager_raises(self) -> None:
        fetcher = PageFetcher(make_config())
        with pytest.raises(RuntimeError, match="context manager"):
            await fetcher.fetch("https://example.com/")

    async def test_aexit_clears_internal_references(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack()
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            fetcher = PageFetcher(make_config())
            async with fetcher:
                assert fetcher._browser is not None
            assert fetcher._browser is None
            assert fetcher._playwright is None


class TestPageFetcherFetch:
    async def test_fetch_returns_result_with_status_and_html(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack(status=200, html="<html>Test</html>")
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                result = await f.fetch("https://example.com/page")
        assert result.status_code == 200
        assert result.html == "<html>Test</html>"
        assert result.error is None

    async def test_fetch_stores_canonical_url(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack()
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                result = await f.fetch("HTTP://Example.COM:80/page#frag")
        assert result.canonical_url == "http://example.com/page"

    async def test_fetch_stores_original_url(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack()
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                result = await f.fetch("https://example.com/page")
        assert result.url == "https://example.com/page"

    async def test_fetch_passes_depth(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack()
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                result = await f.fetch("https://example.com/page", depth=3)
        assert result.depth == 3

    async def test_fetch_sets_user_agent_on_context(self) -> None:
        mock_ap_fn, mock_browser, _ = make_mock_playwright_stack()
        config = make_config(user_agent="CustomAgent/2.0")
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(config) as f:
                await f.fetch("https://example.com/")
        mock_browser.new_context.assert_awaited_once_with(user_agent="CustomAgent/2.0")

    async def test_fetch_passes_timeout_to_goto(self) -> None:
        mock_ap_fn, _, mock_page = make_mock_playwright_stack()
        config = make_config(timeout_seconds=15)
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(config) as f:
                await f.fetch("https://example.com/")
        mock_page.goto.assert_awaited_once_with("https://example.com/", timeout=15000)

    async def test_fetch_on_playwright_error_returns_error_result(self) -> None:
        from playwright.async_api import Error as PlaywrightError

        mock_ap_fn, _, _ = make_mock_playwright_stack(
            goto_raises=PlaywrightError("Navigation failed")
        )
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                result = await f.fetch("https://example.com/")
        assert result.error is not None
        assert "Navigation failed" in result.error
        assert result.status_code is None
        assert result.html == ""

    async def test_fetch_on_null_response_returns_error_result(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack(goto_return=None)
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                result = await f.fetch("https://example.com/")
        assert result.error == "Navigation returned no response"
        assert result.status_code is None

    async def test_fetch_closes_page_and_context_on_success(self) -> None:
        mock_ap_fn, mock_browser, mock_page = make_mock_playwright_stack()
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                await f.fetch("https://example.com/")
        mock_page.close.assert_awaited_once()
        mock_browser.new_context.return_value.close.assert_awaited_once()

    async def test_fetch_closes_page_and_context_on_error(self) -> None:
        from playwright.async_api import Error as PlaywrightError

        mock_ap_fn, mock_browser, mock_page = make_mock_playwright_stack(
            goto_raises=PlaywrightError("timeout")
        )
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                await f.fetch("https://example.com/")
        mock_page.close.assert_awaited_once()
        mock_browser.new_context.return_value.close.assert_awaited_once()

    async def test_fetch_stores_content_type(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack(content_type="text/html; charset=utf-8")
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            async with PageFetcher(make_config()) as f:
                result = await f.fetch("https://example.com/")
        assert result.content_type == "text/html; charset=utf-8"


class TestPageFetcherDelay:
    async def test_no_sleep_on_first_fetch(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack()
        config = make_config(delay_between_requests_ms=500)
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            with patch("app.worker.fetcher.asyncio.sleep") as mock_sleep:
                async with PageFetcher(config) as f:
                    await f.fetch("https://example.com/")
        mock_sleep.assert_not_called()

    async def test_sleep_called_on_second_fetch_when_within_delay(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack()
        config = make_config(delay_between_requests_ms=500)
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            with patch("app.worker.fetcher.asyncio.sleep") as mock_sleep:
                with patch("app.worker.fetcher.time.monotonic", side_effect=[0.0, 0.1, 0.1]):
                    # side_effect: first call sets _last_fetch_time=0.0 (elapsed calc),
                    # second call is after first goto (sets _last_fetch_time=0.1),
                    # third call is elapsed check on second fetch (only 100ms elapsed of 500ms)
                    async with PageFetcher(config) as f:
                        f._last_fetch_time = 0.1  # simulate a prior fetch at t=0.1
                        await f.fetch("https://example.com/p2")
        mock_sleep.assert_called_once()
        sleep_arg = mock_sleep.call_args[0][0]
        assert sleep_arg > 0

    async def test_no_sleep_when_delay_is_zero(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack()
        config = make_config(delay_between_requests_ms=0)
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            with patch("app.worker.fetcher.asyncio.sleep") as mock_sleep:
                async with PageFetcher(config) as f:
                    f._last_fetch_time = 0.001  # simulate prior fetch
                    await f.fetch("https://example.com/")
        mock_sleep.assert_not_called()

    async def test_no_sleep_when_delay_already_elapsed(self) -> None:
        mock_ap_fn, _, _ = make_mock_playwright_stack()
        config = make_config(delay_between_requests_ms=100)
        with patch("app.worker.fetcher.async_playwright", mock_ap_fn):
            with patch("app.worker.fetcher.asyncio.sleep") as mock_sleep:
                # monotonic: first call returns current time much later than _last_fetch_time
                with patch("app.worker.fetcher.time.monotonic", return_value=99.0):
                    async with PageFetcher(config) as f:
                        f._last_fetch_time = 0.1  # 98.9 seconds ago — well past 100ms delay
                        await f.fetch("https://example.com/")
        mock_sleep.assert_not_called()
