"""E2E harness: a real Streamlit server on a temp JOBPILOT_HOME, driven by a real browser.

Runs only when JOBPILOT_E2E=1. Uses dummy data only (nothing from the user's real data folder).
"""
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
import urllib.request
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
REPO_ROOT = E2E_DIR.parent.parent
ARTIFACTS = E2E_DIR / "artifacts"
SHOTS = ARTIFACTS / "screenshots"
STARTUP_TIMEOUT = 90
HEADED = os.environ.get("JOBPILOT_E2E_HEADED") == "1"   # watch the browser: visible window, slowed down
_RESULTS: list[dict] = []


def pytest_collection_modifyitems(config, items):
    if os.environ.get("JOBPILOT_E2E") == "1":
        return
    skip = pytest.mark.skip(reason="E2E tests are off; set JOBPILOT_E2E=1 to run them")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)


def pytest_runtest_logreport(report):
    if "e2e" not in report.keywords:
        return
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        _RESULTS.append({"name": report.nodeid.split("::")[-1], "outcome": report.outcome,
                         "text": report.longreprtext if report.outcome == "failed" else "",
                         "skip": str(report.longrepr) if report.outcome == "skipped" else ""})


def pytest_sessionfinish(session, exitstatus):
    if not _RESULTS:
        return
    ARTIFACTS.mkdir(exist_ok=True)
    lines = [f"# E2E run report ({REPO_ROOT.name})", "",
             f"Run: {datetime.now():%Y-%m-%d %H:%M:%S}  |  mode: {'headed' if HEADED else 'headless'}", "",
             "| Test | Result |", "|---|---|"]
    for r in _RESULTS:
        lines.append(f"| {r['name']} | {r['outcome'].upper().replace('PASSED', 'PASS').replace('FAILED', 'FAIL')} |")
    failed = [r for r in _RESULTS if r["outcome"] == "failed"]
    lines += ["", "## Failures", ""]
    if not failed:
        lines.append("None.")
    for r in failed:
        lines += [f"### {r['name']}", "", f"Screenshot: `screenshots/{r['name']}.png` "
                  f"(failure copy: `{r['name']}.png`)", "", "```", r["text"][-2500:], "```", ""]
    lines += ["## Bugs found", ""]
    if not failed:
        lines.append("No failing tests, so no app bugs detected in this run.")
    else:
        lines.append("Each failure above is either an app bug or a test problem; "
                     "the first docstring line of the test says what it expects.")
        for r in failed:
            lines.append(f"- {r['name']}")
    (ARTIFACTS / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class App:
    """A running Streamlit server plus its throwaway data folder."""

    def __init__(self, home: Path, port: int = 0, proc=None):
        self.home, self.port, self.proc = home, port, proc
        self.log = home / "server.log"
        self.url = f"http://localhost:{port}"

    def query(self, sql: str, args=()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.home / "jobs.db")
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()

    def execute(self, sql: str, args=()) -> None:
        conn = sqlite3.connect(self.home / "jobs.db")
        try:
            conn.execute(sql, args)
            conn.commit()
        finally:
            conn.close()

    def server_log(self) -> str:
        return self.log.read_text(encoding="utf-8", errors="replace") if self.log.exists() else ""


def _start_app(prepare=None, disable_plugins: bool = True, profiles: bool = True) -> App:
    home = Path(tempfile.mkdtemp(prefix="jobpilot_e2e_"))
    env = os.environ.copy()
    env.update({"JOBPILOT_HOME": str(home), "JOBPILOT_DEMO_LLM": "1", "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8"})
    if disable_plugins:
        env["JOBPILOT_DISABLE_PLUGINS"] = "1"
    else:
        env.pop("JOBPILOT_DISABLE_PLUGINS", None)
    subprocess.run([sys.executable, str(E2E_DIR / "seed_home.py"), str(REPO_ROOT)]
                   + ([] if profiles else ["--no-profiles"]),
                   env=env, check=True, cwd=str(home))
    if prepare is not None:
        prepare(App(home))

    port = _free_port()
    logf = open(home / "server.log", "wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py", "--server.headless", "true",
         "--server.port", str(port), "--browser.gatherUsageStats", "false"],
        cwd=str(REPO_ROOT), env=env, stdout=logf, stderr=subprocess.STDOUT)
    app = App(home, port, proc)
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"Streamlit exited early:\n{app.server_log()[-2000:]}")
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=2) as r:
                if r.status == 200:
                    return app
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"Streamlit did not start within {STARTUP_TIMEOUT}s:\n{app.server_log()[-2000:]}")


def _stop_app(app: App) -> None:
    app.proc.terminate()
    try:
        app.proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        app.proc.kill()


@pytest.fixture
def app_factory():
    """Start apps; prepare(app) may edit the DB before the server starts."""
    started: list[App] = []

    def make(prepare=None, disable_plugins: bool = True, profiles: bool = True) -> App:
        a = _start_app(prepare, disable_plugins, profiles)
        started.append(a)
        return a

    yield make
    for a in started:
        _stop_app(a)


@pytest.fixture
def app(app_factory) -> App:
    return app_factory()


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        errors = []
        br = None
        extra = {"headless": False, "slow_mo": 400, "args": ["--window-size=1400,900"]} if HEADED             else {"headless": True}
        for kwargs in ({"channel": "msedge"}, {}):
            try:
                br = pw.chromium.launch(**extra, **kwargs)
                break
            except Exception as exc:  # not installed
                errors.append(f"{kwargs or 'bundled chromium'}: {str(exc).splitlines()[0]}")
        if br is None:
            pytest.skip("No browser could be launched (" + "; ".join(errors) + "). "
                        "Run: .venv\\Scripts\\python.exe -m playwright install chromium")
        yield br
        br.close()


@pytest.fixture
def page(browser, request):
    ctx = browser.new_context(accept_downloads=True, viewport={"width": 1400, "height": 900})
    pg = ctx.new_page()
    pg.set_default_timeout(20000)
    yield pg
    rep = getattr(request.node, "rep_call", None)
    stem = request.node.name.replace("/", "_")
    SHOTS.mkdir(parents=True, exist_ok=True)
    try:
        pg.screenshot(path=str(SHOTS / f"{stem}.png"), full_page=True)   # final state of every test
        if rep is not None and rep.failed:
            pg.screenshot(path=str(ARTIFACTS / f"{stem}.png"), full_page=True)
            (ARTIFACTS / f"{stem}.txt").write_text(pg.inner_text("body"), encoding="utf-8")
    except Exception:
        pass
    try:
        exceptions = pg.locator('[data-testid="stException"]').count()
    except Exception:
        exceptions = 0
    ctx.close()
    if rep is not None and rep.passed and exceptions:
        pytest.fail(f"{exceptions} Streamlit exception box(es) were visible at the end of the test")
