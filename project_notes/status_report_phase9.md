# Phase 9 Status Report

## Sprint 9.1 — AI Backend (Config + Client + API) — COMPLETE 2026-05-16

### What was built

**New files:**
- `app/ai/__init__.py` — package init
- `app/ai/config.py` — `AIConfig` Pydantic model + `load_ai_config()` soft-fail loader; returns `None` if `config/ai/ai_base.yaml` is missing or invalid — app starts normally either way
- `app/ai/client.py` — async `httpx` client for OpenAI-compatible `/v1/chat/completions`; raises `AIClientError` on HTTP errors; never logs the API key
- `app/ai/skills.py` — loads enabled skill files from `config/ai/skills/` into concatenated string; missing files skipped with a warning log
- `app/ai/chat.py` — pure `build_messages()` (system prompt + history + user turn) and `extract_yaml_block()` (regex parse of ` ```yaml ``` ` block) — no I/O, fully unit-testable
- `app/api/ai.py` — `POST /api/ai/chat`: operator auth + CSRF + per-user Redis rate limit (20 req / 5 min); returns `{"reply": str, "suggested_yaml": str | null}`; 503 if AI not configured, 429 on rate limit, 502 on AI service error
- `config/ai/skills/criteria_creation.md` — full criteria YAML schema reference (all sections, all 12 operators, all 5 namespaces) with a complete working example
- `tests/unit/test_ai_config.py` — 15 tests: AIConfig validation, field bounds, soft-fail on missing/invalid/non-mapping YAML
- `tests/unit/test_ai_chat.py` — 18 tests: build_messages history trimming, null bytes, YAML context, extract_yaml_block edge cases
- `tests/api/test_ai_api.py` — 10 tests: 200 reply, YAML extraction, 503 unconfigured, 403 CSRF, 422 empty message, 429 rate limit, 502 client error, 303 unauthenticated, history passthrough, current_yaml passthrough

**Modified files:**
- `app/config/loader.py` — added `load_ai_config()` call; `AppConfigs` dataclass gains `ai: AIConfig | None = None`
- `app/main.py` — registered `api_ai_router`

### Key decisions
- Soft-fail: missing `config/ai/ai_base.yaml` logs at INFO and sets `config.ai = None`; app boots normally
- `httpx.AsyncClient` used directly (no OpenAI SDK) — OpenRouter/LiteLLM are OpenAI-compat; no new dep needed
- Rate limit is per-user (not per-IP) — `ai_rate:{user_id}` Redis key, 20/5min; less punishing than login (no account lockout semantics)
- History capped at 10 turns server-side to prevent prompt injection via accumulation
- `AI_API_KEY` sourced from `Settings` only; never appears in logs, error responses, or templates

### Test results
642 passed, 0 failed, 33 warnings — 5.91s (601 pre-existing + 41 new)

### Bugs found and fixed
- `extract_yaml_block()` returned `""` for an empty ` ```yaml\n``` ` block instead of `None` — fixed by checking `content if content else None` after `.strip()`

---

## Sprint 9.2 — Chat UI — COMPLETE 2026-05-16

### What was built

**New files:**
- `app/templates/criteria/_ai_chat.html` — Alpine.js chat panel: indigo-themed, full-width, collapsible, positioned below the criteria editor grid; animated bounce loading indicator ("Thinking..."); "Apply to editor" button dispatches `input` event on the textarea (triggering HTMX auto-validation); Enter to send, Shift+Enter for newline; graceful error display for network failure, 429, 502; disclaimer that chat history is not persisted between page loads

**Modified files:**
- `app/web/criteria.py` — added `_ai_enabled()` helper (checks `config.ai is not None and ai_api_key is set`); passed `ai_enabled: bool` to template context in both `criteria_new()` and `criteria_editor()` routes
- `app/templates/criteria/editor.html` — added `{% if ai_enabled %}{% include "criteria/_ai_chat.html" %}{% endif %}` after the closing tag of the main grid; no change to the YAML textarea or sidebar

### Key decisions
- Chat panel uses `fetch()` + Alpine.js state (not HTMX) — accumulating message history requires client-side state that HTMX's form-based model cannot easily manage
- CSRF token embedded via `data-csrf="{{ csrf_token }}"` HTML attribute (Jinja2 auto-escapes) and read in `x-init` — avoids embedding in a JS string context
- "Apply to editor" targets textarea by `document.getElementById('yaml_text')` — simpler than Alpine `x-ref` cross-component and works regardless of Alpine.js scope boundaries
- Panel is zero-impact when unconfigured: the `{% if ai_enabled %}` guard means no HTML, no JS, no Alpine.js overhead

### Test results
642 passed, 0 failed, 33 warnings — 5.91s (no new tests — UI-only sprint; AI API tests from Sprint 9.1 cover the endpoint)

### Open issues / follow-ups
- Accessibility scan on the chat panel not performed (no axe-core tooling yet) — add to pre-deploy hardening list
- Chat history is lost on page reload — acceptable for MVP; future improvement could persist to Redis session
- Streaming responses deferred — full response + loading indicator is sufficient for two-user MVP; streaming can be added by replacing the fetch call with `ReadableStream` processing
