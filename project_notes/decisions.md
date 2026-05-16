# Decisions

## Criteria template storage: DB-primary with YAML export/import — 2026-05-15
**What:** Criteria templates live in the DB (`CriteriaGroup` + `CriteriaVersion`). `config/criteria/*.yml` files are a seed library imported on first boot. The UI supports export-to-YAML (download) and import-from-YAML (upload → validate → save as new group or new version). The Pydantic criteria schema is the shared validation layer for the inline editor, import, and AI assistant.
**Why:** File-based templates in a mounted volume can't support CRUD, save-as, or version history without filesystem writes from the app. DB-primary keeps all state in one place; YAML import/export covers the offline-edit workflow.
**Alternatives considered:** Files-only (no CRUD without git), DB-only (no offline edit workflow).

## bcrypt directly instead of passlib — 2026-05-15
**What:** `app/auth/hashing.py` uses `bcrypt.hashpw()` / `bcrypt.checkpw()` directly rather than via `passlib`.
**Why:** passlib 1.7.4 reads `bcrypt.__about__.__version__` which was removed in bcrypt 4.x, causing an `AttributeError` that silently breaks all password verification on Python 3.14. The `bcrypt` library itself is stable and has no such compatibility issue.
**Alternatives considered:** Pin passlib to a pre-4.x bcrypt — rejected; creates a permanent version conflict and blocks security updates.

## NotAuthenticatedException instead of HTTPException for auth redirects — 2026-05-15
**What:** `require_operator()` raises a custom `NotAuthenticatedException` (not `HTTPException(401)`). A FastAPI exception handler catches it and returns a 303 redirect to `/login`.
**Why:** FastAPI's built-in `HTTPException` handler returns JSON `{"detail": "..."}`. For a server-rendered app, unauthenticated requests should redirect, not return a JSON error. A custom exception keeps the redirect logic centralized in `app/main.py` and out of every individual route.
**Alternatives considered:** Return 401 with a `WWW-Authenticate` header — appropriate for pure APIs, wrong for a browser UI.

## Client-side Alpine.js sorting for criteria list — 2026-05-15
**What:** The criteria list page sorts the table client-side using Alpine.js `x-data` computed properties. No server round-trip on column header click.
**Why:** The criteria list is small (expected < 50 rows for this two-user MVP). Alpine sort is simpler to implement, avoids a server round-trip, and keeps the sort state in the browser without URL query params.
**Alternatives considered:** Server-side sort via query params — appropriate for large paginated lists; overkill for this use case.

## FastAPI dependency_overrides for test isolation — 2026-05-15
**What:** Criteria API tests override `require_operator` via `app.dependency_overrides[require_operator] = lambda: mock_user` rather than constructing a full session + Redis mock chain.
**Why:** `require_operator` is already tested in `test_auth_api.py`. Repeating the full auth mock stack in every criteria test couples criteria tests to auth implementation details. `dependency_overrides` is the FastAPI-idiomatic pattern for this.
**Alternatives considered:** Mock Redis + full session cookie in every test — correct but verbose and fragile to auth changes.

## RobotsCache fails open on errors — 2026-05-15
**What:** `RobotsCache.is_allowed()` returns `True` (allow) on any error: 404, non-200 status, network timeout, parse failure.
**Why:** Transient infrastructure issues (DNS blip, overloaded server) should not permanently block a crawl job. A legitimate site with a broken robots.txt should not be treated as fully disallowed. Fail-open is the industry standard for robots.txt handling.
**Alternatives considered:** Fail-closed (block on error) — too aggressive; would silently skip large portions of a crawl due to transient errors.

## PageFetcher.fetch() kept pure — Sprint 4.1 helpers deferred to Phase 6 — 2026-05-15
**What:** `PageFetcher.fetch()` handles only Playwright lifecycle, timeout, inter-request delay, and error capture. It does not call `RobotsCache`, `is_path_blocked`, `is_content_type_blocked`, or `PageLimitTracker`.
**Why:** Those helpers require per-job state (limits tracker) and async HTTP calls (robots fetch). Wiring them into the fetcher would make it stateful and harder to test. The Phase 6 job orchestrator is the correct place to compose all four modules into a coherent crawl loop.
**Alternatives considered:** Wire helpers into fetcher — tighter coupling, harder to unit-test fetcher in isolation.

## playwright added to dev extras (Python package only) — 2026-05-15
**What:** `playwright` appears in both `dev` and `worker` extras in `pyproject.toml`. The Python package and type stubs are installed in dev; browsers (`playwright install chromium`) are only installed in `Dockerfile.worker`.
**Why:** Unit tests need to `import playwright.async_api` to patch `async_playwright`. Without the package in dev extras, `import app.worker.fetcher` fails with `ModuleNotFoundError` in the unit test runner.
**Alternatives considered:** Keep playwright only in worker extras and use `importlib.import_module` with a lazy import guard — more complex, obscures the dependency graph.

## Dedup engine uses plain dataclasses, not ORM objects — 2026-05-15
**What:** `DeduplicationEngine` operates on `RecordData` / `SourceData` dataclasses (defined in `app/dedup/engine.py`), not on `BusinessRecord` / `RecordSource` ORM objects directly. The Phase 6 orchestrator is responsible for mapping ORM rows → dataclasses → running dedup → writing results back to the DB.
**Why:** Keeps the engine pure and testable without a database. Mirrors the same pattern as `ScoringEngine` (operates on a plain `dict[str, Any]` metrics dict, not ORM rows). Engine tests run without any DB fixtures.
**Alternatives considered:** ORM-aware engine that opens its own session — makes unit testing require a live DB and couples the engine to SQLAlchemy transaction boundaries.

## Union-find for transitive deduplication grouping — 2026-05-15
**What:** `DeduplicationEngine.find_duplicates()` uses a union-find data structure (with path compression) to group records transitively. If A matches B and B matches C, all three land in one group regardless of pass order.
**Why:** A naive "collect all pairs and then group" approach requires a second traversal to merge overlapping pairs. Union-find handles this naturally in O(n²·α(n)) — effectively O(n²) — which is fine for the expected record volumes (<10k per job).
**Alternatives considered:** Graph connected-components (DFS/BFS) — equivalent complexity, more code. Pair-only dedup (no transitivity) — misses legitimate multi-hop chains.

## Normalization-based name matching without fuzzy library — 2026-05-15
**What:** Pass 2 of deduplication compares company names after `normalize_name()` (lowercase + strip non-alphanumeric + collapse whitespace). Two names that normalize to the same string are considered duplicates. No edit-distance or Levenshtein library is used.
**Why:** No new dependency needed. Handles the most common real-world cases: punctuation differences ("Joe's Bakery" vs "Joes Bakery"), legal suffix noise ("LLC" vs "Inc"), casing ("GREEN VALLEY" vs "Green Valley"). Edit-distance fuzzy matching produces too many false positives on short names (e.g. "Ace" matches "Axe") without careful threshold tuning.
**Alternatives considered:** `rapidfuzz` / `thefuzz` — more powerful, but adds a dependency and requires a similarity threshold that would need empirical calibration. Deferred to a future improvement if MVP false-negative rate is unacceptable.

## HTMX for inline YAML validation — 2026-05-15
**What:** The criteria editor uses `hx-post="/api/criteria/validate"` with `hx-trigger="input delay:700ms"` to stream validation results into a `#validation-panel` div without a full page reload.
**Why:** HTMX replaces the need for custom JavaScript for this interaction. The server already has `validate_criteria_yaml()` — wrapping it in an HTMX endpoint is ~20 lines. The alternative (full form submit on every keystroke) would be disruptive to the editing experience.
**Alternatives considered:** Client-side YAML parsing in JavaScript — requires a JS YAML parser dependency and duplicates the Python validation logic.
