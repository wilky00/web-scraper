# Phase 10 Status Report — SSO + Pre-deploy Hardening + Staging Deploy

## Sprint 10.1 — Authentik OIDC Integration — COMPLETE 2026-05-16

### What was built

**New files (2):**
- `app/auth/oidc.py` — Full OIDC module: `sso_enabled()` config gate, `load_oidc_discovery()` soft-fail fetcher, `create_oidc_state()` / `verify_oidc_state()` (Redis single-use 10-min TTL), `exchange_code_for_tokens()`, `fetch_userinfo()`, `find_or_provision_sso_user()` (3-case lookup: sso_sub → email → create), `generate_state()`
- `tests/unit/test_oidc.py` — 15 unit tests covering all above helpers
- `tests/api/test_sso_auth.py` — 10 API tests: login redirect shape, state Redis storage, callback success (session cookie), bad state, provider error, missing params, SSO disabled → 404, token exchange failure, login page SSO button on/off

**Modified files (7):**
- `app/settings.py` — added `authentik_app_slug: str = "web-scraper"`
- `app/config/models.py` — added `sso_enabled: bool = False` to `FeaturesConfig`
- `config/app.yml.example` — added `features.sso_enabled: false` with comment
- `.env.example` — added `AUTHENTIK_APP_SLUG` with explanatory comment block
- `app/web/auth.py` — added `_sso_active()` helper, updated `login_page()`, added `GET /auth/oidc/login` and `GET /auth/oidc/callback` routes
- `app/templates/login.html` — added conditional SSO button with horizontal rule divider
- `app/main.py` — OIDC discovery loaded at startup via `load_oidc_discovery()`, cached in `app.state.oidc_discovery`
- `app/api/auth.py` — updated `_render_login()` to compute and pass `sso_enabled` template context
- `tests/api/test_auth_api.py` — updated `_set_state()` / `_clear_state()` to include `config` and `oidc_discovery`

### Key decisions

- Used `httpx.AsyncClient` directly for token exchange and userinfo fetch (consistent with existing AI client pattern; authlib not needed)
- Discovery document loaded once at startup, cached in `app.state` — one HTTP fetch per boot, SSO button hidden if Authentik unreachable
- OIDC state is single-use via `redis.delete()` atomic consume — prevents replay attacks
- All callback failures redirect to `/login` rather than returning error status codes — browser-facing UX
- `sso_sub` column and initial migration already existed (Phase 0 scaffold) — no new migration needed
- Auto-provisioned SSO users get `operator` role with no password hash

### Test results

```
668 passed, 34 warnings in 6.02s
ruff: All checks passed
mypy: Success: no issues found in 83 source files
```

### Bugs found and fixed

1. `test_provision_creates_new_user` / `test_provision_raises_on_missing_email` — `StopIteration` crash from `_mock_db()` helper when both inputs were `None`; fixed by rewriting as variadic `_mock_db(*return_values)` that always creates a result mock per arg.
2. `test_oidc_callback_success_creates_session` — `AttributeError: 'State' has no attribute 'engine'`; fixed by adding `app.state.engine = MagicMock()` to `sso_client` fixture.
3. `test_oidc_callback_success_creates_session` — SQLAlchemy `AsyncSession` initialization with mock engine; fixed by adding `patch("app.web.auth.AsyncSession", ...)` as async context manager mock in test body.
4. 8 pre-existing auth API tests — `AttributeError: 'State' has no attribute 'config'`; fixed by adding `config` + `oidc_discovery` to `_set_state()` / `_clear_state()` in `test_auth_api.py`.
5. `app/main.py` — ruff I001 import sort violation; fixed by grouping `app.auth.oidc` imports with other auth imports.
6. `app/web/auth.py` — mypy `type-arg` on `dict` type annotation; fixed by using `dict[str, str]`.

### Open issues / follow-ups

None. Sprint 10.2 (Pre-deploy Hardening) is next.
