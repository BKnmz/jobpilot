"""
agents/job_assessor.py — Score new jobs against your master CV.

Usage:
    python agents/job_assessor.py
    python agents/job_assessor.py --limit 5   (default: 10)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobpilot.pipeline.score import main

if __name__ == "__main__":
    main()
