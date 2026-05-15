# Phase 2 — Criteria Management — Status Report

## Sprint 2.1 — Criteria YAML Schema
**Completed:** 2026-05-15 (done early, in Sprint 1.1)

### What was built
Sprint 2.1's scope (Criteria YAML Schema) was fully completed during Sprint 1.1 as part of YAML Config Loading. No new work required.

Already delivered in Sprint 1.1:
- `app/config/criteria.py` — CriteriaConfig with all §8 fields, all 12 operators (StrEnum), 5 namespaces validated
- `validate_criteria_yaml()` — returns (CriteriaConfig | None, list[str]), never raises
- 31 unit tests in `tests/unit/test_criteria_schema.py`
- Fixture YAMLs: `tests/fixtures/criteria/valid_minimal.yml`, `valid_full.yml`

### Key decisions
- Plan said 11 operators; §8 of requirements lists 12 — all 12 implemented
- Sprint 2.1 formally closed without new work; Sprint 2.2 was the first criteria-phase work

---

## Sprint 2.2 — Criteria UI + Versioning
**Completed:** 2026-05-15

### What was built
- `app/api/criteria.py` — POST /api/criteria/validate (HTMX partial), POST /api/criteria (create), POST /api/criteria/{group_id}/versions (immutable save), GET /api/criteria/{group_id}/versions (history partial)
- `app/web/criteria.py` — GET /criteria (list), GET /criteria/new (blank editor), GET /criteria/{group_id} (editor with loaded YAML)
- `app/templates/criteria/list.html` — sortable table with status badges; Alpine.js client-side sort; empty state
- `app/templates/criteria/editor.html` — YAML textarea + HTMX live validation panel + version history sidebar + operators/namespace quick reference
- `app/templates/criteria/version_history.html` — HTMX-swappable version list partial
- `app/templates/base.html` — added HTMX CDN, sticky nav bar (Dashboard + Criteria links, dark mode toggle, sign-out)
- `app/templates/dashboard.html` — simplified to use shared nav (removed duplicate header elements)
- `app/main.py` — registered `web_criteria_router` and `api_criteria_router`
- `tests/api/test_criteria_api.py` — 13 tests

### Key decisions
- `app.dependency_overrides[require_operator]` used in tests for clean DI override (FastAPI idiomatic pattern)
- HTMX validate endpoint is auth-gated (POST with payload) but no CSRF needed — read-only operation
- Mutating endpoints (create, save-version) validate CSRF against session token
- `yaml.dump()` used to reconstruct YAML from stored JSON snapshot (lossy roundtrip is acceptable for MVP; comments and formatting are not preserved)
- Nav sign-out uses `csrf_token` template variable; login page has no nav (CSRF not defined → nav suppressed via Jinja2 `{% if csrf_token is defined and csrf_token %}`)
- `sort_keys=False` in `yaml.dump()` to preserve Pydantic model field order

### Test results
148/148 unit+API tests green | ruff clean | mypy strict clean

### Bugs found and fixed
- `(session_data or {}).get("csrf_token", "")` pattern fails mypy strict — empty dict `{}` inferred as `dict[Never, Never]`. Fixed to explicit `if session_data is None: return ""` guards everywhere.
- `yaml` imported but unused in `app/api/criteria.py` (removed)

### Open issues / follow-ups
- `docker compose up` end-to-end smoke test still pending (requires Docker Desktop running)
- httpx DeprecationWarning in API tests (per-request cookies) — tracked, non-blocking
- Tailwind Play CDN still in use — switch to compiled output before staging deploy
- `GET /api/criteria/{group_id}/versions` HTMX partial endpoint is wired but not yet called from the editor template (version list is loaded server-side on page load for now)
