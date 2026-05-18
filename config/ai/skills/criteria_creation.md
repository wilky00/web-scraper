# Criteria YAML — Schema Reference

Criteria files configure what the scraper searches for, how it crawls, what it extracts, how it scores records, and what gets exported. Every section is optional except `metadata` and `source`.

---

## Top-Level Structure

```yaml
metadata:    # required
source:      # required
crawl:       # optional (defaults shown below)
extraction:  # optional
rules:       # optional
scoring:     # optional
dedup:       # optional
output:      # optional
```

---

## `metadata` (required)

```yaml
metadata:
  name: unique-slug           # lowercase, hyphens only — used as identifier
  display_name: Human Name    # shown in the UI
  description: "What this criteria finds"
  tags: [tag1, tag2]          # optional list of strings
```

---

## `source` (required)

Defines the connector and query parameters.

```yaml
source:
  connector: google_places    # connector type (google_places or fixture)
  max_results: 60             # max records to retrieve (default: 60, min: 1)
  query_fields:               # connector-specific query parameters
    - field: type
      value: bakery
    - field: location
      value: "Nashville, TN"
    - field: radius
      value: "48000"          # metres
```

**Google Places query fields:** `type`, `location`, `radius`, `keyword`, `language`

---

## `crawl` (optional)

Controls website crawling after connector discovery.

```yaml
crawl:
  enabled: true               # set false to skip crawling entirely
  max_depth: 2                # link depth from landing page (0–10, default: 3)
  max_pages_per_domain: 10    # per-domain page cap (default: 50)
  timeout_seconds: 30         # per-page timeout (1–300, default: 30)
  delay_ms: 1000              # delay between requests in ms (default: 1000)
  include_url_patterns:       # only follow URLs matching these patterns (regex)
    - ".*menu.*"
    - ".*about.*"
  exclude_url_patterns:       # never follow URLs matching these patterns
    - "/order"
    - "/cart"
```

---

## `extraction` (optional)

Specifies which fields to extract from crawled pages.

```yaml
extraction:
  fields:
    - name: email
    - name: phone
      source_priority: [html, connector]   # which source takes precedence
    - name: address
      source_priority: [connector, html]
    - name: name
    - name: website
```

**Extractable field names:** `email`, `phone`, `name`, `website`, `address`

**source_priority values:** `html` (parsed from page), `connector` (from API result)

---

## `rules` (optional)

Rules determine inclusion, exclusion, and bonus scoring.

```yaml
rules:
  must_have:                  # record excluded if ANY must_have fails
    - metric: extraction.email
      operator: exists
      label: Has email address
  exclude:                    # record excluded if ANY exclude rule matches
    - metric: source.rating
      operator: less_than_or_equal
      value: 2.0
      label: Low rated
  should_have:                # contributes to match_score but not inclusion
    - metric: crawl.status_code
      operator: equals
      value: 200
      label: Website resolves
```

---

## `scoring` (optional)

Weighted scoring on top of `should_have` rules.

```yaml
scoring:
  enabled: true
  minimum_score: 30.0         # records below this score are excluded (0–100)
  weighted_rules:
    - metric: extraction.phone
      operator: exists
      weight: 2.0             # relative weight (default: 1.0)
      label: Has phone
    - metric: extraction.address
      operator: exists
      weight: 1.5
      label: Has physical address
```

---

## `dedup` (optional)

Controls automatic deduplication.

```yaml
dedup:
  primary_key: domain         # first dedup pass key (domain or email)
  secondary_keys: [email, phone]
```

---

## `output` (optional)

Controls which fields are shown, stored, and exported.

```yaml
output:
  display_fields: [name, email, phone, address, website, match_score]
  store_fields: [name, email, phone, address, website, match_score]
  export_fields: [name, email, phone, address, website]
```

---

## Operators

All operators used in `rules` and `scoring.weighted_rules`:

| Operator | Description | Example value |
|---|---|---|
| `exists` | Field has a non-empty value | (no value needed) |
| `not_exists` | Field is missing or empty | (no value needed) |
| `equals` | Exact match | `200` |
| `not_equals` | Not equal | `"deleted"` |
| `contains` | String contains substring | `"bakery"` |
| `contains_any` | String contains any item in list | `["cafe", "bakery"]` |
| `greater_than_or_equal` | Numeric ≥ value | `4.0` |
| `less_than_or_equal` | Numeric ≤ value | `2.0` |
| `in` | Value is in list | `["open", "active"]` |
| `not_in` | Value not in list | `["closed", "inactive"]` |
| `domain_matches` | Domain matches pattern | `"example.com"` |
| `matches_regex` | Value matches regex | `"^https?://"` |

**There is no `not_contains` operator.** To express "field must NOT contain X", put a `contains` rule in the `exclude` section instead:

```yaml
# WRONG — not_contains does not exist:
rules:
  must_have:
    - metric: extraction.website
      operator: not_contains      # invalid — will fail validation
      value: "starbucks.com"

# CORRECT — use exclude with contains:
rules:
  exclude:
    - metric: extraction.website
      operator: contains
      value: "starbucks.com"
      label: Is Starbucks website
```

To exclude records where a field matches any of several values, use `contains_any` in `exclude`:

```yaml
rules:
  exclude:
    - metric: source.name
      operator: contains_any
      value: ["Starbucks", "Dunkin", "McDonald's"]
      label: Chain restaurant
```

---

## Metric Namespaces

Metrics used in rules must be `<namespace>.<field>`:

| Namespace | What it covers |
|---|---|
| `source.*` | Connector API data (e.g. `source.rating`, `source.review_count`) |
| `crawl.*` | Crawl outcomes (e.g. `crawl.status_code`, `crawl.pages_crawled`) |
| `html.*` | Raw HTML properties (e.g. `html.has_schema_org`) |
| `links.*` | Links found on page (e.g. `links.has_email_link`) |
| `extraction.*` | Extracted field presence (e.g. `extraction.email`, `extraction.phone`) |

---

## Complete Example

Search for bakeries near Nashville that have a social media presence:

```yaml
metadata:
  name: bakeries-nashville-social
  display_name: Nashville Bakeries (Social Media Focus)
  description: Bakeries within 30 miles of Nashville whose websites are social media pages
  tags: [bakery, nashville, social-media]

source:
  connector: google_places
  max_results: 100
  query_fields:
    - field: type
      value: bakery
    - field: location
      value: "Nashville, TN"
    - field: radius
      value: "48280"

crawl:
  enabled: false

extraction:
  fields:
    - name: name
    - name: phone
      source_priority: [connector, html]
    - name: address
      source_priority: [connector, html]
    - name: website

rules:
  must_have:
    - metric: extraction.website
      operator: exists
      label: Has website
    - metric: extraction.website
      operator: contains_any
      value: ["facebook.com", "instagram.com"]
      label: Website is a social media page
  exclude:
    - metric: source.rating
      operator: less_than_or_equal
      value: 1.0
      label: Very low rating

scoring:
  enabled: true
  minimum_score: 0.0
  weighted_rules:
    - metric: extraction.phone
      operator: exists
      weight: 1.5
      label: Has phone number
    - metric: source.rating
      operator: greater_than_or_equal
      value: 4.0
      weight: 2.0
      label: High rating

dedup:
  primary_key: domain
  secondary_keys: [phone]

output:
  display_fields: [name, phone, address, website, match_score]
  store_fields: [name, phone, address, website, match_score]
  export_fields: [name, phone, address, website]
```
