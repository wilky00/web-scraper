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

## Phase 2 — Criteria Management

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
