# Phase 6 — Job Queue & Lifecycle — Status Report

## Sprint 6.1 — Job Queue Foundation
**Completed:** 2026-05-16

### What was built
- `app/connectors/base.py` — added optional `extract_fields(raw_data) -> dict[str, str | None]` method (default returns `{}`)
- `app/connectors/fixture.py` — implemented `extract_fields()` to parse Google Places / fixture-format raw_data into standard field names
- `app/jobs/__init__.py` — package init
- `app/jobs/orchestrator.py` — `run_job()` async pipeline: connector → crawl → extract → score → dedup → store; `_try_crawl()` helper wires all Phase 4 crawl modules; `_build_record()`, `_build_metrics()`, `_add_sources()`, `_run_dedup()`, `_orm_to_record_data()` private helpers
- `app/jobs/tasks.py` — RQ entry point `run_crawl_job(job_id_str)`; builds its own engine + session + PageFetcher; loads connector from registry, criteria from DB
- `app/api/jobs.py` — `POST /api/jobs` (create + enqueue via RQ), `GET /api/jobs/{id}`
- `app/web/jobs.py` — `GET /jobs` job list page with connector/criteria names, record counts, status badges
- `app/templates/jobs/list.html` — Tailwind + Jinja2 status-badged table, empty state, dark mode support
- `app/main.py` — registered `web_jobs_router` and `api_jobs_router`
- `app/templates/base.html` — added Jobs nav link with active-state highlighting
- `tests/unit/test_job_orchestrator.py` — 12 unit tests for pipeline helpers and `run_job()`
- `tests/integration/test_job_queue.py` — 2 integration tests (require running PostgreSQL)

### Key decisions
- **`extract_fields()` on `ConnectorBase`**: added as non-abstract method (default `return {}`) so connectors can optionally map their `raw_data` format to standard field names. The orchestrator calls this to get `name`, `website`, `phone`, etc. without knowing each connector's schema.
- **`run_job()` takes `connector` and `criteria` as parameters**: rather than re-loading from DB inside the orchestrator, the caller (RQ task or test) provides them directly. Makes the orchestrator pure and testable without a DB.
- **Crawl step is optional**: `fetcher=None` skips crawling entirely. Integration tests use this to verify the connector → score → dedup pipeline without requiring browsers.
- **Sprint 4.1 helpers wired here**: `RobotsCache`, `PageLimitTracker`, `is_path_blocked`, `is_content_type_blocked` are now composed in `_try_crawl()` — closes the deferred Phase 4 known issue.
- **RecordSource rows**: both connector-provided and extraction-provided sources are stored side-by-side for full attribution. Connector sources use `source_type="connector"`.
- **Dedup write-back**: after `DeduplicationEngine.merge_duplicates()`, losers' `BusinessRecord.status` and `canonical_record_id` are updated in ORM; `RecordSource` rows are transferred via SQLAlchemy core `UPDATE`.

### Test results
12 new unit tests | 496/496 full suite green | ruff clean | mypy strict clean

### Bugs found and fixed
- Criteria YAML test fixture was missing required `source:` section — fixed inline.

### Open issues / follow-ups
- Integration tests require running PostgreSQL — will run in CI but skip locally without Docker Desktop
- `POST /api/jobs` enqueues via sync `redis-py` + `asyncio.to_thread()`; enqueue errors return 201 with a `warning` field rather than failing the request — job is created but may not be in the RQ queue

---

## Sprint 6.2 — Job Controls
**Completed:** 2026-05-16

### What was built
- `app/jobs/orchestrator.py` — added `session.refresh(job)` check after each record commit; `cancel_requested` → transitions to `cancelled`; `paused` → logs event and returns gracefully
- `app/api/jobs.py` — `POST /api/jobs/{id}/cancel`, `/pause`, `/resume`; CSRF validated via session token; returns `HX-Redirect` for HTMX clients; logs event before status change
- `app/web/jobs.py` — `GET /jobs/{id}` detail page; `GET /jobs/{id}/events` HTMX polling partial; `_load_job_detail()` helper loads job + connector/criteria names + record count + events
- `app/templates/jobs/detail.html` — header with status badge, metadata grid (connector, criteria, records, created), contextual control buttons (Pause/Cancel for running; Resume/Cancel for paused; Cancel for queued), event log section
- `app/templates/jobs/_events_poll.html` — event log container; includes `hx-get`/`hx-trigger="every 2s"`/`hx-swap="outerHTML"` when job is active; omits polling attrs when terminal (HTMX outerHTML swap stops polling automatically)
- `app/templates/jobs/list.html` — job IDs now link to `/jobs/{id}` detail page
- `tests/unit/test_job_orchestrator.py` — 2 new tests: `cancel_requested` transitions to `cancelled`; `paused` exits gracefully with records intact
- `tests/integration/test_job_controls.py` — 2 integration tests with real DB: cancel preserves stored records + logs event; pause preserves stored records + logs event

### Key decisions
- **DB poll between records**: after each record commit, `session.refresh(job)` reloads status from DB. With `expire_on_commit=False`, in-memory status is stale — explicit refresh is required. A single DB round-trip per record is acceptable for this throughput.
- **Pause sets status directly**: `POST /pause` sets `job.status = "paused"` immediately. The worker detects this on the next refresh and exits. No intermediate `pause_requested` state — simpler and sufficient.
- **Resume re-queues from scratch**: no mid-stream checkpoint. Resume sets status to `queued` and re-enqueues via RQ. Dedup at end of the new run handles overlap with records from before the pause.
- **HTMX polling stop via outerHTML**: the partial omits `hx-trigger` when job is terminal. Since `hx-swap="outerHTML"` replaces the entire element, the new element has no polling trigger — HTMX stops automatically. No JS required.
- **Integration test patching**: monkeypatches `db_session.commit` and `db_session.refresh` to simulate external status change after N commits. Originals captured before patching and restored after `run_job()` returns.

### Test results
2 new unit tests (14 total in orchestrator file) | 498/498 full suite green | ruff clean | mypy strict clean

### Bugs found and fixed
- `_make_cancel_after_n_commits` initially tried to restore methods via `__class__.__get__` — fragile. Fixed to capture and restore originals directly.

### Open issues / follow-ups
- Integration tests require running PostgreSQL — will run in CI but skip locally
- Status badge on detail page does not auto-update when polling stops (only event log updates); full page reload shows final status — acceptable for MVP
- Resume creates duplicate DB records if job had partial results; dedup covers this but raw_search_results table grows unboundedly — acceptable for MVP
