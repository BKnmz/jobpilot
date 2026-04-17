import subprocess
import sys
import os
import streamlit as st
from db import (
    init_db, get_jobs_by_status, update_status, _connect,
    insert_search, get_all_searches, delete_search, toggle_search,
    get_role_cvs, assign_base_cv_to_job,
    get_setting, set_setting, get_cv_path, get_profile_cv_path, get_profile_name,
    reset_search_opened,
)

st.set_page_config(page_title="JobPilot", page_icon="🚀", layout="wide")
init_db()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ── Brand header ── */
.brand-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e40af 100%);
    border-radius: 14px;
    padding: 22px 32px;
    margin-bottom: 1.4rem;
    display: flex;
    align-items: center;
    gap: 18px;
}
.brand-title  { color: #ffffff; font-size: 2rem; font-weight: 700; margin: 0; letter-spacing: -0.5px; }
.brand-sub    { color: #93c5fd; font-size: 0.95rem; margin: 4px 0 0; }
.brand-badge  {
    background: #3b82f6;
    color: white;
    border-radius: 20px;
    padding: 3px 12px;
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.4px;
    margin-left: auto;
    white-space: nowrap;
}

/* ── Metric pills in header ── */
.stat-row { display:flex; gap:12px; margin-bottom:1.2rem; flex-wrap:wrap; }
.stat-pill {
    background:#f1f5f9; border:1px solid #e2e8f0; border-radius:8px;
    padding:10px 18px; flex:1; min-width:110px; text-align:center;
}
.stat-pill .sp-val { font-size:1.6rem; font-weight:700; color:#1e40af; line-height:1; }
.stat-pill .sp-lbl { font-size:0.72rem; color:#64748b; margin-top:2px; text-transform:uppercase; letter-spacing:.5px; }

/* ── Job cards ── */
.job-card {
    background:#ffffff; border:1px solid #e2e8f0; border-radius:10px;
    padding:16px 20px; margin-bottom:10px;
    box-shadow: 0 1px 3px rgba(0,0,0,.05);
    transition: box-shadow .15s;
}
.job-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,.09); }

/* ── Score badge ── */
.score-badge {
    display:inline-block; width:44px; height:44px; border-radius:50%;
    font-size:1.25rem; font-weight:700; line-height:44px; text-align:center; color:white;
}
.score-hi  { background:#16a34a; }
.score-mid { background:#d97706; }
.score-lo  { background:#dc2626; }

/* ── Section heading style ── */
.section-heading {
    font-size:1.05rem; font-weight:600; color:#1e293b;
    border-left:4px solid #3b82f6; padding-left:10px;
    margin:1.2rem 0 0.6rem;
}

/* ── Step box ── */
.step-box {
    background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;
    padding:14px 18px; margin-bottom:12px;
}
.step-num { font-size:0.75rem; font-weight:700; color:#3b82f6; text-transform:uppercase; letter-spacing:.6px; }
.step-title { font-size:1rem; font-weight:600; color:#1e3a8a; margin:2px 0 4px; }
.step-desc  { font-size:0.85rem; color:#475569; }
</style>
""", unsafe_allow_html=True)

# ── Brand header ─────────────────────────────────────────────────────────────
with _connect() as _c:
    _stats = {r["status"]: r["count"] for r in _c.execute(
        "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
    ).fetchall()}

_new  = _stats.get("new", 0)
_scored = _stats.get("scored", 0)
_approved = _stats.get("approved", 0)
_applied  = _stats.get("applied", 0)

st.markdown(f"""
<div class="brand-header">
  <div>
    <p class="brand-title">🚀 JobPilot</p>
    <p class="brand-sub">AI-powered job scraping, scoring &amp; CV tailoring</p>
  </div>
  <span class="brand-badge">Free · Gemini AI</span>
</div>
<div class="stat-row">
  <div class="stat-pill"><div class="sp-val">{_new}</div><div class="sp-lbl">New</div></div>
  <div class="stat-pill"><div class="sp-val">{_scored}</div><div class="sp-lbl">Scored</div></div>
  <div class="stat-pill"><div class="sp-val">{_approved}</div><div class="sp-lbl">Approved</div></div>
  <div class="stat-pill"><div class="sp-val">{_applied}</div><div class="sp-lbl">Applied</div></div>
</div>
""", unsafe_allow_html=True)

AGENTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents")


def _run_script(script_name: str, extra_args: list = None, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run a Python agent script and return the result."""
    cmd = [sys.executable, os.path.join(AGENTS_DIR, script_name)]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(
        cmd,
        cwd=os.path.dirname(os.path.abspath(__file__)),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _profile_labels() -> dict:
    return {i: get_profile_name(i) for i in [1, 2, 3]}

PROFILE_LABELS = _profile_labels()
PROFILE_KEYS = {v: k for k, v in PROFILE_LABELS.items()}

ALL_COMBOS = [(1,"en"),(1,"de"),(2,"en"),(2,"de"),(3,"en"),(3,"de")]

def _combo_labels() -> dict:
    pl = _profile_labels()
    return {(pid, lang): f"{pl[pid]} {lang.upper()}" for pid, lang in ALL_COMBOS}

COMBO_LABEL = _combo_labels()


def _try_assign_base_cv(job_id: int):
    assign_base_cv_to_job(job_id)


tab_searches, tab0, tab1, tab2, tab3, tab_settings = st.tabs([
    "🔍  Searches",
    "🌐  Scrape",
    "⭐  Review & Score",
    "✅  Approved",
    "📊  Stats",
    "⚙️  Settings",
])

# ---------------------------------------------------------------------------
# Tab: Searches — configure role-based search URLs
# ---------------------------------------------------------------------------
with tab_searches:
    st.markdown('<p class="section-heading">Search Configuration</p>', unsafe_allow_html=True)
    st.caption(
        "Add the search URLs you set up on LinkedIn and Stepstone. "
        "Tag each with a role profile and language so scraped jobs are auto-categorised."
    )

    searches = get_all_searches()
    if searches:
        st.markdown("#### Configured searches")
        for s in searches:
            col_label, col_plat, col_role, col_lang, col_url, col_opened, col_toggle, col_reset, col_del = st.columns(
                [2, 1.2, 2, 0.8, 3, 1.5, 1, 1, 0.8]
            )
            col_label.markdown(f"**{s['label']}**")
            col_plat.caption(s["platform"].capitalize())
            col_role.caption(PROFILE_LABELS.get(s["role_profile"], "—"))
            col_lang.caption(s["language"].upper() if s["language"] else "—")
            col_url.caption(s["search_url"][:50] + ("…" if len(s["search_url"]) > 50 else ""))
            if s.get("last_opened_at"):
                col_opened.caption(f"🟢 {s['last_opened_at'][:10]}")
            else:
                col_opened.caption("🔵 New")
            active_label = "✅ On" if s["active"] else "⏸ Off"
            if col_toggle.button(active_label, key=f"toggle_{s['id']}"):
                toggle_search(s["id"])
                st.rerun()
            if col_reset.button("↺", key=f"reset_{s['id']}", help="Mark as new (re-open next time)"):
                reset_search_opened(s["id"])
                st.rerun()
            if col_del.button("🗑", key=f"del_{s['id']}"):
                delete_search(s["id"])
                st.rerun()
        st.divider()
    else:
        st.info("No searches configured yet. Add one below.")

    st.markdown("#### Add a new search")
    with st.form("add_search_form", clear_on_submit=True):
        col_a, col_b, col_c, col_d = st.columns([2, 2, 1.5, 1])
        label_in    = col_a.text_input("Label", placeholder="e.g. LinkedIn PO Germany")
        platform_in = col_b.selectbox("Platform", ["linkedin", "stepstone"])
        role_in     = col_c.selectbox("Role Profile", list(PROFILE_LABELS.values()))
        lang_in     = col_d.selectbox("Language", ["de", "en"])
        url_in      = st.text_input("Search URL", placeholder="Paste the full search URL from your browser")
        submitted   = st.form_submit_button("Add Search", use_container_width=True)
        if submitted:
            if not url_in.strip():
                st.error("URL cannot be empty.")
            elif not label_in.strip():
                st.error("Label cannot be empty.")
            else:
                insert_search(
                    platform=platform_in,
                    role_profile=PROFILE_KEYS[role_in],
                    search_url=url_in.strip(),
                    label=label_in.strip(),
                    language=lang_in,
                )
                st.success(f"Added: {label_in.strip()}")
                st.rerun()


# ---------------------------------------------------------------------------
# Tab 0 — Scrape Jobs
# ---------------------------------------------------------------------------
with tab0:
    st.markdown('<p class="section-heading">Scrape New Jobs</p>', unsafe_allow_html=True)

    st.markdown("""
    <div class="step-box">
      <div class="step-num">Step 1</div>
      <div class="step-title">Open the Browser</div>
      <div class="step-desc">Launches Edge with your configured search URLs. Log in if prompted, verify filters, then leave all tabs open.</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🌐 Open Browser", use_container_width=True):
        subprocess.Popen(
            [sys.executable, "scraper.py", "--open"],
            cwd=os.path.dirname(__file__),
        )
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
    if col_scrape.button("⚡ Ready to Scrape", use_container_width=True, type="primary"):
        with st.spinner("Connecting to Edge and scraping open tabs..."):
            result = subprocess.run(
                [sys.executable, "scraper.py"],
                cwd=os.path.dirname(__file__),
                capture_output=True,
                text=True,
            )
        output = result.stdout + result.stderr
        st.code(output)
        if "new jobs added" in output:
            st.success("Done! Go to the Review tab to score and approve jobs.")
            st.rerun()

    if col_diag.button("🔍 Diagnose", use_container_width=True, help="Check tabs without scraping"):
        with st.spinner("Inspecting open tabs..."):
            result = subprocess.run(
                [sys.executable, "scraper.py", "--diagnose"],
                cwd=os.path.dirname(__file__),
                capture_output=True,
                text=True,
            )
        st.code(result.stdout + result.stderr)

# ---------------------------------------------------------------------------
# Tab 1 — Review Scored Jobs
# ---------------------------------------------------------------------------
with tab1:
    st.markdown('<p class="section-heading">Review & Score Jobs</p>', unsafe_allow_html=True)

    with _connect() as conn:
        new_count = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='new'").fetchone()[0]

    if new_count > 0:
        st.info(f"**{new_count} unscored job(s)** waiting — click below to score them with Gemini AI.")
        if st.button(f"🤖 Score {new_count} New Job(s) with Gemini", type="primary", use_container_width=True):
            with st.spinner(f"Scoring up to 10 job(s) with Gemini... (~45 seconds)"):
                try:
                    result = _run_script("job_assessor.py", timeout=180)
                    output = result.stdout + result.stderr
                except subprocess.TimeoutExpired:
                    output = "ERROR: timed out after 3 minutes."
            st.code(output)
            st.rerun()

    jobs = get_jobs_by_status("scored")

    if not jobs:
        st.info("No scored jobs yet. Scrape some jobs first, then click Score.")
    else:
        st.caption(f"{len(jobs)} scored job(s) awaiting your decision")
        for job in jobs:
            score = job["match_score"] or 0
            sc_cls = "score-hi" if score >= 7 else "score-mid" if score >= 4 else "score-lo"
            role_label = PROFILE_LABELS.get(job.get("role_profile"), "")
            lang_badge = job["language"].upper() if job.get("language") else ""
            notes = job["notes"] or ""

            col_score, col_info, col_approve, col_reject = st.columns([1, 6, 1.3, 1.3])

            with col_score:
                st.markdown(
                    f'<div style="padding-top:6px"><span class="score-badge {sc_cls}">{score}</span></div>',
                    unsafe_allow_html=True,
                )

            with col_info:
                tags_html = ""
                if role_label:
                    tags_html += f'<span style="background:#dbeafe;color:#1e40af;border-radius:4px;padding:2px 8px;font-size:0.78rem;font-weight:600;margin-right:4px">{role_label}</span>'
                if lang_badge:
                    tags_html += f'<span style="background:#f0fdf4;color:#166534;border-radius:4px;padding:2px 8px;font-size:0.78rem;font-weight:600">{lang_badge}</span>'
                st.markdown(
                    f'<div style="margin-bottom:4px"><strong style="font-size:1rem">{job["title"]}</strong>'
                    f' &nbsp;·&nbsp; {job["company"]}</div>'
                    f'<div style="margin-bottom:6px">{tags_html}</div>'
                    f'<div style="color:#64748b;font-size:0.84rem">{job["location"] or ""}'
                    f'{"  ·  " + notes if notes else ""}</div>',
                    unsafe_allow_html=True,
                )
                if job["source_url"]:
                    st.markdown(f"[🔗 View posting]({job['source_url']})")

            with col_approve:
                if st.button("✅ Approve", key=f"approve_{job['id']}", use_container_width=True):
                    update_status(job["id"], "approved")
                    _try_assign_base_cv(job["id"])
                    st.rerun()

            with col_reject:
                if st.button("❌ Reject", key=f"reject_{job['id']}", use_container_width=True):
                    update_status(job["id"], "rejected")
                    st.rerun()

            st.divider()

# ---------------------------------------------------------------------------
# Tab 2 — Approved Jobs
# ---------------------------------------------------------------------------
with tab2:
    st.markdown('<p class="section-heading">Approved Jobs & CV Building</p>', unsafe_allow_html=True)

    # --- Base CV status grid + selective build ---
    role_cvs = get_role_cvs()
    st.markdown("#### Base CV Status")
    base_cols = st.columns(6)
    for idx, (pid, lang) in enumerate(ALL_COMBOS):
        rec = role_cvs.get((pid, lang))
        label = COMBO_LABEL[(pid, lang)]
        if rec and os.path.exists(rec["cv_path"]):
            base_cols[idx].success(f"✓ {label}")
        else:
            base_cols[idx].error(f"✗ {label}")

    # Smart default: combos needed by active searches
    with _connect() as conn:
        active_combos = [
            (r[0], r[1]) for r in conn.execute(
                "SELECT DISTINCT role_profile, language FROM searches WHERE active=1 "
                "AND role_profile IS NOT NULL AND language IS NOT NULL"
            ).fetchall()
        ]
    default_labels = [COMBO_LABEL[c] for c in ALL_COMBOS
                      if c in active_combos or not role_cvs.get(c)]
    if not default_labels:
        default_labels = [COMBO_LABEL[c] for c in ALL_COMBOS]

    selected_labels = st.multiselect(
        "Select CVs to build",
        options=[COMBO_LABEL[c] for c in ALL_COMBOS],
        default=default_labels,
        help="Defaults to CVs needed by your active searches plus any missing ones.",
    )
    label_to_combo = {v: k for k, v in COMBO_LABEL.items()}
    selected_combos = [label_to_combo[lbl] for lbl in selected_labels]

    if st.button("🔨 Build Selected Base CVs (Gemini)", use_container_width=True, type="primary",
                 disabled=not selected_combos):
        profiles_arg = " ".join(f"{pid}:{lang}" for pid, lang in selected_combos)
        with st.spinner(f"Generating {len(selected_combos)} base CV(s) with Gemini..."):
            try:
                result = _run_script("cv_base_builder.py",
                                     extra_args=["--profiles"] + profiles_arg.split(),
                                     timeout=600)
                output = result.stdout + result.stderr
            except subprocess.TimeoutExpired:
                output = "ERROR: timed out after 10 minutes."
        st.code(output)
        st.rerun()
    st.divider()

    # Approved job count
    with _connect() as conn:
        approved_count = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='approved'"
        ).fetchone()[0]
    st.info(f"**{approved_count} approved job(s) in database**")

    # --- Job list ---
    jobs = get_jobs_by_status("approved")

    if not jobs:
        st.info("No approved jobs yet. Approve some from the Review tab.")
    else:
        for job in jobs:
            col_info, col_cv, col_action = st.columns([5, 3, 2])

            with col_info:
                role_label = PROFILE_LABELS.get(job.get("role_profile"), "—")
                lang_badge = (job.get("language") or "").upper()
                st.markdown(f"**{job['title']}** — {job['company']}")
                st.caption(f"{job['location'] or ''}  ·  {role_label}  ·  {lang_badge}")
                if job["source_url"]:
                    st.markdown(f"[View posting]({job['source_url']})", unsafe_allow_html=True)

            with col_cv:
                if job["cv_path"]:
                    filename = job["cv_path"].replace("\\", "/").split("/")[-1]
                    st.markdown(f"📄 `{filename}`")
                else:
                    pid  = job.get("role_profile")
                    lang = job.get("language")
                    if pid and lang:
                        rec = role_cvs.get((pid, lang))
                        if rec:
                            base_name = rec["cv_path"].replace("\\", "/").split("/")[-1]
                            st.caption(f"Base CV: `{base_name}`")
                        else:
                            st.caption("⚠ Base CV not built yet")
                    else:
                        st.caption("No CV — role/lang unset")

            with col_action:
                if st.button("📤 Mark as Applied", key=f"applied_{job['id']}"):
                    update_status(job["id"], "applied")
                    st.rerun()

            st.divider()

# ---------------------------------------------------------------------------
# Tab 3 — Pipeline Stats
# ---------------------------------------------------------------------------
with tab3:
    st.markdown('<p class="section-heading">Pipeline Stats</p>', unsafe_allow_html=True)

    with _connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        cert_total = conn.execute(
            "SELECT COUNT(*) FROM certificates WHERE is_active=1"
        ).fetchone()[0]

    if not rows:
        st.info("No jobs in the database yet. Use the Scrape tab to fetch some.")
    else:
        data = {row["status"]: row["count"] for row in rows}

        col_jobs, col_certs = st.columns(2)
        col_jobs.metric("Total jobs in DB", total)
        col_certs.metric("Active certificates", cert_total)

        st.bar_chart(data)

        cols = st.columns(len(data))
        status_colors = {
            "new": "🔵", "scored": "🟡", "approved": "🟢",
            "rejected": "🔴", "applied": "⭐"
        }
        for col, (status, count) in zip(cols, data.items()):
            icon = status_colors.get(status, "⚪")
            col.metric(f"{icon} {status.capitalize()}", count)

    st.divider()
    st.markdown("#### Danger Zone")
    confirm = st.checkbox("I want to delete ALL jobs from the database")
    if confirm:
        if st.button("🗑 Clear All Jobs", type="primary", use_container_width=True):
            with _connect() as conn:
                conn.execute("DELETE FROM jobs")
            st.success("All jobs deleted.")
            st.rerun()

# ---------------------------------------------------------------------------
# Tab: Settings
# ---------------------------------------------------------------------------
with tab_settings:
    st.markdown('<p class="section-heading">Settings</p>', unsafe_allow_html=True)

    # ── Gemini API Key ──────────────────────────────────────────────────────
    st.markdown("#### Gemini API Key")
    st.caption(
        "Get a free key at https://aistudio.google.com/app/apikey — "
        "click **Create API key**, no credit card needed."
    )

    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    _current_key = os.environ.get("GEMINI_API_KEY", "")

    with st.form("api_key_form"):
        new_key = st.text_input(
            "GEMINI_API_KEY",
            value=_current_key,
            type="password",
            placeholder="AIzaSy...",
        )
        key_saved = st.form_submit_button("💾 Save API Key", use_container_width=True)
        if key_saved:
            new_key = new_key.strip()
            # Read existing .env, update or add the key line
            lines = []
            if os.path.exists(_env_path):
                with open(_env_path, encoding="utf-8") as f:
                    lines = f.readlines()
            key_line = f"GEMINI_API_KEY={new_key}\n"
            updated = False
            for i, line in enumerate(lines):
                if line.startswith("GEMINI_API_KEY="):
                    lines[i] = key_line
                    updated = True
                    break
            if not updated:
                lines.insert(0, key_line)
            with open(_env_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
            os.environ["GEMINI_API_KEY"] = new_key
            st.success("API key saved to .env. Restart the app if scoring was failing.")
            st.rerun()

    if _current_key and len(_current_key) > 10:
        st.success(f"✓ Key is set ({len(_current_key)} chars)")
    else:
        st.error("✗ No API key set — scoring and CV building will fail.")

    st.divider()
    st.markdown("#### Master CV Path")
    st.caption(
        "Point the pipeline to your master CV file. "
        "Leave blank to use `master_cv.md` in the project directory."
    )

    current_path = get_cv_path()
    stored_path  = get_setting("master_cv_path", "")

    with st.form("cv_path_form"):
        new_path = st.text_input(
            "Absolute path to master CV",
            value=stored_path,
            placeholder=r"e.g. C:\Users\you\Documents\my_cv.md",
        )
        saved = st.form_submit_button("💾 Save Path", use_container_width=True)
        if saved:
            set_setting("master_cv_path", new_path.strip())
            st.success("Path saved.")
            st.rerun()

    if os.path.exists(current_path):
        st.success(f"✓ CV found: `{current_path}`")
    else:
        st.error(f"✗ CV not found: `{current_path}`")

    st.divider()
    st.markdown("#### Role Profile Names & CV Paths")
    st.caption(
        "Rename profiles and optionally point each one to a different source CV. "
        "Leave CV path blank to use the master CV above."
    )

    for pid in [1, 2, 3]:
        with st.expander(f"Profile {pid} — {get_profile_name(pid)}", expanded=False):
            with st.form(f"profile_{pid}_form"):
                p_name = st.text_input(
                    "Profile name",
                    value=get_setting(f"profile_{pid}_name", ""),
                    placeholder=["", "Cybersecurity/GRC", "Product Owner", "Requirements/BA"][pid],
                )
                p_path = st.text_input(
                    "Custom CV path (optional)",
                    value=get_setting(f"profile_{pid}_cv_path", ""),
                    placeholder=r"e.g. C:\Users\you\Documents\cybersec_cv.md  (blank = use master CV)",
                )
                p_saved = st.form_submit_button(f"💾 Save Profile {pid}", use_container_width=True)
                if p_saved:
                    set_setting(f"profile_{pid}_name", p_name.strip())
                    set_setting(f"profile_{pid}_cv_path", p_path.strip())
                    st.success("Saved.")
                    st.rerun()
            p_cv = get_profile_cv_path(pid)
            if os.path.exists(p_cv):
                st.success(f"✓ CV: `{p_cv}`")
            else:
                st.error(f"✗ CV not found: `{p_cv}`")

    st.divider()
    st.markdown("#### Score Model")
    st.caption("Job scoring uses a lightweight model to save tokens. CV building always uses the full model.")
    from llm import MODEL as CV_MODEL, SCORE_MODEL
    st.info(f"**Score model:** `{SCORE_MODEL}`  |  **CV model:** `{CV_MODEL}`\n\n"
            "Change via `GEMINI_SCORE_MODEL` / `GEMINI_MODEL` in your `.env` file.")
