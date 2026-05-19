# ABOUTME: E2E tests for authentication flows — login, logout, and session redirects.
# ABOUTME: Run with E2E_BASE_URL set; tests are skipped otherwise.
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import E2E_EMAIL, E2E_PASSWORD


@pytest.mark.e2e
def test_login_valid_credentials(page: Page) -> None:
    page.goto("/login")
    page.fill("#email", E2E_EMAIL)
    page.fill("#password", E2E_PASSWORD)
    page.click('[type="submit"]')
    page.wait_for_url("**/", timeout=15_000)
    assert "/login" not in page.url


@pytest.mark.e2e
def test_login_invalid_password(page: Page) -> None:
    page.goto("/login")
    page.fill("#email", E2E_EMAIL)
    page.fill("#password", "definitely-wrong-password-xyz")
    page.click('[type="submit"]')
    # Should stay on login page with an error alert
    page.wait_for_url("**/login**", timeout=10_000)
    expect(page.locator('[role="alert"]')).to_be_visible()


@pytest.mark.e2e
def test_unauthenticated_redirect(page: Page) -> None:
    page.goto("/jobs")
    page.wait_for_url("**/login**", timeout=10_000)
    assert "login" in page.url


@pytest.mark.e2e
def test_logout(logged_in: Page) -> None:
    logged_in.click('button:has-text("Sign out")')
    logged_in.wait_for_url("**/login**", timeout=10_000)
    # Confirm session is cleared by navigating to a protected route
    logged_in.goto("/jobs")
    logged_in.wait_for_url("**/login**", timeout=10_000)
    assert "login" in logged_in.url
