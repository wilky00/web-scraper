# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack
- Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2
- PostgreSQL 16, Redis 7, RQ (job queue)
- Jinja2 + HTMX + Alpine.js (minimal) + Tailwind CSS
- Docker Compose for all environments
- Playwright in worker container ONLY

## Package Management
- Use `uv` for all dependency management — never pip directly
- Run `uv lock` after any `pyproject.toml` changes and commit `uv.lock`
- Install with extras: `uv sync --extra dev` for dev, `uv sync --extra worker` for worker

## Running Locally
```bash
cp .env.example .env   # edit and fill in secrets
docker compose up
```

App runs at http://localhost:8000. MinIO console at http://localhost:9001.

## Common Commands

```bash
# Lint and format
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy app/

# Full test suite (requires running DB + Redis):
docker compose run --rm app pytest tests/ -v

# Unit tests only (no external services needed):
uv run pytest tests/unit/ -v

# Single test file:
uv run pytest tests/unit/test_scoring_engine.py -v

# Single test by name:
uv run pytest tests/unit/test_scoring_engine.py::test_score_above_threshold -v
```

## Config
- Non-secret config: `config/*.yml` (mounted read-only into containers)
- Secrets: `.env` only — never in YAML, never in code
- Key config files: `app.yml` (features/roles), `connectors.yml` (per-connector config), `crawl.yml` (page limits/depth/user agent), `retention.yml` (data lifecycle in days)
- App fails fast at startup if any config file fails Pydantic validation

## Database Migrations
```bash
# Apply migrations:
docker compose run --rm app alembic upgrade head

# Generate a new migration (after editing models/):
docker compose run --rm app alembic revision --autogenerate -m "describe_the_change"
```

All schema changes go through Alembic — never modify the DB directly.

## Deployment
- Staging: `ssh saltrun-staging`, `/opt/web-scraper/`
  - `docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d`
  - Routes via Caddy to `scrapy.staging.saltrun.net`
- Production: `ssh saltrun-production`, `/opt/web-scraper/`
  - `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

Staging and prod use external S3 (not MinIO). MinIO is local-only.

## Code Standards
- All new Python files: 2-line `# ABOUTME:` comment block at top
- Type hints on all function signatures — `from __future__ import annotations` in every file
- `structlog` for logging — never `print()` or `logging.getLogger()`
- `ruff` for lint + format (`uv run ruff check . && uv run ruff format .`)
- Playwright imports ONLY in `app/worker/` — never in `app/` elsewhere
- Never log: secrets, passwords, session cookies, API keys

## Architecture

### Dual Interface Pattern
The app exposes two parallel route trees:
- `app/api/` — JSON REST endpoints, authenticated via Bearer token (`require_api_token(scope)`)
- `app/web/` — HTML form endpoints returning Jinja2 templates, authenticated via session cookie (`require_operator()`)

Both auth dependencies live in `app/auth/permissions.py` — always go through these, never inline auth logic.

### Crawl Job Pipeline (`app/jobs/orchestrator.py`)
Each job runs as an RQ background task through a fixed pipeline:
1. **Connector** — `connector.discover()` yields raw results, stored as `RawSearchResult`
2. **Extraction** — `connector.extract_fields()` pulls structured fields (name, phone, email, address, URL)
3. **Crawl** (optional) — if a website URL exists: robots.txt check → page limit check → content-type filter → `PageFetcher` fetches HTML → stored as `CrawlPage` + S3 artifact
4. **Extraction** — `run_extraction()` normalizes fields from fetched HTML (bleach sanitization, phone formatting, address normalization)
5. **Scoring** — `ScoringEngine.score()` evaluates record against `CriteriaVersion` YAML rules
6. **Deduplication** — `DeduplicationEngine.find_match()` fuzzy-matches normalized fields against existing `BusinessRecord` rows
7. **Persistence** — upserts `BusinessRecord` + creates `RecordSource` link + appends `CrawlJobEvent`

Per-record errors are caught and the job transitions to `completed_with_errors`; fatal errors → `failed`.

### Connectors (`app/connectors/`)
Implement `ConnectorBase` ABC (discover, extract_fields). Register in `ConnectorRegistry`. The fixture connector is always available for tests. New connectors add a class + entry in `connectors.yml`.

### Event Sourcing for Jobs
`CrawlJobEvent` rows are append-only (no `updated_at`). Job lifecycle is reconstructed from events, not from a mutable status field on `CrawlJob`. The job record has a `status` denormalization for fast queries, but event rows are the source of truth.

### Config vs Settings
- `app/settings.py` — Pydantic `Settings`, loads from env vars only (secrets, URLs, feature flags that must stay out of YAML)
- `app/config/` — YAML-backed config, loaded at startup, injected via FastAPI `Depends()`; covers operational knobs (crawl limits, connector options, retention windows)

### Worker Isolation
The RQ worker (`Dockerfile.worker`) is a separate container image with Playwright + Chromium. The `app` image has no browser. `app/worker/fetcher.py` and `app/worker/persist.py` are the only files that may import from `playwright`. The RQ job entry point (`app/jobs/tasks.py`) creates its own DB session — it does not share the FastAPI connection pool.

### AI Assist (`app/ai/`)
Optional feature, enabled by `config/ai/ai.yml`. Uses the Anthropic SDK with tool use to suggest criteria YAML and extraction rules. Rate-limited and CSRF-protected. Chat history is stored in Redis, not the DB.
