# Phase 5 — Extraction, Scoring, Deduplication — Status Report

## Sprint 5.1 — Deterministic Extraction
**Completed:** 2026-05-15

### What was built
- `app/extraction/__init__.py` — package init, exports all public symbols
- `app/extraction/models.py` — `ExtractedField` dataclass (value, source_url, source_type, raw_value) + `ExtractionResult` dataclass
- `app/extraction/_json_ld.py` — shared JSON-LD block parser; flattens `@graph` arrays; used by both name and address extractors
- `app/extraction/sanitize.py` — `sanitize_html(html) -> str` via bleach allowlist; pre-decomposes script/style via BeautifulSoup before bleach to prevent inline JS text leakage
- `app/extraction/email.py` — `extract_emails(html, source_url)` — mailto links first, then regex scan of visible text; deduplicated by lowercased address
- `app/extraction/phone.py` — `extract_phones(html, source_url)` — tel links first, then regex scan; normalized to 10-digit string, strips leading country code "1"
- `app/extraction/name.py` — `extract_company_name(html, source_url)` — priority chain: JSON-LD Organization/LocalBusiness → og:site_name → title tag (with separator stripping) → h1
- `app/extraction/url.py` — `extract_website_url(html, base_url, source_url)` — priority chain: og:url → canonical link → base_url fallback
- `app/extraction/address.py` — `extract_address(html, source_url)` — JSON-LD PostalAddress (formats parts) → itemprop address container → itemprop individual parts
- `app/extraction/runner.py` — `run_extraction(html, source_url, base_url) -> ExtractionResult` — pure orchestrator calling all extractors
- `tests/fixtures/html/extraction/` — 10 static HTML fixtures: full_contact, json_ld_local_business, email_only, phone_only, no_contact, malformed, og_tags, address_itemprop, multiple_contacts, regex_contact
- `tests/unit/test_extraction_sanitize.py` — 10 tests
- `tests/unit/test_extraction_email.py` — 12 tests
- `tests/unit/test_extraction_phone.py` — 10 tests
- `tests/unit/test_extraction_name.py` — 12 tests
- `tests/unit/test_extraction_url.py` — 8 tests
- `tests/unit/test_extraction_address.py` — 8 tests
- `tests/unit/test_extraction_runner.py` — 9 tests

### Key decisions
- `ExtractedField` carries `source_type` (e.g. `"mailto_link"`, `"json_ld"`, `"og_tag"`, `"canonical_link"`, `"regex_text"`, `"base_url"`, `"schema_org_itemprop"`) so the Phase 6/7 UI can show exactly where each value came from
- `sanitize_html()` pre-decomposes `<script>` and `<style>` via BeautifulSoup before calling bleach — bleach's `strip=True` removes tag wrappers but preserves their text content, which would expose raw JS in the output
- `_json_ld.py` is a private shared module (leading underscore) rather than duplicating `parse_json_ld_blocks()` in both name.py and address.py
- Email deduplication normalizes to lowercase; the first occurrence wins (mailto link takes priority over regex scan of the same address)
- Phone normalization strips all non-digits and drops the leading "1" for 11-digit US numbers; only 10-digit results are kept
- Title separator stripping splits on ` | `, ` - `, ` – `, ` — `, ` · ` and takes the first part
- All extractors are pure functions — no I/O, no state — making them trivially testable with inline HTML
- `beautifulsoup4>=4.12.0` + `lxml>=5.0.0` added to main dependencies; `types-beautifulsoup4>=4.12.0` added to dev extras

### Test results
69 new tests | 360/360 full suite green | ruff clean | mypy strict clean

### Bugs found and fixed
- bleach `strip=True` text-content leakage: discovered during implementation. Fixed by pre-stripping script/style via BeautifulSoup before calling bleach.

### Open issues / follow-ups
- Extractors produce `ExtractedField` objects; writing them to `record_sources` DB rows is deferred to Phase 6 job orchestrator (Sprint 6.1)
- Phone regex is US-centric (10-digit NANP format); international numbers ignored for MVP
- Title separator detection is heuristic; false positives possible on pages with dashes in company names (acceptable for MVP)

## Sprint 5.3 — Deduplication
**Completed:** 2026-05-15

### What was built
- `app/dedup/__init__.py` — package init, exports `RecordData`, `SourceData`, `DeduplicationEngine`
- `app/dedup/normalize.py` — 4 pure functions: `normalize_domain`, `normalize_name`, `normalize_phone`, `normalize_email`
- `app/dedup/engine.py` — `RecordData` + `SourceData` dataclasses; `DeduplicationEngine` with `find_duplicates()` and `merge_duplicates()`
- `tests/fixtures/records/same_domain.json`, `same_name_city.json`, `same_phone.json`, `no_duplicates.json`
- `tests/unit/test_dedup_normalize.py` — 21 normalization tests
- `tests/unit/test_dedup_engine.py` — 21 engine tests (detection + merge)

### Key decisions
- **Union-find with path compression** — handles transitive duplicate links (A matches B, B matches C → all three in one group) without quadratic merging
- **Missing location = wildcard** — if either record lacks city or state, that dimension is not a blocker. A conflict only fires when both sides have a value that differs
- **Normalization-based "fuzzy" matching** — no edit-distance library; `normalize_name` (lowercase, strip non-alphanumeric, collapse whitespace) handles punctuation and casing differences without new dependencies
- **Pure dataclasses, no ORM** — `RecordData`/`SourceData` mirror the ORM model fields but are plain Python dataclasses. Phase 6 orchestrator maps ORM → dataclass → dedup → applies DB writes
- **Merge is in-place mutation** — `merge_duplicates()` mutates the passed `RecordData` list: sets `loser.status = "duplicate"`, `loser.canonical_record_id = winner.id`, transfers all `SourceData` entries to the winner

### Test results
42 new tests | 484/484 full suite green | ruff clean | mypy strict clean

### Bugs found and fixed
None.

### Open issues / follow-ups
- ORM → RecordData mapping and DB write-back deferred to Phase 6 orchestrator
- `normalize_domain` strips only `www.` — other subdomains (e.g. `shop.example.com`) are not collapsed to root domain (acceptable for MVP)
