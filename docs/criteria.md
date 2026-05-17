# Criteria — User Guide

Criteria are the templates that define *what* to find and *how* to score it. Every scrape job references a criteria entry. This guide covers creating and editing criteria through the web UI.

---

## What Criteria Do

A criteria entry tells the app:

1. **Source** — which connector to use and what to search for
2. **Crawl** — how deep to follow links from each result
3. **Extraction** — which data fields to pull from crawled pages
4. **Rules** — which fields must be present, which are bonuses, which disqualify a record
5. **Scoring** — how to weight rule hits into a numeric score
6. **Dedup** — how to collapse duplicate records
7. **Output** — which fields appear in the UI, get stored, and export to CSV

---

## Creating Criteria

1. Navigate to **Criteria** in the top navigation
2. Click **New Criteria** (top right of the list page)
3. Write or paste YAML into the editor — validation runs automatically as you type
4. Click **Save criteria** to create version 1

When you edit an existing criteria and click **Save as new version**, the previous version is preserved. Versions are immutable and listed in the sidebar.

---

## YAML Structure

Every criteria file has two required sections (`metadata`, `source`) and six optional ones.

```yaml
metadata:
  name: my-criteria             # unique slug — used in URLs and logs
  display_name: My Criteria     # shown in the UI
  description: ''               # optional note
  tags: []                      # optional list of strings

source:
  connector: fixture            # which connector to query
  max_results: 60               # how many results to request from the connector
  query_fields:                 # connector-specific search parameters
    - field: type
      value: bakery

crawl:                          # optional — defaults shown
  enabled: true
  max_depth: 3                  # how many hops from the source URL
  max_pages_per_domain: 50
  timeout_seconds: 30
  delay_ms: 1000                # wait between page fetches (be polite)
  include_url_patterns: []      # regex — only follow matching URLs
  exclude_url_patterns: []      # regex — skip matching URLs

extraction:
  fields:
    - name: email
      source_priority:          # try these sources in order
        - structured            # JSON-LD, microdata, schema.org
        - text                  # visible page text
        - mailto_links
      filters: []               # post-extraction filters (e.g. "valid_email")

rules:
  must_have:                    # record is dropped if any must_have rule fails
    - metric: source.name
      operator: exists
      label: Has a name

  should_have:                  # adds to score when matched
    - metric: extraction.email
      operator: exists
      label: Has email
      weight: 10.0

  exclude:                      # record is dropped if any exclude rule matches
    - metric: html.title
      operator: contains
      value: "permanently closed"
      label: Closed business

scoring:
  enabled: true
  minimum_score: 0.0            # records below this threshold are filtered out
  weighted_rules:               # additional scoring rules beyond should_have
    - metric: crawl.pages_crawled
      operator: greater_than_or_equal
      value: 2
      label: Has multiple pages
      weight: 5.0

dedup:
  primary_key: domain           # field used for first-pass deduplication
  secondary_keys:               # additional fields checked after primary
    - name
    - city

output:
  display_fields:               # columns shown in the Records table
    - name
    - domain
    - email
  store_fields:                 # fields stored in the database
    - name
    - domain
    - email
    - phone
  export_fields:                # columns included in CSV/XLSX export
    - name
    - domain
    - email
    - phone
    - address
```

---

## Field Reference

### `metadata`

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | Yes | Unique slug; lowercase, hyphens only. Used in logs and URLs. |
| `display_name` | string | Yes | Human-readable name shown in the UI. |
| `description` | string | No | Free-text notes; displayed on the criteria detail page. |
| `tags` | list[string] | No | Arbitrary labels for filtering (not yet exposed in the UI). |

### `source`

| Field | Type | Default | Notes |
|---|---|---|---|
| `connector` | string | — | Required. Must match a connector defined in `connectors.yml`. Use `fixture` for testing. |
| `max_results` | int | 60 | Maximum records to fetch from the connector. Range: 1–∞. |
| `query_fields` | list | [] | Connector-specific key/value pairs passed as search parameters. |

### `crawl`

| Field | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | true | Set to `false` to skip crawling and use connector data only. |
| `max_depth` | int | 3 | How many link hops from the source URL. Range: 0–10. |
| `max_pages_per_domain` | int | 50 | Cap per domain to avoid getting stuck. |
| `timeout_seconds` | int | 30 | Per-page timeout. Range: 1–300. |
| `delay_ms` | int | 1000 | Milliseconds between page fetches. |
| `include_url_patterns` | list[string] | [] | Regexes; only follow URLs matching at least one pattern. Empty = follow all. |
| `exclude_url_patterns` | list[string] | [] | Regexes; skip URLs matching any pattern. |

### `extraction.fields`

Each field defines one data point to extract from crawled pages.

| Sub-field | Type | Notes |
|---|---|---|
| `name` | string | Name of the extracted field (e.g. `email`, `phone`, `address`). |
| `source_priority` | list[string] | Order of extraction sources to try: `structured`, `text`, `mailto_links`, `tel_links`. |
| `filters` | list[string] | Post-extraction transformations (e.g. `valid_email`, `normalize_phone`). |

### `rules` — `must_have`, `should_have`, `exclude`

Each rule targets a metric in `namespace.field` format and applies an operator.

**Valid namespaces:** `source`, `crawl`, `html`, `links`, `extraction`

**Operators:**

| Operator | Meaning |
|---|---|
| `exists` | Field is present and non-empty |
| `not_exists` | Field is absent or empty |
| `equals` | Field exactly matches `value` |
| `not_equals` | Field does not match `value` |
| `contains` | Field contains `value` as a substring |
| `contains_any` | Field contains any of the strings in `value` list |
| `greater_than_or_equal` | Numeric field ≥ `value` |
| `less_than_or_equal` | Numeric field ≤ `value` |
| `in` | Field is one of the values in `value` list |
| `not_in` | Field is not in the `value` list |
| `domain_matches` | URL field's domain matches `value` (exact or suffix) |
| `matches_regex` | Field matches `value` as a regex pattern |

Rule fields:

| Field | Type | Default | Notes |
|---|---|---|---|
| `metric` | string | — | Required. Format: `namespace.field_name` |
| `operator` | string | — | Required. One of the operators above. |
| `value` | any | null | Required for most operators; omit for `exists`/`not_exists`. |
| `label` | string | `""` | Human-readable description shown in logs and the UI. |
| `weight` | float | 1.0 | Contribution to score for `should_have` and `scoring.weighted_rules`. Range: 0–100. |

**Rule sections:**

- `must_have` — all rules must pass or the record is dropped entirely
- `should_have` — each matching rule adds `weight` to the record's score
- `exclude` — any matching rule drops the record entirely

### `scoring`

| Field | Type | Default | Notes |
|---|---|---|---|
| `enabled` | bool | true | Set to `false` to skip scoring entirely. |
| `minimum_score` | float | 0.0 | Records below this score are filtered from results. Range: 0–100. |
| `weighted_rules` | list[Rule] | [] | Additional rules that contribute to scoring but don't exclude records. |

### `dedup`

| Field | Type | Default | Notes |
|---|---|---|---|
| `primary_key` | string | `"domain"` | Field used for first-pass deduplication (exact match). |
| `secondary_keys` | list[string] | [] | Additional fields checked in subsequent dedup passes. |

### `output`

| Field | Type | Notes |
|---|---|---|
| `display_fields` | list[string] | Columns shown in the Records table in the UI. |
| `store_fields` | list[string] | Fields persisted to the database. Must include everything you want to export. |
| `export_fields` | list[string] | Columns included in CSV/XLSX downloads. Must be a subset of `store_fields`. |

---

## Version History

Every save creates a new immutable version. Versions are listed in the sidebar of the editor. To view a previous version's YAML, you can't load it directly from the UI yet — but the full config snapshot is stored in the database and preserved forever.

---

## AI Assist

When AI Assist is configured (see `docs/config.md`), an AI chat panel appears in the editor. You can describe what you want in plain language:

> "Create a template for coffee shops in Nashville with website and phone number required"

The AI generates YAML that you can review and apply to the editor with one click. The AI never saves directly — you still control the final YAML and must click **Save criteria** yourself.

---

## Tips

- Always **Validate** before saving — the button runs all rules against the current YAML and shows errors in the panel below the editor.
- Use `connector: fixture` while building a template. The fixture connector returns static test data so you can iterate without consuming API quota.
- Keep `name` short and URL-safe — it appears in job logs and the DB. Use hyphens, not spaces.
- Start with `minimum_score: 0` during development so no records are filtered out while you tune scoring rules.
