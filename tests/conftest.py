"""Test setup: point JobPilot at a throwaway data folder before anything imports it."""
import os
import sys
import tempfile
from pathlib import Path

_TMP_HOME = tempfile.mkdtemp(prefix="jobpilot_test_")
os.environ["JOBPILOT_HOME"] = _TMP_HOME
os.environ["JOBPILOT_DISABLE_PLUGINS"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from jobpilot import db, llm, paths  # noqa: E402


class FakeProvider(llm.Provider):
    """Stands in for a real AI service; returns queued answers and records prompts."""
    name = "fake"
    label = "Fake"
    env_key = "FAKE_API_KEY"
    min_interval = 0.0

    def __init__(self):
        self.answers: list[str] = []
        self.prompts: list[str] = []

    def api_key(self) -> str:
        return "test-key"

    def list_models(self) -> list[str]:
        return ["fake-1"]

    def default_model(self, task: str) -> str:
        return "fake-1"

    def generate(self, prompt, *, model, system=None, want_json=False, max_tokens=None) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError("FakeProvider has no queued answer")
        return self.answers.pop(0)


@pytest.fixture(autouse=True)
def fresh_home():
    """Every test starts with an empty database and data folder."""
    assert str(paths.HOME) == str(Path(_TMP_HOME).resolve())
    for item in paths.HOME.iterdir():
        if item.is_file():
            item.unlink()
        else:
            import shutil
            shutil.rmtree(item)
    db.init_db()
    yield


@pytest.fixture
def fake_llm():
    provider = FakeProvider()
    llm.register_provider(provider)
    db.set_setting("llm_provider", "fake")
    yield provider
    llm._providers.pop("fake", None)


@pytest.fixture
def profiles():
    """Two neutral role profiles, created the way a user would (JobPilot ships none)."""
    first = db.save_role_profile(
        name="Supply Chain Analyst", keywords="supply chain, logistics, SAP, forecasting",
        headline="Supply Chain Analyst | Logistics", focus="Lead with logistics analytics.",
        cert_tags="data, logistics")
    second = db.save_role_profile(
        name="Operations Analyst", keywords="operations, reporting, Power BI, SQL",
        headline="Operations Analyst | Reporting", focus="Lead with reporting and dashboards.",
        cert_tags="data, analytics")
    return [db.get_role_profile(first), db.get_role_profile(second)]


@pytest.fixture
def master_cv():
    text = (paths.REPO_ROOT / "master_cv.example.md").read_text(encoding="utf-8")
    paths.DEFAULT_MASTER_CV.write_text(text, encoding="utf-8")
    return text
