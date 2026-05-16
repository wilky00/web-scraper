# Progress Log

## Phase 0 — Project Scaffold

### Sprint 0.1 — Repo & Docker Foundation
- [x] `pyproject.toml` with all pinned dependencies (uv, ruff, pytest, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, structlog, passlib[bcrypt], redis, rq, httpx, playwright, openpyxl, boto3, python-multipart, jinja2, itsdangerous, tenacity, bleach, authlib)
- [x] `Dockerfile` (Python 3.12-slim, uv install, non-root user)
- [x] `Dockerfile.worker` (same base + Playwright browser install)
- [x] `docker-compose.yml` (db: postgres:16, redis: redis:7, app: port 8000, worker — all with healthchecks, named volumes, restart: unless-stopped)
- [x] `docker-compose.staging.yml` (staging overrides — no local MinIO, uses existing)
- [x] `docker-compose.prod.yml` (prod overrides — stricter, no exposed ports beyond Caddy)
- [x] `.env.example` documenting all required secrets
- [x] `config/app.yml.example`, `connectors.yml.example`, `crawl.yml.example`, `retention.yml.example`, `ai/ai_base.yaml.example`
- [x] Minimal FastAPI app (`app/main.py`) with `GET /health` → `{"status": "ok", "db": "ok", "redis": "ok"}`
- [x] `CLAUDE.md` in project root with project-specific instructions
- [x] GitHub Actions CI workflow: ruff, mypy, pytest, pip-audit
- [x] 4/4 unit tests passing, ruff clean, mypy clean
- NOTE: `docker compose up` end-to-end test pending (requires Docker Desktop running)

### Sprint 0.2 — Core Data Model — COMPLETE (40/40 unit tests green, ruff+mypy clean)
- [x] All 12 SQLAlchemy 2.0 models (type-annotated, `dict[str, Any]` on JSONB columns)
  - `users`, `criteria_groups`, `criteria_versions`, `connectors`, `crawl_jobs`,
    `crawl_job_events`, `raw_search_results`, `crawl_pages`, `business_records`,
    `record_sources`, `record_audit_log`, `exports`
  - NOTE: `metadata` renamed to `event_data` (CrawlJobEvent) and `extra_fields` (BusinessRecord) — avoids DeclarativeBase collision
- [x] Alembic setup: `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`
- [x] Initial migration `def32db42b5c_initial_schema.py` — all 12 tables with indexes and FKs
- [x] 36 model unit tests (structure checks, no DB required)
- [x] Integration tests: `tests/integration/test_migrations.py` (requires DB — runs in CI)

## 2026-05-15
**Completed:** Sprint 0.2 — 12 models, Alembic initial migration, 40 unit tests green
**In progress:** Phase 1 ready to start
**Next:** Sprint 1.1 — YAML Config Loading

## Phase 1 — Auth & Config Foundation

### Sprint 1.1 — YAML Config Loading — COMPLETE (104/104 unit tests green, ruff+mypy clean)
- [x] Pydantic v2 models for `app.yml` (AppConfig, FeaturesConfig)
- [x] Pydantic v2 models for `connectors.yml` (ConnectorsConfig)
- [x] Pydantic v2 models for `crawl.yml` (CrawlConfig)
- [x] Pydantic v2 models for `retention.yml` (RetentionConfig, RetentionDays)
- [x] YAML loader (`app/config/loader.py`) — ConfigLoadError, load_all_configs(), per-file loaders, AppConfigs dataclass
- [x] Criteria YAML schema (`app/config/criteria.py`) — CriteriaConfig with all §8 fields, all 12 operators (StrEnum), 5 namespaces validated
- [x] validate_criteria_yaml() — returns (CriteriaConfig | None, list[str]), never raises
- [x] Wire loader into FastAPI lifespan — app.state.config = AppConfigs; SystemExit(1) on failure
- [x] app/settings.py — config_dir: Path field (default Path("config"), overridable via CONFIG_DIR env var)
- [x] 33 unit tests for config models + loaders (test_config.py)
- [x] 31 unit tests for criteria schema (test_criteria_schema.py — all 12 operators, all 5 namespaces, error paths)
- [x] Fixture YAML files: tests/fixtures/criteria/valid_minimal.yml, valid_full.yml
  - NOTE: plan said 11 operators; requirements §8 lists 12 — implemented all 12 from requirements

### Sprint 1.2 — Local Auth — COMPLETE (verified green 2026-05-15, 135/135 tests, ruff+mypy clean)
- [x] `users` table seeded with one operator on first boot (email + password from `.env`)
- [x] bcrypt password hashing via bcrypt library directly (passlib+bcrypt4.x incompatible on Python 3.14)
- [x] `POST /auth/login` → HTTP-only, same-site session cookie (itsdangerous signed, Redis-backed)
- [x] `POST /auth/logout` → deletes session from Redis, clears cookie
- [x] `app/auth/permissions.py` — central `require_operator()` FastAPI dependency
- [x] Rate-limit login: 10 attempts / 60s per IP (Redis INCR/EXPIRE)
- [x] CSRF on login form (double-submit signed cookie) + session CSRF on post-auth forms
- [x] Session ID generated fresh on login (no fixation)
- [x] Login page (`/login`) — Jinja2, Tailwind Play CDN, Light/Dark mode (Alpine.js + localStorage)
- [x] Dashboard stub (`/`) — auth-protected, shows username + sign-out button
- [x] 19 unit tests: hashing, session signing, CSRF, rate limiter
- [x] 16 API tests: login/logout flows, unauthenticated redirect, rate limit, CSRF validation
  - NOTE: Starlette 1.0 changed TemplateResponse — `request` is first positional arg, not in context dict
  - NOTE: ruff B008 per-file ignore added for app/web/*.py + app/api/*.py (FastAPI Depends pattern)

## Phase 2 — Criteria Management — COMPLETE (2026-05-15)

### Sprint 2.1 — Criteria YAML Schema — COMPLETE (done in Sprint 1.1)
- [x] Pydantic v2 schema covering all fields from §8 of requirements — done in Sprint 1.1
- [x] All 12 operators validated as StrEnum — done in Sprint 1.1 (plan said 11; requirements list 12)
- [x] All 5 metric namespaces validated — done in Sprint 1.1
- [x] Unit tests with valid and invalid fixtures — done in Sprint 1.1 (31 tests)

### Sprint 2.2 — Criteria UI + Versioning — COMPLETE (verified green 2026-05-15, 148/148 tests, ruff+mypy clean)
- [x] Criteria list page (`GET /criteria`) — sortable table with status badges, Alpine.js client-side sort
- [x] Criteria editor (`GET /criteria/new`, `GET /criteria/{group_id}`) — YAML textarea, version history sidebar
- [x] Inline validation (`POST /api/criteria/validate`) — HTMX partial returning error list or success badge
- [x] Create new criteria (`POST /api/criteria`) — validates YAML, creates CriteriaGroup + CriteriaVersion v1
- [x] Save new version (`POST /api/criteria/{group_id}/versions`) — immutable, increments version number
- [x] Audit log entry on every save (action: `criteria_save`)
- [x] Nav bar in base.html with HTMX — Dashboard + Criteria links, dark mode toggle, sign-out
- [x] 13 API tests in `tests/api/test_criteria_api.py` covering validate, create, version save, list, editor
  - NOTE: Used `app.dependency_overrides[require_operator]` for clean test isolation (FastAPI DI pattern)
  - NOTE: Sprint 2.1 (Criteria YAML Schema) was completed early in Sprint 1.1; 2.2 was the first new work

## Phase 3 — Connectors

### Sprint 3.1 — Connector Abstraction + Fixture — COMPLETE (verified green 2026-05-15, 149/149 tests, ruff+mypy clean)
- [x] `app/connectors/base.py` — `ConnectorBase` ABC + `ConnectorResult` Pydantic schema
- [x] `app/connectors/fixture.py` — `FixtureConnector` reads `*.json` from fixture dir, yields `ConnectorResult`
- [x] `app/connectors/registry.py` — `ConnectorRegistry` maps connector names to instances
- [x] `tests/fixtures/connector_responses/*.json` — valid (3 results), empty, and partial-data (2 results) fixtures
- [x] `tests/unit/test_connectors.py` — 26 unit tests for fixture connector and registry
  - NOTE: `ConnectorResult` is a Pydantic DTO (not the ORM model) — `job_id` is added by the job runner in Phase 6
  - NOTE: `google_places` connector type logged but not registered until Sprint 3.2

### Sprint 3.2 — Google Places Connector — COMPLETE (verified green 2026-05-15, 172/172 tests, ruff+mypy clean)
- [x] `app/connectors/google_places.py` — `GooglePlacesConnectorConfig` + `GooglePlacesConnector`
- [x] Places API v1 Text Search with pagination (`nextPageToken`), per-page rate limiting, tenacity retry
- [x] API key read from `GOOGLE_PLACES_API_KEY` env var at discover-time; never stored or logged
- [x] `ConnectorRegistry` updated to register `google_places` connector type
- [x] `tests/unit/test_google_places.py` — 23 tests: config, discover, pagination, retry, registry
  - NOTE: `http_client` param injected for testing; live connector creates+closes its own `httpx.AsyncClient`
  - NOTE: Sprint 3.1 `test_unknown_connector_type_not_registered` updated to use `brave_search` now that `google_places` is implemented

## Phase 4 — Crawl Engine

### Sprint 4.1 — Crawler Foundation — COMPLETE (verified green 2026-05-15, 252/252 tests, ruff+mypy clean)
- [x] `app/crawl/__init__.py` — package init
- [x] `app/crawl/canonicalize.py` — URL canonicalization (normalize scheme, strip fragments, dedupe query params)
- [x] `app/crawl/robots.py` — robots.txt fetch, parse, cache, and compliance check
- [x] `app/crawl/filter.py` — blocked path pattern matching and binary Content-Type detection
- [x] `app/crawl/limits.py` — per-job and per-domain page limit tracker
- [x] `tests/fixtures/robots/allow_all.txt`, `disallow_all.txt`, `selective.txt`
- [x] `tests/unit/test_canonicalize.py` — 25 URL canonicalization unit tests
- [x] `tests/unit/test_robots.py` — 18 robots.txt compliance tests (mocked HTTP)
- [x] `tests/unit/test_crawl_filter.py` — 24 blocked path and content-type filter tests
- [x] `tests/unit/test_crawl_limits.py` — 13 per-job/per-domain limit tracker tests
  - NOTE: URL inline fixtures used; no separate `tests/fixtures/urls/` dir needed
  - NOTE: `RobotsCache` fails open (allows all) on 404, non-200, and network errors
  - NOTE: Path blocking uses prefix match for bare patterns, fnmatch for glob patterns

### Sprint 4.2 — Playwright Worker — COMPLETE (verified green 2026-05-15, 298/298 tests, ruff+mypy clean)
- [x] `app/worker/__init__.py` — package init (Playwright imports permitted here)
- [x] `app/worker/fetcher.py` — `FetchResult` dataclass + `PageFetcher` async context manager
- [x] `app/worker/persist.py` — `persist_crawl_page()` and `log_crawl_event()` DB helpers
- [x] `tests/fixtures/html/simple.html` — minimal static HTML fixture
- [x] `tests/fixtures/html/with_links.html` — HTML fixture with outbound links
- [x] `tests/unit/test_fetcher.py` — 24 unit tests with mocked Playwright async API
- [x] `tests/unit/test_worker_persist.py` — 15 unit tests for DB helpers
- [x] `tests/integration/test_playwright_crawl.py` — 7 real Playwright integration tests
  - NOTE: `playwright` added to dev extras so unit tests can import+mock it; browsers not needed for mocked tests
  - NOTE: `persist_crawl_page()` sets `raw_html_path=None` — MinIO upload deferred to Phase 8
  - NOTE: Sprint 4.1 helpers (robots, filter, limits) are not wired into `PageFetcher.fetch()` — deferred to Phase 6 job orchestrator

## Phase 5 — Extraction, Scoring, Deduplication

### Sprint 5.1 — Deterministic Extraction — COMPLETE (verified green 2026-05-15, 360/360 tests, ruff+mypy clean)
- [x] `app/extraction/__init__.py` — package init, exports public symbols
- [x] `app/extraction/models.py` — `ExtractedField` + `ExtractionResult` dataclasses
- [x] `app/extraction/_json_ld.py` — shared JSON-LD block parser (used by name + address)
- [x] `app/extraction/sanitize.py` — `sanitize_html(html) -> str` via bleach (pre-strips script/style to prevent text leakage)
- [x] `app/extraction/email.py` — mailto link + regex text extraction, deduped, lowercased
- [x] `app/extraction/phone.py` — tel link + regex text extraction, normalized to 10 digits
- [x] `app/extraction/name.py` — JSON-LD → og:site_name → title → h1 priority chain
- [x] `app/extraction/url.py` — og:url → canonical → base_url priority chain
- [x] `app/extraction/address.py` — JSON-LD PostalAddress → itemprop microdata
- [x] `app/extraction/runner.py` — `run_extraction(html, source_url, base_url) -> ExtractionResult`
- [x] `tests/fixtures/html/extraction/` — 10 static HTML fixtures
- [x] `tests/unit/test_extraction_sanitize.py` — 10 tests
- [x] `tests/unit/test_extraction_email.py` — 12 tests
- [x] `tests/unit/test_extraction_phone.py` — 10 tests
- [x] `tests/unit/test_extraction_name.py` — 12 tests
- [x] `tests/unit/test_extraction_url.py` — 8 tests
- [x] `tests/unit/test_extraction_address.py` — 8 tests
- [x] `tests/unit/test_extraction_runner.py` — 9 tests
  - NOTE: `beautifulsoup4>=4.12.0` + `lxml>=5.0.0` added to main deps; `types-beautifulsoup4` to dev extras
  - NOTE: `sanitize_html()` pre-decomposes script/style via BS4 before bleach — bleach `strip=True` preserves tag text content, which would leave raw JS inline
  - NOTE: `_json_ld.py` is a private shared utility (leading underscore) used by both name.py and address.py
  - NOTE: Phone extractor normalizes to 10-digit string (strips country code "1" if present)

### Sprint 5.2 — Scoring Engine — COMPLETE (verified green 2026-05-15, 442/442 tests, ruff+mypy clean)
- [x] `app/scoring/__init__.py` — package init, exports public symbols
- [x] `app/scoring/models.py` — `RuleResult` + `ScoringResult` dataclasses
- [x] `app/scoring/operators.py` — `evaluate_operator(op, metric_val, rule_val) -> bool` — all 12 operators
- [x] `app/scoring/engine.py` — `ScoringEngine` with `score(metrics, criteria) -> ScoringResult`
- [x] `tests/fixtures/scoring/` — 4 fixture metric JSON files
- [x] `tests/unit/test_scoring_operators.py` — 64 tests (all 12 operators + edge cases)
- [x] `tests/unit/test_scoring_engine.py` — 18 tests (exclude, must-have, should-have, weighted, scoring disabled, minimum score)
  - NOTE: `match_score = (earned_weight / total_weight) * 100.0` — both should_have and weighted_rules contribute
  - NOTE: Evaluation order is deterministic: exclude → must_have → scoring
  - NOTE: `Operator.in_` is the Python alias for YAML "in" (reserved keyword)

### Sprint 5.3 — Deduplication — COMPLETE (verified green 2026-05-15, 484/484 tests, ruff+mypy clean)
- [x] `app/dedup/__init__.py` — package init, exports public symbols
- [x] `app/dedup/normalize.py` — `normalize_domain()`, `normalize_name()`, `normalize_phone()`, `normalize_email()` pure functions
- [x] `app/dedup/engine.py` — `DeduplicationEngine` with 3-pass duplicate detection + `merge_duplicates()` mutating merge
- [x] `tests/fixtures/records/` — JSON fixture files: same domain set, same name+city set, same phone set, no-duplicates set
- [x] `tests/unit/test_dedup_normalize.py` — normalization function tests
- [x] `tests/unit/test_dedup_engine.py` — 3-pass detection tests, merge tests (source re-pointer, status/canonical_id set)
  - NOTE: Union-find with path compression used for transitive dedup grouping (A-B + B-C → one group)
  - NOTE: Missing city/state on either side is a wildcard — only conflicts when both sides have a value that differs
  - NOTE: Merge is in-place mutation on RecordData dataclasses; DB writes deferred to Phase 6 orchestrator

## Phase 5 COMPLETE — 2026-05-15
- 484/484 unit tests green | ruff clean | mypy strict clean
- Deferred: ExtractedField → record_sources DB writes → Phase 6 orchestrator
- Deferred: ExtractionResult → scoring metrics dict bridge → Phase 6 orchestrator
- Deferred: RecordData → ORM write-back after dedup merge → Phase 6 orchestrator

## Phase 6 — Job Queue & Lifecycle — COMPLETE (2026-05-16)
498/498 unit tests green | ruff clean | mypy strict clean
Deferred: Status badge auto-update on detail page → Phase 7 or pre-deploy
Deferred: Accessibility scan for Phase 6 UI → Phase 8 / pre-deploy hardening
Deferred: Resume re-runs from scratch (no checkpoint) → acceptable for MVP

### Sprint 6.2 — Job Controls — COMPLETE (verified green 2026-05-16, 498/498 tests, ruff+mypy clean)
- [x] `app/jobs/orchestrator.py` — poll job status after each record commit; cancel_requested → cancelled; paused → graceful exit
- [x] `app/api/jobs.py` — `POST /api/jobs/{id}/cancel`, `/pause`, `/resume` with CSRF validation
- [x] `app/web/jobs.py` — `GET /jobs/{id}` detail page, `GET /jobs/{id}/events` HTMX partial
- [x] `app/templates/jobs/detail.html` — job detail page with status badge, metadata grid, control buttons
- [x] `app/templates/jobs/_events_poll.html` — live event log with HTMX outerHTML polling (stops when terminal)
- [x] `app/templates/jobs/list.html` — job IDs are now links to detail page
- [x] `tests/unit/test_job_orchestrator.py` — 2 new tests: cancel_requested → cancelled, paused → graceful stop
- [x] `tests/integration/test_job_controls.py` — 2 integration tests: cancel preserves records, pause preserves records
  - NOTE: HTMX polling uses outerHTML swap — response omits hx-trigger when job is terminal, stopping the poll
  - NOTE: Resume re-enqueues the job from scratch; existing records preserved; dedup catches any new duplicates
  - NOTE: Integration tests monkeypatch session.commit/refresh to simulate external status changes mid-job

### Sprint 6.1 — Job Queue Foundation — COMPLETE (verified green 2026-05-16, 496/496 tests, ruff+mypy clean)
- [x] `app/connectors/base.py` — add `extract_fields()` default method
- [x] `app/connectors/fixture.py` — implement `extract_fields()` (Google Places field names)
- [x] `app/jobs/__init__.py` — package init
- [x] `app/jobs/orchestrator.py` — `run_job()` async pipeline (connector → crawl → extract → score → dedup → store)
- [x] `app/jobs/tasks.py` — RQ entry point `run_crawl_job(job_id_str)`
- [x] `app/api/jobs.py` — `POST /api/jobs` (create + enqueue), `GET /api/jobs/{id}`
- [x] `app/web/jobs.py` — `GET /jobs` job list page
- [x] `app/templates/jobs/list.html` — status badges, created_at, connector/criteria names
- [x] `app/main.py` — register job routes + nav
- [x] `app/templates/base.html` — add Jobs nav link
- [x] `tests/unit/test_job_orchestrator.py` — 12 unit tests
- [x] `tests/integration/test_job_queue.py` — 2 integration tests (require running DB)
  - NOTE: Sprint 4.1 helpers (robots, limits, path filter) now wired into orchestrator crawl loop — closes that known issue
  - NOTE: `extract_fields()` added to `ConnectorBase` (default returns `{}`) + implemented in `FixtureConnector`
  - NOTE: Integration tests skipped in local runs (Docker Desktop not running); pass in CI against test DB

## Phase 7 — Records UI + REST API — COMPLETE (2026-05-16)
559/559 unit + API tests green | ruff clean | mypy strict clean | pip-audit clean
Deferred: Accessibility scan for Phase 7 UI (records pages) → pre-deploy hardening
Deferred: Integration tests (require Docker DB) → CI only

### Sprint 7.1 — Records Table & Detail — COMPLETE (verified green 2026-05-16, 539/539 tests, ruff+mypy clean)
- [x] `app/web/records.py` — `GET /records` list page (filter/sort/paginate), `GET /records/{id}` detail page, `GET /records/{id}/edit` HTMX partial
- [x] `app/api/records.py` — `POST /api/records` (manual add), `POST /api/records/{id}` (inline edit), `POST /api/records/{id}/delete` (soft delete with audit log)
- [x] `app/templates/records/list.html` — filterable/sortable table, status badges, pagination controls
- [x] `app/templates/records/detail.html` — field values, source attribution table, score breakdown
- [x] `app/templates/records/_edit_form.html` — inline HTMX edit partial (swapped into #record-fields)
- [x] `app/templates/records/_add_modal.html` — Alpine.js modal with HTMX form submit
- [x] `app/main.py` — register records web + API routers
- [x] `app/templates/base.html` — add Records nav link
- [x] `tests/api/test_records_api.py` — 16 tests: CRUD, filter, auth, CSRF, pagination
- [x] Audit log entries on create, edit, delete
  - NOTE: Edit uses POST /api/records/{id} (not PATCH) for simpler HTMX form handling
  - NOTE: Delete is POST /api/records/{id}/delete (soft delete — sets status="deleted")
  - NOTE: Cancel edit navigates back to /records/{id} as a plain link (full page reload)

### Sprint 7.2 — REST API — COMPLETE (verified green 2026-05-16, 559/559 tests, ruff+mypy clean)
- [x] `app/models/user.py` — add `api_key_hash` + `api_key_scopes` columns
- [x] `migrations/versions/a1b2c3d4e5f6_add_api_token_to_users.py` — Alembic migration
- [x] `app/auth/permissions.py` — add `require_api_token(scope)` factory (HMAC-keyed token hash)
- [x] `app/api/auth.py` — add `POST /api/auth/token` (generate) + `DELETE /api/auth/token` (revoke)
- [x] `app/api/records.py` — add `GET /api/records` + `GET /api/records/{id}` (token auth, JSON envelope)
- [x] `app/api/connectors.py` — `GET /api/connectors` (session auth)
- [x] `app/main.py` — global exception handlers (422/500); disable `/docs` when ENVIRONMENT=production
- [x] `tests/api/test_token_auth.py` — 20 tests: token CRUD, scope enforcement, GET records endpoints
  - NOTE: Token hash uses HMAC-SHA256 keyed with `api_token_secret` (not plain SHA-256 — server-secret keyed)
  - NOTE: One token per user; stored as `api_key_hash` + `api_key_scopes` (JSONB) on users table
  - NOTE: `_require_records_read` stored as module-level var so tests can use `dependency_overrides`
  - NOTE: HTMX POST endpoints unchanged — they use session auth; envelope only on new JSON GET endpoints

## Phase 8 — Exports + Audit Log UI + Dashboard — COMPLETE (2026-05-16)
601/601 unit + API tests green | ruff clean | mypy strict clean
Deferred: Accessibility scan for Phase 8 UI (exports, audit, dashboard, settings) → pre-deploy hardening
Deferred: app/templates/exports/ force-added due to broad `exports/` gitignore — narrow the pattern pre-deploy
Deferred: Token management UI (generate/revoke via browser) → deferred from Phase 7, still open


### Sprint 8.1 — Export + Raw HTML Upload — COMPLETE (verified green 2026-05-16, 594/594 tests, ruff+mypy clean)
- [x] `app/services/__init__.py` — package init
- [x] `app/services/storage.py` — S3/MinIO boto3 wrapper (upload_bytes, download_bytes, generate_export_key, generate_html_key)
- [x] `app/jobs/export_task.py` — RQ task: query → CSV/XLSX → upload → update Export status → audit log
- [x] `app/api/exports.py` — POST /api/exports (create), GET /api/exports/{id} (JSON status)
- [x] `app/web/exports.py` — GET /exports, GET /exports/{id}/status (HTMX partial), GET /exports/{id}/download (proxy stream)
- [x] `app/templates/exports/list.html` — export trigger form + history table with HTMX polling
- [x] `app/templates/exports/_status.html` — HTMX status badge fragment (pending→processing→ready+link)
- [x] `app/worker/persist.py` — wire raw HTML upload via storage service; graceful no-op if S3 not configured
- [x] `app/templates/records/list.html` — add Export button posting current filter params
- [x] `app/main.py` — register api_exports_router + web_exports_router
- [x] `app/templates/base.html` — add Exports nav link
- [x] `tests/unit/test_storage.py` — upload/download/key-gen with mocked boto3
- [x] `tests/unit/test_export_task.py` — CSV/XLSX generation, status transitions, audit log, error path
- [x] `tests/api/test_exports_api.py` — create, status, download proxy, auth enforcement

### Sprint 8.2 — Audit Log UI + Dashboard + Settings — COMPLETE (verified green 2026-05-16, 601/601 tests, ruff+mypy clean)
- [x] `app/web/audit.py` — GET /audit-log with action/resource_type/user_id/date_from/date_to filters, 50/page
- [x] `app/templates/audit/list.html` — filter bar + table + pagination
- [x] `app/web/settings_page.py` — GET /settings, _redact() config, YAML code block
- [x] `app/templates/settings.html` — read-only YAML display
- [x] `app/web/dashboard.py` — real data: record counts by status + recent 5 jobs
- [x] `app/templates/dashboard.html` — job cards, count badges, quick-link buttons
- [x] `app/main.py` — register web_audit_router + web_settings_router
- [x] `app/templates/base.html` — add Audit Log + Settings nav links
- [x] `tests/api/test_audit_page.py` — auth, filter by action, filter by date, pagination

## Phase 4 COMPLETE — 2026-05-15
- 298/298 tests green (291 unit + 7 Playwright integration)
- ruff clean, mypy strict clean
- Deferred: MinIO raw HTML upload (`raw_html_path`) → Phase 8
- Deferred: Sprint 4.1 helpers wired into orchestrator → Phase 6
