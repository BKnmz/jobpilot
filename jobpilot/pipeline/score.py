"""
score.py — Score new jobs against the master CV.

Usage:
    python -m jobpilot.pipeline.score              # up to 10 jobs
    python -m jobpilot.pipeline.score --limit 25
"""
import argparse
import os
import sys
import time

from .. import db, llm


def score_new_jobs(limit: int = 10, pause: float | None = None) -> tuple[int, int]:
    """Score up to `limit` jobs with status 'new'. Returns (scored, errors)."""
    db.init_db()
    cv_path = db.get_cv_path()
    if not os.path.exists(cv_path):
        print(f"ERROR: master CV not found at: {cv_path}")
        return 0, 1
    with open(cv_path, encoding="utf-8") as f:
        master_cv = f.read()
    if len(master_cv.strip()) < 200:
        print("ERROR: the master CV looks empty. Fill it in first.")
        return 0, 1

    total_new = db.count_by_status().get("new", 0)
    rows = db.get_jobs_by_status("new", limit=limit)
    if not rows:
        print("No new jobs to score.")
        return 0, 0

    provider = llm.active_provider()
    model = llm.model_for("score", provider)
    wait = provider.min_interval if pause is None else pause
    profiles = db.get_role_profiles()
    names = {p["id"]: p["name"] for p in profiles}

    remaining = total_new - len(rows)
    suffix = f" ({remaining} more waiting)" if remaining > 0 else ""
    print(f"Scoring {len(rows)} of {total_new} new job(s) with {model}{suffix} ...")

    scored = errors = 0
    top: tuple | None = None

    for i, job in enumerate(rows):
        try:
            result = llm.score_job(job["title"], job["company"], job["location"],
                                   job["jd_text"] or "", master_cv, profiles)
            db.save_score(job["id"], result["score"], result["reason"], result["role_profile"],
                          result["matched"], result["missing"])
            scored += 1
            role = names.get(result["role_profile"], "?")
            print(f"  [{result['score']}/10] {role}  {job['title']} @ {job['company']}  — {result['reason']}")
            if top is None or result["score"] > top[0]:
                top = (result["score"], job["title"], job["company"], role)
        except Exception as exc:
            errors += 1
            print(f"  ERROR scoring [{job['id']}] {job['title']}: {exc}")

        if wait and i < len(rows) - 1:
            time.sleep(wait)

    print(f"\nDone. Scored {scored}/{len(rows)} jobs ({errors} errors).")
    if top:
        print(f"Top match: {top[1]} at {top[2]} (score {top[0]}, {top[3]})")
    return scored, errors


def main():
    parser = argparse.ArgumentParser(description="Score new jobs against your CV")
    parser.add_argument("--limit", type=int, default=10, help="Max jobs to score (default 10)")
    args = parser.parse_args()
    _, errors = score_new_jobs(limit=args.limit)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
