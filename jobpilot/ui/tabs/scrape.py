"""Scrape tab: open the browser with your searches, then read the open tabs."""
import streamlit as st

from ..common import heading, run_module, start_module


def render() -> None:
    heading("Scrape New Jobs")

    st.markdown("""
    <div class="step-box">
      <div class="step-num">Step 1</div>
      <div class="step-title">Open the Browser</div>
      <div class="step-desc">Launches Edge with your configured search URLs. Log in if prompted, verify filters, then leave all tabs open.</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🌐 Open Browser", width="stretch"):
        start_module("jobpilot.scraper", ["--open"])
        st.success(
            "Edge is opening with your configured search URLs.\n"
            "1. Log in if prompted\n"
            "2. Verify filters are correct on each tab\n"
            "3. Leave all tabs open\n"
            "4. Come back here and click **Ready to Scrape**"
        )

    st.markdown("""
    <div class="step-box" style="margin-top:14px">
      <div class="step-num">Step 2</div>
      <div class="step-title">Scrape Open Tabs</div>
      <div class="step-desc">Make sure your job search tabs are still open in Edge, then click Scrape.</div>
    </div>
    """, unsafe_allow_html=True)

    col_scrape, col_diag = st.columns([3, 1])
    if col_scrape.button("⚡ Ready to Scrape", width="stretch", type="primary"):
        with st.spinner("Connecting to Edge and scraping open tabs..."):
            output = run_module("jobpilot.scraper", timeout=1800)
        st.session_state["scrape_log"] = output
        st.rerun()

    if col_diag.button("🔍 Diagnose", width="stretch", help="Check tabs without scraping"):
        with st.spinner("Inspecting open tabs..."):
            st.session_state["scrape_log"] = run_module("jobpilot.scraper", ["--diagnose"], timeout=300)

    log = st.session_state.get("scrape_log")
    if log:
        st.code(log)
        if "new jobs added" in log:
            st.success("Done. Go to the Review tab to score and approve jobs.")
