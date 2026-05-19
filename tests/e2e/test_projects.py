# ABOUTME: E2E tests for the projects page — list, create, API key generate/revoke.
# ABOUTME: Run with E2E_BASE_URL set; tests are skipped otherwise.
from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_projects_list_loads(logged_in: Page) -> None:
    logged_in.goto("/projects")
    expect(logged_in).not_to_have_url(re.compile(r".*/login.*"))
    expect(logged_in.locator("h1")).to_contain_text("Projects")
    # Default project should always exist
    expect(logged_in.locator("text=Default")).to_be_visible()


@pytest.mark.e2e
def test_create_project(logged_in: Page) -> None:
    unique = str(uuid.uuid4())[:8]
    project_name = f"[E2E] Project {unique}"

    logged_in.goto("/projects/new")
    logged_in.fill('input[name="name"]', project_name)
    logged_in.locator('button[type="submit"]', has_text=re.compile(r"Create|Save", re.IGNORECASE)).click()
    # Should redirect to project detail or list after creation
    logged_in.wait_for_url(re.compile(r".*/projects.*"), timeout=15_000)

    # Verify the new project is visible
    logged_in.goto("/projects")
    expect(logged_in.locator(f"text={project_name}")).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_generate_api_key(logged_in: Page) -> None:
    # Navigate to Default project detail
    logged_in.goto("/projects")
    default_link = logged_in.locator("a", has_text="Default").first
    default_link.click()
    logged_in.wait_for_load_state("networkidle", timeout=10_000)

    # Open the generate key modal
    generate_btn = logged_in.locator("button", has_text=re.compile(r"Generate|New Key|Add Key", re.IGNORECASE)).first
    generate_btn.click()

    # Fill in key label if prompted
    label_input = logged_in.locator('input[name="label"]')
    if label_input.is_visible(timeout=2_000):
        label_input.fill(f"e2e-key-{str(uuid.uuid4())[:8]}")

    # Submit
    logged_in.locator('button[type="submit"]', has_text=re.compile(r"Generate|Create", re.IGNORECASE)).first.click()
    logged_in.wait_for_load_state("networkidle", timeout=15_000)

    # A key should now be listed (masked like sk-...)
    expect(logged_in.locator("table tbody tr").first).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_revoke_api_key(logged_in: Page) -> None:
    # Navigate to Default project and generate a fresh key to revoke
    logged_in.goto("/projects")
    default_link = logged_in.locator("a", has_text="Default").first
    default_link.click()
    logged_in.wait_for_load_state("networkidle", timeout=10_000)

    label = f"e2e-revoke-{str(uuid.uuid4())[:8]}"
    generate_btn = logged_in.locator("button", has_text=re.compile(r"Generate|New Key|Add Key", re.IGNORECASE)).first
    generate_btn.click()

    label_input = logged_in.locator('input[name="label"]')
    if label_input.is_visible(timeout=2_000):
        label_input.fill(label)

    logged_in.locator('button[type="submit"]', has_text=re.compile(r"Generate|Create", re.IGNORECASE)).first.click()
    logged_in.wait_for_load_state("networkidle", timeout=15_000)

    # Count rows before revoke
    rows_before = logged_in.locator("table tbody tr").count()
    assert rows_before > 0

    # Accept the confirm dialog and click Revoke on the first key row
    logged_in.on("dialog", lambda d: d.accept())
    logged_in.locator("button", has_text=re.compile(r"Revoke", re.IGNORECASE)).first.click()
    logged_in.wait_for_load_state("networkidle", timeout=15_000)

    rows_after = logged_in.locator("table tbody tr").count()
    assert rows_after < rows_before or rows_after == 0
