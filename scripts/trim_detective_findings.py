"""
trim_detective_findings.py -- projects detective-findings.csv down to the 5
columns that carry real model-facing value (authorship framing and use
caveats), dropping process-tracking/portfolio-classification columns that
don't help a builder/critique LLM call. Writes
detective-findings-trimmed.csv, which is what actually gets wired into
KB_ALLOWLIST -- not the raw file (measured: ~57,850 -> ~29,983 tokens, a
48.2% reduction).

Re-run this whenever detective-findings.csv gets new rows.

Usage:
    python trim_detective_findings.py
"""

import csv
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402
import cli_art

KB_DIR = profile_paths.kb_dir()

SOURCE_CSV = os.path.join(KB_DIR, "detective-findings.csv")
OUTPUT_CSV = os.path.join(KB_DIR, "detective-findings-trimmed.csv")

KEEP_COLUMNS = ["Source File", "Finding Type", "Best Details", "Confidence", "Use Caveat"]


def trim_detective_findings(source_csv: str = SOURCE_CSV) -> list[dict]:
    """Reads source_csv and returns rows projected to KEEP_COLUMNS."""
    with open(source_csv, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [{col: row.get(col, "") for col in KEEP_COLUMNS} for row in rows]


def main():
    if not os.path.exists(SOURCE_CSV):
        cli_art.cli_error(f"{SOURCE_CSV} not found.")
        raise SystemExit(1)
    trimmed_rows = trim_detective_findings()
    with atomic_write(OUTPUT_CSV, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KEEP_COLUMNS)
        w.writeheader()
        w.writerows(trimmed_rows)
    cli_art.console.print(f"Wrote {OUTPUT_CSV} ({len(trimmed_rows)} rows)", markup=False, soft_wrap=True)


if __name__ == "__main__":
    main()
