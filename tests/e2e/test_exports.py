# ABOUTME: E2E tests for the exports page — create, status polling, and download.
# ABOUTME: Run with E2E_BASE_URL set; tests are skipped otherwise.
from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_exports_page_loads(logged_in: Page) -> None:
    logged_in.goto("/exports")
    expect(logged_in).not_to_have_url(re.compile(r".*/login.*"))
    expect(logged_in.locator("h1")).to_contain_text("Exports")


@pytest.mark.e2e
def test_create_csv_export(logged_in: Page) -> None:
    logged_in.goto("/exports")
    # Select CSV format and submit the export form
    logged_in.locator('select[name="format"]').select_option("csv")
    logged_in.locator('button[type="submit"]', has_text=re.compile(r"Export", re.IGNORECASE)).click()
    # Page should reload (the form uses fetch + location.reload())
    logged_in.wait_for_load_state("networkidle", timeout=15_000)
    # At least one export row should now appear in history
    expect(logged_in.locator("table tbody tr").first).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_export_status_auto_refreshes(logged_in: Page) -> None:
    logged_in.goto("/exports")
    # Create an export to ensure there's a pending/processing state
    logged_in.locator('select[name="format"]').select_option("csv")
    logged_in.locator('button[type="submit"]', has_text=re.compile(r"Export", re.IGNORECASE)).click()
    logged_in.wait_for_load_state("networkidle", timeout=15_000)

    # If any export is pending/processing, the page should include the auto-reload script
    page_content = logged_in.content()
    # The page either has the reload script (pending export) or shows ready exports
    has_reload_script = "setTimeout" in page_content and "location.reload" in page_content
    has_ready_exports = logged_in.locator("a", has_text=re.compile(r"Download", re.IGNORECASE)).count() > 0
    assert has_reload_script or has_ready_exports


@pytest.mark.e2e
def test_download_ready_export(logged_in: Page) -> None:
    logged_in.goto("/exports")
    # Look for an existing ready export with a Download link
    download_link = logged_in.locator("a", has_text=re.compile(r"Download", re.IGNORECASE)).first
    if download_link.count() == 0:
        # Create an export and wait for it to become ready
        logged_in.locator('select[name="format"]').select_option("csv")
        logged_in.locator('button[type="submit"]', has_text=re.compile(r"Export", re.IGNORECASE)).click()
        logged_in.wait_for_load_state("networkidle", timeout=15_000)
        # Wait up to 60 seconds for the export to become ready (page auto-reloads every 5s)
        download_link = logged_in.locator("a", has_text=re.compile(r"Download", re.IGNORECASE)).first
        download_link.wait_for(timeout=60_000)

    # Trigger download and verify a file is received
    with logged_in.expect_download(timeout=30_000) as dl_info:
        download_link.click()
    download = dl_info.value
    assert download.suggested_filename.endswith((".csv", ".xlsx"))
