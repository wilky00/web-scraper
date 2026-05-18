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

---

## Criteria Overhaul — Sprint 2.1 — `is_template` column + seeder update
**Completed:** 2026-05-17

### What was built
- `app/models/criteria.py` — added `is_template: Mapped[bool]` column (nullable=False, default=False) to CriteriaGroup
- `migrations/versions/b1c2d3e4f5a6_add_is_template_to_criteria_groups.py` — Alembic migration; `server_default="false"` ensures zero-downtime apply on existing rows; down_revision=a9c69ca6be9b
- `app/criteria/seed.py` — seeded CriteriaGroup constructor now passes `is_template=True`; all 5 example templates will be flagged on next startup
- `tests/unit/test_criteria_seed.py` — refactored to capture full CriteriaGroup objects (not just names); asserts `is_template=True` on all seeded groups
- `pyproject.toml` — added per-file E501 ignore for seed.py (YAML string literals in _TEMPLATES legitimately exceed 100 chars)

### Key decisions
- `server_default="false"` used in migration instead of a post-migrate UPDATE — safer for zero-downtime deploys; staging backfill SQL provided separately
- Delete endpoint (Sprint 2.2) will return 422 if `is_template=True` — prevents accidental loss of seeded templates
- `pyproject.toml` per-file-ignore is the right fix for E501 inside Python string literals where `# noqa` is impossible without corrupting the string content

### Test results
572/572 unit tests green | ruff clean

### Staging backfill required
After applying migration `b1c2d3e4f5a6` on staging, run:
```sql
UPDATE criteria_groups SET is_template = true
WHERE name IN (
  'social-only-businesses-nashville',
  'nashville-barbershops-legacy-html',
  'restaurants-missing-contact-info',
  'local-shops-http-only',
  'nashville-gyms-without-online-booking'
);
```
(The seeder will set this on new installs, but existing staging rows got `server_default=false`.)

### Open issues / follow-ups
- None; clean sprint

---

## Criteria Overhaul — Sprint 2.3 — Editor: Save As + Version restore
**Completed:** 2026-05-17

### What was built
- `app/api/criteria.py` — `GET /api/criteria/{group_id}/versions/{version_id}/yaml`: loads a specific CriteriaVersion by both `id` and `group_id` (cross-group access prevented), returns `JSONResponse({"yaml": ...})`
- `app/api/criteria.py` — `POST /api/criteria/{group_id}/save-as`: form params `yaml_text` + `new_display_name`; slugifies name via `re.sub(r'[^a-z0-9]+', '-', ...)`; validates YAML (422 on error); overrides `metadata.name`/`display_name` in snapshot; creates CriteriaGroup (`is_template=False`) + CriteriaVersion v1 with pre-generated UUID; audit log `action="criteria_save_as"`; IntegrityError → 409 editor render; success → 303 redirect
- `app/templates/criteria/editor.html` — added `loadVersion(groupId, versionId)` JS function (alongside `loadCriteriaTemplate`); added `x-data="{ showSaveAs: false, newName: '' }"` to editor column div; added Load button per version in inline server-side version list; added "Save As" button in button row (only when `group` is not None); added Save As modal (fixed overlay, Alpine.js, `@submit` handler populates hidden `yaml_text` from textarea before POST)
- `app/templates/criteria/version_history.html` — added Load button per version entry (calls `loadVersion(group_id, v.id)`)
- `tests/api/test_criteria_api.py` — 4 new tests: `test_get_version_yaml_returns_yaml`, `test_get_version_yaml_wrong_group_returns_404`, `test_save_as_creates_new_group`, `test_save_as_invalid_yaml_returns_error`

### Key decisions
- `GET /versions/{version_id}/yaml` queries on both `id == version_id AND group_id == group_id` — prevents fetching a version from a different group via a valid version UUID
- `save-as` validates YAML before any DB interaction, so invalid-YAML 422 errors need no DB mock in tests
- Save As modal uses `@submit="$el.querySelector('[name=yaml_text]').value = document.getElementById('yaml_text').value"` — populates hidden field synchronously before form submit, avoiding Alpine reactive binding complexity
- `style="display: none;"` on modal div prevents flash before Alpine.js initializes
- Load buttons added to BOTH the inline server-side version list in `editor.html` AND the `version_history.html` HTMX partial (since the HTMX partial is wired but not yet invoked from the template; the inline list is what users see today)

### Test results
572/572 unit tests green | 24/24 API tests green | ruff clean | mypy strict clean

### Bugs found and fixed
- None; clean sprint

### Open issues / follow-ups
- None; clean sprint

## Criteria Overhaul — Sprint 2.2 — List page redesign + delete/clone API
**Completed:** 2026-05-17

### What was built
- `app/web/criteria.py` — added `"is_template": g.is_template` to `groups_data` dict
- `app/api/criteria.py` — `POST /api/criteria/{group_id}/delete`: soft-deletes (`is_active=False`), 422 if `is_template=True`, audit log `action="criteria_delete"`, returns JSON `{"ok": true}`
- `app/api/criteria.py` — `POST /api/criteria/{group_id}/clone`: deep-copies latest CriteriaVersion snapshot, creates new CriteriaGroup (`is_template=False`) with `{name}-copy` suffix, retries up to 5 times on IntegrityError, audit log `action="criteria_clone"`, returns `HX-Redirect` header
- `app/templates/criteria/list.html` — full Alpine.js redesign: tag filter pills (`allTags` getter + `toggleTag()`), search input (`filtered` getter replaces `sorted`), Template badge (purple) on seeded rows, Clone icon button (all rows), Delete icon button (hidden for templates), two creation buttons (Advanced live + Guided disabled with tooltip)
- `tests/api/test_criteria_api.py` — 4 new tests: soft delete, template delete blocked (422), clone creates copy (HX-Redirect), name collision retries to success

### Key decisions
- Clone pre-generates the new group UUID (`id=candidate_id`) before the session, so the id is available without relying on SQLAlchemy flush to apply the `default=uuid.uuid4` column default — that default only runs during real DB INSERT
- Delete returns `{"ok": true}` (200 JSON) and the Alpine handler splices the row from `items` client-side (no full page reload); Clone returns `HX-Redirect` header and Alpine redirects to the new editor
- Delete button is hidden for templates in the template (`x-if="!group.is_template"`); the API still guards with a 422 as a defense-in-depth measure

### Test results
572/572 unit tests green | ruff clean | mypy strict clean

### Bugs found and fixed
- `commit_side_effect: list[object]` type annotation caused mypy `[misc]` error on `raise effects[i]` — fixed to `list[Exception | None]` so mypy recognizes the raise is valid

### Open issues / follow-ups
- None; clean sprint
