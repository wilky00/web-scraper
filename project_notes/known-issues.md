# Known Issues

## httpx per-request cookies DeprecationWarning in API tests
**Status:** open
**Description:** `httpx` is deprecating per-request `cookies={}` in async requests. Affects `tests/api/test_auth_api.py` and `tests/api/test_criteria_api.py` — 12 warnings emitted on every test run. Tests still pass.
**Workaround:** Set cookies on the `AsyncClient` instance instead of per-request. Fix in a future sprint when cleaning up test helpers.
**Ref:** `tests/api/test_auth_api.py` (all login/logout tests), `tests/api/test_criteria_api.py` (all session cookie tests)

## Tailwind Play CDN — not production-ready
**Status:** open
**Description:** `app/templates/base.html` loads Tailwind via the Play CDN (`https://cdn.tailwindcss.com`). This is a development-only approach — it is slower, downloads unused styles, and should not be used in staging or production.
**Workaround:** Use as-is for local development. Switch to compiled Tailwind output before staging deploy (Phase 8 or pre-deploy hardening sprint).
**Ref:** `app/templates/base.html:8`

## docker compose up end-to-end smoke test never run
**Status:** open
**Description:** The full `docker compose up` + `GET /health` end-to-end test has not been run because Docker Desktop is not running in the dev environment. All unit and API tests pass, but the full container stack has not been validated.
**Workaround:** Run manually on saltrun-staging or when Docker Desktop is available.

## Accessibility scan not performed on Phase 2 UI
**Status:** open
**Description:** No axe-core or Lighthouse accessibility scan has been run on the criteria list (`/criteria`) or criteria editor (`/criteria/new`, `/criteria/{group_id}`) pages. These pages use semantic HTML, keyboard-accessible buttons, ARIA labels on icon buttons, and sufficient color contrast by design, but no automated scan has confirmed WCAG 2.1 AA compliance.
**Workaround:** Run Lighthouse accessibility audit once the app is accessible in a browser (requires `docker compose up`). Target score ≥ 90. Address any critical/serious issues before staging deploy.

## YAML round-trip is lossy (comments and formatting not preserved)
**Status:** open — acceptable for MVP
**Description:** When loading an existing criteria for editing, the stored `config_snapshot` (JSON) is re-serialized to YAML via `yaml.dump()`. Original comments, blank lines, and custom field ordering from the author's YAML are not preserved.
**Workaround:** No workaround — this is acceptable for MVP. A future improvement would store the raw YAML text alongside the JSON snapshot in `CriteriaVersion`.
**Ref:** `app/web/criteria.py:155-163`

## `app/auth/permissions.py` low unit test coverage (48%)
**Status:** open — intentional
**Description:** `require_operator()` is tested indirectly via API tests using `dependency_overrides`, so the function body itself (lines 31–49) is not exercised in unit tests. Coverage is low but the logic is validated end-to-end through auth API tests.
**Workaround:** Add a dedicated integration test that exercises `require_operator()` with a real Redis + DB connection. Defer to integration test sprint.

## `app/web/dashboard.py` low unit test coverage (62%)
**Status:** open — intentional
**Description:** Dashboard is a stub page. Coverage will improve when Phase 7 fleshes it out.
**Ref:** `app/web/dashboard.py`

## `persist_crawl_page()` always sets `raw_html_path=None`
**Status:** open — deferred to Phase 8
**Description:** MinIO/S3 raw HTML upload is not implemented. `CrawlPage.raw_html_path` is always `None` until Phase 8 adds the upload step.
**Ref:** `app/worker/persist.py:23`

## Sprint 4.1 helpers not wired into `PageFetcher`
**Status:** open — deferred to Phase 6
**Description:** `RobotsCache`, `is_path_blocked`, `is_content_type_blocked`, and `PageLimitTracker` exist but are not called from `PageFetcher.fetch()`. The Phase 6 job orchestrator is the correct integration point. Until then, no robots/filter/limits enforcement happens on fetches.
**Ref:** `app/worker/fetcher.py`, `app/crawl/`

## Dedup domain matching doesn't collapse subdomains — Phase 5
**Status:** open — acceptable for MVP
**Description:** `normalize_domain` strips only `www.` — `shop.example.com` and `example.com` are treated as different domains and won't be deduped by domain pass. Only exact root-domain matches (after www. strip) are caught.
**Workaround:** Acceptable for MVP. A future improvement would normalize to registered domain (e.g. via `tldextract`).
**Ref:** `app/dedup/normalize.py:35-37`

## Phone normalization is US-only in both extraction and dedup — Phase 5
**Status:** open — intentional for MVP
**Description:** `app/extraction/phone.py` and `app/dedup/normalize.normalize_phone()` both treat 10-digit NANP format as canonical. International numbers (non-US country codes) are silently discarded.
**Workaround:** Acceptable for MVP. International support would require a library like `phonenumbers`.
**Ref:** `app/extraction/phone.py:25-33`, `app/dedup/normalize.py:59-77`

## `RobotsCache` in-memory only — not shared across jobs
**Status:** open — acceptable for MVP
**Description:** `RobotsCache` caches robots.txt per domain in a dict on the object instance. A new instance is created per job run, so the cache does not persist across jobs or worker restarts. Every new job re-fetches robots.txt for all domains.
**Ref:** `app/crawl/robots.py`
