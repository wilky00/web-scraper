# Web Scraper — Project Instructions

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

## Config
- Non-secret config: `config/*.yml` (mounted read-only into containers)
- Secrets: `.env` only — never in YAML, never in code

## Database migrations
```bash
docker compose run --rm app alembic upgrade head
```

## Tests
```bash
# Full suite (requires running DB + Redis):
docker compose run --rm app pytest tests/ -v

# Unit tests only (no external services needed):
uv run pytest tests/unit/ -v
```

## Deployment
- Staging: `ssh saltrun-staging`, `/opt/web-scraper/`
  - `docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d`
  - Routes via Caddy to `web-scraper.staging.saltrun.net`
- Production: `ssh saltrun-production`, `/opt/web-scraper/`
  - `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d`

## Code Standards
- All new Python files: 2-line `# ABOUTME:` comment block at top
- Type hints on all function signatures — `from __future__ import annotations` in every file
- `structlog` for logging — never `print()` or `logging.getLogger()`
- `ruff` for lint + format (`uv run ruff check . && uv run ruff format .`)
- Playwright imports ONLY in `app/worker/` or `worker/` — never in `app/`
- Never log: secrets, passwords, session cookies, API keys

## Architecture Notes
- `app/auth/permissions.py` — central auth dependency, always go through this
- `app/config/` — YAML loaders; app fails fast on invalid config at startup
- `app/models/` — all SQLAlchemy models; Alembic manages all schema changes
- `app/jobs/` — RQ task entry points; workers pick these up
- `config/criteria/*.yml` — human-authored scoring/extraction templates
