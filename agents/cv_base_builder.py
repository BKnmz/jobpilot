"""
agents/cv_base_builder.py — Build base CVs (one per role profile and language).

Usage:
    python agents/cv_base_builder.py                          # build all
    python agents/cv_base_builder.py --profiles 1:en 2:de    # build specific ones
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobpilot.pipeline.base_cvs import main

if __name__ == "__main__":
    main()
