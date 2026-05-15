# MVP Requirements: Configurable Web Scraper

## 1. Purpose

Build a small, self-hosted application for two internal users that can discover public business records, crawl approved public websites, extract configurable fields, score records with deterministic rules, deduplicate results, and export or expose the records for downstream systems.

The MVP must stay simple enough to operate on a VPS, but flexible enough that new connectors, scoring rules, fields, exports, roles, and UI screens can be added later without rewriting the foundation.

## 2. Guiding Principles

- Configuration over code: scraping targets, extraction fields, scoring rules, retention, limits, and connector behavior live in YAML.
- Secrets stay out of config: credentials, API keys, database passwords, token secrets, and encryption keys live only in `.env` or host-provided environment variables.
- One role for MVP: all authenticated users have the `operator` role. The data model and authorization helper must support adding roles later.
- Deterministic MVP: no AI is required for crawl execution, extraction, scoring, filtering, or matching.
- Public data only: the crawler must not bypass authentication, CAPTCHA, paywalls, robots.txt restrictions, or technical access controls.
- Small frontend surface: use simple server-rendered UI with progressive enhancement instead of a complex SPA.
- Every sprint leaves the app testable end to end.
- Every feature must be reviewed for whether it creates technical debt for later phases.

## 3. MVP Scope

### Included

- Login for trusted internal users.
- One active user role: `operator`.
- SSO or Local auth - SSO uses Authentik (use local Authentik instance on nexus for staging environment with MFA and passwordless flow.)
- Caddy for reverse proxy, for staging use caddy-local on nexus, for production, will setup production Caddy instance on VPS with ufw-docker, Crowdsec, and fail2ban. Let's Ecrypt certs and Cloudflare for public DNS, 
- YAML-based application config, connector config, crawl profiles, criteria definitions, scoring rules, output fields, and retention settings.
- `.env`-based secrets.
- Criteria management with immutable versions.
- One connector abstraction, with Google Places as the first production connector and a fixture/mock connector for tests and demos.
- Optional Brave Search connector only if Google Places is completed without adding schedule risk.
- Website crawling after connector discovery.
- Deterministic extraction for company name, website URL, email, phone, address/location where available, source URLs, and configurable metadata.
- Deterministic scoring with explainable must-have, should-have, and exclude rules.
- Deduplication by normalized domain, then company/location, then phone/email.
- Job queue with one active crawl job by default.
- Job lifecycle: queued, running, paused, cancel requested, cancelled, completed, completed with errors, failed.
- Job event log visible in the UI.
- Records table with pagination, sorting, filtering, detail view, edit, delete, manual add, and source attribution.
- CSV export for selected or filtered records.
- Authenticated REST API for records, criteria, jobs, connectors, and exports.
- Ability to export crawl results to XLSX or CSV
- Audit log for user actions that create, update, delete, export, start, pause, resume, or cancel.
- Docker Compose for local, staging, and production.
- Deployment documentation for `ssh saltrun-staging` and `ssh saltrun-production`.
- Unit, integration, API, and E2E tests.
- Dependency vulnerability checks in CI and before deployment.
- MinIO for S3 compatible object storage on staging (already installed on saltrun-staging) Production may use commerically available S3 storage, as needed.
- User optionally can levergae AI for critera authoring and updates using LiteLLM/OpenRouter endpoint via a chat interface on the configuration page.
- UI/UX should be thoughtful and clean, usability is paramount, only use UI/UX components that meet this goal, avoiding  client-side routing, global state stores, and a large frontend test surface for a two-user internal MVP.
- Build  Light/Dark mode from the start,
### Explicitly Deferred

- Public SaaS signup, tenant isolation, billing, Stripe, SendGrid, and customer onboarding.
- Multi-role UI behavior beyond the future-ready role field and authorization helper.
- Spreadsheet import.
- Duplicate merge UI beyond automatic deduplication and source preservation.
- Scheduled recurring crawls.
- Advanced analytics dashboards.
- GCP/Cloud Run scaffolding.
- Full connector marketplace.

## 4. Recommended MVP Architecture

### Backend

- Python 3.12.
- FastAPI for REST APIs and server-rendered pages.
- SQLAlchemy 2.0 and Alembic.
- PostgreSQL 16.
- Redis plus RQ for background jobs.
- Playwright only in the worker container for website crawling.
- Pydantic for settings and YAML schema validation.

### Frontend

- FastAPI/Jinja2 templates for pages.
- Django where it makes sense based on full project review
- HTMX for table refreshes, forms, job event updates, and small interactions.
- Alpine.js only where local UI state is genuinely needed.
- Tailwind CSS with a adequate project-owned component set.


### Storage

- PostgreSQL stores application data and validated criteria JSON snapshots.
- YAML files store human-authored configuration.
- Configurable local mounted volume or S3 endpoint to store  generated exports and optional artifacts (ie.Website screenshots from Playwright), staging will use  MinIO for S3 stoarge on saltrun-staging

## 5. Configuration and Secrets

### YAML Configuration

All non-secret runtime configuration must live in YAML files mounted into the containers:

- `config/app.yml`: app name, base URL, environment, pagination defaults, active role list, feature flags.
- `config/connectors.yml`: enabled connectors, connector defaults, rate limits, retry policy, non-secret API options.
- `config/crawl.yml`: global crawl safety defaults, user agent, max pages, max depth, timeout, delay, blocked path patterns.
- `config/retention.yml`: retention days for logs, raw responses, raw HTML, screenshots, artifacts, and exports.
- `config/criteria/*.yml`: reusable scrape/extraction/scoring criteria templates.
- `conifg/ai/ai_base.yaml`: AI endpoint, Anthropic, or OpenAI compatible for OpenAI or LiteLLM
- `config/ai/skills/*.md` : directory of skills used by AI-Assist for critera creatia creation and validation and scoring. (Future skills may be enabled)

### Secrets

All secrets must live in `.env` locally and host-provided env files on staging/production:

- Database URL/password.
- Redis URL/password if used.
- Cookie/session signing secret.
- API token signing secret or encryption key.
- Google Places API key.
- Brave API key if enabled.
- S3 credentials.
- AI endpoint credentials

Secrets must never be logged, returned from API responses, committed to Git, rendered into templates, or stored in YAML.

## 6. Authentication and Authorization

- MVP requires local login and SSO integration with Authentik (staging will integrate with local Authentik instance)
- User table includes `role`, but MVP seeds and supports only `operator`.
- Authorization must go through a small central permission helper, not scattered inline checks.
- Future roles can be added by extending config and tests, not by rewriting every route.
- Passwords must be hashed with a modern password hashing library.
- Session cookies must be HTTP-only, secure in production, same-site, and rotated on login.
- API tokens are allowed for downstream systems, stored hashed, scoped initially as `records:read` or `records:write`.

## 7. Core Data Model

Minimum tables:

- `users`
- `criteria_groups`
- `criteria_versions`
- `connectors`
- `crawl_jobs`
- `crawl_job_events`
- `raw_search_results`
- `crawl_pages`
- `business_records`
- `record_sources`
- `record_audit_log`
- `exports`

Criteria versions and crawl jobs must store a complete validated config snapshot so historic jobs remain reproducible even after YAML templates change.

## 8. Criteria YAML Requirements

Each criteria file must support:

- Metadata: name, display name, description, tags.
- Source: connector, max source results, connector query fields.
- Crawl: enabled, max depth, max pages per domain, timeout, delay, include/exclude URL patterns.
- Extraction: fields, source priority, basic filters.
- Rules: must-have, should-have, exclude.
- Scoring: enabled, minimum score, weighted rules.
- Deduplication: primary and secondary keys.
- Output: fields displayed, stored, and exported.

Supported MVP operators:

- `exists`
- `not_exists`
- `equals`
- `not_equals`
- `contains`
- `contains_any`
- `greater_than_or_equal`
- `less_than_or_equal`
- `in`
- `not_in`
- `domain_matches`
- `matches_regex`

Supported metric namespaces:

- `source.*`
- `crawl.*`
- `html.*`
- `links.*`
- `extraction.*`

Additional namespaces can be added later through schema versioning.

## 9. Crawl and Extraction Requirements

- Crawl only URLs discovered through configured connectors or explicitly approved seed URLs.
- Respect `robots.txt` where applicable.
- Use a configurable user agent.
- Apply default blocked paths: login, account, admin, checkout, cart, payment, privacy, terms, logout.
- Skip binary files unless explicitly allowed.
- Canonicalize URLs and avoid duplicate visits.
- Enforce per-job and per-domain limits.
- Store crawl errors as events without deleting successful records.
- Extract fields through deterministic parsers that can be unit tested with static HTML.
- Store source attribution for every extracted field where possible.
- Sanitize extracted content before rendering it in the browser.

## 10. Scoring and Deduplication

- Scoring must be deterministic and explainable.
- Must-have rules determine inclusion.
- Exclude rules remove records.
- Should-have and scoring rules contribute to `match_score`.
- Every record detail view must show matched rules, failed rules, excluded rules, and evidence/source URLs.
- Deduplication automatically merges by normalized domain first, then company/location, then phone/email.
- Source history must be preserved when duplicates merge.

## 11. UI Requirements

MVP screens:

- Login.
- Dashboard with latest jobs and record counts.
- Criteria list.
- Criteria editor using YAML text with validation results. AI Chat interface for critera generation and update  assistance using natual language.
- Start crawl form.
- Job list.
- Job detail with event log and pause/resume/cancel controls.
- Records table with server-side filtering, sorting, and pagination.
- Record detail/edit with source attribution.
- Export form for selected or filtered CSV.
- Audit log.
- Settings readout showing active YAML config without secrets.

The UI should be clean, visually appealing, and fully  operational. It should prioritize fast review and correction over decorative dashboards.

## 12. API Requirements

Required REST endpoint groups:

- `/api/auth`
- `/api/criteria`
- `/api/connectors`
- `/api/jobs`
- `/api/records`
- `/api/exports`
- `/api/audit-log`
- `/health`

The API must provide consistent validation errors, pagination metadata, filtering, sorting, OpenAPI docs, and no stack traces or secrets in responses.

## 13. Deployment Requirements

### Local

- `docker compose up` starts the full application.
- `.env.example` documents required secrets.
- `config/*.example.yml` documents required YAML.

### Staging

- Target host: `ssh saltrun-staging`.
- Deployment uses Docker Compose.
- Staging has its own `.env` and mounted YAML config.
- Every merge to `main` may deploy to staging after CI passes.
- Use caddy-local on nexus (ssh nexus) for local secure routing. 
### Production

- Target host: `ssh saltrun-production`.
- Deployment uses Docker Compose.
- Production deploy requires a manual command or manually approved workflow.
- HTTPS is required through Caddy.
- Database backups and restore instructions are required before production use.

## 14. Security Requirements

- Pin direct dependencies.
- Run `pip-audit` for Python dependencies.
- Run `npm audit` only if a Node-based asset pipeline is used.
- Run container image vulnerability scanning before deployment.
- Any known vulnerability that cannot be removed must be documented in `docs/security-exceptions.md` with package, version, CVE, severity, reason, mitigation, and owner.
- Validate all user input server-side.
- Use parameterized database access through SQLAlchemy.
- Escape template output by default.
- Sanitize extracted HTML and never render raw crawled HTML directly.
- Apply CSRF protection to cookie-authenticated form submissions.
- Rate-limit login and crawl-start endpoints.
- Do not log secrets, cookies, tokens, or raw credentials.
- Keep production debug mode off.

## 15. Testing Requirements

Every sprint must end with:

- Unit tests for new pure logic.
- Integration tests for database and worker behavior touched by the sprint.
- API tests for changed endpoints.
- UI tests or E2E tests for changed user flows.
- Security checks for dependencies and input validation.
- A written debt check: whether the sprint creates friction for the next phase.

Every feature commit must leave one testable vertical behavior, even if the UI is basic.

Required fixtures:

- Mock connector responses.
- Valid and invalid criteria YAML.
- Static HTML pages for extraction.
- Robots.txt samples.
- Duplicate record samples.
- API failure, timeout, empty result, malformed HTML, and rate-limit cases.

## 16. Acceptance Criteria for MVP

- A user can log in as `operator`.
- A user can validate and save a criteria YAML file as an immutable version.
- A user can start a crawl from a criteria version and configured connector.
- A job can complete using mocked connector data and static or local HTML fixtures.
- A production connector can discover public candidate records.
- The crawler visits allowed pages, extracts fields, scores records, deduplicates records, stores attribution, and logs job events.
- A user can pause, resume, and cancel a job without corrupting stored results.
- A user can view, filter, sort, edit, delete, and manually add records.
- A user can export filtered or selected records as CSV and XLSX
  A user can use AI Assistance for creating and managing configuration templates in natural human language. ( Please create a new template to search for bakery shops within 30 miles of Nashville that have URLs that resolve only to a social media site like Facebook or Instagram) 
- Audit history is created for record edits/deletes, criteria changes, job actions, and exports.
- Local, staging, and production deployment instructions exist and are tested at least once.
- CI passes linting, unit tests, integration tests, E2E smoke tests, and dependency vulnerability checks.
