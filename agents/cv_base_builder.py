"""
agents/cv_base_builder.py — Generate base CVs (3 profiles × EN/DE) using Gemini.

Usage:
    python agents/cv_base_builder.py                          # build all 6
    python agents/cv_base_builder.py --profiles 1:en 2:de    # build specific ones
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build_base_cvs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build base CVs")
    parser.add_argument(
        "--profiles", nargs="*", metavar="PROFILE:LANG",
        help="Which CVs to build, e.g. 1:en 2:de 3:en. Omit to build all 6."
    )
    args = parser.parse_args()

    profiles_to_build = None
    if args.profiles:
        profiles_to_build = []
        for token in args.profiles:
            try:
                pid_str, lang = token.split(":")
                profiles_to_build.append((int(pid_str), lang))
            except ValueError:
                print(f"ERROR: invalid profile token '{token}' — expected format like '1:en'")
                sys.exit(1)

    build_base_cvs.main(profiles_to_build=profiles_to_build)
