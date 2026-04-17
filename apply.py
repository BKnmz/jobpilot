"""
apply.py — Semi-automated job application via Playwright.

Usage:
    python apply.py --job-id <ID>

Flow:
    1. Load job + profile from jobs.db
    2. Detect platform from source_url (LinkedIn / Stepstone / unknown)
    3. Open headed browser, navigate to job URL
    4. Auto-fill standard fields (name, email, phone, upload CV)
    5. STOP before submit — wait for user confirmation
    6. After Enter: click submit, update DB status to 'applied'

Rules:
    - Headed mode only — never headless
    - No AI calls
    - Always stops before final submit
    - If cv_path is missing: exit with instructions
"""

import argparse
import os
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

from db import init_db, get_profile, update_status, _connect


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_job(job_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

def _detect_platform(url: str) -> str:
    url = url.lower()
    if "linkedin.com" in url:
        return "linkedin"
    if "stepstone.de" in url:
        return "stepstone"
    return "unknown"


# ---------------------------------------------------------------------------
# LinkedIn Easy Apply
# ---------------------------------------------------------------------------

def _apply_linkedin(page, job: dict, profile: dict, cv_path: str):
    print(f"[LinkedIn] Opening job page...")
    page.goto(job["source_url"], wait_until="domcontentloaded", timeout=30_000)
    time.sleep(2)

    # Click Easy Apply button
    try:
        easy_apply = page.locator(
            "button:has-text('Easy Apply'), "
            "button.jobs-apply-button:has-text('Apply')"
        ).first
        easy_apply.click(timeout=8_000)
        time.sleep(2)
        print("  Clicked Easy Apply.")
    except PWTimeout:
        print("  Could not find Easy Apply button — the job may require external application.")
        print(f"  URL: {job['source_url']}")
        return False

    # Fill contact fields if present
    _fill_field(page, "input[id*='name'], input[name*='name'], input[aria-label*='name' i]",
                profile.get("full_name", ""))
    _fill_field(page, "input[id*='email'], input[name*='email'], input[type='email']",
                profile.get("email", ""))
    _fill_field(page, "input[id*='phone'], input[name*='phone'], input[type='tel']",
                profile.get("phone", ""))

    # Upload CV
    _upload_cv(page, cv_path,
               "input[type='file'][accept*='pdf'], input[type='file'][accept*='doc']")

    print("  Form filled.")
    return True


# ---------------------------------------------------------------------------
# Stepstone application
# ---------------------------------------------------------------------------

def _apply_stepstone(page, job: dict, profile: dict, cv_path: str):
    print(f"[Stepstone] Opening job page...")
    page.goto(job["source_url"], wait_until="domcontentloaded", timeout=30_000)
    time.sleep(2)

    # Click apply button
    try:
        apply_btn = page.locator(
            "a:has-text('Jetzt bewerben'), "
            "button:has-text('Jetzt bewerben'), "
            "a:has-text('Apply now'), "
            "button:has-text('Apply now')"
        ).first
        apply_btn.click(timeout=8_000)
        time.sleep(3)
        print("  Clicked apply button.")
    except PWTimeout:
        print("  Could not find apply button — may require manual navigation.")
        print(f"  URL: {job['source_url']}")
        return False

    # Fill fields
    _fill_field(page,
                "input[name*='firstname' i], input[id*='firstname' i], input[placeholder*='Vorname' i]",
                _first_name(profile.get("full_name", "")))
    _fill_field(page,
                "input[name*='lastname' i], input[id*='lastname' i], input[placeholder*='Nachname' i]",
                _last_name(profile.get("full_name", "")))
    _fill_field(page,
                "input[type='email'], input[name*='email' i], input[id*='email' i]",
                profile.get("email", ""))
    _fill_field(page,
                "input[type='tel'], input[name*='phone' i], input[name*='telefon' i]",
                profile.get("phone", ""))

    # Upload CV
    _upload_cv(page, cv_path, "input[type='file']")

    print("  Form filled.")
    return True


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _fill_field(page, selector: str, value: str):
    if not value:
        return
    try:
        el = page.locator(selector).first
        if el.count() and el.is_visible(timeout=3_000):
            el.fill("")
            el.type(value, delay=40)
    except Exception:
        pass  # Field not present on this form — skip silently


def _upload_cv(page, cv_path: str, selector: str):
    if not cv_path or not os.path.isfile(cv_path):
        print(f"  Warning: CV file not found at '{cv_path}' — skipping upload.")
        return
    try:
        file_input = page.locator(selector).first
        if file_input.count():
            file_input.set_input_files(cv_path)
            time.sleep(1)
            print(f"  CV uploaded: {os.path.basename(cv_path)}")
    except Exception as e:
        print(f"  Warning: CV upload failed — {e}")


def _first_name(full_name: str) -> str:
    parts = full_name.strip().split()
    return parts[0] if parts else ""


def _last_name(full_name: str) -> str:
    parts = full_name.strip().split()
    return " ".join(parts[1:]) if len(parts) > 1 else ""


def _find_submit_button(page):
    """Return the submit button locator without clicking it."""
    candidates = [
        "button[type='submit']:has-text('Submit')",
        "button[type='submit']:has-text('Absenden')",
        "button[type='submit']:has-text('Send')",
        "button:has-text('Submit application')",
        "button:has-text('Bewerbung absenden')",
        "button[type='submit']",
    ]
    for sel in candidates:
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible(timeout=2_000):
                return loc
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Semi-automated job application via Playwright.")
    parser.add_argument("--job-id", type=int, required=True, help="Job ID from jobs.db")
    args = parser.parse_args()

    init_db()

    # Load job
    job = _get_job(args.job_id)
    if not job:
        print(f"Error: No job found with id={args.job_id}")
        sys.exit(1)

    print(f"\nJob: {job['title']} @ {job['company']}")
    print(f"URL: {job['source_url']}")
    print(f"Status: {job['status']}")

    # Check CV
    cv_path = job.get("cv_path", "")
    if not cv_path:
        print("\nNo tailored CV found for this job.")
        print("Run the cv-tailor agent first:")
        print("  use cv-tailor for job id", args.job_id)
        sys.exit(1)

    cv_path = os.path.abspath(cv_path)
    if not os.path.isfile(cv_path):
        print(f"\nCV file not found at: {cv_path}")
        print("Re-run the cv-tailor agent to regenerate it.")
        sys.exit(1)

    # Load profile
    profile = get_profile()
    missing = [k for k, v in profile.items() if not v]
    if missing:
        print(f"\nWarning: Profile fields are empty: {missing}")
        print("Update them with:")
        for field in missing:
            print(f"  sqlite3 jobs.db \"UPDATE profile SET field_value='YOUR_VALUE' WHERE field_name='{field}'\"")
        print()

    # Detect platform
    platform = _detect_platform(job["source_url"] or "")

    if platform == "unknown":
        print(f"\nUnknown platform — opening browser for manual application.")
        print(f"URL: {job['source_url']}")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(job["source_url"], wait_until="domcontentloaded", timeout=30_000)
            print("\nBrowser opened. Complete the application manually.")
            input("Press Enter when done (or Ctrl+C to cancel)...")
            browser.close()

        mark = input("Mark this job as applied? (y/n): ").strip().lower()
        if mark == "y":
            update_status(args.job_id, "applied")
            print(f"Marked as applied: {job['title']} @ {job['company']}")
        sys.exit(0)

    # LinkedIn or Stepstone — use Edge scraper profile (already logged in)
    edge_profile = os.path.join(os.path.dirname(__file__), ".edge_scraper_profile")
    edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    if not os.path.isdir(edge_profile):
        print("Edge scraper profile not found.")
        print("Run the scraper first (Open Browser in the UI) to set up the login.")
        sys.exit(1)

    print(f"\nLaunching Edge with your scraper profile...")
    print(f"Platform: {platform.upper()}")

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=edge_profile,
            executable_path=edge_exe if os.path.isfile(edge_exe) else None,
            headless=False,
            args=["--start-maximized"],
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Fill form
        filled = False
        if platform == "linkedin":
            filled = _apply_linkedin(page, job, profile, cv_path)
        elif platform == "stepstone":
            filled = _apply_stepstone(page, job, profile, cv_path)

        if not filled:
            print("\nCould not auto-fill the form. Complete it manually in the browser.")

        # Locate submit button
        submit_btn = _find_submit_button(page)
        if submit_btn:
            print(f"\nSubmit button located: '{submit_btn.inner_text().strip()}'")
        else:
            print("\nCould not locate submit button automatically — find it manually.")

        # ----------------------------------------------------------------
        # HARD STOP — human reviews before anything is submitted
        # ----------------------------------------------------------------
        print("\n" + "=" * 60)
        print("  REVIEW THE BROWSER WINDOW BEFORE PROCEEDING")
        print("  Check all fields, attachments, and answers.")
        print("=" * 60)
        print("\nPress Enter to SUBMIT  |  Ctrl+C to CANCEL\n")

        try:
            input()
        except KeyboardInterrupt:
            print("\nCancelled. Nothing was submitted.")
            context.close()
            sys.exit(0)

        # Submit
        if submit_btn:
            try:
                submit_btn.click()
                time.sleep(3)
                print("Submitted.")
            except Exception as e:
                print(f"Could not click submit automatically: {e}")
                print("Please click the submit button manually, then close the browser.")
                input("Press Enter when done...")
        else:
            print("Click submit manually, then press Enter here.")
            input()

        context.close()

    # Update DB
    update_status(args.job_id, "applied")
    print(f"\nApplied to: {job['title']} @ {job['company']}")
    print("Status updated to 'applied' in jobs.db")


if __name__ == "__main__":
    main()
