"""
base_cvs.py — Build ready-to-send base CVs, one per (role profile, language).

Usage:
    python -m jobpilot.pipeline.base_cvs                    # all active profiles x enabled languages
    python -m jobpilot.pipeline.base_cvs --profiles 1:en 2:de
"""
import argparse
import os
import sys
import time

from .. import db, generator, languages, llm, paths


def all_combos() -> list[tuple[int, str]]:
    """Every (profile id, language) pair the user has enabled."""
    return [(p["id"], lang) for p in db.get_role_profiles() for lang in db.get_enabled_languages()]


def build(combos: list[tuple[int, str]] | None = None) -> tuple[int, int]:
    """Build the given base CVs (default: all). Returns (built, requested)."""
    db.init_db()
    paths.BASE_CV_DIR.mkdir(parents=True, exist_ok=True)
    combos = combos if combos else all_combos()
    contact = db.get_profile()
    provider = llm.active_provider()
    built = 0

    for n, (profile_id, lang) in enumerate(combos):
        role = db.get_role_profile(profile_id)
        if not role:
            print(f"  ERROR: role profile {profile_id} does not exist.")
            continue
        if lang not in languages.LANGUAGES:
            print(f"  ERROR: unknown language '{lang}'.")
            continue

        cv_path = db.get_profile_cv_path(profile_id)
        if not os.path.exists(cv_path):
            print(f"  ERROR: CV not found for '{role['name']}' at: {cv_path}")
            continue
        with open(cv_path, encoding="utf-8") as f:
            source_cv = f.read()
        if len(source_cv.strip()) < 200:
            print(f"  ERROR: CV for '{role['name']}' looks empty.")
            continue

        slug = role.get("slug") or db.slugify(role["name"])
        md_path = paths.BASE_CV_DIR / f"profile_{profile_id}_{slug}_{lang}.md"
        print(f"\n[{role['name']} / {lang}] Generating {md_path.name} ...")

        try:
            cv_text = llm.build_base_cv(source_cv, db.cert_lines(profile_id), contact, role, lang)
            md_path.write_text(cv_text, encoding="utf-8")
            docx_path = generator.render(str(md_path))
            db.upsert_role_cv(profile_id, lang, paths.relative(docx_path))
            built += 1
            print(f"  Wrote {paths.relative(docx_path)}")
        except Exception as exc:
            print(f"  ERROR: {exc}")

        if provider.min_interval and n < len(combos) - 1:
            time.sleep(provider.min_interval)

    assigned = db.assign_base_cvs_to_approved()
    print(f"\nBuilt {built}/{len(combos)} base CVs. Auto-assigned CVs to {assigned} approved job(s).")
    return built, len(combos)


def parse_combos(tokens: list[str]) -> list[tuple[int, str]]:
    combos = []
    for token in tokens:
        try:
            pid, lang = token.split(":")
            combos.append((int(pid), lang.lower()))
        except ValueError:
            raise SystemExit(f"ERROR: invalid token '{token}' — expected something like '1:en'")
    return combos


def main():
    parser = argparse.ArgumentParser(description="Build base CVs")
    parser.add_argument("--profiles", nargs="*", metavar="PROFILE:LANG",
                        help="Which CVs to build, e.g. 1:en 2:de. Omit to build all.")
    args = parser.parse_args()
    built, requested = build(parse_combos(args.profiles) if args.profiles else None)
    sys.exit(0 if built == requested else 1)


if __name__ == "__main__":
    main()
