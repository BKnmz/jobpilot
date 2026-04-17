"""
agents/job_assessor.py — Score new jobs against master_cv.md using Gemini.

Usage:
    python agents/job_assessor.py
    python agents/job_assessor.py --limit 5   (default: 10)
"""
import argparse
import os
import sys
import time

# Allow imports from the project root when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_db, _connect, get_cv_path
from llm import score_job, SCORE_MODEL

PROFILE_NAMES = {1: "Cybersecurity/GRC", 2: "Product Owner", 3: "Requirements/BA"}

_INTER_CALL_DELAY = 4.5  # seconds between API calls (free tier: 15 RPM)
_MAX_RETRIES = 3


def _score_with_retry(title, company, location, jd_text, master_cv):
    delay = 15
    for attempt in range(_MAX_RETRIES):
        try:
            return score_job(title, company, location, jd_text, master_cv)
        except Exception as e:
            msg = str(e).lower()
            is_rate = any(k in msg for k in ("429", "resource_exhausted", "quota", "rate"))
            if is_rate and attempt < _MAX_RETRIES - 1:
                print(f"    Rate limit — waiting {delay}s (retry {attempt+2}/{_MAX_RETRIES})...")
                time.sleep(delay)
                delay *= 2
            else:
                raise


def main():
    parser = argparse.ArgumentParser(description="Score new jobs with Gemini")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to score (default 10)")
    args = parser.parse_args()

    init_db()
    CV_PATH = get_cv_path()

    if not os.path.exists(CV_PATH):
        print(f"ERROR: master CV not found at: {CV_PATH}")
        sys.exit(1)
    with open(CV_PATH, encoding="utf-8") as f:
        master_cv = f.read()
    if len(master_cv.strip()) < 200:
        print("ERROR: master_cv.md looks empty. Fill it in first.")
        sys.exit(1)

    with _connect() as conn:
        total_new = conn.execute("SELECT COUNT(*) FROM jobs WHERE status='new'").fetchone()[0]
        rows = conn.execute(
            f"SELECT id, title, company, location, jd_text FROM jobs WHERE status='new' LIMIT {args.limit}"
        ).fetchall()

    if not rows:
        print("No new jobs to score.")
        return

    remaining = total_new - len(rows)
    suffix = f" ({remaining} more waiting)" if remaining > 0 else ""
    print(f"Scoring {len(rows)} of {total_new} new job(s) with {SCORE_MODEL}{suffix} ...")

    scored = 0
    top_job = None
    top_score = -1

    for i, row in enumerate(rows):
        job_id = row["id"]
        title, company, location = row["title"], row["company"], row["location"]
        jd_text = row["jd_text"] or ""

        try:
            result = _score_with_retry(title, company, location, jd_text, master_cv)
            sc = result["score"]
            reason = result["reason"]
            rp = result["role_profile"]

            with _connect() as conn:
                conn.execute(
                    """UPDATE jobs
                       SET match_score=?, notes=?, role_profile=?, status='scored'
                       WHERE id=?""",
                    (sc, reason, rp, job_id),
                )
            scored += 1
            print(f"  [{sc}/10] profile={rp} ({PROFILE_NAMES.get(rp, '?')})  {title} @ {company}  — {reason}")

            if sc > top_score:
                top_score = sc
                top_job = (title, company, sc, rp)

        except Exception as e:
            print(f"  ERROR scoring [{job_id}] {title}: {e}")

        if i < len(rows) - 1:
            time.sleep(_INTER_CALL_DELAY)

    if top_job:
        title, company, sc, rp = top_job
        print(
            f"\nScored {scored} jobs. "
            f"Top match: {title} at {company} "
            f"(score: {sc}, profile: {PROFILE_NAMES.get(rp, rp)})"
        )
    else:
        print(f"\nScored {scored}/{len(rows)} jobs.")


if __name__ == "__main__":
    main()
