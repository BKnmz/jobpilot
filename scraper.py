"""
scraper.py — Edge-based job scraper using remote debugging (CDP).

Flow:
  1. UI clicks "Open Browser" → python scraper.py --open
     - Launches Edge with remote debugging on port 9222
     - Opens LinkedIn Jobs and Stepstone in tabs
     - User logs in, sets up searches, leaves tabs open

  2. UI clicks "Ready to Scrape" → python scraper.py
     - Connects to the already-running Edge via CDP
     - Scrapes every open tab that looks like a job search results page
     - Inserts new jobs into jobs.db

Usage:
    python scraper.py --open    # open the browser (Step 1)
    python scraper.py           # scrape open tabs (Step 2)
"""

import argparse
import os
import subprocess
import sys
import time

import requests
from playwright.sync_api import sync_playwright

from urllib.parse import urlparse

from db import init_db, insert_job, get_active_searches, get_unopened_searches, mark_searches_opened, _connect

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EDGE_EXE         = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
EDGE_PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".edge_scraper_profile")
DEBUG_PORT       = 9222
CDP_URL          = f"http://localhost:{DEBUG_PORT}"

# Fallback URLs if no searches are configured in DB
FALLBACK_URLS = [
    "https://www.linkedin.com/jobs/search/",
    "https://www.stepstone.de/jobs/",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _match_search(tab_url: str, searches: list) -> dict | None:
    """Find the best matching search record for a tab URL by domain + path prefix."""
    tab = urlparse(tab_url)
    # Pass 1: exact path-prefix match
    for s in searches:
        s_parsed = urlparse(s["search_url"])
        if tab.netloc == s_parsed.netloc and tab.path.startswith(s_parsed.path):
            return s
    # Pass 2: same hostname fallback (first active match wins)
    for s in searches:
        s_parsed = urlparse(s["search_url"])
        if tab.netloc == s_parsed.netloc:
            return s
    return None


def _already_exists(source_url: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM jobs WHERE source_url=?", (source_url,)
        ).fetchone()
    return row is not None


def _is_edge_running() -> bool:
    """Check if Edge is already running with remote debugging on our port."""
    try:
        r = requests.get(f"{CDP_URL}/json/version", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _scroll_and_wait(page, times=3, pause=2.0):
    for _ in range(times):
        page.evaluate("window.scrollBy(0, window.innerHeight)")
        time.sleep(pause)


def _scroll_linkedin_panel(page, max_rounds=25, pause=1.5) -> list[str]:
    """
    Scroll LinkedIn's left job-list panel using mouse wheel (simulates real user scroll)
    and collect all unique /jobs/view/ URLs as they load.
    """
    collected: set[str] = set()

    # Position mouse over the left panel (left quarter of the viewport)
    vp = page.viewport_size or {"width": 1280, "height": 800}
    left_x = max(200, vp["width"] // 4)
    mid_y  = vp["height"] // 2

    # Move mouse to left panel and click once to make sure it has focus
    page.mouse.move(left_x, mid_y)
    page.mouse.click(left_x, mid_y)
    time.sleep(0.5)

    stable_rounds = 0
    for i in range(max_rounds):
        # Collect URLs visible now
        links: list[str] = page.evaluate("""() =>
            [...document.querySelectorAll('a[href*="/jobs/view/"]')]
                .map(a => a.href.split('?')[0])
                .filter(h => /\\/jobs\\/view\\/\\d/.test(h))
        """)
        before = len(collected)
        collected.update(links)
        after = len(collected)
        print(f"  Scroll {i+1}: {after} job URL(s)")

        if after == before:
            stable_rounds += 1
            if stable_rounds >= 3:
                break
        else:
            stable_rounds = 0

        # Scroll the left panel with mouse wheel — 3 wheel ticks per round
        for _ in range(3):
            page.mouse.wheel(0, 500)
            time.sleep(0.3)
        time.sleep(pause)

    return list(collected)


# ---------------------------------------------------------------------------
# Step 1 — Open browser
# ---------------------------------------------------------------------------

def open_browser():
    """Launch Edge with remote debugging and open new (never-opened) search tabs."""
    new_searches = get_unopened_searches()
    if new_searches:
        searches_to_open = new_searches
        print(f"Opening {len(new_searches)} new search URL(s) (never opened before).")
    else:
        all_active = get_active_searches()
        if all_active:
            searches_to_open = all_active
            print(f"All searches have been opened before — opening all {len(all_active)} active search(es).")
        else:
            searches_to_open = []

    if searches_to_open:
        urls_to_open = [s["search_url"] for s in searches_to_open]
    else:
        urls_to_open = FALLBACK_URLS
        print("No searches configured in DB — opening default homepages.")
        print("Add searches in the UI (Searches tab) for role-based scraping.")

    opened_ids = [s["id"] for s in searches_to_open] if searches_to_open else []

    if _is_edge_running():
        print("Edge is already running with remote debugging.")
        print("Opening new tabs in the existing window...")
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(CDP_URL)
                ctx = browser.contexts[0] if browser.contexts else None
                if ctx:
                    for url in urls_to_open:
                        page = ctx.new_page()
                        page.goto(url, wait_until="domcontentloaded", timeout=15_000)
                        print(f"  Opened: {url}")
            if opened_ids:
                mark_searches_opened(opened_ids)
        except Exception as e:
            print(f"Could not open tabs: {e}")
        return

    os.makedirs(EDGE_PROFILE_DIR, exist_ok=True)
    print(f"Launching Edge with remote debugging on port {DEBUG_PORT}...")

    cmd = [
        EDGE_EXE,
        f"--remote-debugging-port={DEBUG_PORT}",
        f"--user-data-dir={EDGE_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
    ] + urls_to_open

    subprocess.Popen(cmd)
    if opened_ids:
        mark_searches_opened(opened_ids)
    print("Edge launched.")
    print()
    print("In the browser:")
    print("  1. Log in to LinkedIn / Stepstone (if prompted)")
    print("  2. Verify filters are set correctly on each tab")
    print("  3. Leave all tabs open")
    print("  4. Go back to the UI and click 'Ready to Scrape'")


# ---------------------------------------------------------------------------
# Step 2 — Scrape open tabs
# ---------------------------------------------------------------------------

def scrape_open_tabs() -> tuple[int, int]:
    """Connect to running Edge and scrape all open job search tabs."""
    if not _is_edge_running():
        print("Edge is not running with remote debugging.")
        print("Click 'Open Browser' first, then set up your searches.")
        return 0, 0

    total_added = total_skipped = 0
    active_searches = get_active_searches()

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        contexts = browser.contexts

        if not contexts:
            print("No browser context found.")
            return 0, 0

        all_pages = []
        for ctx in contexts:
            all_pages.extend(ctx.pages)

        print(f"Found {len(all_pages)} open tab(s).")

        for page in all_pages:
            url = page.url
            print(f"\nTab: {url[:80]}")

            # Find the matching search config for this tab
            search = _match_search(url, active_searches)
            role_profile = search["role_profile"] if search else None
            language = search["language"] if search else None
            if search:
                print(f"  -> Matched search: {search['label']} (profile={role_profile}, lang={language})")

            if ("linkedin.com/jobs/" in url
                    and "/view/" not in url
                    and "/collections/" not in url
                    and "linkedin.com" in url):
                a, s = _scrape_linkedin_tab(page, role_profile=role_profile, language=language)
                total_added += a
                total_skipped += s

            elif "stepstone.de/jobs" in url or "stepstone.de/stellenangebote" in url:
                a, s = _scrape_stepstone_tab(page, role_profile=role_profile, language=language)
                total_added += a
                total_skipped += s

            else:
                print("  Not a job search tab — skipping.")

    return total_added, total_skipped


# ---------------------------------------------------------------------------
# LinkedIn tab scraper
# ---------------------------------------------------------------------------

# All known LinkedIn job card selectors (newest first)
_LI_CARD_SELECTORS = [
    "li[data-occludable-job-id]",
    "li.jobs-search-results__list-item",
    "li[class*='jobs-search-results__list-item']",
    "div[data-view-name='job-card']",
    "div.job-card-container",
    "[data-job-id]",
]

_LI_TITLE_SELECTORS = (
    "a[data-control-name='jobcard_title'], "
    ".job-card-list__title--link, "
    ".job-card-list__title, "
    "a.job-card-container__link, "
    "strong.job-card-search__title"
)

_LI_COMPANY_SELECTORS = (
    ".job-card-container__primary-description, "
    ".job-card-container__company-name, "
    "span[class*='company']"
)

_LI_LOCATION_SELECTORS = (
    "li.job-card-container__metadata-item, "
    ".job-card-container__metadata-item, "
    "li[class*='metadata']"
)

_LI_JD_SELECTORS = (
    "#job-details, "
    ".jobs-description-content__text, "
    ".jobs-box__html-content, "
    ".jobs-description__content, "
    ".job-view-layout, "
    "div[class*='jobs-description']"
)


def _scrape_linkedin_tab(page, role_profile=None, language=None) -> tuple[int, int]:
    """
    Scrape a LinkedIn job search tab.
    Strategy A (fast): cards in DOM — click each to load detail panel, read JD in-place.
    Strategy B (fallback): scroll panel to collect job IDs, visit each page individually.
    """
    print("[LinkedIn] Scraping...")
    added = skipped = 0
    search_url = page.url

    try:
        time.sleep(2)

        # ── Strategy A: find cards already in DOM ──────────────────────────
        cards = []
        for sel in _LI_CARD_SELECTORS:
            cards = page.query_selector_all(sel)
            if cards:
                print(f"  Strategy A: {len(cards)} cards via '{sel}'")
                break

        if cards:
            # Scroll to load more cards first
            _scroll_linkedin_panel(page, max_rounds=15, pause=1.2)
            # Re-query after scrolling
            for sel in _LI_CARD_SELECTORS:
                more = page.query_selector_all(sel)
                if more:
                    cards = more
                    break
            print(f"  After scroll: {len(cards)} cards")

            for card in cards:
                try:
                    # Extract job ID → build canonical /jobs/view/ URL
                    job_id = (
                        card.get_attribute("data-occludable-job-id")
                        or card.get_attribute("data-job-id")
                        or ""
                    )
                    if job_id:
                        job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
                    else:
                        link_el = card.query_selector("a[href*='/jobs/view/']")
                        if not link_el:
                            skipped += 1
                            continue
                        job_url = link_el.get_attribute("href").split("?")[0]

                    if _already_exists(job_url):
                        skipped += 1
                        continue

                    # Click card → wait for right panel to load
                    card.scroll_into_view_if_needed()
                    card.click()
                    time.sleep(2.0)

                    # Read all fields from the right detail panel (works regardless of obfuscated card CSS)
                    title = ""
                    for sel in [
                        "h2.job-details-jobs-unified-top-card__job-title",
                        "h1.job-details-jobs-unified-top-card__job-title",
                        "h1[class*='job-title']", "h2[class*='job-title']",
                        ".jobs-details-top-card__job-title",
                        "h1", "h2",
                    ]:
                        el = page.query_selector(sel)
                        if el:
                            t = el.inner_text().strip().splitlines()[0]
                            if t:
                                title = t
                                break
                    if not title:
                        skipped += 1
                        continue

                    company = ""
                    for sel in [
                        ".job-details-jobs-unified-top-card__company-name a",
                        ".jobs-unified-top-card__company-name a",
                        "a[class*='company-name']",
                        ".job-details-jobs-unified-top-card__company-name",
                    ]:
                        el = page.query_selector(sel)
                        if el:
                            company = el.inner_text().strip().splitlines()[0]
                            break

                    location = ""
                    for sel in [
                        ".job-details-jobs-unified-top-card__bullet",
                        ".jobs-unified-top-card__bullet",
                        "span[class*='bullet']",
                        ".job-details-jobs-unified-top-card__tertiary-description",
                    ]:
                        el = page.query_selector(sel)
                        if el:
                            location = el.inner_text().strip().splitlines()[0]
                            break

                    jd_el = page.query_selector(_LI_JD_SELECTORS)
                    jd_text = jd_el.inner_text().strip() if jd_el else ""

                    insert_job(title, company, location, jd_text, job_url,
                               role_profile=role_profile, language=language)
                    added += 1
                    print(f"  + {title} @ {company}")

                except Exception as e:
                    print(f"  Warning: skipped card — {e}")

        else:
            # ── Strategy B: scroll to collect job IDs via data-occludable-job-id ──
            print("  Strategy B: collecting job IDs via scroll...")
            job_ids: set[str] = set()

            vp = page.viewport_size or {"width": 1280, "height": 800}
            lx, ly = max(200, vp["width"] // 4), vp["height"] // 2
            page.mouse.move(lx, ly)
            page.mouse.click(lx, ly)
            time.sleep(0.5)

            for i in range(25):
                ids = page.evaluate("""() => {
                    const els = document.querySelectorAll('[data-occludable-job-id],[data-job-id]');
                    return [...new Set([...els].map(e =>
                        e.getAttribute('data-occludable-job-id') ||
                        e.getAttribute('data-job-id')
                    ).filter(Boolean))];
                }""")
                before = len(job_ids)
                job_ids.update(ids)
                print(f"  Scroll {i+1}: {len(job_ids)} job ID(s)")
                for _ in range(3):
                    page.mouse.wheel(0, 500)
                    time.sleep(0.3)
                time.sleep(1.2)
                if len(job_ids) == before and i > 3:
                    break

            print(f"  Collected {len(job_ids)} unique job ID(s)")
            for jid in job_ids:
                job_url = f"https://www.linkedin.com/jobs/view/{jid}/"
                try:
                    if _already_exists(job_url):
                        skipped += 1
                        continue
                    page.goto(job_url, wait_until="domcontentloaded", timeout=25_000)
                    time.sleep(1.5)
                    title_el = page.query_selector("h1")
                    title = title_el.inner_text().strip().splitlines()[0] if title_el else ""
                    if not title:
                        skipped += 1
                        continue
                    company_el = page.query_selector(
                        ".job-details-jobs-unified-top-card__company-name a, "
                        "a[class*='company']"
                    )
                    company = company_el.inner_text().strip().splitlines()[0] if company_el else ""
                    loc_el = page.query_selector(".job-details-jobs-unified-top-card__bullet")
                    location = loc_el.inner_text().strip().splitlines()[0] if loc_el else ""
                    jd_el = page.query_selector(_LI_JD_SELECTORS)
                    jd_text = jd_el.inner_text().strip() if jd_el else ""
                    insert_job(title, company, location, jd_text, job_url,
                               role_profile=role_profile, language=language)
                    added += 1
                    print(f"  + {title} @ {company}")
                except Exception as e:
                    print(f"  Warning: {e}")
            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=15_000)
            except Exception:
                pass

    except Exception as e:
        print(f"  Error: {e}")

    print(f"  {added} added, {skipped} skipped")
    return added, skipped


# ---------------------------------------------------------------------------
# Stepstone tab scraper
# ---------------------------------------------------------------------------

def _scrape_stepstone_tab(page, role_profile=None, language=None) -> tuple[int, int]:
    print("[Stepstone] Scraping...")
    added = skipped = 0

    try:
        _scroll_and_wait(page, times=3, pause=2)

        cards = page.query_selector_all("article[data-at='job-item']")
        if not cards:
            cards = page.query_selector_all("article.res-1vkl8ot")

        print(f"  Found {len(cards)} job cards")

        # --- Pass 1: collect all metadata while still on the listing page ---
        jobs_to_visit = []
        for card in cards:
            try:
                link_el = card.query_selector("a[href*='/stellenangebote--']") or card.query_selector("a")
                if not link_el:
                    skipped += 1
                    continue

                href = link_el.get_attribute("href") or ""
                job_url = href if href.startswith("http") else f"https://www.stepstone.de{href}"
                job_url = job_url.split("?")[0]

                if _already_exists(job_url):
                    skipped += 1
                    continue

                title_el = card.query_selector("[data-at='job-item-title'], h2.res-nehv70")
                title = title_el.inner_text().strip() if title_el else "Unknown"

                company_el = card.query_selector("[data-at='job-item-company-name'], span.res-1foufh")
                company = company_el.inner_text().strip() if company_el else ""

                location_el = card.query_selector("[data-at='job-item-location'], span.res-1btlclk")
                location = location_el.inner_text().strip() if location_el else ""

                jobs_to_visit.append((job_url, title, company, location))

            except Exception as e:
                print(f"  Warning: skipped card metadata — {e}")

        # --- Pass 2: visit each job page to get full JD ---
        listing_url = page.url
        for job_url, title, company, location in jobs_to_visit:
            try:
                page.goto(job_url, wait_until="domcontentloaded", timeout=20_000)
                time.sleep(1.5)
                jd_el = page.query_selector(
                    "[data-at='job-ad-content'], .at-section-text-description, "
                    ".jobdescription, [class*='jobDescription']"
                )
                jd_text = jd_el.inner_text().strip() if jd_el else ""
                insert_job(title, company, location, jd_text, job_url,
                           role_profile=role_profile, language=language)
                added += 1
                print(f"  + {title} @ {company}")
            except Exception as e:
                print(f"  Warning: could not get JD for {title} — {e}")

        # Return to the original listing page
        page.goto(listing_url, wait_until="domcontentloaded", timeout=20_000)

    except Exception as e:
        print(f"  Error: {e}")

    print(f"  {added} added, {skipped} skipped")
    return added, skipped


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def diagnose():
    """Print what tabs are open and whether the scraper can see job cards — no data written."""
    print("\n=== Scraper Diagnosis ===\n")
    if not _is_edge_running():
        print("FAIL: Edge is not running with remote debugging on port 9222.")
        print("      Click 'Open Browser' in the app first.")
        return

    print("OK: Edge is running with remote debugging.\n")
    active_searches = get_active_searches()
    print(f"Active searches in DB: {len(active_searches)}")
    for s in active_searches:
        print(f"  [{s['id']}] {s['label']}  ({s['platform']}, profile={s['role_profile']}, lang={s['language']})")
        print(f"       {s['search_url'][:90]}")

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        all_pages = [p for ctx in browser.contexts for p in ctx.pages]
        print(f"\nOpen tabs: {len(all_pages)}")

        for i, page in enumerate(all_pages):
            url = page.url
            title = page.title()
            print(f"\n  Tab {i+1}: {title[:60]}")
            print(f"          {url[:100]}")

            search = _match_search(url, active_searches)
            if search:
                print(f"          -> Matched: '{search['label']}'")
            else:
                print(f"          -> No matching search config")

            is_li = "linkedin.com/jobs/" in url and "/view/" not in url
            is_ss = "stepstone.de/jobs" in url or "stepstone.de/stellenangebote" in url

            if is_li:
                print("          -> LinkedIn job page detected")
                cards = []
                for sel in _LI_CARD_SELECTORS:
                    found = page.query_selector_all(sel)
                    if found:
                        print(f"          -> Selector '{sel}' found {len(found)} card(s)")
                        cards = found
                        break
                    else:
                        print(f"          -> Selector '{sel}': 0 results")
                if not cards:
                    print("          -> NO JOB CARDS FOUND — running scroll test + DOM dump:")
                    # Try mouse scroll on left panel and recount links
                    vp = page.viewport_size or {"width": 1280, "height": 800}
                    lx, ly = max(200, vp["width"] // 4), vp["height"] // 2
                    page.mouse.move(lx, ly)
                    page.mouse.click(lx, ly)
                    time.sleep(0.5)
                    for _ in range(5):
                        page.mouse.wheel(0, 500)
                        time.sleep(0.4)
                    time.sleep(1.5)
                    after_scroll = page.evaluate("""() =>
                        [...document.querySelectorAll('a[href*="/jobs/view/"]')]
                            .map(a => a.href.split('?')[0])
                            .filter(h => /\\/jobs\\/view\\/\\d/.test(h)).length
                    """)
                    print(f"          -> After mouse scroll: {after_scroll} job link(s) found")
                    dom_info = page.evaluate("""() => {
                        const info = {};
                        // Count likely job list containers
                        const selectors = [
                            'ul.scaffold-layout__list-container',
                            'div.scaffold-layout__list',
                            'div[class*="jobs-search"]',
                            'ul[class*="jobs"]',
                            'li[class*="job"]',
                            'div[class*="job-card"]',
                            'a[href*="/jobs/view/"]',
                            '[data-job-id]',
                            'li[data-occludable-job-id]',
                            '[data-occludable-job-id]',
                            '[data-view-name]',
                        ];
                        for (const sel of selectors) {
                            const count = document.querySelectorAll(sel).length;
                            if (count > 0) info[sel] = count;
                        }
                        // Sample first job link href
                        const link = document.querySelector('a[href*="/jobs/view/"]');
                        if (link) info['sample_job_link'] = link.href.substring(0, 80);
                        // First 3 unique data-* attributes on any element
                        const el = document.querySelector('li');
                        if (el) info['first_li_classes'] = el.className.substring(0, 120);
                        return info;
                    }""")
                    for k, v in dom_info.items():
                        print(f"             {k}: {v}")
            elif is_ss:
                print("          -> Stepstone job page detected")
            else:
                print("          -> Not a recognised job search page (will be skipped)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--open",     action="store_true", help="Open the browser (Step 1)")
    parser.add_argument("--diagnose", action="store_true", help="Diagnose open tabs without scraping")
    args = parser.parse_args()

    init_db()

    if args.open:
        open_browser()
        return

    if args.diagnose:
        diagnose()
        return

    # Step 2 — scrape
    added, skipped = scrape_open_tabs()
    print(f"\nDone — {added} new jobs added, {skipped} duplicates skipped.")


if __name__ == "__main__":
    main()
