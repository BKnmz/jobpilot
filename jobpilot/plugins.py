"""
plugins.py — lets add-on packages extend JobPilot without changing core code.

An add-on declares an entry point in its pyproject.toml:

    [project.entry-points."jobpilot.plugins"]
    myaddon = "myaddon:register"

register(api) receives this module and may call register_tab(),
register_job_action() and jobpilot.llm.register_provider().
Set JOBPILOT_DISABLE_PLUGINS=1 to run the core alone.
"""
import os
from importlib.metadata import entry_points
from typing import Callable

ENTRY_POINT_GROUP = "jobpilot.plugins"

tabs: list[tuple[str, Callable[[], None]]] = []
job_actions: list[Callable[[dict], None]] = []
loaded: list[str] = []
errors: list[str] = []
_done = False


def register_tab(label: str, render: Callable[[], None]) -> None:
    """Add a tab to the app. render() is called inside the tab on every rerun."""
    if all(existing != label for existing, _ in tabs):
        tabs.append((label, render))


def register_job_action(render: Callable[[dict], None]) -> None:
    """Add UI shown under each approved job. render(job) gets the job row as a dict."""
    if render not in job_actions:
        job_actions.append(render)


def load_plugins() -> list[str]:
    """Discover and register installed add-ons once per process. Returns their names."""
    global _done
    if _done:
        return loaded
    _done = True
    if os.environ.get("JOBPILOT_DISABLE_PLUGINS"):
        return loaded
    import sys

    api = sys.modules[__name__]
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        try:
            ep.load()(api)
            loaded.append(ep.name)
        except Exception as exc:  # a broken add-on must not take the app down
            errors.append(f"{ep.name}: {exc}")
    return loaded
