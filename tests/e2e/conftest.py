# ABOUTME: E2E test fixtures — Playwright browser setup, login helper, base URL config.
# ABOUTME: Set E2E_BASE_URL, E2E_EMAIL, E2E_PASSWORD env vars to run against a live environment.
from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page

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


@pytest.fixture
def logged_in(page: Page) -> Page:
    """Log in and return an authenticated page."""
    page.goto("/login")
    page.fill("#email", E2E_EMAIL)
    page.fill("#password", E2E_PASSWORD)
    page.click('[type="submit"]')
    page.wait_for_url("**/", timeout=15_000)
    return page
