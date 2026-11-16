"""Small helpers for driving Streamlit pages."""
import time

from playwright.sync_api import Page, expect


def assert_no_exception(page: Page) -> None:
    boxes = page.locator('[data-testid="stException"]')
    if boxes.count():
        raise AssertionError("Streamlit exception box on the page:\n" + boxes.first.inner_text()[:1500])


def settle(page: Page, timeout: float = 60000) -> None:
    """Wait until Streamlit has finished running (also across st.rerun()) and show no exception."""
    end = time.time() + timeout / 1000
    quiet = 0
    while time.time() < end:
        running = page.locator('[data-testid="stStatusWidget"]').count() > 0
        quiet = 0 if running else quiet + 1
        if quiet >= 4:
            break
        time.sleep(0.15)
    else:
        raise AssertionError("Streamlit kept running past the timeout")
    assert_no_exception(page)


def open_app(page: Page, url: str) -> None:
    page.goto(url)
    page.get_by_role("tab").first.wait_for(timeout=60000)
    settle(page)


def tab(page: Page, name: str) -> None:
    """Open a tab by (part of) its label."""
    page.get_by_role("tab").filter(has_text=name).first.click()
    settle(page)


def click(page: Page, name: str, *, exact: bool = False, timeout: float = 60000) -> None:
    """Click a visible button by its text and wait for the rerun to finish."""
    page.get_by_role("button", name=name, exact=exact).first.click()
    try:   # give the rerun a moment to start, otherwise settle() can return before it began
        page.locator('[data-testid="stStatusWidget"]').first.wait_for(state="attached", timeout=1500)
    except Exception:
        pass
    settle(page, timeout)


def text_of(page: Page) -> str:
    return page.inner_text("body")


def wait_text(page: Page, text: str, timeout: float = 60000) -> None:
    expect(page.get_by_text(text).first).to_be_visible(timeout=timeout)
    assert_no_exception(page)
