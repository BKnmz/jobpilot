"""
agents/pipeline_tester.py — Health check for the whole pipeline.

Usage:
    python agents/pipeline_tester.py
    python agents/pipeline_tester.py --models   # also list models your key can use
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobpilot.pipeline.health import main

if __name__ == "__main__":
    main()
