"""
health.py — Health check for the whole pipeline. Makes no AI calls unless --models is given.

Usage:
    python -m jobpilot.pipeline.health
    python -m jobpilot.pipeline.health --models    # also list the models your key can use
"""
import argparse
import os
import tempfile

from .. import db, generator, llm, paths, plugins
from . import base_cvs

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


def _check(label: str, status: str, detail: str = "") -> bool:
    line = f"  {label:<24}: {status}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return status == PASS


def run(show_models: bool = False) -> tuple[int, int]:
    db.init_db()
    print("\n=== JobPilot Health Report ===\n")
    print(f"  Data folder: {paths.HOME}")
    loaded = plugins.load_plugins()
    print(f"  Add-ons: {', '.join(loaded) if loaded else 'none'}")
    for err in plugins.errors:
        print(f"  Add-on error: {err}")
    print()
    results = []

    required = {"jobs", "profile", "certificates", "searches", "role_cvs", "settings", "role_profiles"}
    with db._connect() as conn:
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        active_searches = conn.execute("SELECT COUNT(*) FROM searches WHERE active=1").fetchone()[0]
        cert_count = conn.execute("SELECT COUNT(*) FROM certificates WHERE is_active=1").fetchone()[0]
    missing = required - existing
    results.append(_check("Database", FAIL if missing else PASS,
                          f"missing: {', '.join(sorted(missing))}" if missing else ""))

    profiles = db.get_role_profiles()
    results.append(_check("Role profiles", PASS if profiles else FAIL,
                          ", ".join(p["name"] for p in profiles) or "none — add one in Settings"))

    results.append(_check("Searches", PASS if active_searches else WARN,
                          f"{active_searches} active" if active_searches
                          else "none yet — add some in the Searches tab"))

    cv_path = db.get_cv_path()
    if not os.path.exists(cv_path):
        results.append(_check("Master CV", FAIL, f"not found at: {cv_path}"))
    else:
        size = len(open(cv_path, encoding="utf-8").read().strip())
        results.append(_check("Master CV", PASS if size >= 200 else WARN,
                              f"{size} chars — {cv_path}"))

    combos = base_cvs.all_combos()
    role_cvs = db.get_role_cvs()
    found = sum(1 for c in combos if c in role_cvs and paths.resolve(role_cvs[c]["cv_path"]).exists())
    status = PASS if combos and found == len(combos) else WARN
    results.append(_check("Base CVs", status, f"{found}/{len(combos)} built"))

    with tempfile.TemporaryDirectory() as tmp:
        sample = os.path.join(tmp, "sample.md")
        with open(sample, "w", encoding="utf-8") as f:
            f.write("Test User\nBerlin | test@example.com\nTester\n\n## Professional Summary\n\nTest.\n")
        try:
            generator.render(sample)
            results.append(_check("Document generator", PASS))
        except Exception as exc:
            results.append(_check("Document generator", FAIL, str(exc)[:80]))

    provider = llm.active_provider()
    if not provider.available():
        results.append(_check("AI key", FAIL, f"{provider.env_key} not set — add it in Settings"))
    else:
        results.append(_check("AI key", PASS, f"{provider.label} key is set"))
        if show_models:
            try:
                models = provider.list_models()
                print(f"\n  Models available to your key ({len(models)}):")
                for name in models:
                    print(f"    {name}")
                print(f"  In use — write: {llm.model_for('write', provider)}, "
                      f"score: {llm.model_for('score', provider)}")
            except Exception as exc:
                results.append(_check("AI models", FAIL, str(exc)[:120]))

    counts = db.count_by_status()
    print(f"\n  Jobs in database: {sum(counts.values())}  (certificates: {cert_count})")
    for status, n in counts.items():
        print(f"    {status:<12}: {n}")

    passed = sum(results)
    print(f"\n  {passed}/{len(results)} checks passed.\n")
    return passed, len(results)


def main():
    parser = argparse.ArgumentParser(description="JobPilot health check")
    parser.add_argument("--models", action="store_true", help="List models available to your API key")
    args = parser.parse_args()
    run(show_models=args.models)


if __name__ == "__main__":
    main()
