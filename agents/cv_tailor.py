"""
agents/cv_tailor.py — Tailor master_cv.md for a specific approved job using Gemini.

Usage:
    python agents/cv_tailor.py --job-id 5
"""
import argparse
import os
import re
import subprocess
import sys

# Allow imports from the project root when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_db, update_cv_path, get_profile, _connect, get_cv_path
from llm import tailor_cv

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR    = os.path.join(ROOT, "cv_outputs")
GEN_SCRIPT = os.path.join(ROOT, "generator.py")

# Cert query tags per role profile
CERT_TAGS = {
    1: "tags LIKE '%cybersec%' OR tags LIKE '%grc%' OR tags LIKE '%compliance%'",
    2: "tags LIKE '%product%' OR tags LIKE '%agile%' OR tags LIKE '%ai%'",
    3: "tags LIKE '%data%' OR tags LIKE '%ba%' OR tags LIKE '%cybersec%'",
}


def _safe_filename(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s]+", "_", text)
    return text[:60]


def main():
    parser = argparse.ArgumentParser(description="Tailor CV for a specific job")
    parser.add_argument("--job-id", type=int, required=True, help="Job ID from jobs.db")
    args = parser.parse_args()

    init_db()
    os.makedirs(OUT_DIR, exist_ok=True)
    CV_PATH = get_cv_path()

    # Fetch job
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, title, company, jd_text, role_profile FROM jobs WHERE id=?",
            (args.job_id,)
        ).fetchone()
    if not row:
        print(f"ERROR: No job found with id={args.job_id}")
        sys.exit(1)

    job_id, title, company, jd_text, role_profile = (
        row["id"], row["title"], row["company"],
        row["jd_text"] or "", row["role_profile"]
    )

    if not role_profile:
        print(f"ERROR: job {job_id} has no role_profile set. Score it first.")
        sys.exit(1)

    # Read master CV
    if not os.path.exists(CV_PATH):
        print(f"ERROR: master CV not found at: {CV_PATH}")
        sys.exit(1)
    with open(CV_PATH, encoding="utf-8") as f:
        master_cv = f.read()

    # Fetch profile data
    profile = get_profile()

    # Fetch certs for this role
    tag_filter = CERT_TAGS.get(role_profile, CERT_TAGS[1])
    with _connect() as conn:
        cert_rows = conn.execute(
            f"SELECT cert_name, issuer, year FROM certificates "
            f"WHERE is_active=1 AND ({tag_filter}) ORDER BY year DESC LIMIT 6"
        ).fetchall()
    certs = [
        f"{r['cert_name']} — {r['issuer']} ({r['year']})"
        if r["issuer"] and r["year"]
        else r["cert_name"]
        for r in cert_rows
    ]

    print(f"Tailoring CV for: {title} at {company} (profile {role_profile}) ...")

    # Call Gemini
    md_text = tailor_cv(
        title=title,
        company=company,
        jd_text=jd_text,
        cv_text=master_cv,
        certs=certs,
        profile=profile,
        role_profile=role_profile,
    )

    # Build output filename
    filename_base = f"{_safe_filename(company)}_{_safe_filename(title)}_tailored"
    md_path   = os.path.join(OUT_DIR, f"{filename_base}.md")
    docx_path = os.path.join(OUT_DIR, f"{filename_base}.docx")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)
    print(f"  Wrote {md_path}")

    # Render to docx
    result = subprocess.run(
        [sys.executable, GEN_SCRIPT, md_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  WARNING: generator error — {result.stderr.strip()}")
    else:
        print(f"  Rendered {docx_path}")

    # Update DB
    rel_docx = os.path.relpath(docx_path, ROOT).replace("\\", "/")
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET cv_path=?, status='approved' WHERE id=?",
            (rel_docx, job_id),
        )

    print(f"\nCV tailored for {title} at {company} using Role Profile {role_profile}. Saved to {rel_docx}")


if __name__ == "__main__":
    main()
