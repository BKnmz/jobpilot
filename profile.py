"""
profile.py — View and update your profile details stored in jobs.db

Usage:
    python profile.py              # show current profile
    python profile.py --edit       # interactively update all fields
"""

import argparse
from db import init_db, get_profile, _connect


def show():
    profile = get_profile()
    print("\nYour current profile:")
    print("-" * 40)
    for k, v in profile.items():
        print(f"  {k:<15} {v or '(empty)'}")
    print()


def edit():
    profile = get_profile()
    print("\nUpdate your profile (press Enter to keep current value):\n")
    updates = {}
    prompts = {
        "full_name":    "Full name",
        "email":        "Email",
        "phone":        "Phone (e.g. +49 151 000 0000)",
        "location":     "Location (e.g. Munich, Germany)",
        "linkedin_url": "LinkedIn URL",
    }
    for field, label in prompts.items():
        current = profile.get(field, "")
        hint = f" [{current}]" if current else ""
        val = input(f"  {label}{hint}: ").strip()
        if val:
            updates[field] = val

    if updates:
        with _connect() as conn:
            for k, v in updates.items():
                conn.execute(
                    "UPDATE profile SET field_value=? WHERE field_name=?", (v, k)
                )
        print(f"\n{len(updates)} field(s) updated.")
    else:
        print("\nNo changes made.")

    show()


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser()
    parser.add_argument("--edit", action="store_true", help="Interactively update profile")
    args = parser.parse_args()

    if args.edit:
        edit()
    else:
        show()
