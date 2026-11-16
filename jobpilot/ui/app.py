"""Main Streamlit page: header, core tabs, and tabs contributed by add-ons."""
import streamlit as st

from .. import db, links, paths, plugins
from .common import CSS, esc
from .tabs import approved, review, scrape, searches, settings, stats


def _header() -> None:
    counts = db.count_by_status()
    edition = "Pro" if plugins.loaded else "Free"
    pills = "".join(
        f'<div class="stat-pill"><div class="sp-val">{counts.get(key, 0)}</div>'
        f'<div class="sp-lbl">{label}</div></div>'
        for key, label in (("new", "New"), ("scored", "Scored"),
                           ("approved", "Approved"), ("applied", "Applied"))
    )
    st.markdown(f"""
<div class="brand-header">
  <div>
    <p class="brand-title">🚀 JobPilot</p>
    <p class="brand-sub">AI-powered job scraping, scoring &amp; CV tailoring</p>
  </div>
  <span class="brand-badge">{esc(edition)}</span>
</div>
<div class="stat-row">{pills}</div>
""", unsafe_allow_html=True)


def _footer() -> None:
    parts = []
    if not plugins.loaded and links.SUPPORT_URL:
        parts.append(f'JobPilot is free and open source · <a href="{esc(links.SUPPORT_URL)}" '
                     f'target="_blank">☕ Buy me a coffee</a>')
    if not plugins.loaded and links.PRO_URL:
        parts.append(f'<a href="{esc(links.PRO_URL)}" target="_blank">'
                     f'Pro: cover letters in your own voice</a>')
    if parts:
        st.markdown(f'<div class="jp-footer">{" · ".join(parts)}</div>', unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="JobPilot", page_icon="🚀", layout="wide")
    paths.load_env()
    plugins.load_plugins()
    db.init_db()

    st.markdown(CSS, unsafe_allow_html=True)
    _header()
    for err in plugins.errors:
        st.warning(f"An add-on could not be loaded — {err}")

    core_before = [
        ("🔍  Searches", searches.render),
        ("🌐  Scrape", scrape.render),
        ("⭐  Review & Score", review.render),
        ("✅  Approved", approved.render),
    ]
    core_after = [
        ("📊  Stats", stats.render),
        ("⚙️  Settings", settings.render),
    ]
    entries = core_before + list(plugins.tabs) + core_after

    for tab, (_, render) in zip(st.tabs([label for label, _ in entries]), entries):
        with tab:
            render()

    _footer()
