"""Review tab: score new jobs, then approve or reject them."""
import streamlit as st

from ... import db, llm
from ..common import esc, heading, link, profile_labels, run_module


def _keyword_html(job: dict) -> str:
    matched, missing = db.job_keywords(job)
    chips = "".join(f'<span class="kw kw-hit">✓ {esc(k)}</span>' for k in matched)
    chips += "".join(f'<span class="kw kw-miss">✗ {esc(k)}</span>' for k in missing)
    return f'<div style="margin-top:6px">{chips}</div>' if chips else ""


def render() -> None:
    heading("Review & Score Jobs")
    labels = profile_labels()
    new_count = db.count_by_status().get("new", 0)

    if new_count > 0:
        provider = llm.active_provider()
        col_info, col_n = st.columns([4, 1])
        col_info.info(f"**{new_count} unscored job(s)** waiting.")
        batch = col_n.number_input("Score how many", min_value=1, max_value=100,
                                   value=min(10, new_count), step=5)
        seconds = int(batch * (provider.min_interval + 4))
        if st.button(f"🤖 Score {int(batch)} job(s) with {provider.label}", type="primary", width="stretch"):
            with st.spinner(f"Scoring {int(batch)} job(s)... (roughly {max(seconds, 10)} seconds)"):
                st.session_state["score_log"] = run_module(
                    "jobpilot.pipeline.score", ["--limit", str(int(batch))],
                    timeout=max(300, seconds * 3))
            st.rerun()

    log = st.session_state.get("score_log")
    if log:
        with st.expander("Last scoring run", expanded="ERROR" in log):
            st.code(log)

    jobs = db.get_jobs_by_status("scored")
    if not jobs:
        st.info("No scored jobs yet. Scrape some jobs first, then click Score.")
        return

    st.caption(f"{len(jobs)} scored job(s) awaiting your decision")
    for job in jobs:
        score = job["match_score"] or 0
        sc_cls = "score-hi" if score >= 7 else "score-mid" if score >= 4 else "score-lo"
        role_label = labels.get(job.get("role_profile"), "")
        lang_badge = (job.get("language") or "").upper()
        notes = job["notes"] or ""

        col_score, col_info, col_approve, col_reject = st.columns([1, 6, 1.3, 1.3])

        with col_score:
            st.markdown(
                f'<div style="padding-top:6px"><span class="score-badge {sc_cls}">{int(score)}</span></div>',
                unsafe_allow_html=True,
            )

        with col_info:
            tags = ""
            if role_label:
                tags += f'<span class="tag tag-role">{esc(role_label)}</span>'
            if lang_badge:
                tags += f'<span class="tag tag-lang">{esc(lang_badge)}</span>'
            detail = esc(job["location"])
            if notes:
                detail += ("  ·  " if detail else "") + esc(notes)
            st.markdown(
                f'<div style="margin-bottom:4px"><strong style="font-size:1rem">{esc(job["title"])}</strong>'
                f' &nbsp;·&nbsp; {esc(job["company"])}</div>'
                f'<div style="margin-bottom:6px">{tags}</div>'
                f'<div style="color:#64748b;font-size:0.84rem">{detail}</div>'
                f'{_keyword_html(job)}',
                unsafe_allow_html=True,
            )
            link(job["source_url"], "🔗 View posting")

        with col_approve:
            if st.button("✅ Approve", key=f"approve_{job['id']}", width="stretch"):
                db.update_status(job["id"], "approved")
                db.assign_base_cv_to_job(job["id"])
                st.rerun()

        with col_reject:
            if st.button("❌ Reject", key=f"reject_{job['id']}", width="stretch"):
                db.update_status(job["id"], "rejected")
                st.rerun()

        st.divider()
