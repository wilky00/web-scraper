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

## DB poll per record for pause/cancel detection — 2026-05-16
**What:** The job orchestrator calls `session.refresh(job)` after each per-record commit to detect externally-set `paused` or `cancel_requested` status. With `expire_on_commit=False` on the session, in-memory job status does not refresh after commit — an explicit reload is required.
**Why:** Simplest coordination mechanism for a single-worker system. Avoids a Redis pub/sub dependency, keeps the orchestrator free of additional infrastructure, and is accurate enough for the expected throughput (seconds per record, not milliseconds). A DB round-trip per record is negligible at this volume.
**Alternatives considered:** Redis flag (faster, no DB hit, but adds Redis coupling to orchestrator) — rejected; overkill for MVP. In-memory asyncio.Event (can't cross process boundaries, no persistence) — rejected.

## Pause sets status directly; cancel uses cancel_requested intermediate — 2026-05-16
**What:** `POST /pause` sets `job.status = "paused"` immediately. The worker detects "paused" on the next `session.refresh()` and exits without changing it. `POST /cancel` sets `job.status = "cancel_requested"`. The worker detects this and transitions to `"cancelled"` itself.
**Why:** Pause is idempotent — if the worker has already finished by the time the API request arrives, the status is already terminal and the endpoint rejects the request with 409. No intermediate "pause_requested" state is needed. Cancel uses an intermediate state because the API cannot know when the worker will actually stop — "cancelled" as the final state should only be set by the worker that confirms the stop.
**Alternatives considered:** Single `paused` state for both API and worker — simpler, but doesn't distinguish "user requested pause" from "worker confirmed stop" for cancel.

## Resume re-queues from scratch (no checkpoint) — 2026-05-16
**What:** `POST /resume` sets status to `queued` and re-enqueues via RQ. The job re-runs the full connector from the beginning. Records stored before the pause are preserved in the DB. Dedup at the end of the resumed run handles overlap.
**Why:** `connector.discover()` is an async generator with no cursor or offset API. Mid-stream checkpointing would require either (a) a connector-specific persistence layer or (b) replaying all connector results and skipping already-processed ones. Both are out of scope for MVP.
**Alternatives considered:** Connector cursor stored in `CrawlJob.config_snapshot` — possible future improvement if high-latency connectors (e.g. Google Places with many pages) make full re-runs costly.

## HTMX outerHTML swap for polling stop — 2026-05-16
**What:** The events polling container uses `hx-swap="outerHTML"`. When the job is active, the server response includes `hx-trigger="every 2s"` on the container div. When the job is terminal, the server omits `hx-trigger`. Because outerHTML replaces the element itself, the new element has no polling attribute — HTMX stops automatically.
**Why:** No JavaScript, no custom events, no `HX-Stop-Polling` header hack. The pattern is idiomatic HTMX 2.x and self-documenting: the presence or absence of `hx-trigger` on the response element controls whether polling continues.
**Alternatives considered:** JS event listener + `HX-Trigger` response header — more complex, requires inline JS. Poll forever (always include `hx-trigger`) — simple but wastes requests after job completes.

## httpx AsyncClient instead of OpenAI SDK for AI calls — 2026-05-16
**What:** `app/ai/client.py` uses `httpx.AsyncClient` to POST directly to `/v1/chat/completions`. No `openai` package, no `anthropic` package.
**Why:** The project targets OpenRouter and LiteLLM, both of which expose an OpenAI-compatible REST API. `httpx` is already a project dependency; adding an SDK just for its HTTP transport would add a pinned dep for no functional benefit. The payload shape is simple: `{"model", "messages", "max_tokens", "temperature"}`. Nothing in the request or response requires SDK-specific features.
**Alternatives considered:** `openai` package — works with OpenRouter but adds a new dep and couples the codebase to OpenAI's release cycle. `anthropic` package — only works with Anthropic directly; requires provider-specific branching.

## Full response mode (not SSE streaming) for AI chat — 2026-05-16
**What:** `POST /api/ai/chat` waits for the full model response before returning JSON. The UI shows an animated "Thinking..." loading indicator while waiting.
**Why:** Streaming via SSE requires `flush_interval -1` in Caddy (not the default) and ~80 extra lines of JavaScript using `ReadableStream` + `TextDecoder` event parsing. The full response approach is a single `fetch()` call with standard JSON parsing — it's more durable through intermediate proxies and simpler to test. For a two-user MVP, the round-trip latency is acceptable.
**Alternatives considered:** SSE streaming — better UX for long responses but adds Caddy config dependency, JS complexity, and a more fragile proxy chain. Deferred; can be added by replacing the `fetch()` with `ReadableStream` processing without changing the backend response format.

## Client-side chat history (Alpine.js state, not Redis) — 2026-05-16
**What:** Conversation history is held entirely in Alpine.js `x-data` state. The server receives the last 10 turns as a JSON form field on each request. No server-side session storage.
**Why:** Two-user MVP. Persisting history to Redis adds a session schema, TTL management, and cross-request state that buys nothing for the MVP use case. History loss on page reload is disclosed to the user in the panel footer.
**Alternatives considered:** Redis session key `ai_chat:{user_id}:{group_id}` — durable across reloads, natural TTL via Redis expiry. Deferred; add if users find reload-loss frustrating in practice.

## HTMX inline edit via POST (not PATCH) for records — 2026-05-16
**What:** `POST /api/records/{id}` handles record updates (inline edit form submit). REST conventions would use PATCH or PUT, but HTMX forms only support GET and POST.
**Why:** HTMX 2.x does not support `hx-method="PATCH"` natively without a custom extension. Using POST keeps the HTMX template simple and consistent with the other HTMX form endpoints in the project. No external API clients were consuming this endpoint at the time it was designed.
**Alternatives considered:** HTMX `hx-patch` via the `htmx-method-override` extension — adds a dependency and a client-side JS include for marginal benefit at MVP scale.

## API token storage on users table (one token per user) — 2026-05-16
**What:** API tokens are stored as `api_key_hash` (HMAC-SHA256 of the plaintext token, keyed with `api_token_secret`) and `api_key_scopes` (JSONB array) directly on the `users` table. One token per user.
**Why:** MVP has two users. A separate `api_tokens` table adds a migration, a new model, and a join on every auth check without any practical benefit at this scale. The single-token-per-user limit is acceptable — regenerating the token (which overwrites `api_key_hash`) is the revocation + reissue path.
**Alternatives considered:** Separate `api_tokens` table — supports multiple named tokens with individual expiry and revocation. Deferred; add if a user actually needs concurrent integrations.

## S3/MinIO sync boto3 client wrapped with asyncio.to_thread() — 2026-05-16
**What:** `app/services/storage.py` exposes synchronous `upload_bytes()` and `download_bytes()` functions. Callers in async contexts (`app/api/exports.py`, `app/web/exports.py`) call these via `asyncio.to_thread()`.
**Why:** boto3 has no async API and ships no async client. The two options are `asyncio.to_thread()` (stdlib, no new deps, idiomatic for sync-in-async) or `aioboto3` (third-party wrapper, additional dep). `to_thread()` is sufficient for the expected upload/download volumes and keeps the storage module itself simple and testable with plain synchronous mocks.
**Alternatives considered:** `aioboto3` — adds a dependency with its own compatibility surface. `run_in_executor` with a ThreadPoolExecutor — functionally equivalent to `to_thread()` but more verbose.

## Export always async via RQ; no synchronous path — 2026-05-16
**What:** `POST /api/exports` always enqueues an RQ task. There is no synchronous "generate now and return bytes" path even for small record sets.
**Why:** Consistency. The API returns immediately with 201 + `HX-Redirect` to `/exports`. The client polls `GET /api/exports/{id}` via HTMX until ready. A synchronous path would require a different API shape and different UI handling, and would time out for large exports anyway.
**Alternatives considered:** Synchronous generation for small record sets (e.g., < 1000 rows) — adds branching logic, different response shapes, and unpredictable latency on the request thread.

## _redact() applies keyword match on dict keys, not a fixed allowlist — 2026-05-16
**What:** `app/web/settings_page.py::_redact()` hides any dict value whose key name (lowercased) contains one of: `key`, `secret`, `password`, `token`, `credential`. It recurses into nested dicts and lists.
**Why:** The config YAML structure is not known at compile time — it can contain arbitrary nesting from user-authored `config/*.yml` files. A fixed allowlist would need maintenance as config schemas evolve. A keyword-based approach catches secrets-by-convention without enumerating every possible field name.
**Alternatives considered:** Explicit blocklist of known secret field names — more precise but requires updates with every schema change. Run `Settings` model redaction directly — would require re-parsing env vars into a displayable form and risks leaking fields that are secret by name but not in the Settings model.

## Response envelope only on new JSON GET endpoints — 2026-05-16
**What:** The `{data, pagination, errors}` envelope is applied only to `GET /api/records` and `GET /api/records/{id}`. The existing HTMX POST endpoints (`/api/records`, `/api/records/{id}`, `/api/jobs`, etc.) return bare JSON or `HX-Redirect` headers — no envelope.
**Why:** The HTMX POST endpoints are consumed by the browser HTMX library, not by machine API clients. The browser reads `HX-Redirect` headers, not JSON bodies. Wrapping them in an envelope would be unused noise and would break HTMX's behavior. The envelope is meaningful only for endpoints designed for programmatic consumption.
**Alternatives considered:** Retrofit all `/api/` endpoints — breaks existing tests, wraps HTMX endpoints that don't benefit from it.

## HTMX for inline YAML validation — 2026-05-15
**What:** The criteria editor uses `hx-post="/api/criteria/validate"` with `hx-trigger="input delay:700ms"` to stream validation results into a `#validation-panel` div without a full page reload.
**Why:** HTMX replaces the need for custom JavaScript for this interaction. The server already has `validate_criteria_yaml()` — wrapping it in an HTMX endpoint is ~20 lines. The alternative (full form submit on every keystroke) would be disruptive to the editing experience.
**Alternatives considered:** Client-side YAML parsing in JavaScript — requires a JS YAML parser dependency and duplicates the Python validation logic.
