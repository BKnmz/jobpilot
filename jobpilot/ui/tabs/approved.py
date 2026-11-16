"""Approved tab: build base CVs, tailor a CV per job, download, mark as applied."""
import os

import streamlit as st

from ... import db, languages, llm, paths, plugins
from ..common import heading, link, profile_labels, run_module


def _base_cv_section(labels: dict[int, str]) -> dict:
    role_cvs = db.get_role_cvs()
    langs = db.get_enabled_languages()
    combos = [(pid, lang) for pid in labels for lang in langs]

    def combo_label(combo: tuple[int, str]) -> str:
        return f"{labels[combo[0]]} {combo[1].upper()}"

    def exists(combo) -> bool:
        rec = role_cvs.get(combo)
        return bool(rec and paths.resolve(rec["cv_path"]).exists())

    st.markdown("#### Base CVs")
    st.caption("One ready-to-send CV per role profile and language. Approved jobs get the matching one.")
    for pid, name in labels.items():
        cols = st.columns([2] + [1] * len(langs))
        cols[0].markdown(f"**{name}**")
        for col, lang in zip(cols[1:], langs):
            if exists((pid, lang)):
                col.success(f"✓ {lang.upper()}")
            else:
                col.error(f"✗ {lang.upper()}")

    with db._connect() as conn:
        needed = {(r[0], r[1]) for r in conn.execute(
            "SELECT DISTINCT role_profile, language FROM searches WHERE active=1 "
            "AND role_profile IS NOT NULL AND language IS NOT NULL").fetchall()}
        needed |= {(r[0], r[1]) for r in conn.execute(
            "SELECT DISTINCT role_profile, language FROM jobs WHERE status='approved' "
            "AND role_profile IS NOT NULL AND language IS NOT NULL").fetchall()}
    default = [c for c in combos if c in needed and not exists(c)]

    selected = st.multiselect(
        "Select CVs to build", options=combos, default=default, format_func=combo_label,
        help="Preselected: CVs your active searches and approved jobs need that are not built yet.",
    )
    provider = llm.active_provider()
    if st.button(f"🔨 Build {len(selected)} base CV(s) with {provider.label}", width="stretch",
                 type="primary", disabled=not selected):
        args = ["--profiles"] + [f"{pid}:{lang}" for pid, lang in selected]
        with st.spinner(f"Writing {len(selected)} base CV(s)..."):
            st.session_state["base_cv_log"] = run_module("jobpilot.pipeline.base_cvs", args, timeout=900)
        st.rerun()

    log = st.session_state.get("base_cv_log")
    if log:
        with st.expander("Last base CV build", expanded="ERROR" in log):
            st.code(log)
    return role_cvs


def _cv_cell(job: dict, role_cvs: dict) -> None:
    if job["cv_path"]:
        cv_file = paths.resolve(job["cv_path"])
        kind = "Tailored" if "_tailored" in cv_file.name else "Base CV"
        st.markdown(f"📄 **{kind}** `{cv_file.name}`")
        if cv_file.exists():
            st.download_button(
                "⬇ Download .docx", data=cv_file.read_bytes(), file_name=cv_file.name,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key=f"dl_{job['id']}")
        else:
            st.caption("⚠ File is missing — build or tailor it again.")
    elif job.get("role_profile") and job.get("language"):
        if (job["role_profile"], job["language"]) in role_cvs:
            st.caption("Base CV exists but is not attached yet — it is attached when you build or approve.")
        else:
            st.caption("⚠ Base CV for this role and language is not built yet")
    else:
        st.caption("No CV — role or language is not set")


def render() -> None:
    heading("Approved Jobs & CVs")
    labels = profile_labels()
    if not labels:
        st.warning("Create your role profiles first: Settings → Role profiles. JobPilot can suggest them from your CV.")
        return

    role_cvs = _base_cv_section(labels)
    st.divider()

    jobs = db.get_jobs_by_status("approved")
    st.info(f"**{len(jobs)} approved job(s)**")
    if not jobs:
        st.caption("Approve some jobs in the Review tab.")
        return

    log = st.session_state.get("tailor_log")
    if log:
        with st.expander("Last tailoring run", expanded="ERROR" in log):
            st.code(log)

    lang_codes = languages.codes()
    for job in jobs:
        col_info, col_cv, col_action = st.columns([5, 3.5, 2.5])

        with col_info:
            st.markdown(f"**{job['title']}** — {job['company']}")
            lang = (job.get("language") or "").upper()
            st.caption(f"{job['location'] or ''}  ·  {labels.get(job.get('role_profile'), '—')}  ·  {lang or '—'}")
            link(job["source_url"], "View posting")

        with col_cv:
            _cv_cell(job, role_cvs)

        with col_action:
            job_lang = job.get("language") if job.get("language") in lang_codes else languages.DEFAULT_LANGUAGE
            target = st.selectbox("Language", lang_codes, index=lang_codes.index(job_lang),
                                  format_func=lambda c: languages.get(c).native,
                                  key=f"tl_{job['id']}", label_visibility="collapsed")
            if st.button("✨ Tailor CV for this job", key=f"tailor_{job['id']}", width="stretch"):
                with st.spinner("Tailoring CV..."):
                    st.session_state["tailor_log"] = run_module(
                        "jobpilot.pipeline.tailor", ["--job-id", str(job["id"]), "--lang", target],
                        timeout=300)
                st.rerun()
            if st.button("📤 Mark as applied", key=f"applied_{job['id']}", width="stretch"):
                db.update_status(job["id"], "applied")
                st.rerun()

        for action in plugins.job_actions:
            action(job)

        st.divider()
