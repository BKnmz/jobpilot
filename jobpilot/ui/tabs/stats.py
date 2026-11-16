"""Stats tab: counts per status and the reset switch."""
import streamlit as st

from ... import db
from ..common import heading

_ICONS = {"new": "🔵", "scored": "🟡", "approved": "🟢", "rejected": "🔴", "applied": "⭐"}


def render() -> None:
    heading("Pipeline Stats")
    data = db.count_by_status()
    with db._connect() as conn:
        cert_total = conn.execute("SELECT COUNT(*) FROM certificates WHERE is_active=1").fetchone()[0]

    if not data:
        st.info("No jobs in the database yet. Use the Scrape tab to fetch some.")
    else:
        col_jobs, col_certs = st.columns(2)
        col_jobs.metric("Total jobs in DB", sum(data.values()))
        col_certs.metric("Active certificates", cert_total)
        st.bar_chart(data)
        for col, (status, count) in zip(st.columns(len(data)), data.items()):
            col.metric(f"{_ICONS.get(status, '⚪')} {status.capitalize()}", count)

    st.divider()
    st.markdown("#### Danger Zone")
    if st.checkbox("I want to delete ALL jobs from the database"):
        if st.button("🗑 Clear All Jobs", type="primary", width="stretch"):
            db.delete_all_jobs()
            st.success("All jobs deleted.")
            st.rerun()
