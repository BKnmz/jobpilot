"""
score_jobs.py — Score all new jobs against master_cv.md using Gemini.
Called directly from the Streamlit UI or from agents/job_assessor.py.
"""
import os
import sys
import time

from db import init_db, _connect, get_cv_path
from llm import score_job

# Free-tier Gemini: 15 RPM. Wait this many seconds between calls to stay safe.
_INTER_CALL_DELAY = 4.5
# Retry up to this many times on rate-limit errors (429 / ResourceExhausted)
_MAX_RETRIES = 3


def _score_with_retry(title, company, location, jd_text, master_cv):
    """Call score_job with exponential backoff on rate-limit errors."""
    delay = 15
    for attempt in range(_MAX_RETRIES):
        try:
            return score_job(title, company, location, jd_text, master_cv)
        except Exception as e:
            msg = str(e).lower()
            is_rate = any(k in msg for k in ("429", "resource_exhausted", "quota", "rate"))
            if is_rate and attempt < _MAX_RETRIES - 1:
                print(f"    Rate limit hit — waiting {delay}s before retry {attempt+2}/{_MAX_RETRIES}...")
                time.sleep(delay)
                delay *= 2
            else:
                raise


def main():
    init_db()
    CV_PATH = get_cv_path()

    if not os.path.exists(CV_PATH):
        print("ERROR: master_cv.md not found.")
        sys.exit(1)
    with open(CV_PATH, encoding="utf-8") as f:
        master_cv = f.read()
    if len(master_cv.strip()) < 200:
        print("ERROR: master_cv.md looks empty. Fill it in first.")
        sys.exit(1)

    with _connect() as conn:
        total_new = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='new'"
        ).fetchone()[0]
        rows = conn.execute(
            "SELECT id, title, company, location, jd_text FROM jobs WHERE status='new' LIMIT 10"
        ).fetchall()

    if not rows:
        print("No new jobs to score.")
        return

    print(f"Scoring {len(rows)} of {total_new} new job(s) with Gemini (4.5s delay between calls)...")
    scored = errors = 0

    for i, row in enumerate(rows):
        job_id = row["id"]
        title, company, location = row["title"], row["company"], row["location"]
        jd_text = row["jd_text"] or ""

        try:
            result = _score_with_retry(title, company, location, jd_text, master_cv)

            score        = result["score"]
            reason       = result["reason"].replace("'", "''")
            role_profile = result["role_profile"]

            with _connect() as conn:
                conn.execute(
                    """UPDATE jobs
                       SET match_score=?, notes=?, role_profile=?, status='scored'
                       WHERE id=?""",
                    (score, reason, role_profile, job_id),
                )
            scored += 1
            print(f"  [{score}/10] profile={role_profile}  {title} @ {company}  — {reason}")

        except Exception as e:
            errors += 1
            print(f"  ERROR scoring [{job_id}] {title}: {e}")

        # Pace requests to stay within free-tier RPM limit
        if i < len(rows) - 1:
            time.sleep(_INTER_CALL_DELAY)

    print(f"\nDone. Scored {scored}/{len(rows)} jobs ({errors} errors).")


if __name__ == "__main__":
    main()
