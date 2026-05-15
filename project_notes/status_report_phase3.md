# Phase 3 — Connectors — Status Report

## Sprint 3.1 — Connector Abstraction + Fixture
**Completed:** 2026-05-15

### What was built
- `app/connectors/__init__.py` — package init, exports all public classes
- `app/connectors/base.py` — `ConnectorBase` ABC + `ConnectorResult` Pydantic DTO
- `app/connectors/fixture.py` — `FixtureConnector` reads sorted `*.json` files from a directory
- `app/connectors/registry.py` — `ConnectorRegistry` maps config dict keys to connector instances; `UnknownConnectorError`
- `tests/fixtures/connector_responses/valid_results.json` — 3 Google Places-shaped results
- `tests/fixtures/connector_responses/empty_results.json` — empty array
- `tests/fixtures/connector_responses/partial_data.json` — 2 results with missing optional fields
- `tests/unit/test_connectors.py` — 26 unit tests

### Key decisions
- `ConnectorResult` is a Pydantic DTO (not the ORM `RawSearchResult`) — `job_id` is intentionally absent and is added by the job runner in Phase 6 when persisting to DB
- `FixtureConnector` reads files in sorted filename order for deterministic test output
- `ConnectorRegistry` accepts the raw `connectors.yml` dict; each connector validates its own config section in `__init__`

### Test results
149/149 unit tests green | ruff clean | mypy strict clean

---

## Sprint 3.2 — Google Places Connector
**Completed:** 2026-05-15

### What was built
- `app/connectors/google_places.py`:
  - `GooglePlacesConnectorConfig` — Pydantic v2 model with `extra="ignore"`, maps to `connectors.yml` google_places section
  - `GooglePlacesConnector(ConnectorBase)` — Places API v1 Text Search with pagination, rate limiting, and tenacity retry
- `app/connectors/registry.py` — updated `_build()` to register `google_places` connector type
- `tests/unit/test_google_places.py` — 23 tests

### Key decisions
- API key (`GOOGLE_PLACES_API_KEY`) read from environment at `discover()` time, not at `__init__` or registry build time — connector registers cleanly even if the key isn't set, which avoids boot failures in dev
- Inter-page rate limiting: `asyncio.sleep(60 / requests_per_minute)` between pages; no delay on the first page
- Retry via `tenacity.AsyncRetrying` context manager — `stop_after_attempt`, `wait_exponential`, `retry_if_exception` — retries only on status codes listed in `retry.retry_on_status` (default: 429, 500, 502, 503, 504)
- `http_client` constructor kwarg for test injection — connector creates and closes its own `httpx.AsyncClient` when `None` (production path)
- `X-Goog-FieldMask` requests only the fields needed for extraction: `id`, `displayName`, `formattedAddress`, `websiteUri`, `nationalPhoneNumber`, `types`, `rating`, `userRatingCount`, `businessStatus`, `nextPageToken`

### Test results
172/172 unit tests green | ruff clean | mypy strict clean

### Bugs found and fixed
- Sprint 3.1 `test_unknown_connector_type_not_registered` used `google_places` as the "unknown type" example — stale once 3.2 implemented it. Updated to use `brave_search` (genuinely unimplemented).

### Open issues / follow-ups
- Live smoke test against Google Places API not run (requires `GOOGLE_PLACES_API_KEY` — tracked in Manual Tasks)
- `brave_search` connector is explicitly deferred per requirements §3 ("only if Google Places is completed without schedule risk")
