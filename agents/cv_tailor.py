"""
agents/cv_tailor.py — Tailor the CV for one job.

Usage:
    python agents/cv_tailor.py --job-id 5
    python agents/cv_tailor.py --job-id 5 --lang de
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobpilot.pipeline.tailor import main

if __name__ == "__main__":
    main()
