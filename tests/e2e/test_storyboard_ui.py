"""The workshop storyboard in a real browser, across roles. Doubles as the automated dry run.

    E2E_BASE_URL=http://localhost:5174 uv run --env-file .env pytest tests/e2e -q
    E2E_BASE_URL=https://mastercard-tawny.vercel.app uv run --env-file .env pytest tests/e2e -q

Skipped unless E2E_BASE_URL is set. Uses the locally installed Chrome; resets the demo first.
"""
import os
import re
import tempfile

import pytest

BASE = os.environ.get("E2E_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set E2E_BASE_URL to run the browser storyboard")
SHOTS = tempfile.mkdtemp(prefix="mc-e2e-")


@pytest.fixture(scope="module")
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
        pg = ctx.new_page()
        pg.errors = []
        pg.on("pageerror", lambda e: pg.errors.append(str(e)))
        pg.goto(BASE, wait_until="networkidle")
        if pg.get_by_placeholder(re.compile("passcode", re.I)).count() or pg.locator("form.login").count():
            pg.locator("form.login input").fill(os.environ["DEMO_PASSWORD"])
            pg.locator("form.login button").click()
            pg.wait_for_load_state("networkidle")
        yield pg
        browser.close()


def sign_in(pg, name):
    pg.wait_for_selector(".signin, button.user")
    if pg.locator(".signin").count() == 0:
        pg.locator("button.user").click()
    pg.wait_for_selector(".person-card")
    pg.locator(".person-card", has_text=name).click()
    pg.wait_for_selector("button.user")
    assert name in pg.locator("button.user").inner_text()


def api(pg, path):
    return pg.request.get(f"{BASE}/api/{path}").json()


def toast(pg, text, timeout=60_000):
    try:
        pg.wait_for_selector(f".toast:has-text('{text}')", timeout=timeout)
    except Exception:
        pg.screenshot(path=f"{SHOTS}/missing-toast.png")
        raise AssertionError(f"No '{text}' toast; on screen: {pg.locator('.toast').all_inner_texts()} "
                             f"(screenshot {SHOTS}/missing-toast.png)") from None


def test_01_reset_and_morning_mailbox(page):
    sign_in(page, "Alex Rivera")
    page.once("dialog", lambda d: d.accept())
    page.get_by_role("button", name="Reset demo").click()
    toast(page, "Demo reset")
    page.goto(f"{BASE}/", wait_until="networkidle")
    assert "This morning" in page.inner_text("main")
    page.locator("[data-tour=run-mailbox]").click()
    toast(page, "Agent worked", timeout=180_000)
    assert sum(1 for r in api(page, "queue") if r["status"] == "NEW") == 0


def test_02_dell_was_really_run_and_is_recorded(page):
    dell = api(page, "meta")["storyboard"]["dell"]
    page.goto(f"{BASE}/invoice/{dell}", wait_until="networkidle")
    assert "Worked by the mailbox run" in page.inner_text("[data-tour=run-line]")
    page.get_by_role("button", name=re.compile("^Agent console")).click()
    assert page.locator(".tool-call").count() >= 25
    page.get_by_role("button", name="Recommendation").click()
    assert "1540" in page.inner_text("[data-tour=recommendation]")
    assert "OR-9918274" in page.inner_text("[data-tour=receipt]")
    page.get_by_role("button", name="Accept and send for approval").click()
    toast(page, "Accepted")


def test_03_only_the_next_approver_can_approve(page):
    dell = api(page, "meta")["storyboard"]["dell"]
    nxt = api(page, f"invoices/{dell}")["decision"]["chain"][0]
    people = {p["id"]: p["name"] for p in api(page, "people")}
    sign_in(page, "Kevin Brandt")
    page.goto(f"{BASE}/invoice/{dell}", wait_until="networkidle")
    assert page.locator("[data-tour=approval] button", has_text="Approve").count() == 0
    sign_in(page, people[nxt])
    page.goto(f"{BASE}/invoice/{dell}", wait_until="networkidle")
    page.locator("[data-tour=approval] button", has_text="Approve").click()
    toast(page, "Approved")


def test_04_laptop_journal_prepared_approved_and_posted(page):
    case = next(c for c in api(page, "cases") if "Laptop refresh" in (c["finding"].get("description") or ""))
    sign_in(page, "Ben Keller")
    page.goto(f"{BASE}/close?case={case['case_id']}", wait_until="networkidle")
    page.get_by_role("button", name="Prepare and submit").click()
    toast(page, "Prepared")
    sign_in(page, "Samuel Whitaker")
    page.goto(f"{BASE}/close?case={case['case_id']}", wait_until="networkidle")
    page.locator(".drawer").get_by_role("button", name="Approve").click()
    toast(page, "Approved")
    with page.expect_popup():
        page.locator("[data-tour=export-gl]").click()
    toast(page, "corrections exported")
    assert api(page, f"cases/{case['case_id']}")["status"] == "Exported"


def test_05_policy_change_marks_earlier_runs_stale(page):
    sign_in(page, "Tessa Mendes")
    page.goto(f"{BASE}/policies", wait_until="networkidle")
    page.locator("input[placeholder='2.5']").fill("3")
    page.locator(".policy-save textarea").fill("Fewer false holds on seasonal suppliers")
    page.get_by_role("button", name=re.compile("^Save as version")).click()
    toast(page, "Policy version 2")
    tel = api(page, "meta")["storyboard"]["telecoms"]
    page.goto(f"{BASE}/invoice/{tel}", wait_until="networkidle")
    assert "Policy changed to version 2" in page.inner_text(".banner")


def test_06_model_and_architecture_render(page):
    page.goto(f"{BASE}/model", wait_until="networkidle")
    assert "First-time-right" in page.inner_text("[data-tour=model-kpis]")
    page.goto(f"{BASE}/architecture", wait_until="networkidle")
    page.get_by_role("tab", name="Approval routing (DoA, SoD, delegates)").click()
    page.get_by_role("button", name="Next").click()
    assert "1/" in page.inner_text(".seq-step")
    page.screenshot(path=f"{SHOTS}/architecture.png")


def test_07_no_page_errors(page):
    assert page.errors == [], page.errors
