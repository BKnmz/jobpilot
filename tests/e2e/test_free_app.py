"""Browser end-to-end tests for the free JobPilot app (real Streamlit, real browser, demo AI)."""
import json
from pathlib import Path

import pytest
from docx import Document
from playwright.sync_api import expect

from e2e_helpers import click, open_app, settle, tab, text_of, wait_text

pytestmark = pytest.mark.e2e

TABS = ["Searches", "Scrape", "Review & Score", "Approved", "Stats", "Settings"]


def panel(page):
    return page.get_by_role("tabpanel")


def set_status(app, job_id: int, status: str, score: int | None = None) -> None:
    app.execute("UPDATE jobs SET status=?, match_score=?, matched_keywords=?, missing_keywords=? WHERE id=?",
                (status, score, json.dumps(["SAP", "Power BI"]), json.dumps(["Kubernetes"]), job_id))


def select_option(page, label: str, option: str, scope=None) -> None:
    """Pick an option in a Streamlit selectbox by its label."""
    scope = scope or page
    scope.get_by_label(label, exact=True).first.click()
    page.get_by_role("option", name=option, exact=True).click()
    settle(page)


def read_docx_text(path) -> str:
    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


# 1 ---------------------------------------------------------------------------

def test_app_loads_with_six_tabs(app, page):
    open_app(page, app.url)
    labels = [t.strip() for t in page.get_by_role("tab").all_inner_texts()]
    assert len(labels) == 6, labels
    for expected in TABS:
        assert any(expected in label for label in labels), (expected, labels)
    assert page.locator(".brand-badge").inner_text().strip() == "Free"
    kofi = page.locator('.jp-footer a[href="https://ko-fi.com/consultbknmz"]')
    assert kofi.count() == 1
    # header counters reflect the 3 seeded jobs
    assert "NEW" in page.locator(".stat-row").inner_text().upper()
    assert page.locator(".stat-pill").first.inner_text().split()[0] == "3"


# 2 ---------------------------------------------------------------------------

def test_settings_provider_contact_profile_languages(app, page):
    open_app(page, app.url)
    tab(page, "Settings")
    body = text_of(page)
    assert "Demo (offline)" in body
    assert "key is set" in body                       # demo provider is considered ready
    assert "CV found" in body                         # master_cv.md copied into the temp home

    # contact details
    p = panel(page)
    p.get_by_label("Full name").fill("Sam Example")
    p.get_by_label("Email").fill("sam.example@example.com")
    p.get_by_label("Phone").fill("+49 160 111 2222")
    click(page, "Save contact details")
    saved = {r["field_name"]: r["field_value"] for r in app.query("SELECT * FROM profile")}
    assert saved["full_name"] == "Sam Example" and saved["email"] == "sam.example@example.com"
    open_app(page, app.url)
    tab(page, "Settings")
    expect(panel(page).get_by_label("Full name")).to_have_value("Sam Example")

    # add a role profile
    expander = page.locator('[data-testid="stExpander"]').filter(has_text="Add a role profile")
    expander.locator("summary").click()
    expander.get_by_label("Name", exact=True).fill("Demand Planner")
    expander.get_by_role("textbox", name="Keywords that identify this kind of job").fill("SQL, dashboards")
    expander.get_by_label("CV headline").fill("Demand Planner | Retail")
    click(page, "Add role profile")
    rows = app.query("SELECT name FROM role_profiles ORDER BY id")
    assert [r["name"] for r in rows][-1] == "Demand Planner"
    assert len(rows) == 3
    expect(page.locator("summary").filter(has_text="Demand Planner")).to_have_count(1)

    # CV languages: drop Turkish
    remove = panel(page).get_by_role("button", name="Remove Türkçe")
    expect(remove).to_have_count(1)
    remove.click()
    settle(page)
    assert app.query("SELECT value FROM settings WHERE key='cv_languages'")[0]["value"] == "en,de"


# 3 ---------------------------------------------------------------------------

def _add_search(page, label: str, url: str, platform: str | None = None) -> None:
    p = panel(page)
    p.get_by_label("Label", exact=True).fill(label)
    if platform:
        select_option(page, "Platform", platform, scope=p)
    p.get_by_label("Search URL").fill(url)
    click(page, "Add Search")


def test_searches_add_validate_toggle_delete(app, page):
    open_app(page, app.url)
    tab(page, "Searches")
    assert "No searches configured yet" in text_of(page)

    _add_search(page, "Demo PO Hamburg", "https://example.com/search?q=po", platform="stepstone")
    wait_text(page, "Demo PO Hamburg")
    row = app.query("SELECT * FROM searches")[0]
    assert row["platform"] == "stepstone" and row["active"] == 1 and row["language"] == "en"

    # invalid URL shows an error and does not add anything
    _add_search(page, "Broken", "ftp://x")
    wait_text(page, "The URL must start with http")
    assert len(app.query("SELECT * FROM searches")) == 1

    # toggle off and on
    click(page, "✅ On")
    assert app.query("SELECT active FROM searches")[0]["active"] == 0
    expect(page.get_by_role("button", name="⏸ Off")).to_be_visible()
    click(page, "⏸ Off")
    assert app.query("SELECT active FROM searches")[0]["active"] == 1

    # delete
    click(page, "🗑")
    assert app.query("SELECT * FROM searches") == []
    wait_text(page, "No searches configured yet")


def test_searches_form_keeps_input_after_validation_error(app, page):
    """A failed submit should not wipe what the user typed."""
    open_app(page, app.url)
    tab(page, "Searches")
    _add_search(page, "Keep my text", "ftp://x")
    wait_text(page, "The URL must start with http")
    expect(panel(page).get_by_label("Label", exact=True)).to_have_value("Keep my text")


def test_searches_success_message_is_visible(app, page):
    """After adding a search the user should see a confirmation, not only a changed list."""
    open_app(page, app.url)
    tab(page, "Searches")
    _add_search(page, "Confirm me", "https://example.com/search?q=1")
    wait_text(page, "Confirm me")
    assert "Added: Confirm me" in text_of(page)


# 4 ---------------------------------------------------------------------------

def test_review_score_approve_reject(app, page):
    open_app(page, app.url)
    tab(page, "Review & Score")
    assert "3 unscored job(s)" in text_of(page)
    click(page, "Score 3 job(s) with Demo (offline)", timeout=120000)

    wait_text(page, "3 scored job(s) awaiting your decision")
    assert [r["match_score"] for r in app.query("SELECT match_score FROM jobs")] == [7, 7, 7]
    badges = page.locator(".score-badge")
    expect(badges).to_have_count(3)
    assert badges.first.inner_text() == "7"
    expect(page.locator(".kw-hit").first).to_contain_text("SAP")
    expect(page.locator(".kw-miss").first).to_contain_text("Kubernetes")
    page.get_by_text("Last scoring run").click()
    assert "Scored 3/3 jobs (0 errors)" in text_of(page)

    click(page, "✅ Approve")
    click(page, "❌ Reject")
    statuses = sorted(r["status"] for r in app.query("SELECT status FROM jobs"))
    assert statuses == ["approved", "rejected", "scored"]
    wait_text(page, "1 scored job(s) awaiting your decision")


# 5 ---------------------------------------------------------------------------

def _approve_two(app):
    set_status(app, 1, "approved", 7)
    set_status(app, 2, "approved", 7)


def test_approved_build_base_cv_tailor_download_apply(app_factory, page, tmp_path):
    app = app_factory(prepare=_approve_two)
    open_app(page, app.url)
    tab(page, "Approved")
    wait_text(page, "2 approved job(s)")
    assert "✗ EN" in text_of(page)

    click(page, "Build 2 base CV(s) with Demo (offline)", timeout=120000)
    wait_text(page, "Last base CV build")
    page.get_by_text("Last base CV build").click()
    assert "Built 2/2 base CVs" in text_of(page)
    expect(page.get_by_text("✓ EN").first).to_be_visible()
    assert len(app.query("SELECT * FROM role_cvs")) == 2

    # tailor job 1 (EN)
    cards = page.get_by_role("button", name="Tailor CV for this job")
    cards.first.click()
    settle(page, 120000)
    page.get_by_text("Last tailoring run").click()
    assert "Saved to cv_outputs/" in text_of(page)
    expect(page.locator("strong", has_text="Tailored").first).to_be_visible(timeout=60000)
    with page.expect_download() as dl:
        page.get_by_role("button", name="Download .docx").first.click()
    out = tmp_path / dl.value.suggested_filename
    dl.value.save_as(out)
    assert out.name.endswith("_tailored.docx")
    assert "Alex Demo" in read_docx_text(out)
    assert "Operations Analyst" in read_docx_text(out)

    click(page, "Mark as applied")
    wait_text(page, "1 approved job(s)")
    assert sorted(r["status"] for r in app.query("SELECT status FROM jobs WHERE id IN (1,2)")) == \
        ["applied", "approved"]


def test_approved_german_tailor_uses_german_headings(app_factory, page, tmp_path):
    app = app_factory(prepare=lambda a: set_status(a, 2, "approved", 7))
    open_app(page, app.url)
    tab(page, "Approved")
    wait_text(page, "1 approved job(s)")
    click(page, "Tailor CV for this job", timeout=120000)
    expect(page.locator("strong", has_text="Tailored").first).to_be_visible(timeout=60000)
    with page.expect_download() as dl:
        page.get_by_role("button", name="Download .docx").first.click()
    out = tmp_path / dl.value.suggested_filename
    dl.value.save_as(out)
    text = read_docx_text(out)
    assert "Berufserfahrung" in text and "Alex Demo" in text


# 6 ---------------------------------------------------------------------------

def test_stats_counts_and_danger_zone(app_factory, page):
    def prepare(a):
        set_status(a, 1, "scored", 7)
        set_status(a, 2, "rejected", 3)

    app = app_factory(prepare=prepare)
    open_app(page, app.url)
    tab(page, "Stats")
    p = panel(page)
    expect(p.get_by_text("Total jobs in DB")).to_be_visible()
    metrics = p.locator('[data-testid="stMetric"]').all_inner_texts()
    joined = " | ".join(" ".join(m.split()) for m in metrics)
    assert "Total jobs in DB 3" in joined
    assert "Scored 1" in joined and "Rejected 1" in joined and "New 1" in joined

    expect(p.get_by_role("button", name="Clear All Jobs")).to_have_count(0)
    p.get_by_text("I want to delete ALL jobs from the database").click()
    settle(page)
    expect(p.get_by_role("button", name="Clear All Jobs")).to_be_visible()
    click(page, "Clear All Jobs")
    assert app.query("SELECT * FROM jobs") == []
    wait_text(page, "No jobs in the database yet")
    tab(page, "Review & Score")
    assert "No scored jobs yet" in text_of(page)


# 7 ---------------------------------------------------------------------------

XSS_TITLE = "<img src=x onerror=alert(1)>Dev"


def _seed_xss(app):
    app.execute(
        "INSERT INTO jobs (title, company, location, jd_text, source_url, date_found, match_score, status,"
        " role_profile, language, matched_keywords, missing_keywords, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (XSS_TITLE, "<b>bold</b>Corp", "<i>Nowhere</i>", "text", "https://example.com/xss", "2026-11-01", 8,
         "scored", 2, "en", json.dumps(["<img src=x onerror=alert(2)>kw"]),
         json.dumps(["<script>alert(3)</script>"]), "<img src=y onerror=alert(4)>note"))
    xss_id = app.query("SELECT id FROM jobs WHERE source_url='https://example.com/xss'")[0]["id"]
    app.execute("INSERT INTO jobs (title, company, location, jd_text, source_url, date_found, match_score,"
                " status, role_profile, language) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (XSS_TITLE + " approved", "<u>Corp2</u>", "x", "t", "https://example.com/xss2",
                 "2026-11-01", 8, "approved", 2, "en"))
    app.execute("INSERT INTO searches (platform, role_profile, search_url, label, language, active) "
                "VALUES ('linkedin', 2, 'https://example.com/s', ?, 'en', 1)", (XSS_TITLE + " search",))
    return xss_id


def test_html_in_scraped_text_is_escaped(app_factory, page):
    app = app_factory(prepare=_seed_xss)
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    open_app(page, app.url)

    for name in ("Searches", "Review & Score", "Approved"):
        tab(page, name)
        body = text_of(page)
        assert "<img src=x onerror=alert(1)>Dev" in body, f"{name}: title is not shown literally"
        assert page.locator('img[src="x"], img[src="y"]').count() == 0, name
        assert page.locator("script:not([src])", has_text="alert").count() == 0, name
    tab(page, "Review & Score")
    assert "<b>bold</b>Corp" in text_of(page)
    assert page.locator("strong", has_text="Corp").count() <= 1
    assert page.locator("u", has_text="Corp2").count() == 0
    assert "<script>alert(3)</script>" in text_of(page)
    page.wait_for_timeout(500)
    assert dialogs == [], f"a script ran in the page: {dialogs}"


def test_settings_save_confirmation_is_visible(app, page):
    """After 'Save contact details' the user should see a confirmation, not a silent reload."""
    open_app(page, app.url)
    tab(page, "Settings")
    panel(page).get_by_label("Full name").fill("Sam Example")
    click(page, "Save contact details")
    assert "Saved." in text_of(page)


# 8 ---------------------------------------------------------------------------

def test_settings_suggest_role_profiles_from_cv(app_factory, page):
    """With no role profiles, the user can get suggestions from the CV, edit, save and then use them."""
    app = app_factory(profiles=False)
    assert app.query("SELECT * FROM role_profiles") == []
    open_app(page, app.url)

    # Searches and Approved tell the user what is missing instead of showing an empty dropdown
    tab(page, "Searches")
    assert "Create your role profiles first: Settings" in text_of(page)

    tab(page, "Settings")
    assert "No role profiles yet" in text_of(page)
    click(page, "Suggest role profiles from my CV")
    keep = panel(page).get_by_label("Use this profile")
    expect(keep).to_have_count(2)
    names = panel(page).get_by_role("textbox", name="Name", exact=True)
    expect(names.first).to_have_value("Supply Chain Analyst")
    names.first.fill("Supply Chain Analyst (edited)")
    panel(page).get_by_text("Use this profile").nth(1).click()          # drop the second suggestion
    expect(keep.nth(1)).not_to_be_checked()
    click(page, "Save selected profiles")
    assert [r["name"] for r in app.query("SELECT name FROM role_profiles")] == ["Supply Chain Analyst (edited)"]
    wait_text(page, "Saved 1 role profile(s)")
    expect(page.locator("summary").filter(has_text="Supply Chain Analyst (edited)")).to_have_count(1)

    tab(page, "Searches")
    panel(page).get_by_label("Role profile", exact=True).first.click()
    expect(page.get_by_role("option", name="Supply Chain Analyst (edited)")).to_be_visible()
