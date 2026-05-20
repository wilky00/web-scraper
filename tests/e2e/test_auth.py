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
    # The nav bar also has a Sign Out [type=submit] — target the login form specifically
    page.locator('form[action="/auth/login"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle", timeout=30_000)
    assert "/login" not in page.url


@pytest.mark.e2e
def test_login_invalid_password(page: Page) -> None:
    page.goto("/login")
    page.fill("#email", E2E_EMAIL)
    page.fill("#password", "definitely-wrong-password-xyz")
    page.locator('form[action="/auth/login"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle", timeout=10_000)
    # Should stay on the login/auth path with an error alert
    assert "login" in page.url.lower() or "auth" in page.url.lower()
    expect(page.locator('[role="alert"]')).to_be_visible()


@pytest.mark.e2e
def test_unauthenticated_redirect(page: Page) -> None:
    page.goto("/jobs")
    page.wait_for_url("**/login**", timeout=10_000)
    assert "login" in page.url


@pytest.mark.e2e
def test_logout(page: Page) -> None:
    # Fresh login — do NOT use logged_in here; logging out invalidates the shared
    # _auth_storage session and breaks all subsequent tests in the run.
    page.goto("/login")
    page.fill("#email", E2E_EMAIL)
    page.fill("#password", E2E_PASSWORD)
    page.locator('form[action="/auth/login"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle", timeout=30_000)
    assert "/login" not in page.url, f"Login failed — still on {page.url}"

    page.click('button:has-text("Sign out")')
    page.wait_for_url("**/login**", timeout=10_000)
    # Confirm session is cleared by navigating to a protected route
    page.goto("/jobs")
    page.wait_for_url("**/login**", timeout=10_000)
    assert "login" in page.url
