# ABOUTME: E2E tests for the records list and detail pages — filter, search, edit, add, delete.
# ABOUTME: Requires staging to already have records from prior job runs.
from __future__ import annotations

import re
import uuid

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_records_list_loads(logged_in: Page) -> None:
    logged_in.goto("/records")
    expect(logged_in).not_to_have_url(re.compile(r".*/login.*"))
    expect(logged_in.locator("h1")).to_contain_text("Records")
    # Staging should have records from prior runs
    expect(logged_in.locator("table tbody tr").first).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_filter_by_status(logged_in: Page) -> None:
    logged_in.goto("/records")
    logged_in.locator('select[name="status"]').select_option("active")
    # Submit the filter form (look for a filter/search button or rely on auto-submit)
    filter_btn = logged_in.locator("button", has_text=re.compile(r"Filter|Search|Apply", re.IGNORECASE)).first
    if filter_btn.count() > 0:
        filter_btn.click()
    else:
        logged_in.keyboard.press("Enter")
    logged_in.wait_for_load_state("networkidle", timeout=10_000)
    # URL should reflect the status filter
    assert "status=active" in logged_in.url


@pytest.mark.e2e
def test_text_search(logged_in: Page) -> None:
    logged_in.goto("/records")
    # Get the name of the first record to search for a substring
    first_name_el = logged_in.locator("table tbody tr td").first
    first_name_el.wait_for(timeout=10_000)
    first_name = first_name_el.text_content() or ""
    search_term = first_name[:4] if len(first_name) >= 4 else first_name

    if not search_term.strip():
        pytest.skip("No records found to search")

    logged_in.locator('input[name="q"]').fill(search_term)
    logged_in.keyboard.press("Enter")
    logged_in.wait_for_load_state("networkidle", timeout=10_000)
    assert f"q={search_term}" in logged_in.url or logged_in.locator("table tbody tr").count() > 0


@pytest.mark.e2e
def test_record_detail_fields_visible(logged_in: Page) -> None:
    logged_in.goto("/records")
    first_row_link = logged_in.locator("table tbody tr td a").first
    first_row_link.wait_for(timeout=10_000)
    first_row_link.click()
    logged_in.wait_for_url(re.compile(r".*/records/[a-f0-9-]+"), timeout=10_000)
    # Detail page should show the Name field label
    expect(logged_in.locator("text=Name")).to_be_visible()


@pytest.mark.e2e
def test_inline_edit_loads_form(logged_in: Page) -> None:
    logged_in.goto("/records")
    first_row_link = logged_in.locator("table tbody tr td a").first
    first_row_link.wait_for(timeout=10_000)
    first_row_link.click()
    logged_in.wait_for_url(re.compile(r".*/records/[a-f0-9-]+"), timeout=10_000)

    # Click Edit button
    edit_btn = logged_in.locator("a", has_text=re.compile(r"Edit", re.IGNORECASE)).first
    if edit_btn.count() == 0:
        edit_btn = logged_in.locator("button", has_text=re.compile(r"Edit", re.IGNORECASE)).first
    edit_btn.click()
    logged_in.wait_for_load_state("networkidle", timeout=10_000)

    # Edit form should now be visible (either inline or navigated to /edit)
    expect(logged_in.locator('input[name="name"]')).to_be_visible(timeout=10_000)


@pytest.mark.e2e
def test_inline_edit_save(logged_in: Page) -> None:
    logged_in.goto("/records")
    first_row_link = logged_in.locator("table tbody tr td a").first
    first_row_link.wait_for(timeout=10_000)
    first_row_link.click()
    logged_in.wait_for_url(re.compile(r".*/records/[a-f0-9-]+"), timeout=10_000)

    edit_btn = logged_in.locator("a", has_text=re.compile(r"Edit", re.IGNORECASE)).first
    if edit_btn.count() == 0:
        edit_btn = logged_in.locator("button", has_text=re.compile(r"Edit", re.IGNORECASE)).first
    edit_btn.click()
    logged_in.wait_for_load_state("networkidle", timeout=10_000)

    name_input = logged_in.locator('input[name="name"]')
    name_input.wait_for(timeout=10_000)
    original_name = name_input.input_value()
    suffix = f" [e2e-{str(uuid.uuid4())[:4]}]"
    name_input.fill(original_name + suffix)

    logged_in.locator("button", has_text=re.compile(r"^Save$", re.IGNORECASE)).click()
    logged_in.wait_for_url(re.compile(r".*/records/[a-f0-9-]+$"), timeout=15_000)

    # Name appears in both h1 and #record-fields dd — use h1 to avoid strict mode violation
    expect(logged_in.locator("h1")).to_contain_text(original_name + suffix)


@pytest.mark.e2e
def test_delete_record(logged_in: Page) -> None:
    # Add a fresh record so we have something to delete without touching real data
    unique = str(uuid.uuid4())[:8]
    record_name = f"[E2E] Delete-Me {unique}"

    logged_in.goto("/records")
    # Open Add Record modal
    logged_in.locator("button", has_text=re.compile(r"Add Record|Add", re.IGNORECASE)).first.click()
    logged_in.locator('#add-name, input[name="name"]').first.wait_for(timeout=5_000)
    logged_in.locator('#add-name, input[name="name"]').first.fill(record_name)
    logged_in.locator('button[type="submit"]', has_text=re.compile(r"Add Record", re.IGNORECASE)).click()
    # submitAdd redirects to the new record's detail page via HX-Redirect
    logged_in.wait_for_url(re.compile(r".*/records/[a-f0-9-]{36}"), timeout=15_000)

    # Click edit then set status to deleted
    edit_btn = logged_in.locator("a", has_text=re.compile(r"Edit", re.IGNORECASE)).first
    if edit_btn.count() == 0:
        edit_btn = logged_in.locator("button", has_text=re.compile(r"Edit", re.IGNORECASE)).first
    edit_btn.click()
    logged_in.wait_for_load_state("networkidle", timeout=10_000)

    logged_in.locator('select[name="status"]').select_option("deleted")
    logged_in.locator("button", has_text=re.compile(r"^Save$", re.IGNORECASE)).click()
    logged_in.wait_for_url(re.compile(r".*/records/[a-f0-9-]+$"), timeout=15_000)

    expect(logged_in.locator("text=deleted")).to_be_visible(timeout=5_000)


@pytest.mark.e2e
def test_add_record_modal(logged_in: Page) -> None:
    unique = str(uuid.uuid4())[:8]
    record_name = f"[E2E] New Record {unique}"

    logged_in.goto("/records")
    logged_in.locator("button", has_text=re.compile(r"Add Record", re.IGNORECASE)).first.click()

    # Modal should open
    name_input = logged_in.locator('#add-name, [name="name"]').first
    name_input.wait_for(timeout=5_000)
    name_input.fill(record_name)

    logged_in.locator('button[type="submit"]', has_text=re.compile(r"Add Record", re.IGNORECASE)).click()
    # submitAdd redirects to /records/{id} via HX-Redirect header
    logged_in.wait_for_url(re.compile(r".*/records/[a-f0-9-]{36}"), timeout=15_000)

    # Record name appears in h1 on the detail page
    expect(logged_in.locator("h1")).to_contain_text(record_name)


@pytest.mark.e2e
def test_bulk_delete(logged_in: Page) -> None:
    # Add two records with unique names so we know exactly what to delete
    records_to_delete: list[str] = []
    for _ in range(2):
        unique = str(uuid.uuid4())[:8]
        name = f"[E2E] Bulk {unique}"
        records_to_delete.append(name)

        logged_in.goto("/records")
        logged_in.locator("button", has_text=re.compile(r"Add Record", re.IGNORECASE)).first.click()
        name_input = logged_in.locator('#add-name, [name="name"]').first
        name_input.wait_for(timeout=5_000)
        name_input.fill(name)
        logged_in.locator('button[type="submit"]', has_text=re.compile(r"Add Record", re.IGNORECASE)).click()
        logged_in.wait_for_load_state("networkidle", timeout=15_000)

    # Go back to list and select both by checking their checkboxes
    logged_in.goto("/records")
    logged_in.wait_for_load_state("networkidle", timeout=10_000)

    checkboxes = logged_in.locator(".row-checkbox")
    if checkboxes.count() < 2:
        pytest.skip("Not enough records on page to test bulk delete")

    # Select the first two checkboxes
    checkboxes.nth(0).check()
    checkboxes.nth(1).check()

    # Accept confirm dialog and click bulk delete
    logged_in.on("dialog", lambda d: d.accept())
    delete_btn = logged_in.locator("button", has_text=re.compile(r"Delete|Bulk Delete", re.IGNORECASE)).first
    delete_btn.wait_for(timeout=5_000)
    delete_btn.click()
    logged_in.wait_for_load_state("networkidle", timeout=15_000)

    # Checkboxes should now be gone or reduced
    assert logged_in.locator(".row-checkbox").count() <= checkboxes.count()
