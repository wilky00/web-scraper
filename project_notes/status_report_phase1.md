# Phase 1 — Auth & Config Foundation — Status Report

## Sprint 1.1 — YAML Config Loading
**Completed:** 2026-05-15

### What was built
- `app/config/__init__.py` — package init
- `app/config/models.py` — Pydantic v2 models: AppConfig, FeaturesConfig, ConnectorsConfig, CrawlConfig, RetentionConfig, RetentionDays
- `app/config/criteria.py` — CriteriaConfig schema (all 8 sections), Operator StrEnum (12 operators), validate_criteria_yaml() returning structured errors
- `app/config/loader.py` — ConfigLoadError, per-file loaders, AppConfigs dataclass, load_all_configs()
- `app/settings.py` — added `config_dir: Path` field (default `Path("config")`, overridable via CONFIG_DIR env var)
- `app/main.py` — wired config loading into lifespan; SystemExit(1) on ConfigLoadError
- `tests/unit/test_config.py` — 33 tests covering all config models and loader error paths
- `tests/unit/test_criteria_schema.py` — 31 tests covering all 12 operators, all 5 namespaces, 10 error cases
- `tests/fixtures/criteria/valid_minimal.yml`, `valid_full.yml`

### Key decisions
- Criteria templates: DB-primary (CriteriaGroup + CriteriaVersion). config/criteria/*.yml are seed files only. UI supports YAML export/import for offline editing workflows.
- validate_criteria_yaml() returns (CriteriaConfig | None, list[str]) — soft errors, never raises; for AI assist to consume
- 12 operators implemented (plan doc said 11; §8 of requirements lists 12)
- `in_` used as Python identifier for `"in"` operator (keyword conflict)

### Test results
104/104 unit tests green | ruff clean | mypy strict clean

### Bugs found and fixed
- ruff E501 on ABOUTME comments (shortened)
- ruff UP042: `str, Enum` → `StrEnum`
- ruff I001: import ordering in criteria.py and test files
- ruff F401: unused imports removed from test files

---

## Sprint 1.2 — Local Auth
**Completed:** 2026-05-15

### What was built
- `app/auth/__init__.py`
- `app/auth/hashing.py` — bcrypt hash/verify (direct bcrypt, not passlib — see bug note)
- `app/auth/session.py` — Redis-backed sessions (itsdangerous signed cookie, 7-day TTL)
- `app/auth/csrf.py` — double-submit signed cookie pattern for pre-auth forms
- `app/auth/rate_limit.py` — Redis INCR/EXPIRE, 10 attempts / 60s per IP
- `app/auth/permissions.py` — `require_operator()` dependency, `NotAuthenticatedException`
- `app/auth/seed.py` — idempotent operator seeding on first boot
- `app/api/__init__.py`
- `app/api/auth.py` — POST /auth/login, POST /auth/logout
- `app/web/__init__.py`
- `app/web/auth.py` — GET /login
- `app/web/dashboard.py` — GET / (auth-protected stub)
- `app/templates/base.html` — Tailwind Play CDN + Alpine.js CDN, dark mode via store + localStorage
- `app/templates/login.html` — email/password form, CSRF hidden field, error banner, dark mode toggle
- `app/templates/dashboard.html` — stub with sign-out form (CSRF) and dark mode toggle
- `app/main.py` — added settings to app.state, registered routers, NotAuthenticatedException handler, seed call in lifespan
- `tests/conftest.py` — added test env vars (os.environ.setdefault), updated set_app_state to inject app.state.settings
- `tests/unit/test_auth.py` — 19 tests: hashing, session signing, CSRF, rate limiter
- `tests/api/test_auth_api.py` — 16 tests: login/logout flows, CSRF, rate limit, unauthenticated redirect

### Test results
135/135 unit+API tests green | ruff clean | mypy strict clean

### Bugs found and fixed
1. **passlib + bcrypt 4.x incompatible on Python 3.14** — passlib 1.7.4 fails to detect bcrypt 4.x version (removed `__about__` attribute) and breaks on all passwords. Switched `app/auth/hashing.py` to use `bcrypt` library directly.
2. **Starlette 1.0 changed TemplateResponse signature** — `request` is now the first positional argument; it is no longer included in the context dict. All three route files updated.
3. **ruff B008** — FastAPI `Depends()` in function default arguments is a known false positive. Added `"app/web/*.py"` and `"app/api/*.py"` per-file ignores to `pyproject.toml`.
4. **mypy arg-type on `verify_password`** — restructured credential checks to use separate early-return guards so mypy can narrow `user` from `User | None` to `User`.

### Open issues / follow-ups
- Tailwind is loaded via Play CDN (development only). Switch to compiled output when adding a static asset build step (likely Phase 8 or before staging deploy).
- `app/web/dashboard.py` has low coverage (62%) — intentional, it's a stub that will be fleshed out in Phase 7+.
- The `httpx` DeprecationWarning in API tests (per-request cookies being deprecated) — tracked; will update test helpers to set cookies on the client instance in a future sprint.
- `docker compose up` end-to-end smoke test still pending (requires Docker Desktop running locally).
