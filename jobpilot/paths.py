"""
paths.py — one place that knows where JobPilot keeps user data.

Everything personal (database, .env, master CV, generated CVs, browser login
profile) lives under HOME. HOME is the JOBPILOT_HOME environment variable if
set, otherwise the repository folder, which is where older versions kept it.
"""
import os
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent

HOME = Path(os.environ.get("JOBPILOT_HOME") or REPO_ROOT).resolve()

DB_PATH = HOME / "jobs.db"
ENV_PATH = HOME / ".env"
DEFAULT_MASTER_CV = HOME / "master_cv.md"
CV_OUT_DIR = HOME / "cv_outputs"
BASE_CV_DIR = CV_OUT_DIR / "base"
EDGE_PROFILE_DIR = HOME / ".edge_scraper_profile"
ROLE_PROFILE_SEED = HOME / "profiles.seed.json"
ROLE_PROFILE_EXAMPLE = PKG_DIR / "data" / "profiles.example.json"


def resolve(path: str | os.PathLike) -> Path:
    """Turn a path stored in the database (relative to HOME) into an absolute one."""
    p = Path(path)
    return p if p.is_absolute() else HOME / p


def relative(path: str | os.PathLike) -> str:
    """Store paths relative to HOME, with forward slashes, so HOME can be moved."""
    p = Path(path).resolve()
    try:
        return p.relative_to(HOME).as_posix()
    except ValueError:
        return p.as_posix()


def load_env() -> None:
    """Load API keys from HOME/.env into the process environment."""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)


def save_env_value(key: str, value: str) -> None:
    """Set KEY=value in HOME/.env (replacing an existing line) and in this process."""
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    new_line = f"{key}={value}\n"
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = new_line
            break
    else:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(new_line)
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    ENV_PATH.write_text("".join(lines), encoding="utf-8")
    os.environ[key] = value
