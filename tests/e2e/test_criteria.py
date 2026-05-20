# ABOUTME: E2E tests for the criteria editor — YAML validate, save, and template load.
# ABOUTME: Run with E2E_BASE_URL set; tests are skipped otherwise.
from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import Page, expect

_VALID_YAML = """\
metadata:
  name: e2e-test-placeholder
  display_name: "[E2E] Test Criteria"
  description: Created by E2E test suite
  tags: [e2e, test]

source:
  connector: fixture
  max_results: 5
  query_fields:
    - field: location
      value: "90210"

crawl:
  enabled: false

rules:
  must_have:
    - metric: source.name
      operator: exists
      label: Has a business name
"""

_INVALID_YAML = """\
this: is: invalid: yaml: [[[
  badly: - formatted
"""


@pytest.mark.e2e
def test_criteria_list_loads(logged_in: Page) -> None:
    logged_in.goto("/criteria")
    logged_in.wait_for_load_state("networkidle", timeout=10_000)
    expect(logged_in).not_to_have_url(re.compile(r".*/login.*"))
    expect(logged_in.locator("h1")).to_contain_text("Criteria")
    # Table renders via Alpine.js x-for — skip gracefully if staging has no data
    table_row = logged_in.locator("table tbody tr").first
    if table_row.count() == 0:
        pytest.skip("No criteria on staging — run test_save_criteria_appears_in_list first")
    expect(table_row).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_new_criteria_editor_loads(logged_in: Page) -> None:
    logged_in.goto("/criteria/new")
    expect(logged_in).not_to_have_url(re.compile(r".*/login.*"))
    expect(logged_in.locator("#yaml_text")).to_be_visible()


@pytest.mark.e2e
def test_valid_yaml_validates(logged_in: Page) -> None:
    logged_in.goto("/criteria/new")
    ta = logged_in.locator("#yaml_text")
    ta.fill(_VALID_YAML)
    logged_in.locator("button", has_text=re.compile(r"Validate", re.IGNORECASE)).click()
    # Validation panel should appear without an error badge
    panel = logged_in.locator("#validation-panel")
    panel.wait_for(timeout=15_000)
    expect(panel.locator("text=error")).not_to_be_visible(timeout=5_000)


@pytest.mark.e2e
def test_invalid_yaml_shows_error(logged_in: Page) -> None:
    logged_in.goto("/criteria/new")
    ta = logged_in.locator("#yaml_text")
    ta.fill(_INVALID_YAML)
    logged_in.locator("button", has_text=re.compile(r"Validate", re.IGNORECASE)).click()
    panel = logged_in.locator("#validation-panel")
    panel.wait_for(timeout=15_000)
    # Panel should contain some error indication
    expect(panel).to_contain_text(re.compile(r"error|invalid|failed", re.IGNORECASE))


@pytest.mark.e2e
def test_save_criteria_appears_in_list(logged_in: Page) -> None:
    unique = str(uuid.uuid4())[:8]
    display_name = f"[E2E] Criteria {unique}"
    yaml_with_name = _VALID_YAML.replace(
        'display_name: "[E2E] Test Criteria"',
        f'display_name: "{display_name}"',
    ).replace(
        "name: e2e-test-placeholder",
        f"name: e2e-test-{unique}",
    )

    logged_in.goto("/criteria/new")
    ta = logged_in.locator("#yaml_text")
    ta.fill(yaml_with_name)

    # Save the criteria — API returns HX-Redirect to /criteria/{id} (a UUID)
    logged_in.locator("button", has_text=re.compile(r"Save", re.IGNORECASE)).first.click()
    # Wait for redirect away from /criteria/new (must match UUID, not just /criteria/new)
    logged_in.wait_for_url(re.compile(r".*/criteria/[a-f0-9-]{36}"), timeout=15_000)

    # Verify it shows up in the criteria list — Alpine.js renders rows via x-text
    logged_in.goto("/criteria")
    logged_in.wait_for_load_state("networkidle", timeout=10_000)
    expect(logged_in.locator("a", has_text=display_name).first).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_template_load_populates_editor(logged_in: Page) -> None:
    logged_in.goto("/criteria/new")
    # Click the first template in the sidebar (if one exists)
    first_template_btn = logged_in.locator("button", has_text=re.compile(r"Use|Load|Select", re.IGNORECASE)).first
    if first_template_btn.count() == 0:
        pytest.skip("No template buttons found in criteria editor sidebar")
    initial_content = logged_in.locator("#yaml_text").input_value()
    first_template_btn.click()
    # YAML textarea should now have content
    updated = logged_in.locator("#yaml_text").input_value()
    assert len(updated) > len(initial_content) or len(updated) > 0
