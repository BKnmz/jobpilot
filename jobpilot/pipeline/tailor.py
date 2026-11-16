"""
tailor.py — Tailor the CV for one specific job and render it to .docx.

Usage:
    python -m jobpilot.pipeline.tailor --job-id 5
    python -m jobpilot.pipeline.tailor --job-id 5 --lang tr
"""
import argparse
import os
import re
import sys

from .. import db, generator, languages, llm, paths


def _safe_filename(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", (text or "").lower().strip())
    return re.sub(r"\s+", "_", text)[:60] or "x"


def tailor_job(job_id: int, lang: str | None = None) -> str:
    """Write a tailored CV for the job. Returns the .docx path relative to HOME."""
    db.init_db()
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"No job found with id={job_id}")

    lang = (lang or job.get("language") or languages.DEFAULT_LANGUAGE).lower()
    role = db.get_role_profile(job.get("role_profile"))

    cv_path = db.get_profile_cv_path(job.get("role_profile"))
    if not os.path.exists(cv_path):
        raise FileNotFoundError(f"Source CV not found at: {cv_path}")
    with open(cv_path, encoding="utf-8") as f:
        source_cv = f.read()

    print(f"Tailoring CV for: {job['title']} at {job['company']} "
          f"({role['name'] if role else 'no role profile'}, {lang}) ...")
    cv_text = llm.tailor_cv(job, source_cv, db.cert_lines(job.get("role_profile")),
                            db.get_profile(), role, lang)

    paths.CV_OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = f"{_safe_filename(job['company'])}_{_safe_filename(job['title'])}_{lang}_tailored"
    md_path = paths.CV_OUT_DIR / f"{base}.md"
    md_path.write_text(cv_text, encoding="utf-8")
    docx_path = generator.render(str(md_path))

    rel = paths.relative(docx_path)
    db.update_cv_path(job_id, rel)
    print(f"Saved to {rel}")
    return rel


def main():
    parser = argparse.ArgumentParser(description="Tailor the CV for one job")
    parser.add_argument("--job-id", type=int, required=True, help="Job id from the database")
    parser.add_argument("--lang", choices=languages.codes(), help="Output language (default: the job's)")
    args = parser.parse_args()
    try:
        tailor_job(args.job_id, args.lang)
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
