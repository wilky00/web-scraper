# ABOUTME: E2E test fixtures — Playwright browser setup, login helper, base URL config.
# ABOUTME: Set E2E_BASE_URL, E2E_EMAIL, E2E_PASSWORD env vars to run against a live environment.
from __future__ import annotations

import os
from typing import Any

import pytest
from playwright.sync_api import Page, Playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
E2E_EMAIL = os.environ.get("E2E_EMAIL", "admin@example.com")
E2E_PASSWORD = os.environ.get("E2E_PASSWORD", "changeme")


def pytest_collection_modifyitems(items: list, config: pytest.Config) -> None:
    if os.environ.get("E2E_BASE_URL"):
        return
    skip = pytest.mark.skip(reason="Set E2E_BASE_URL env var to run E2E tests")
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict) -> dict:
    return {**browser_context_args, "base_url": BASE_URL, "ignore_https_errors": True}


@pytest.fixture(scope="session")
def _auth_storage(playwright: Playwright) -> dict[str, Any]:
    """Log in once per test session; return Playwright storage state for reuse.

    Each logged_in test injects these cookies into its fresh context instead of
    re-authenticating — avoids burning through the 10-attempt/60s rate limit.
    """
    browser = playwright.chromium.launch()
    ctx = browser.new_context(base_url=BASE_URL, ignore_https_errors=True)
    page = ctx.new_page()
    page.goto("/login")
    page.fill("#email", E2E_EMAIL)
    page.fill("#password", E2E_PASSWORD)
    # The nav bar also renders a Sign Out submit on the login page — target login form only
    page.locator('form[action="/auth/login"] button[type="submit"]').click()
    page.wait_for_load_state("networkidle", timeout=30_000)
    assert "/login" not in page.url, f"Session login failed — still on {page.url}"
    state: dict[str, Any] = ctx.storage_state()
    ctx.close()
    browser.close()
    return state


@pytest.fixture
def logged_in(page: Page, _auth_storage: dict[str, Any]) -> Page:
    """Return an authenticated page using the pre-saved session state.

    Injects the session cookies from the shared _auth_storage into the current
    page's context so each test starts logged in without a fresh login POST.
    """
    page.context.add_cookies(_auth_storage.get("cookies", []))
    page.goto("/")
    page.wait_for_load_state("networkidle", timeout=15_000)
    return page
