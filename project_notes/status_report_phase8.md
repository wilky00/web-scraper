# Phase 8 Status Report

## Sprint 8.1 — Export + Raw HTML Upload — COMPLETE 2026-05-16

### What was built

**New files:**
- `app/services/__init__.py` — package init
- `app/services/storage.py` — sync S3/MinIO boto3 wrapper; `upload_bytes()`, `download_bytes()`, `generate_export_key()`, `generate_html_key()`; raises `StorageError` / `StorageNotFoundError`; credentials read from Settings only, never logged
- `app/jobs/export_task.py` — RQ task `run_export(export_id_str)` → async pipeline: set processing → query records with filter params → build CSV (stdlib) or XLSX (openpyxl) → upload via `asyncio.to_thread()` → set ready + row_count + audit log; error path sets status=failed
- `app/api/exports.py` — `POST /api/exports` (CSRF-checked, format validated, RQ-enqueued, returns 201 + HX-Redirect); `GET /api/exports/{id}` (JSON status polling)
- `app/web/exports.py` — `GET /exports` list (last 50); `GET /exports/{id}/status` HTMX fragment; `GET /exports/{id}/download` proxy (operator auth required; 404 if not ready)
- `app/templates/exports/list.html` — export form + history table
- `app/templates/exports/_status.html` — HTMX outerHTML polling fragment; omits `hx-trigger` on terminal states to auto-stop polling
- `tests/unit/test_storage.py` — 10 tests
- `tests/unit/test_export_task.py` — 26 tests
- `tests/api/test_exports_api.py` — 9 tests (create, invalid format, CSRF, unauthenticated, status JSON, not found, invalid id, download, not-ready)

**Modified files:**
- `app/worker/persist.py` — raw HTML upload: calls `storage.upload_bytes()` when `settings.s3_endpoint_url` is set and `result.html` is populated; graceful warning log on `StorageError`; closes the Phase 4 deferral
- `app/jobs/orchestrator.py` + `app/jobs/tasks.py` — pass `Settings` through to `persist_crawl_page()`
- `app/templates/records/list.html` — Export form with hidden filter inputs posts to `/api/exports`
- `app/templates/base.html` — Exports nav link
- `app/main.py` — registers `api_exports_router` + `web_exports_router`

### Key decisions
- Export always async via RQ — same pattern as `run_crawl_job`
- S3 credentials sourced from `Settings` only; never logged or included in error messages
- `gitignore` has `exports/` pattern which also matches `app/templates/exports/` — force-added with `-f`; consider narrowing the gitignore rule in a follow-up
- `_make_client()` return type annotated as `Any` (boto3 has no stubs) instead of the previous `# type: ignore[return]` that mypy rejected

### Test results
594 passed, 0 failed, 24 warnings — 5.77s

---

## Sprint 8.2 — Audit Log UI + Dashboard + Settings — COMPLETE 2026-05-16

### What was built

**New files:**
- `app/web/audit.py` — `GET /audit-log`; 5 filter params (action, resource_type, user_id, date_from, date_to); 50/page; resolves user emails in one batched query; invalid filter values silently ignored
- `app/templates/audit/list.html` — filter bar with Clear link, color-coded action badges, resource ID truncation, pagination controls with preserved filter query string
- `app/web/settings_page.py` — `GET /settings`; `_redact()` recursively masks dict values whose key name contains `key`, `secret`, `password`, `token`, or `credential`; renders each config section as YAML
- `app/templates/settings.html` — dark-theme code block per config section
- `tests/api/test_audit_page.py` — 7 tests: 200 auth, 303 unauthenticated, filter by action, filter by date_from, invalid date ignored, pagination page 2, entry count display

**Modified files:**
- `app/web/dashboard.py` — replaced stub with real queries: `GROUP BY status` record counts + recent 5 jobs with joined connector and criteria names
- `app/templates/dashboard.html` — status count badges, job table with status badges, quick-link buttons (New Job, Browse Records, Manage Criteria), empty states
- `app/main.py` — registered `web_audit_router` + `web_settings_router`
- `app/templates/base.html` — Audit Log + Settings nav links

### Key decisions
- `_redact()` is a recursive pure function — never reads from `Settings`, only scans the config YAML structure; no risk of accidentally exposing env secrets
- Dashboard `GROUP BY status` query returns only statuses that exist — template uses `record_counts.items()` loop + a "Total" card computed in Python to avoid N+1 queries
- Audit log count uses a lightweight `select(RecordAuditLog.id)` subquery rather than `COUNT(*)` to keep it compatible with the existing filter-building pattern

### Test results
601 passed, 0 failed, 24 warnings — 5.97s

### Open issues / follow-ups
- `app/templates/exports/` is force-added due to broad `exports/` gitignore pattern — flag for Sprint 8.2 or pre-deploy cleanup
- Accessibility scan for Phase 8 UI deferred to pre-deploy hardening (no axe-core tooling yet)
