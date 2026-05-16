# ABOUTME: Worker package — contains all Playwright-dependent code for the crawl worker.
# ABOUTME: Playwright must ONLY be imported from this package, never from app/ directly.
from __future__ import annotations

from app.worker.fetcher import FetchResult, PageFetcher
from app.worker.persist import log_crawl_event, persist_crawl_page

__all__ = ["FetchResult", "PageFetcher", "log_crawl_event", "persist_crawl_page"]
