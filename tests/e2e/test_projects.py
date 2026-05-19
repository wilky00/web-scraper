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
    # Default project link — use role selector to avoid strict mode violation
    # (the word "Default" also appears in a badge and a hidden dropdown option)
    expect(logged_in.get_by_role("link", name="Default")).to_be_visible()


@pytest.mark.e2e
def test_create_project(logged_in: Page) -> None:
    unique = str(uuid.uuid4())[:8]
    project_name = f"[E2E] Project {unique}"

    logged_in.goto("/projects/new")
    logged_in.fill('input[name="name"]', project_name)
    # Nav also has a "Sign out" submit — target by role+name to avoid strict mode
    logged_in.get_by_role("button", name="Create Project").click()
    # Alpine fetch handler reads HX-Redirect and navigates to /projects
    logged_in.wait_for_url(re.compile(r".*/projects$"), timeout=15_000)

    # Verify the new project is visible — use link role to avoid matching the modal option
    expect(logged_in.get_by_role("link", name=project_name)).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_generate_api_key(logged_in: Page) -> None:
    # Navigate to Default project detail
    logged_in.goto("/projects")
    default_link = logged_in.locator("a", has_text="Default").first
    default_link.click()
    logged_in.wait_for_load_state("networkidle", timeout=10_000)

    key_label = f"e2e-key-{str(uuid.uuid4())[:8]}"

    # Open the generate key modal (Alpine.js toggles showKeyModal)
    logged_in.locator("button", has_text="Generate Key").click()

    # Wait for modal input to appear
    label_input = logged_in.locator('input[name="label"]')
    label_input.wait_for(timeout=5_000)
    label_input.fill(key_label)

    # Submit — the nav has a "Sign out" submit too; filter to "Generate" text
    logged_in.locator('button[type="submit"]').filter(has_text=re.compile(r"Generate", re.IGNORECASE)).click()
    logged_in.wait_for_load_state("networkidle", timeout=15_000)

    # Keys are rendered as divs, not table rows — look for the label text
    expect(logged_in.locator("a, p, span", has_text=key_label).first).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_revoke_api_key(logged_in: Page) -> None:
    # Navigate to Default project and generate a fresh key to revoke
    logged_in.goto("/projects")
    default_link = logged_in.locator("a", has_text="Default").first
    default_link.click()
    logged_in.wait_for_load_state("networkidle", timeout=10_000)

    label = f"e2e-revoke-{str(uuid.uuid4())[:8]}"
    logged_in.locator("button", has_text="Generate Key").click()

    label_input = logged_in.locator('input[name="label"]')
    label_input.wait_for(timeout=5_000)
    label_input.fill(label)

    logged_in.locator('button[type="submit"]').filter(has_text=re.compile(r"Generate", re.IGNORECASE)).click()
    logged_in.wait_for_load_state("networkidle", timeout=15_000)

    # Our key's label appears in a <p> element — verify it's there after generate
    key_label_el = logged_in.locator("p", has_text=label)
    key_label_el.wait_for(timeout=10_000)

    # Find the innermost div that contains both our label AND a Revoke button (the per-key row)
    # Use .last because nested divs appear later in DOM order than their ancestors
    key_row = logged_in.locator("div").filter(
        has=logged_in.locator("p", has_text=label)
    ).filter(
        has=logged_in.locator("button", has_text="Revoke")
    ).last

    # revokeKey() calls window.confirm() — accept the dialog before clicking
    logged_in.on("dialog", lambda d: d.accept())
    key_row.get_by_role("button", name="Revoke").click()
    logged_in.wait_for_load_state("networkidle", timeout=15_000)

    # After reload, our label's <p> should no longer appear
    assert logged_in.locator("p", has_text=label).count() == 0
