"""Searches tab: the job-board search URLs to open and scrape."""
import streamlit as st

from ... import db, languages
from ..common import heading, profile_labels


def render() -> None:
    heading("Search Configuration")
    st.caption(
        "Add the search URLs you set up on LinkedIn and Stepstone. "
        "Tag each with a role profile and language so scraped jobs are categorised automatically."
    )
    labels = profile_labels()

    searches = db.get_all_searches()
    if searches:
        st.markdown("#### Configured searches")
        for s in searches:
            cols = st.columns([2, 1.2, 2, 0.8, 3, 1.5, 1, 1, 0.8])
            cols[0].markdown(f"**{s['label']}**")
            cols[1].caption((s["platform"] or "").capitalize())
            cols[2].caption(labels.get(s["role_profile"], "—"))
            cols[3].caption(s["language"].upper() if s["language"] else "—")
            url = s["search_url"] or ""
            cols[4].caption(url[:50] + ("…" if len(url) > 50 else ""))
            cols[5].caption(f"🟢 {s['last_opened_at'][:10]}" if s.get("last_opened_at") else "🔵 New")
            if cols[6].button("✅ On" if s["active"] else "⏸ Off", key=f"toggle_{s['id']}"):
                db.toggle_search(s["id"])
                st.rerun()
            if cols[7].button("↺", key=f"reset_{s['id']}", help="Mark as new (re-open next time)"):
                db.reset_search_opened(s["id"])
                st.rerun()
            if cols[8].button("🗑", key=f"del_{s['id']}"):
                db.delete_search(s["id"])
                st.rerun()
        st.divider()
    else:
        st.info("No searches configured yet. Add one below.")

    st.markdown("#### Add a new search")
    if not labels:
        st.warning("Add a role profile in Settings first.")
        return

    with st.form("add_search_form", clear_on_submit=True):
        col_a, col_b, col_c, col_d = st.columns([2, 2, 1.5, 1])
        label_in = col_a.text_input("Label", placeholder="e.g. LinkedIn PO Germany")
        platform_in = col_b.selectbox("Platform", ["linkedin", "stepstone"])
        role_in = col_c.selectbox("Role profile", list(labels), format_func=lambda pid: labels[pid])
        lang_in = col_d.selectbox("CV language", db.get_enabled_languages(),
                                  format_func=lambda c: languages.get(c).native)
        url_in = st.text_input("Search URL", placeholder="Paste the full search URL from your browser")
        if st.form_submit_button("Add Search", width="stretch"):
            if not url_in.strip():
                st.error("URL cannot be empty.")
            elif not url_in.strip().lower().startswith(("http://", "https://")):
                st.error("The URL must start with http:// or https://")
            elif not label_in.strip():
                st.error("Label cannot be empty.")
            else:
                db.insert_search(platform=platform_in, role_profile=role_in,
                                 search_url=url_in.strip(), label=label_in.strip(), language=lang_in)
                st.success(f"Added: {label_in.strip()}")
                st.rerun()
