#!/usr/bin/env python3
"""
detect_blank_scores.py

Scans bullet bank CSV files for rows that are missing scoring columns
(hidden_gem_score, hidden_gem_flag, hidden_gem_reason, strength_category)
and reports a summary so you know which bullets still need to be run
through score_keeper_gems.py or rewrite_bullets.py.

Usage:
  python scripts/detect_blank_scores.py
  python scripts/detect_blank_scores.py --csv path/to/bullets.csv
  python scripts/detect_blank_scores.py --fix   # writes a filtered CSV of unscored rows only

Outputs:
  - Console report of blank-score counts per file / per column
  - Optional: output/json/unscored_bullets.json  (with --fix flag)
"""

import argparse
import json
import os
from pathlib import Path

import pandas as pd
import theme

# ---------------------------------------------------------------------------
# PATH RESOLUTION
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
KB_DIR       = PROJECT_ROOT / "resume-engine" / "knowledge_base"
OUTPUT_DIR   = PROJECT_ROOT / "output" / "json"

# Columns considered "score columns" — a blank in any of these flags the row.
SCORE_COLS = [
    "hidden_gem_score",
    "hidden_gem_flag",
    "hidden_gem_reason",
    "strength_category",
]

# Default CSV files to scan (in priority order).
DEFAULT_CSVS = [
    KB_DIR / "bullet-bank-keepers-audited.csv",
    KB_DIR / "bullet-bank-clean.csv",
    KB_DIR / "bullet-bank-keepers.csv",
]

BULLET_COL      = "Bullet Point"
FALLBACK_COLS   = ["bullet", "achievement", "text", "Bullet", "Achievement"]


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def detect_bullet_col(headers: list) -> str | None:
    if BULLET_COL in headers:
        return BULLET_COL
    for col in FALLBACK_COLS:
        if col in headers:
            return col
    return None


def scan_csv(csv_path: Path) -> dict:
    """
    Scan a single CSV. Returns a report dict:
      {
        'path': str,
        'total_rows': int,
        'bullet_col': str | None,
        'missing_by_col': {col: count},   # only present score cols
        'fully_unscored_rows': int,        # rows where ALL score cols are blank
        'unscored_bullets': [str],         # bullet text for unscored rows
      }
    """
    report = {
        "path": str(csv_path),
        "total_rows": 0,
        "bullet_col": None,
        "missing_by_col": {},
        "fully_unscored_rows": 0,
        "unscored_bullets": [],
    }

    if not csv_path.exists():
        report["error"] = "File not found"
        return report

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        report["error"] = str(e)
        return report

    report["total_rows"] = len(df)
    bullet_col = detect_bullet_col(list(df.columns))
    report["bullet_col"] = bullet_col

    present_score_cols = [c for c in SCORE_COLS if c in df.columns]

    for col in present_score_cols:
        blank_mask = df[col].isna() | (df[col].astype(str).str.strip() == "")
        report["missing_by_col"][col] = int(blank_mask.sum())

    if present_score_cols:
        # A row is "fully unscored" if ALL present score cols are blank
        all_blank_mask = df[present_score_cols].apply(
            lambda col: col.isna() | (col.astype(str).str.strip() == ""), axis=0
        ).all(axis=1)
    else:
        # No score cols present at all — every row is unscored
        all_blank_mask = pd.Series([True] * len(df))
        report["note"] = "No score columns found — entire file is unscored"

    report["fully_unscored_rows"] = int(all_blank_mask.sum())

    if bullet_col and all_blank_mask.any():
        report["unscored_bullets"] = (
            df.loc[all_blank_mask, bullet_col]
            .dropna()
            .astype(str)
            .str.strip()
            .tolist()
        )

    return report


def print_report(report: dict) -> None:
    path_label = Path(report["path"]).name
    print(f"\n📄 {path_label}")

    if "error" in report:
        print(f"   {theme.ICONS['error']} Error: {report['error']}")
        return

    print(f"   Total rows:           {report['total_rows']}")
    print(f"   Fully unscored rows:  {report['fully_unscored_rows']}")

    if report.get("note"):
        print(f"   {theme.ICONS['warning']}  {report['note']}")

    if report["missing_by_col"]:
        print("   Blank counts per score column:")
        for col, count in report["missing_by_col"].items():
            status = "{theme.ICONS['success']}" if count == 0 else "{theme.ICONS['warning']} "
            print(f"     {status} {col}: {count} blank")
    else:
        print("   {theme.ICONS['warning']}  No score columns present in this file.")

    if report["fully_unscored_rows"] == 0:
        print("   {theme.ICONS['success']} All rows scored — nothing to do.")
    else:
        print(f"   🎯 Action needed: run score_keeper_gems.py to fill {report['fully_unscored_rows']} blank rows.")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Detect bullet bank rows with missing score columns."
    )
    parser.add_argument(
        "--csv",
        default=None,
        help="Path to a specific CSV to scan (default: scans all default KB CSVs).",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Write a JSON file of unscored bullets to output/json/unscored_bullets.json.",
    )
    args = parser.parse_args()

    if args.csv:
        csv_paths = [Path(args.csv)]
    else:
        csv_paths = DEFAULT_CSVS

    print("🔍 detect_blank_scores.py — scanning for unscored bullets...")

    all_reports = []
    total_unscored = 0

    for csv_path in csv_paths:
        report = scan_csv(csv_path)
        print_report(report)
        all_reports.append(report)
        total_unscored += report.get("fully_unscored_rows", 0)

    print(f"\n{'='*50}")
    print(f"Total unscored rows across all files: {total_unscored}")

    if total_unscored == 0:
        print("{theme.ICONS['success']} All bullet bank files are fully scored. Nothing to do.")
    else:
        print("🎯 Run: python scripts/score_keeper_gems.py  to fill blank scores.")

    if args.fix:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / "unscored_bullets.json"
        all_unscored = []
        for report in all_reports:
            for bullet in report.get("unscored_bullets", []):
                all_unscored.append({
                    "source_file": Path(report["path"]).name,
                    "bullet": bullet,
                })
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_unscored, f, indent=2)
        print(f"\n📥 Unscored bullets written to: {out_path} ({len(all_unscored)} rows)")


if __name__ == "__main__":
    main()
