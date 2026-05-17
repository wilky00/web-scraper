# Lead Generator — Configurable Web Scraper

A self-hosted tool for discovering and qualifying business leads from publicly available web data. Define exactly what you're looking for in YAML — business type, location, website characteristics, missing contact info, technology signals — run a job, and export scored, deduplicated records ready for outreach.

Built for small teams. Runs on a single VPS with Docker Compose.

---

## What It Does

You write a **criteria** template describing your target business profile. The app queries a connector (Google Places, Brave Search, or static fixtures), crawls the discovered websites, extracts contact information and page signals, scores each record against your rules, deduplicates results, and lets you export a clean lead list.

**Example use cases:**

- Find businesses in your city whose website URL redirects to Facebook or Instagram — they need a real website
- Identify hair salons still running HTML 4.0 pages — prime candidates for a web modernization pitch
- Surface restaurants that have no phone or email anywhere on their site — unreachable customers waiting to be found
- Locate retail shops whose Google Places URL uses plain HTTP — an easy SEO/SSL upgrade sell
- Flag gyms with no evidence of Mindbody, ClassPass, or Calendly — opening for scheduling platform outreach

Every rule, weight, and output field is configurable without touching code.

---

## Documentation

| Document | Description |
|---|---|
| [docs/criteria.md](docs/criteria.md) | Full YAML reference — all 8 sections, every field, all operators, scoring and dedup explained |
| [docs/config.md](docs/config.md) | Environment variables, YAML config files, secrets vs. config decision guide |
| [docs/deployment.md](docs/deployment.md) | Staging and production deployment, Caddy setup, Authentik SSO, rollback procedure |
| [docs/security-exceptions.md](docs/security-exceptions.md) | Known dependency exceptions with CVE, severity, and mitigation notes |
| [mvp-requirements.md](mvp-requirements.md) | Original product requirements and acceptance criteria |

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- A Google Places API key (or use the `fixture` connector to start without one)
- Optionally: an OpenRouter/LiteLLM API key for AI-assisted criteria authoring

### 1. Clone and configure

```bash
git clone <repo-url> && cd web-scraper
cp .env.example .env
```

Edit `.env` and fill in the required values:

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/web_scraper
SECRET_KEY=<output of: openssl rand -hex 32>
API_TOKEN_SECRET=<output of: openssl rand -hex 32>
SEED_OPERATOR_EMAIL=admin@example.com
SEED_OPERATOR_PASSWORD=changeme
```

### 2. Copy config files

```bash
cp config/app.yml.example       config/app.yml
cp config/connectors.yml.example config/connectors.yml
cp config/crawl.yml.example      config/crawl.yml
cp config/retention.yml.example  config/retention.yml
```

To enable Google Places:

```bash
# In .env:
GOOGLE_PLACES_API_KEY=your_key_here

# In config/connectors.yml:
connectors:
  google_places:
    enabled: true
```

### 3. Start

```bash
docker compose up
```

App → http://localhost:8000
MinIO console → http://localhost:9001

### 4. Run migrations

```bash
docker compose run --rm app alembic upgrade head
```

Log in with the credentials from `SEED_OPERATOR_EMAIL` / `SEED_OPERATOR_PASSWORD`. Five example criteria templates are seeded automatically on first boot.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser                                                        │
│  Jinja2 + HTMX + Alpine.js + Tailwind                          │
└────────────────────────┬────────────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────────────┐
│  FastAPI app container  (Python 3.12)                           │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  │
│  │  Web routes      │  │  REST API        │  │  Auth        │  │
│  │  /criteria       │  │  /api/criteria   │  │  Session     │  │
│  │  /jobs           │  │  /api/jobs       │  │  OIDC/SSO    │  │
│  │  /records        │  │  /api/records    │  │  CSRF        │  │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  │
└────────┬───────────────────────────────────────────────────────-┘
         │                                │
┌────────▼────────┐              ┌────────▼────────┐
│  PostgreSQL 16  │              │  Redis 7         │
│  Business data  │              │  Sessions        │
│  Criteria       │              │  Job queue (RQ)  │
│  Audit log      │              └────────┬─────────┘
└─────────────────┘                       │
                                 ┌────────▼─────────┐
                                 │  Worker container │
                                 │  Playwright       │
                                 │  Connector fetch  │
                                 │  Crawl + extract  │
                                 │  Score + dedup    │
                                 └──────────────────┘
```

**Services** (`docker compose ps`):

| Service | Role |
|---|---|
| `app` | FastAPI web + API server |
| `worker` | Background job runner (RQ + Playwright) |
| `db` | PostgreSQL 16 |
| `redis` | Session store and job queue |
| `minio` | S3-compatible storage for exports and crawl artifacts |

---

## How to Build a Lead Search

### 1. Create a criteria

Navigate to **Criteria → New Criteria**. Either:

- Load a built-in template from the **Templates** panel in the right sidebar and modify it, or
- Write YAML from scratch using the [criteria reference](docs/criteria.md), or
- Use the **AI Assist** chat panel (if configured) and describe what you want in plain English

The editor validates YAML in real time. Click **Save criteria** when ready.

### 2. Start a job

Go to **Jobs → Start Job**, select your criteria, and click **Start**. The job page shows a live event log as the worker runs.

### 3. Review records

Once the job completes, open **Records**. Filter, sort, and inspect individual records. Each record shows matched rules, score breakdown, and source attribution.

### 4. Export

Use **Exports** to download CSV or XLSX. Choose all records, filtered records, or a manual selection.

---

## Criteria YAML — 60-Second Overview

```yaml
metadata:
  name: nashville-shops-no-https      # unique slug
  display_name: Nashville Shops Without HTTPS
  description: >
    Retail shops still on plain HTTP — easy SSL upgrade pitch.
  tags: [retail, security, nashville]

source:
  connector: google_places             # or: brave_search, fixture
  max_results: 60
  query_fields:
    - field: type
      value: store
    - field: location
      value: "Nashville, TN"
    - field: radius
      value: "30000"

crawl:
  enabled: true
  max_depth: 1
  max_pages_per_domain: 2
  timeout_seconds: 20
  delay_ms: 1000

extraction:
  fields:
    - name: email
      source_priority: [structured, text, mailto_links]
    - name: phone
      source_priority: [structured, text, tel_links]

rules:
  must_have:
    - metric: source.name
      operator: exists
      label: Has a business name
  exclude:
    - metric: source.website
      operator: matches_regex
      value: "^https://"
      label: Already uses HTTPS (skip these)
  should_have:
    - metric: source.website
      operator: matches_regex
      value: "^http://"
      label: Website uses plain HTTP
      weight: 100.0

scoring:
  enabled: true
  minimum_score: 50.0
  weighted_rules: []

dedup:
  primary_key: domain
  secondary_keys: [name, phone]

output:
  display_fields: [name, source.website, phone, email, location_city, match_score]
  store_fields: [name, source.website, phone, email, location_city, location_state, match_score]
  export_fields: [name, source.website, phone, email, location_city, location_state]
```

Full field reference: [docs/criteria.md](docs/criteria.md)

---

## AI Assist

The criteria editor includes an AI chat panel that can generate and modify YAML from plain English.

**To enable it:**

1. Copy `config/ai/ai_base.yaml.example` → `config/ai/ai_base.yaml`
2. Set `AI_API_KEY` in `.env` to your OpenRouter, LiteLLM proxy, or Anthropic key
3. Restart the app

**Usage examples:**

> "Create a template for coffee shops within 20 miles of zip code 37214 that have a website but no phone number listed"

> "Add a rule that excludes any business rated below 3 stars"

> "Change the connector to brave_search and update the query fields"

The AI suggests YAML — you review and apply it. Nothing saves until you click **Save criteria**.

The model picker in the chat panel lets you choose any model available through your configured provider. Models update dynamically without restarting.

---

## Development

### Package management

```bash
uv sync --extra dev      # install dev dependencies
uv sync --extra worker   # install worker dependencies (Playwright)
```

### Tests

```bash
make test-unit           # unit tests — no DB/Redis required
make test-api            # API/web tests — mocked, no DB/Redis required
make test                # full suite — requires docker compose up
make test-integration    # integration tests only
```

### Lint and format

```bash
make lint                # ruff check
make format              # ruff format
make check               # lint + format check together (CI)
```

### Database migrations

```bash
# Apply pending migrations
docker compose run --rm app alembic upgrade head

# Create a new migration after changing a model
docker compose run --rm app alembic revision --autogenerate -m "describe the change"

# Check current revision
docker compose exec app alembic current
```

See [docs/deployment.md](docs/deployment.md) for rollback procedures.

---

## Configuration Reference

| File | What it controls |
|---|---|
| `.env` | Secrets: DB URL, API keys, signing secrets, S3 credentials |
| `config/app.yml` | Feature flags, roles, pagination, base URL |
| `config/connectors.yml` | Enabled connectors, rate limits, retry policy |
| `config/crawl.yml` | Global crawl safety: max pages, blocked paths, user agent |
| `config/retention.yml` | How long to keep jobs, HTML, exports, audit logs |
| `config/ai/ai_base.yaml` | AI provider, model, and enabled skills |

Full reference: [docs/config.md](docs/config.md)

---

## API

The REST API mirrors all web UI functionality. OpenAPI docs are available at `/docs` (disabled in production).

Base path: `/api/`

| Route group | Purpose |
|---|---|
| `/api/auth` | Login, logout, session |
| `/api/criteria` | CRUD for criteria groups and versions |
| `/api/jobs` | Start, pause, resume, cancel jobs |
| `/api/records` | List, filter, edit, delete records |
| `/api/exports` | Create and download CSV/XLSX exports |
| `/api/connectors` | List available connectors |
| `/api/ai/chat` | AI criteria authoring endpoint |
| `/api/ai/models` | List available AI models from the configured provider |
| `/health` | Liveness check — returns DB and Redis status |

---

## Deployment

Quick reference:

```bash
# Staging
ssh saltrun-staging "cd /opt/web-scraper && git pull && \
  docker compose -f docker-compose.yml -f docker-compose.staging.yml up -d"
ssh saltrun-staging "cd /opt/web-scraper && docker compose exec app alembic upgrade head"

# Production
ssh saltrun-production "cd /opt/web-scraper && git pull && \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
ssh saltrun-production "cd /opt/web-scraper && docker compose exec app alembic upgrade head"
```

Full instructions including Caddy configuration, Authentik SSO setup, and rollback: [docs/deployment.md](docs/deployment.md)

---

## Security

- All secrets in `.env` only — never in YAML or committed files
- CSRF protection on all cookie-authenticated form submissions
- Rate limiting on login and job-start endpoints
- Passwords hashed with Argon2; sessions HTTP-only and rotated on login
- Extracted HTML is sanitized before rendering
- Parameterized DB queries via SQLAlchemy (no raw SQL interpolation)
- Dependency vulnerability scanning: `pip-audit` before deploy
- Known exceptions documented with CVE and mitigation: [docs/security-exceptions.md](docs/security-exceptions.md)
