#!/usr/bin/env python3
"""reinstate_job.py -- reinstates an archived job back to the active pipeline.

Usage:
    python scripts/reinstate_job.py <archived_job_path>

This moves a job from jds/<profile>/archived/ back to jds/<profile>/ so it
reappears in the active pipeline.
"""

import os
import sys

# Ensure the project root is on sys.path so imports work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.jd_manager import reinstate_jd


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python scripts/reinstate_job.py <archived_job_path>")
        return 1

    jd_path = sys.argv[1]
    try:
        new_path = reinstate_jd(jd_path)
        print(f"Reinstated: {new_path}")
        return 0
    except Exception as e:
        print(f"Error reinstating {jd_path}: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
