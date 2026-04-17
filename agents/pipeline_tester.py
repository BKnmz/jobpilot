"""
agents/pipeline_tester.py — Health check for the entire pipeline.

Usage:
    python agents/pipeline_tester.py
"""
import os
import subprocess
import sys
import tempfile

# Allow imports from the project root when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_db, _connect, get_cv_path, get_setting

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PASS  = "PASS "
FAIL  = "FAIL "
WARN  = "WARN "
SKIP  = "SKIP "


def _check(label: str, status: str, detail: str = ""):
    width = 30
    line = f"  {label:<{width}}: {status}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return status == PASS


def main():
    init_db()
    print("\n=== Pipeline Health Report ===\n")
    passes = 0
    total = 0

    # -------------------------------------------------------------------------
    # Test 1 — DB Schema
    # -------------------------------------------------------------------------
    total += 1
    required_tables = {"jobs", "profile", "certificates", "searches", "role_cvs"}
    with _connect() as conn:
        existing = {
            r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    missing = required_tables - existing
    if missing:
        passes += _check("DB Schema", FAIL, f"missing: {', '.join(missing)}")
    else:
        passes += _check("DB Schema", PASS)

    # -------------------------------------------------------------------------
    # Test 2 — Searches Config
    # -------------------------------------------------------------------------
    total += 1
    with _connect() as conn:
        active = conn.execute("SELECT COUNT(*) FROM searches WHERE active=1").fetchone()[0]
    if active == 0:
        passes += _check("Searches Config", WARN, "no active searches — add some in the UI")
    else:
        passes += _check("Searches Config", PASS, f"{active} active search(es)")

    # -------------------------------------------------------------------------
    # Test 3 — Master CV
    # -------------------------------------------------------------------------
    total += 1
    cv_path = get_cv_path()
    configured = get_setting("master_cv_path", "")
    cv_label = f"master_cv.md (configured: {cv_path})" if configured else "master_cv.md (default)"
    if not os.path.exists(cv_path):
        passes += _check("Master CV", FAIL, f"not found at: {cv_path}")
    else:
        with open(cv_path, encoding="utf-8") as f:
            content = f.read()
        if len(content.strip()) < 200:
            passes += _check("Master CV", WARN, f"looks empty — fill it in ({cv_path})")
        else:
            passes += _check("Master CV", PASS, f"{len(content)} chars — {cv_path}")

    # -------------------------------------------------------------------------
    # Test 4 — Base CVs registered
    # -------------------------------------------------------------------------
    total += 1
    with _connect() as conn:
        registered = conn.execute("SELECT COUNT(*) FROM role_cvs").fetchone()[0]
    found = 0
    for pid in [1, 2, 3]:
        for lang in ["en", "de"]:
            with _connect() as conn:
                row = conn.execute(
                    "SELECT cv_path FROM role_cvs WHERE profile_id=? AND language=?",
                    (pid, lang)
                ).fetchone()
            if row and os.path.exists(os.path.join(ROOT, row["cv_path"])):
                found += 1
    if found == 6:
        passes += _check("Base CVs", PASS, "all 6 present")
    elif found > 0:
        passes += _check("Base CVs", WARN, f"{found}/6 present — rebuild missing ones")
    else:
        passes += _check("Base CVs", FAIL, "none built — run Build Base CVs in the UI")

    # -------------------------------------------------------------------------
    # Test 5 — Generator smoke test
    # -------------------------------------------------------------------------
    total += 1
    gen_script = os.path.join(ROOT, "generator.py")
    if not os.path.exists(gen_script):
        passes += _check("Generator", FAIL, "generator.py not found")
    else:
        sample_md = "# Test User\ntest@example.com\n\n## Summary\n\nTest.\n"
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w",
                                         delete=False, encoding="utf-8") as tmp:
            tmp.write(sample_md)
            tmp_path = tmp.name
        try:
            res = subprocess.run(
                [sys.executable, gen_script, tmp_path],
                capture_output=True, text=True, timeout=30,
            )
            if res.returncode == 0:
                passes += _check("Generator", PASS)
            else:
                passes += _check("Generator", FAIL, res.stderr.strip()[:80])
        except Exception as e:
            passes += _check("Generator", FAIL, str(e)[:80])
        finally:
            os.unlink(tmp_path)

    # -------------------------------------------------------------------------
    # Test 6 — Gemini API key present
    # -------------------------------------------------------------------------
    total += 1
    from dotenv import load_dotenv
    load_dotenv()
    key = os.environ.get("GEMINI_API_KEY", "")
    if key and len(key) > 10:
        passes += _check("Gemini API Key", PASS, "set in environment")
    else:
        passes += _check("Gemini API Key", FAIL, "GEMINI_API_KEY not set -- copy .env.example to .env")

    # -------------------------------------------------------------------------
    # Test 7 — Job counts (informational)
    # -------------------------------------------------------------------------
    print()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM jobs GROUP BY status"
        ).fetchall()
        total_jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        cert_count = conn.execute(
            "SELECT COUNT(*) FROM certificates WHERE is_active=1"
        ).fetchone()[0]

    print(f"  {'Jobs in DB':<30}: {total_jobs}  (certs: {cert_count})")
    for row in rows:
        print(f"    {row['status']:<28}: {row['n']}")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    print(f"\n  {passes}/{total} checks passed.\n")


if __name__ == "__main__":
    main()
