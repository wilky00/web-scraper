# ABOUTME: First-boot criteria seeding. Inserts 5 example templates if the table is empty.
# ABOUTME: Called from the FastAPI lifespan; safe to run on every startup (idempotent).
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config.criteria import validate_criteria_yaml
from app.models.criteria import CriteriaGroup, CriteriaVersion

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Example templates
# ---------------------------------------------------------------------------

_TEMPLATES: list[str] = [
    # 1 — Social-only businesses near Nashville
    """\
metadata:
  name: social-only-businesses-nashville
  display_name: Social-Only Businesses Near Nashville (20 mi of 37214)
  description: >
    Finds local businesses within 20 miles of ZIP 37214 whose website page title
    reveals a Facebook or Instagram redirect instead of an independent site.
    Useful for outreach campaigns targeting businesses that need a real website.
  tags: [outreach, social-media, no-website, nashville]

source:
  connector: google_places
  max_results: 60
  query_fields:
    - field: location
      value: "37214"
    - field: radius
      value: "32186"

crawl:
  enabled: true
  max_depth: 1
  max_pages_per_domain: 2
  timeout_seconds: 20
  delay_ms: 1000

extraction:
  fields:
    - name: email
      source_priority: [structured, text, mailto_links]
    - name: phone
      source_priority: [structured, text, tel_links]

rules:
  must_have:
    - metric: source.name
      operator: exists
      label: Has a business name
  exclude:
    - metric: html.title
      operator: contains
      value: "404"
      label: Website returns not-found page
  should_have:
    - metric: html.title
      operator: contains_any
      value: ["Facebook", "Log into Facebook", "Instagram", "Log In to Instagram"]
      label: Page title indicates social media redirect
      weight: 100.0

scoring:
  enabled: true
  minimum_score: 50.0
  weighted_rules: []

dedup:
  primary_key: domain
  secondary_keys: [name, phone]

output:
  display_fields: [name, source.website, phone, location_city, match_score]
  store_fields: [name, source.website, phone, email, location_city, location_state, match_score]
  export_fields: [name, source.website, phone, email, location_city, location_state]
""",

    # 2 — Nashville barbershops with legacy HTML
    """\
metadata:
  name: nashville-barbershops-legacy-html
  display_name: Nashville Barbershops with Legacy HTML Websites
  description: >
    Finds barbershops and hair salons in the Nashville metro area whose websites
    use HTML 4.0 or XHTML — indicating an outdated, likely unmaintained web presence.
    These businesses may be receptive to website modernization services.
  tags: [barbershop, legacy-tech, nashville, website-audit]

source:
  connector: google_places
  max_results: 60
  query_fields:
    - field: type
      value: hair_care
    - field: location
      value: "Nashville, TN"
    - field: radius
      value: "40000"

crawl:
  enabled: true
  max_depth: 1
  max_pages_per_domain: 3
  timeout_seconds: 30
  delay_ms: 1000

extraction:
  fields:
    - name: email
      source_priority: [structured, text, mailto_links]
    - name: phone
      source_priority: [structured, text, tel_links]

rules:
  must_have:
    - metric: source.name
      operator: exists
      label: Has a business name
  exclude:
    - metric: source.rating
      operator: less_than_or_equal
      value: 2.0
      label: Poorly rated (below 2 stars)
  should_have:
    - metric: html.title
      operator: contains_any
      value: ["HTML 4.0", "HTML 4.01", "XHTML 1.0", "XHTML 1.1"]
      label: Page DOCTYPE indicates legacy HTML
      weight: 100.0
    - metric: extraction.email
      operator: exists
      label: Has contact email
      weight: 10.0

scoring:
  enabled: true
  minimum_score: 50.0
  weighted_rules:
    - metric: extraction.phone
      operator: exists
      label: Has phone number on site
      weight: 5.0

dedup:
  primary_key: domain
  secondary_keys: [name, phone]

output:
  display_fields: [name, source.website, phone, email, location_city, match_score]
  store_fields: [name, source.website, phone, email, location_city, location_state, match_score]
  export_fields: [name, source.website, phone, email, location_city, location_state]
""",

    # 3 — Nashville restaurants missing contact info
    """\
metadata:
  name: restaurants-missing-contact-info
  display_name: Nashville Restaurants Without Contact Info Online
  description: >
    Finds restaurants in Nashville that have a Google Places listing and website
    but are missing both email and phone number on their site. These businesses
    make it hard for customers to reach them and may benefit from a contact page update.
  tags: [restaurant, food, nashville, contact-info, outreach]

source:
  connector: google_places
  max_results: 60
  query_fields:
    - field: type
      value: restaurant
    - field: location
      value: "Nashville, TN"
    - field: radius
      value: "25000"

crawl:
  enabled: true
  max_depth: 2
  max_pages_per_domain: 10
  include_url_patterns:
    - ".*contact.*"
    - ".*about.*"
  timeout_seconds: 30
  delay_ms: 1000

extraction:
  fields:
    - name: email
      source_priority: [structured, text, mailto_links]
      filters: [valid_email]
    - name: phone
      source_priority: [structured, text, tel_links]
      filters: [normalize_phone]

rules:
  must_have:
    - metric: source.name
      operator: exists
      label: Has business name
  exclude:
    - metric: extraction.email
      operator: exists
      label: Already has email on site (we want those WITHOUT)
    - metric: extraction.phone
      operator: exists
      label: Already has phone on site (we want those WITHOUT)
    - metric: source.rating
      operator: less_than_or_equal
      value: 2.5
      label: Poorly rated
  should_have:
    - metric: crawl.pages_crawled
      operator: greater_than_or_equal
      value: 2
      label: Website has multiple pages
      weight: 5.0

scoring:
  enabled: true
  minimum_score: 0.0
  weighted_rules: []

dedup:
  primary_key: domain
  secondary_keys: [name]

output:
  display_fields: [name, source.website, location_city, source.rating, match_score]
  store_fields: [name, source.website, location_city, location_state, source.rating, match_score]
  export_fields: [name, source.website, location_city, location_state, source.rating]
""",

    # 4 — Local shops without HTTPS
    """\
metadata:
  name: local-shops-http-only
  display_name: Nashville Retail Shops Without HTTPS
  description: >
    Identifies local retail businesses in Nashville whose Google Places website URL
    still uses plain HTTP instead of HTTPS. Sites without SSL display "Not Secure"
    warnings in browsers and are penalized in search rankings — a clear selling point
    for an upgrade pitch.
  tags: [retail, security, https, ssl, nashville]

source:
  connector: google_places
  max_results: 60
  query_fields:
    - field: type
      value: store
    - field: location
      value: "Nashville, TN"
    - field: radius
      value: "30000"

crawl:
  enabled: true
  max_depth: 1
  max_pages_per_domain: 2
  timeout_seconds: 20
  delay_ms: 1000

extraction:
  fields:
    - name: email
      source_priority: [structured, text, mailto_links]
    - name: phone
      source_priority: [structured, text, tel_links]

rules:
  must_have:
    - metric: source.name
      operator: exists
      label: Has business name
  exclude:
    - metric: source.website
      operator: matches_regex
      value: "^https://"
      label: Already uses HTTPS
  should_have:
    - metric: source.website
      operator: matches_regex
      value: "^http://"
      label: Website URL uses HTTP (not HTTPS)
      weight: 100.0

scoring:
  enabled: true
  minimum_score: 50.0
  weighted_rules:
    - metric: extraction.email
      operator: exists
      label: Has email for follow-up
      weight: 10.0
    - metric: extraction.phone
      operator: exists
      label: Has phone for follow-up
      weight: 5.0

dedup:
  primary_key: domain
  secondary_keys: [name, phone]

output:
  display_fields: [name, source.website, phone, email, location_city, match_score]
  store_fields: [name, source.website, phone, email, location_city, location_state, match_score]
  export_fields: [name, source.website, phone, email, location_city, location_state]
""",

    # 5 — Nashville gyms without online booking
    """\
metadata:
  name: nashville-gyms-without-online-booking
  display_name: Nashville Gyms Without Online Class Booking
  description: >
    Finds gyms, yoga studios, and fitness centers in Nashville that have a website
    but show no evidence of Mindbody, ClassPass, Acuity, or Calendly integrations.
    Gyms without online booking lose walk-in conversions and are prime candidates
    for scheduling platform adoption.
  tags: [fitness, gym, nashville, booking, scheduling]

source:
  connector: google_places
  max_results: 60
  query_fields:
    - field: type
      value: gym
    - field: location
      value: "Nashville, TN"
    - field: radius
      value: "35000"

crawl:
  enabled: true
  max_depth: 2
  max_pages_per_domain: 15
  include_url_patterns:
    - ".*schedule.*"
    - ".*class.*"
    - ".*book.*"
  timeout_seconds: 30
  delay_ms: 1000

extraction:
  fields:
    - name: email
      source_priority: [structured, text, mailto_links]
    - name: phone
      source_priority: [structured, text, tel_links]

rules:
  must_have:
    - metric: source.name
      operator: exists
      label: Has business name
  exclude:
    - metric: html.title
      operator: contains_any
      value: ["Mindbody", "ClassPass", "Acuity", "Calendly", "Book a Class"]
      label: Uses a known booking platform (visible in page title)
    - metric: source.rating
      operator: less_than_or_equal
      value: 3.0
      label: Poorly rated
  should_have:
    - metric: extraction.email
      operator: exists
      label: Has contact email
      weight: 10.0
    - metric: crawl.pages_crawled
      operator: greater_than_or_equal
      value: 3
      label: Active website with multiple pages
      weight: 5.0

scoring:
  enabled: true
  minimum_score: 0.0
  weighted_rules:
    - metric: extraction.phone
      operator: exists
      label: Has phone number
      weight: 5.0

dedup:
  primary_key: domain
  secondary_keys: [name, phone]

output:
  display_fields: [name, source.website, phone, email, location_city, source.rating, match_score]
  store_fields: [name, source.website, phone, email, location_city, location_state, source.rating, match_score]
  export_fields: [name, source.website, phone, email, location_city, location_state, source.rating]
""",
]


async def seed_example_criteria(
    engine: AsyncEngine, created_by: uuid.UUID | None = None
) -> None:
    """Seed 5 example criteria templates if they don't already exist by name. Idempotent."""
    count = 0
    for yaml_text in _TEMPLATES:
        config, errors = validate_criteria_yaml(yaml_text)
        if errors or config is None:
            logger.error("criteria.seed.invalid_yaml", errors=errors)
            continue

        snapshot = config.model_dump()
        async with AsyncSession(engine) as db:
            existing = await db.execute(
                select(CriteriaGroup).where(CriteriaGroup.name == config.metadata.name)
            )
            if existing.scalar_one_or_none() is not None:
                continue

            group = CriteriaGroup(
                name=config.metadata.name,
                display_name=config.metadata.display_name,
                description=config.metadata.description,
                tags=config.metadata.tags,
                is_active=True,
            )
            db.add(group)
            await db.flush()
            group_id = group.id

            version = CriteriaVersion(
                group_id=group_id,
                version=1,
                config_snapshot=snapshot,
                is_active=True,
                created_by=created_by,
            )
            db.add(version)
            await db.commit()
        count += 1

    if count:
        logger.info("criteria.seed.complete", templates_created=count)
