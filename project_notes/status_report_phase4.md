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
