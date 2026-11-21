"""Shared UI helpers: styles, safe HTML, and running pipeline steps as subprocesses."""
import html
import os
import subprocess
import sys

import streamlit as st

from .. import db, paths


def flash(message: str, scope: str) -> None:
    """Remember a success message so it survives the st.rerun() that follows a save.

    `scope` names the tab: all tabs render in one run, so each tab shows only its own messages."""
    st.session_state.setdefault(f"_flash_{scope}", []).append(message)


def show_flash(scope: str) -> None:
    """Show (once) the messages stored by flash() for this scope. Call near the top of a tab."""
    for message in st.session_state.pop(f"_flash_{scope}", []):
        st.success(message)


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

.brand-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e40af 100%);
    border-radius: 14px; padding: 22px 32px; margin-bottom: 1.4rem;
    display: flex; align-items: center; gap: 18px;
}
.brand-title { color: #ffffff; font-size: 2rem; font-weight: 700; margin: 0; letter-spacing: -0.5px; }
.brand-sub   { color: #93c5fd; font-size: 0.95rem; margin: 4px 0 0; }
.brand-badge {
    background: #3b82f6; color: white; border-radius: 20px; padding: 3px 12px;
    font-size: 0.78rem; font-weight: 600; letter-spacing: 0.4px; margin-left: auto; white-space: nowrap;
}

.stat-row { display:flex; gap:12px; margin-bottom:1.2rem; flex-wrap:wrap; }
.stat-pill {
    background:#f1f5f9; border:1px solid #e2e8f0; border-radius:8px;
    padding:10px 18px; flex:1; min-width:110px; text-align:center;
}
.stat-pill .sp-val { font-size:1.6rem; font-weight:700; color:#1e40af; line-height:1; }
.stat-pill .sp-lbl { font-size:0.72rem; color:#64748b; margin-top:2px; text-transform:uppercase; letter-spacing:.5px; }

.score-badge {
    display:inline-block; width:44px; height:44px; border-radius:50%;
    font-size:1.25rem; font-weight:700; line-height:44px; text-align:center; color:white;
}
.score-hi  { background:#16a34a; }
.score-mid { background:#d97706; }
.score-lo  { background:#dc2626; }

.section-heading {
    font-size:1.05rem; font-weight:600; color:#1e293b;
    border-left:4px solid #3b82f6; padding-left:10px; margin:1.2rem 0 0.6rem;
}

.step-box { background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px; padding:14px 18px; margin-bottom:12px; }
.step-num { font-size:0.75rem; font-weight:700; color:#3b82f6; text-transform:uppercase; letter-spacing:.6px; }
.step-title { font-size:1rem; font-weight:600; color:#1e3a8a; margin:2px 0 4px; }
.step-desc  { font-size:0.85rem; color:#475569; }

.tag { border-radius:4px; padding:2px 8px; font-size:0.78rem; font-weight:600; margin-right:4px; display:inline-block; }
.tag-role { background:#dbeafe; color:#1e40af; }
.tag-lang { background:#f0fdf4; color:#166534; }
.kw { border-radius:10px; padding:1px 8px; font-size:0.74rem; margin:0 4px 4px 0; display:inline-block; }
.kw-hit  { background:#dcfce7; color:#166534; }
.kw-miss { background:#fee2e2; color:#991b1b; }
.jp-footer { color:#64748b; font-size:0.82rem; text-align:center; margin-top:2.5rem; }
.jp-footer a { color:#1e40af; text-decoration:none; }
</style>
"""


def esc(value) -> str:
    """Escape text that came from outside (job boards, AI answers) before putting it in HTML."""
    return html.escape(str(value or ""), quote=True)


def heading(text: str) -> None:
    st.markdown(f'<p class="section-heading">{esc(text)}</p>', unsafe_allow_html=True)


def link(url: str, label: str) -> None:
    """Show a link only for http(s) addresses."""
    if url and url.lower().startswith(("http://", "https://")):
        st.markdown(f"[{label}]({url})")


def profile_labels() -> dict[int, str]:
    return {p["id"]: p["name"] for p in db.get_role_profiles()}


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(paths.REPO_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["PYTHONUTF8"] = "1"          # job titles contain ü, ş, ğ ...; cp1252 pipes would crash
    env["PYTHONIOENCODING"] = "utf-8"
    env["JOBPILOT_HOME"] = str(paths.HOME)
    return env


def run_module(module: str, args: list[str] | None = None, timeout: int = 300) -> str:
    """Run `python -m <module>` and return its combined output."""
    cmd = [sys.executable, "-m", module] + list(args or [])
    try:
        result = subprocess.run(cmd, cwd=str(paths.REPO_ROOT), env=_env(), capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return f"ERROR: timed out after {timeout // 60} minute(s)."
    return (result.stdout or "") + (result.stderr or "")


def start_module(module: str, args: list[str] | None = None) -> None:
    """Start `python -m <module>` without waiting for it."""
    subprocess.Popen([sys.executable, "-m", module] + list(args or []),
                     cwd=str(paths.REPO_ROOT), env=_env())
