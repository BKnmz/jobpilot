"""
build_base_cvs.py — Generate all 6 base CVs (3 profiles × EN/DE) using Gemini.
Called directly from the Streamlit UI or from agents/cv_base_builder.py.
"""
import os
import subprocess
import sys

from db import init_db, get_certs_for_role, upsert_role_cv, _connect, get_cv_path, get_profile_cv_path, get_profile_name, assign_base_cv_to_job
from llm import build_base_cv

BASE_DIR   = os.path.join(os.path.dirname(__file__), "cv_outputs", "base")
GEN_SCRIPT = os.path.join(os.path.dirname(__file__), "generator.py")

PROFILES = {
    1: {
        "name": "cybersec",
        "focus_en": (
            "Lead with Cybersecurity/GRC expertise. "
            "Skills order: Governance & Compliance first, AI Governance second, Engineering third. "
            "Front-load automotive cybersecurity bullets (ISO 21434, UN R155, CSMS, ISMS, risk management). "
            "Summary: 2-3 sentences emphasising security compliance and regulatory delivery."
        ),
        "focus_de": (
            "Gleiche Inhalte auf Deutsch. Abschnittsueberschriften: Berufsprofil, Kernkompetenzen, "
            "Berufserfahrung, Ausbildung, Zertifizierungen, Sprachen. "
            "Cybersecurity-Fachbegriffe (ISO 21434, CSMS, GRC) bleiben auf Englisch. "
            "Zusammenfassung: 2-3 Saetze mit Fokus auf Sicherheits-Compliance und regulatorische Umsetzung."
        ),
    },
    2: {
        "name": "po",
        "focus_en": (
            "Lead with Product Owner expertise. "
            "Skills order: Engineering first, Project/ALM second, AI Governance third. "
            "Front-load PO bullets: roadmap ownership, backlog, sprint planning, SAFe, MVP, AI prototyping. "
            "Summary: 2-3 sentences emphasising product delivery and agile leadership."
        ),
        "focus_de": (
            "Gleiche Inhalte auf Deutsch. Abschnittsueberschriften: Berufsprofil, Kernkompetenzen, "
            "Berufserfahrung, Ausbildung, Zertifizierungen, Sprachen. "
            "'Product Owner', 'Agile', 'Scrum', 'SAFe', 'MVP', 'Roadmap' bleiben auf Englisch. "
            "Zusammenfassung: 2-3 Saetze mit Fokus auf Produktlieferung und agile Fuehrung."
        ),
    },
    3: {
        "name": "ba",
        "focus_en": (
            "Lead with Requirements Engineering / Business Analysis expertise. "
            "Skills order: Engineering first (ASPICE, ALM, Codebeamer, traceability), Governance second. "
            "Front-load requirements and BA bullets. "
            "Summary: 2-3 sentences emphasising requirements traceability and systems engineering."
        ),
        "focus_de": (
            "Gleiche Inhalte auf Deutsch. Abschnittsueberschriften: Berufsprofil, Kernkompetenzen, "
            "Berufserfahrung, Ausbildung, Zertifizierungen, Sprachen. "
            "Fachbegriffe wie 'ASPICE', 'ALM', 'Codebeamer', 'Business Analyst' bleiben auf Englisch. "
            "Zusammenfassung: 2-3 Saetze mit Fokus auf Anforderungsmanagement und Systems Engineering."
        ),
    },
}

LANG_INSTRUCTIONS = {
    "en": (
        "Write entirely in English. "
        "Use these section headers: Professional Profile, Core Competencies, "
        "Professional Experience, Education, Certifications, Languages."
    ),
    "de": (
        "Schreibe vollstaendig auf Deutsch (ausser Fachbegriffe die im Deutschen auf Englisch benutzt werden). "
        "Verwende diese Abschnittsueberschriften: Berufsprofil, Kernkompetenzen, Berufserfahrung, "
        "Ausbildung, Zertifizierungen, Sprachen. Kein Foto, kein Geburtsdatum."
    ),
}


def _cert_lines(profile_id: int) -> list[str]:
    certs = get_certs_for_role(profile_id)
    return [f"{c['cert_name']}, {c['issuer']}, {c['year']}" for c in certs]


def main(profiles_to_build: list[tuple[int, str]] | None = None):
    init_db()
    os.makedirs(BASE_DIR, exist_ok=True)

    combos = profiles_to_build if profiles_to_build else [
        (pid, lang) for pid in [1, 2, 3] for lang in ["en", "de"]
    ]
    built = 0

    for profile_id, lang in combos:
        # Per-profile CV path (falls back to global master CV)
        CV_PATH = get_profile_cv_path(profile_id)
        if not os.path.exists(CV_PATH):
            print(f"  ERROR: CV not found for profile {profile_id} at: {CV_PATH}")
            continue
        with open(CV_PATH, encoding="utf-8") as f:
            master_cv = f.read()
        if len(master_cv.strip()) < 200:
            print(f"  ERROR: CV for profile {profile_id} looks empty.")
            continue

        name = PROFILES[profile_id]["name"]
        md_filename = f"profile_{profile_id}_{name}_{lang}.md"
        md_path     = os.path.join(BASE_DIR, md_filename)
        docx_path   = md_path.replace(".md", ".docx")

        print(f"\n[{profile_id}/{lang}] Generating {md_filename} ...")

        try:
            focus = PROFILES[profile_id]["focus_de" if lang == "de" else "focus_en"]
            certs = _cert_lines(profile_id)

            cv_text = build_base_cv(
                profile_num=profile_id,
                language=lang,
                cv_text=master_cv,
                certs=certs,
                focus_instructions=focus,
                lang_instructions=LANG_INSTRUCTIONS[lang],
            )

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(cv_text)
            print(f"  Wrote {md_path}")

            result = subprocess.run(
                [sys.executable, GEN_SCRIPT, md_path],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"  WARNING: generator error — {result.stderr.strip()}")
            else:
                print(f"  Rendered {docx_path}")

            rel_docx = os.path.relpath(docx_path, os.path.dirname(__file__))
            upsert_role_cv(profile_id, lang, rel_docx.replace("\\", "/"))
            built += 1

        except Exception as e:
            print(f"  ERROR: {e}")

    # Auto-assign base CVs to approved jobs missing a cv_path
    with _connect() as conn:
        conn.execute("""
            UPDATE jobs
            SET cv_path = (
                SELECT cv_path FROM role_cvs
                WHERE profile_id = jobs.role_profile
                  AND language   = jobs.language
            )
            WHERE status      = 'approved'
              AND cv_path      IS NULL
              AND role_profile IS NOT NULL
              AND language     IS NOT NULL
        """)
        assigned = conn.execute("SELECT changes()").fetchone()[0]

    total = len(combos)
    print(f"\nBuilt {built}/{total} base CVs. Auto-assigned CVs to {assigned} approved job(s).")


if __name__ == "__main__":
    main()
