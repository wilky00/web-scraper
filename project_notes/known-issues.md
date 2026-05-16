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

## `app/web/dashboard.py` low unit test coverage
**Status:** open — intentional
**Description:** Dashboard queries are exercised via the audit page and exports API tests, but the dashboard route itself has no dedicated test. Coverage is 38%. The route uses the same DB session pattern as other tested routes.
**Ref:** `app/web/dashboard.py`

## `app/web/settings_page.py` has no dedicated tests
**Status:** open — intentional
**Description:** `GET /settings` and `_redact()` have no test coverage (38%). The `_redact()` pure function is straightforward but untested. Add unit tests for `_redact()` and a GET /settings API test in a future hardening sprint.
**Ref:** `app/web/settings_page.py`

## `persist_crawl_page()` raw HTML upload: RESOLVED in Phase 8
**Status:** RESOLVED in Sprint 8.1
**Description:** `storage.upload_bytes()` is now called from `persist_crawl_page()` when `settings.s3_endpoint_url` is set. `CrawlPage.raw_html_path` is set to the S3 key when upload succeeds; `None` otherwise (graceful no-op when S3 is not configured).
**Ref:** `app/worker/persist.py`

## Sprint 4.1 helpers not wired into `PageFetcher`
**Status:** RESOLVED in Sprint 6.1
**Description:** `RobotsCache`, `is_path_blocked`, `is_content_type_blocked`, and `PageLimitTracker` are now called from `app/jobs/orchestrator.py`'s `_try_crawl()` helper. `PageFetcher` remains a pure fetch primitive; the orchestrator composes all four modules.
**Ref:** `app/jobs/orchestrator.py:_try_crawl()`

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

## Status badge on job detail page does not auto-update — Phase 6
**Status:** open — acceptable for MVP
**Description:** The status badge at the top of `/jobs/{id}` is rendered on initial page load and does not update during HTMX event-log polling. The event log (`#events-poll`) updates every 2s while the job is active, but the badge in the page header is static. Final status is only visible after a full page reload.
**Workaround:** User can reload the page once polling stops to see the final status badge. Acceptable for MVP — the event log stream makes current state clear.
**Ref:** `app/templates/jobs/detail.html`, `app/templates/jobs/_events_poll.html`

## Resume re-runs job from scratch; raw_search_results grows on repeated resume — Phase 6
**Status:** open — acceptable for MVP
**Description:** `POST /api/jobs/{id}/resume` re-enqueues the job to run from the beginning. There is no mid-stream checkpoint. Records stored before the pause are preserved; the resumed run may create duplicate `BusinessRecord` rows (caught by dedup) and additional `RawSearchResult` rows (not deduplicated). On repeated pause/resume cycles, `raw_search_results` grows unboundedly for the same job.
**Workaround:** Acceptable for MVP. A future improvement would store a connector cursor/offset to enable true resume.
**Ref:** `app/api/jobs.py:resume_job()`, `app/jobs/orchestrator.py`

## Accessibility scan not performed on Phase 6 UI — Phase 6
**Status:** open
**Description:** No axe-core or Lighthouse scan has been run on the job detail page (`/jobs/{id}`) or the events polling fragment (`/jobs/{id}/events`). These pages use semantic HTML, keyboard-accessible buttons with visible labels, and consistent Tailwind color scheme matching earlier pages, but no automated scan has confirmed WCAG 2.1 AA compliance.
**Workaround:** Run Lighthouse accessibility audit once the app is accessible in a browser (requires `docker compose up`). Target score ≥ 90. Address any critical/serious issues before staging deploy.
**Ref:** `app/templates/jobs/detail.html`, `app/templates/jobs/_events_poll.html`

## Accessibility scan not performed on Phase 7 UI — Phase 7
**Status:** open
**Description:** No axe-core or Lighthouse scan has been run on the records list (`/records`), detail (`/records/{id}`), inline edit form (`/records/{id}/edit` HTMX partial), or add modal pages. These pages follow the same Tailwind patterns as earlier pages but no automated scan has confirmed WCAG 2.1 AA compliance.
**Workaround:** Run Lighthouse accessibility audit once the app is accessible in a browser. Target score ≥ 90.
**Ref:** `app/templates/records/list.html`, `app/templates/records/detail.html`, `app/templates/records/_edit_form.html`, `app/templates/records/_add_modal.html`

## Accessibility scan not performed on Phase 8 UI — Phase 8
**Status:** open
**Description:** No axe-core or Lighthouse scan has been run on the exports list (`/exports`), audit log (`/audit-log`), settings (`/settings`), or updated dashboard (`/`) pages. Pages follow the same accessible Tailwind patterns as earlier phases but no automated scan has been done.
**Workaround:** Run Lighthouse accessibility audit once the app is accessible in a browser. Target score ≥ 90. Address critical/serious issues before staging deploy.
**Ref:** `app/templates/exports/list.html`, `app/templates/audit/list.html`, `app/templates/settings.html`, `app/templates/dashboard.html`

## `app/templates/exports/` force-added to git due to `.gitignore` pattern — Phase 8
**Status:** open — minor
**Description:** `.gitignore` contains `exports/` to exclude generated export files. This pattern also matches `app/templates/exports/`, causing the template directory to be ignored. The templates were force-added with `git add -f`. The gitignore rule should be narrowed to `/exports/` (root-anchored) or `exports/*.csv` / `exports/*.xlsx` before staging deploy.
**Ref:** `.gitignore`, `app/templates/exports/`

## API token management UI not implemented — Phase 7
**Status:** open — deferred
**Description:** `POST /api/auth/token` and `DELETE /api/auth/token` exist and work (20 tests pass), but there is no UI page for managing tokens. A user must call the API directly (e.g., with curl) to generate or revoke their token. A simple token management page on a settings/profile page would be the natural home for this.
**Workaround:** Use curl: `curl -X POST http://localhost:8000/api/auth/token -H "Content-Type: application/json" -d '{"scopes":["records:read"]}' -b session=<cookie>`. Defer to Phase 8 or pre-deploy hardening.

## `test_migrations.py` does not assert new `api_key_hash`/`api_key_scopes` columns — Phase 7
**Status:** open — minor gap
**Description:** `tests/integration/test_migrations.py::test_users_table_has_expected_columns` checks a subset of user columns but does not assert the Sprint 7.2 migration columns (`api_key_hash`, `api_key_scopes`) exist. These columns will be present after `alembic upgrade head`, but the integration test does not verify it.
**Workaround:** Acceptable for MVP. Add assertions in a future integration test sprint.
**Ref:** `tests/integration/test_migrations.py:84-86`, `migrations/versions/a1b2c3d4e5f6_add_api_token_to_users.py`
