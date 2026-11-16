"""Settings tab: AI provider and model, contact details, CV source, languages, role profiles."""
import os

import streamlit as st

from ... import db, languages, llm, paths
from ..common import heading

_CONTACT_LABELS = {
    "full_name": ("Full name", "Jane Doe"),
    "email": ("Email", "jane@example.com"),
    "phone": ("Phone", "+49 151 000 0000"),
    "location": ("Location", "Munich, Germany"),
    "linkedin_url": ("LinkedIn", "linkedin.com/in/janedoe"),
    "website": ("Website (optional)", "janedoe.dev"),
}


def _ai_section() -> None:
    st.markdown("#### AI provider and model")
    available = llm.providers()
    active = llm.active_provider()

    if len(available) > 1:
        names = list(available)
        chosen = st.selectbox("Provider", names, index=names.index(active.name),
                              format_func=lambda n: available[n].label)
        if chosen != active.name:
            db.set_setting("llm_provider", chosen)
            st.session_state.pop("model_list", None)
            st.rerun()

    for provider in available.values():
        current = provider.api_key()
        with st.form(f"key_form_{provider.name}"):
            st.caption(f"{provider.label} — get a key at {provider.key_url}. {provider.key_hint}")
            new_key = st.text_input(provider.env_key, value=current, type="password")
            if st.form_submit_button(f"💾 Save {provider.label} key", width="stretch"):
                paths.save_env_value(provider.env_key, new_key.strip())
                st.session_state.pop("model_list", None)
                st.success("Key saved to the .env file in your data folder.")
                st.rerun()
        if provider.name == active.name:
            if current:
                st.success(f"✓ {provider.label} key is set")
            else:
                st.error(f"✗ No {provider.label} key — scoring and CV writing will fail.")

    if not active.available():
        return

    cache = st.session_state.get("model_list")
    if st.button("🔄 Load the models my key can use"):
        try:
            st.session_state["model_list"] = (active.name, active.list_models())
        except Exception as exc:
            st.error(f"Could not list models: {exc}")
        cache = st.session_state.get("model_list")

    saved = {task: db.get_setting(f"model_{task}_{active.name}", "") for task in llm.TASKS}
    if cache and cache[0] == active.name and cache[1]:
        models = cache[1]
        with st.form("model_form"):
            picks = {}
            for task, label in (("write", "Model for writing CVs"), ("score", "Model for scoring jobs")):
                options = models if saved[task] in models or not saved[task] else [saved[task]] + models
                index = options.index(saved[task]) if saved[task] in options else 0
                picks[task] = st.selectbox(label, options, index=index)
            if st.form_submit_button("💾 Save models", width="stretch"):
                for task, model in picks.items():
                    db.set_setting(f"model_{task}_{active.name}", model)
                st.success("Models saved.")
                st.rerun()
    shown = {task: saved[task] or "chosen automatically on first use" for task in llm.TASKS}
    st.info(f"**Writing:** `{shown['write']}`  |  **Scoring:** `{shown['score']}`\n\n"
            "Providers retire models and change free limits. If calls start failing, "
            "load the model list and pick a current one.")


def _contact_section() -> None:
    st.markdown("#### Contact details")
    st.caption("Used in the header of generated CVs. Leave empty to take them from your master CV.")
    current = db.get_profile()
    with st.form("contact_form"):
        cols = st.columns(2)
        values = {}
        for i, (field, (label, placeholder)) in enumerate(_CONTACT_LABELS.items()):
            values[field] = cols[i % 2].text_input(label, value=current.get(field, ""),
                                                   placeholder=placeholder)
        if st.form_submit_button("💾 Save contact details", width="stretch"):
            db.set_profile_fields(values)
            st.success("Saved.")
            st.rerun()


def _cv_section() -> None:
    st.markdown("#### Master CV")
    st.caption("The full CV every tailored version is derived from, as a markdown file. "
               "Leave blank to use `master_cv.md` in your data folder.")
    with st.form("cv_path_form"):
        new_path = st.text_input("Absolute path to master CV", value=db.get_setting("master_cv_path", ""),
                                 placeholder=r"e.g. C:\Users\you\Documents\my_cv.md")
        if st.form_submit_button("💾 Save path", width="stretch"):
            db.set_setting("master_cv_path", new_path.strip())
            st.success("Path saved.")
            st.rerun()
    current = db.get_cv_path()
    if os.path.exists(current):
        st.success(f"✓ CV found: `{current}`")
    else:
        st.error(f"✗ CV not found: `{current}`")

    st.markdown("#### CV languages")
    enabled = db.get_enabled_languages()
    chosen = st.multiselect("Languages you apply in", languages.codes(), default=enabled,
                            format_func=lambda c: languages.get(c).native)
    if chosen and set(chosen) != set(enabled):
        db.set_setting("cv_languages", ",".join(chosen))
        st.rerun()


def _profile_form(profile: dict | None) -> None:
    pid = profile["id"] if profile else None
    p = profile or {}
    with st.form(f"role_profile_form_{pid or 'new'}", clear_on_submit=profile is None):
        name = st.text_input("Name", value=p.get("name", ""), placeholder="e.g. Data Analyst")
        keywords = st.text_input(
            "Keywords that identify this kind of job", value=p.get("keywords", ""),
            placeholder="e.g. SQL, Power BI, reporting, analytics, dashboards",
            help="The scorer uses these to decide which role profile a job belongs to.")
        headline = st.text_input("CV headline", value=p.get("headline", ""),
                                 placeholder="e.g. Data Analyst | Business Intelligence")
        focus = st.text_area(
            "What the CV should emphasise for this role", value=p.get("focus", ""), height=110,
            placeholder="e.g. Lead with analytics projects. Put data skills first. "
                        "Front-load bullets with measurable results.")
        col_a, col_b = st.columns(2)
        cert_tags = col_a.text_input("Certificate tags", value=p.get("cert_tags", ""),
                                     placeholder="e.g. data, analytics",
                                     help="Certificates with one of these tags are listed in the CV.")
        cv_path = col_b.text_input("Own source CV (optional)", value=p.get("cv_path", ""),
                                   placeholder="absolute path; blank = master CV")
        if st.form_submit_button("💾 Save role profile" if profile else "➕ Add role profile",
                                 width="stretch"):
            if not name.strip():
                st.error("Give the role profile a name.")
            else:
                db.save_role_profile(pid, name=name, keywords=keywords, headline=headline,
                                     focus=focus, cert_tags=cert_tags, cv_path=cv_path,
                                     slug=p.get("slug", ""))
                st.success("Saved.")
                st.rerun()


def _profiles_section() -> None:
    st.markdown("#### Role profiles")
    st.caption("The kinds of job you apply for. Each one gets its own base CV per language, "
               "and the scorer sorts every job into one of them.")
    for profile in db.get_role_profiles(active_only=False):
        with st.expander(profile["name"]):
            _profile_form(profile)
            source = db.get_profile_cv_path(profile["id"])
            if not os.path.exists(source):
                st.error(f"✗ Source CV not found: `{source}`")
            if st.checkbox("Delete this role profile", key=f"del_confirm_{profile['id']}"):
                if st.button("🗑 Delete", key=f"del_profile_{profile['id']}"):
                    db.delete_role_profile(profile["id"])
                    st.rerun()
    with st.expander("➕ Add a role profile"):
        _profile_form(None)


def render() -> None:
    heading("Settings")
    st.caption(f"Data folder: `{paths.HOME}`")
    _ai_section()
    st.divider()
    _contact_section()
    st.divider()
    _cv_section()
    st.divider()
    _profiles_section()
