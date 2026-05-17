# Configuration Reference

The app uses two separate configuration systems:

- **Secrets and environment-specific values** → `.env` (never committed)
- **Non-secret runtime options** → `config/*.yml` (committed, mounted read-only)

---

## Environment Variables (`.env`)

Copy `.env.example` to `.env` and fill in each value before starting. None of these belong in YAML.

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | SQLAlchemy async URL. Format: `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `REDIS_URL` | No | Default: `redis://redis:6379/0` |
| `SECRET_KEY` | Yes | Long random string used to sign session cookies. Generate with `openssl rand -hex 32`. |
| `API_TOKEN_SECRET` | Yes | Separate secret used for API token HMAC signing. |
| `ENVIRONMENT` | No | `local` (default) \| `staging` \| `production`. Controls session cookie flags and log verbosity. |
| `SEED_OPERATOR_EMAIL` | No | Email for the first operator account created on first boot. Default: `admin@example.com` |
| `SEED_OPERATOR_PASSWORD` | No | Password for the seed operator. Leave empty in production and set via the UI after first boot. |
| `S3_ENDPOINT_URL` | No | MinIO/S3 endpoint. Leave empty to disable file storage (HTML uploads, exports). |
| `S3_ACCESS_KEY_ID` | No | MinIO/S3 access key. |
| `S3_SECRET_ACCESS_KEY` | No | MinIO/S3 secret key. |
| `S3_BUCKET_NAME` | No | Bucket name. Default: `web-scraper` |
| `GOOGLE_PLACES_API_KEY` | No | Required if `connectors.google_places.enabled: true` |
| `BRAVE_API_KEY` | No | Required if `connectors.brave_search.enabled: true` |
| `AI_API_KEY` | No | API key for the AI Assist feature. Works with any OpenAI-compatible provider (OpenRouter, Anthropic, LiteLLM, etc.) |
| `AUTHENTIK_CLIENT_ID` | No | OAuth2 client ID from Authentik. Required for SSO. |
| `AUTHENTIK_CLIENT_SECRET` | No | OAuth2 client secret from Authentik. Required for SSO. |
| `AUTHENTIK_BASE_URL` | No | Base URL of your Authentik instance, e.g. `https://auth.example.com` |
| `AUTHENTIK_APP_SLUG` | No | Authentik application slug. Default: `web-scraper`. Must match the slug on the Authentik Application object. |
| `CONFIG_DIR` | No | Override the config directory path. Default: `config`. Useful in tests. |

---

## YAML Config Files

All YAML files live in `config/` and are mounted read-only into containers. Copy each `.example` file and edit for your environment.

```
config/
├── app.yml             # Application settings and feature flags
├── connectors.yml      # Connector options (API limits, retries)
├── crawl.yml           # Global crawl safety defaults
├── retention.yml       # Data retention policy (days)
└── ai/
    └── ai_base.yaml    # AI Assist model and skill config
```

The app fails to start if any required YAML file is missing or invalid. The AI config (`ai/ai_base.yaml`) is optional — if absent, AI Assist is disabled.

---

### `config/app.yml`

Controls application-level behavior and feature flags.

```yaml
app_name: "Web Scraper"
base_url: "https://scrapy.staging.saltrun.net"   # used in OIDC redirect URIs

environment: staging        # local | staging | production

default_page_size: 25       # rows per page in tables
max_page_size: 100          # upper bound clients can request

roles:
  - operator                # active roles (MVP: operator only)

features:
  ai_assist: false          # reserved — AI Assist uses ai/ai_base.yaml presence instead
  brave_connector: false    # show Brave Search connector in the UI
  api_docs: true            # expose /docs (OpenAPI UI) — disable in production
  sso_enabled: false        # show "Sign in with Authentik" button on login page
```

**`features.sso_enabled`** must be `true` AND the four `AUTHENTIK_*` env vars must be set for SSO to work.

**AI Assist** is enabled by the presence of `config/ai/ai_base.yaml` AND a non-empty `AI_API_KEY` env var. The `features.ai_assist` flag is reserved for future use and has no current effect.

---

### `config/connectors.yml`

Defines which connectors are available and their rate limits. API keys belong in `.env`.

```yaml
connectors:
  google_places:
    enabled: true
    max_results: 60
    rate_limit:
      requests_per_minute: 30
    retry:
      max_attempts: 3
      backoff_factor: 2.0
      retry_on_status: [429, 500, 502, 503, 504]
    options:
      language: "en"
      region: "us"

  brave_search:
    enabled: false
    max_results: 20
    rate_limit:
      requests_per_minute: 10
    retry:
      max_attempts: 3
      backoff_factor: 2.0

  fixture:
    enabled: true
    fixture_dir: "tests/fixtures/connector_responses"
```

The `fixture` connector returns static test data from JSON files. Use it in criteria while developing templates so you don't consume API quota.

---

### `config/crawl.yml`

Global safety defaults that apply to all jobs. Individual criteria can override per-criteria limits but cannot exceed the global caps defined here.

```yaml
user_agent: "WebScraper/1.0 (internal; not-indexing)"

max_pages_per_job: 500
max_pages_per_domain: 50
max_depth: 3
timeout_seconds: 30
delay_between_requests_ms: 1000

blocked_path_patterns:       # never crawled regardless of criteria
  - "/login"
  - "/admin"
  - "/checkout"
  # ... see config/crawl.yml.example for full list

blocked_content_types:       # skip responses with these Content-Type prefixes
  - "application/pdf"
  - "image/"
  # ...
```

**`blocked_path_patterns`** and **`blocked_content_types`** are global safety guardrails — they override any `include_url_patterns` in a criteria file.

---

### `config/retention.yml`

How long data is kept before automated cleanup runs. Set a value to `0` to keep indefinitely.

```yaml
retention_days:
  job_events: 90        # job event log entries
  raw_responses: 30     # raw connector API responses
  raw_html: 7           # HTML stored in S3 during crawling
  screenshots: 7        # Playwright screenshots in S3
  artifacts: 30         # other crawl artifacts
  exports: 90           # CSV/XLSX files in S3
  audit_log: 365        # audit log entries (keep long for compliance)
```

---

### `config/ai/ai_base.yaml`

Controls which AI model is used for the AI Assist chat in the Criteria editor.

```yaml
provider: openrouter               # openrouter | anthropic | openai | litellm
base_url: "https://openrouter.ai/api/v1"
model: "anthropic/claude-3-5-sonnet"
max_tokens: 4096
temperature: 0.3

skills:
  criteria_creation: true          # generate a criteria YAML from plain language
  criteria_update: true            # modify existing YAML based on instructions
  criteria_validation: true        # explain validation errors
```

The API key goes in `.env` as `AI_API_KEY`. This file must exist for the chat widget to appear. Copy from `config/ai/ai_base.yaml.example`.

**LiteLLM proxy:** If you're routing through a local LiteLLM proxy, set `provider: litellm`, `base_url` to your proxy URL, and `model` to whatever your proxy exposes.

---

### `config/criteria/` — Not What You Think

This directory exists but criteria templates are **not stored as files**. The criteria editor in the web UI stores all criteria as database records (in `criteria_groups` and `criteria_versions` tables). The `config/criteria/` directory is a placeholder for future file-based bulk import.

To add criteria: use the web UI at `/criteria/new`.

---

## Secrets vs. YAML: Decision Rule

Use `.env` for anything that:
- Would be a secret if committed (API keys, passwords, signing keys)
- Changes between environments without a code deploy (URLs, credentials)

Use `config/*.yml` for anything that:
- Is safe to commit (no credentials)
- Is reviewed as part of a deploy (rate limits, feature flags, retention policy)

Never put secrets in YAML. Never put connection strings in YAML. Never use `config/*.yml` for values that differ between developer laptops.
