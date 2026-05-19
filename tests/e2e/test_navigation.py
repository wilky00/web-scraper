# ABOUTME: E2E tests for navigation — nav links, health check, 404 handling, settings page.
# ABOUTME: Run with E2E_BASE_URL set; tests are skipped otherwise.
from __future__ import annotations

import re

import pytest
import requests
from playwright.sync_api import Page, expect

from tests.e2e.conftest import BASE_URL


@pytest.mark.e2e
def test_health_endpoint() -> None:
    resp = requests.get(f"{BASE_URL}/health", timeout=10)
    assert resp.status_code == 200


@pytest.mark.e2e
def test_nav_links_all_load(logged_in: Page) -> None:
    nav_links = ["/", "/projects", "/criteria/new", "/jobs", "/records", "/exports", "/settings"]
    for path in nav_links:
        logged_in.goto(path)
        expect(logged_in).not_to_have_url(re.compile(r".*/login.*"))
        assert logged_in.locator("h1").count() > 0 or logged_in.title() != ""


@pytest.mark.e2e
def test_unknown_route_returns_404(logged_in: Page) -> None:
    resp = logged_in.request.get(f"{BASE_URL}/does-not-exist-route-xyz-abc")
    assert resp.status == 404
    # Should not be a Python traceback
    body = resp.text()
    assert "Traceback" not in body
    assert "Internal Server Error" not in body


@pytest.mark.e2e
def test_settings_page_loads(logged_in: Page) -> None:
    logged_in.goto("/settings")
    expect(logged_in).not_to_have_url(re.compile(r".*/login.*"))
    expect(logged_in.locator("h1")).to_be_visible()
