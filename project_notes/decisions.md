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

## HTMX for inline YAML validation — 2026-05-15
**What:** The criteria editor uses `hx-post="/api/criteria/validate"` with `hx-trigger="input delay:700ms"` to stream validation results into a `#validation-panel` div without a full page reload.
**Why:** HTMX replaces the need for custom JavaScript for this interaction. The server already has `validate_criteria_yaml()` — wrapping it in an HTMX endpoint is ~20 lines. The alternative (full form submit on every keystroke) would be disruptive to the editing experience.
**Alternatives considered:** Client-side YAML parsing in JavaScript — requires a JS YAML parser dependency and duplicates the Python validation logic.
