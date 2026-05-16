# Phase 4 — Crawl Engine — Status Report

## Sprint 4.1 — Crawler Foundation
**Completed:** 2026-05-15

### What was built
- `app/crawl/__init__.py` — package init, exports all public symbols
- `app/crawl/canonicalize.py` — `canonicalize(url)` pure function
- `app/crawl/robots.py` — `RobotsCache` class with per-domain in-memory cache
- `app/crawl/filter.py` — `is_path_blocked()` and `is_content_type_blocked()` pure functions
- `app/crawl/limits.py` — `PageLimitTracker` with `is_within_limits()` / `record_crawled()`
- `tests/fixtures/robots/allow_all.txt` — `User-agent: * / Allow: /`
- `tests/fixtures/robots/disallow_all.txt` — `User-agent: * / Disallow: /`
- `tests/fixtures/robots/selective.txt` — disallows `/admin/`, `/private/`, `/login`
- `tests/unit/test_canonicalize.py` — 25 tests
- `tests/unit/test_robots.py` — 18 tests
- `tests/unit/test_crawl_filter.py` — 24 tests
- `tests/unit/test_crawl_limits.py` — 13 tests

### Key decisions
- `canonicalize()` strips trailing slashes via `posixpath.normpath` — intentional for deduplication; `/about/` and `/about` canonicalize to the same URL
- `RobotsCache` fails open: 404, non-200 status, and network errors all result in allow-all. This avoids blocking crawls due to transient infrastructure issues
- `RobotsCache` uses `http_client` constructor injection for test isolation (same pattern as `GooglePlacesConnector`)
- `is_path_blocked` uses prefix matching for bare patterns (`/admin` blocks `/admin/users` but not `/administrator`) and `fnmatch` for patterns containing `*`, `?`, or `[`
- `PageLimitTracker` is deliberately stateful and non-thread-safe — designed for single-threaded async use within one RQ job. A new instance is created per job run
- No `tests/fixtures/urls/` directory created — all canonicalization test cases use inline strings; the fixture dir would have been redundant

### Test results
80/80 Sprint 4.1 tests green | 252/252 full suite green | ruff clean | mypy strict clean

### Bugs found and fixed
None — first-pass implementation was clean.

### Open issues / follow-ups
- Sprint 4.2 (Playwright Worker) will consume all four modules; no standalone integration test possible until then
- `crawl.yml` `delay_between_requests_ms` is modeled in `CrawlConfig` but not yet enforced — Sprint 4.2 will add the inter-request delay to the page fetcher

---

## Sprint 4.2 — Playwright Worker
**Completed:** 2026-05-15

### What was built
- `app/worker/__init__.py` — package init; Playwright imports are only permitted in this package
- `app/worker/fetcher.py` — `FetchResult` dataclass + `PageFetcher` async context manager
- `app/worker/persist.py` — `persist_crawl_page()` and `log_crawl_event()` DB write helpers
- `tests/fixtures/html/simple.html` — minimal static HTML fixture page
- `tests/fixtures/html/with_links.html` — HTML fixture page with internal + external links
- `tests/unit/test_fetcher.py` — 24 unit tests (mocked Playwright)
- `tests/unit/test_worker_persist.py` — 15 unit tests (mocked AsyncSession)
- `tests/integration/test_playwright_crawl.py` — 7 real Playwright integration tests against a local HTTP fixture server
- `pyproject.toml` — `playwright` added to dev extras so unit tests can import + mock it

### Key decisions
- `PageFetcher.fetch()` is pure: takes URL + depth, returns `FetchResult`. No robots/filter/limits wiring — that belongs in the Phase 6 job orchestrator, not the fetcher
- `delay_between_requests_ms` enforced via `time.monotonic()` + `asyncio.sleep()` before each fetch after the first; skipped if delay=0 or elapsed time already exceeds the delay
- `persist_crawl_page()` sets `raw_html_path=None` — MinIO raw HTML upload deferred to Phase 8
- `playwright` added to dev extras (Python package only, no browsers) so tests can patch `async_playwright` without needing the worker container; actual Playwright browsers only installed in `Dockerfile.worker`
- Integration tests skip automatically if ms-playwright browser cache is absent (safe for CI without playwright install)

### Test results
46 new tests (24 unit + 15 unit persist + 7 integration) | 298/298 full suite green | ruff clean | mypy strict clean

### Bugs found and fixed
None — first-pass implementation was clean.

### Open issues / follow-ups
- Sprint 4.1 helpers (`RobotsCache`, `is_path_blocked`, `is_content_type_blocked`, `PageLimitTracker`) not wired into `PageFetcher` — Phase 6 job orchestrator is the correct integration point
- MinIO raw HTML upload (`raw_html_path`) deferred to Phase 8
