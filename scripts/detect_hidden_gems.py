#!/usr/bin/env python3
"""
detect_hidden_gems.py

Reads a scored bullets JSON file (or CSV) and flags bullets that meet the
"Hidden Gem" criteria: high believability, specific evidence, and memorable
impact that most candidates would overlook.

Inputs  (profiles/<profile>/knowledge_base/):
  bullet-bank-keepers.csv     keeper bullets with critique scores

Outputs (profiles/<profile>/knowledge_base/):
  hidden-gems.csv             subset of keepers flagged as Hidden Gems

Hidden Gem criteria (any one sufficient, all ideal):
  - hidden_gem_score  >= 90
  - hidden_gem_flag   == True
  - accuracy_score    >= 90  AND  believability_score >= 90

Usage:
  python detect_hidden_gems.py
"""

import os
import sys
import pandas as pd
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
import cli_art
import theme

KB_DIR       = profile_paths.kb_dir()

load_dotenv(profile_paths.env_path(), override=True)

KEEPERS_CSV  = os.path.join(KB_DIR, "bullet-bank-keepers.csv")
GEMS_CSV     = os.path.join(KB_DIR, "hidden-gems.csv")

# ---------------------------------------------------------------------------
# CRITERIA THRESHOLDS
# ---------------------------------------------------------------------------
GEM_SCORE_MIN        = 90   # hidden_gem_score >= this
ACCURACY_MIN         = 90   # accuracy_score   >= this (combined with believability)
BELIEVABILITY_MIN   = 90   # believability_score >= this (combined with accuracy)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    cli_art.console.print()
    cli_art.console.rule("DETECT HIDDEN GEMS", style="dim")

    if not os.path.exists(KEEPERS_CSV):
        cli_art.console.print(f"  {cli_art.ERROR} {KEEPERS_CSV} not found.", soft_wrap=True)
        cli_art.cli_warning("Run the audit + rewrite pipeline first to produce keepers.")
        return

    df = pd.read_csv(KEEPERS_CSV)
    cli_art.cli_info(f"Loaded {len(df)} bullets from {KEEPERS_CSV}")

    # Coerce score columns to numeric
    for col in ("hidden_gem_score", "accuracy_score", "believability_score"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Build gem mask
    mask = pd.Series([False] * len(df), index=df.index)

    if "hidden_gem_score" in df.columns:
        mask |= df["hidden_gem_score"] >= GEM_SCORE_MIN

    if "hidden_gem_flag" in df.columns:
        flag_col = df["hidden_gem_flag"].astype(str).str.lower()
        mask |= flag_col.isin(["true", "1", "yes"])

    if "accuracy_score" in df.columns and "believability_score" in df.columns:
        mask |= (
            (df["accuracy_score"]     >= ACCURACY_MIN) &
            (df["believability_score"] >= BELIEVABILITY_MIN)
        )

    gems = df[mask].copy()

    if len(gems) == 0:
        cli_art.cli_info("No Hidden Gems found with current thresholds.")
        cli_art.detail(
            f"Thresholds: hidden_gem_score>={GEM_SCORE_MIN}, "
            f"accuracy>={ACCURACY_MIN} + believability>={BELIEVABILITY_MIN}",
            level=cli_art.NORMAL,
        )
        return

    # Sort: hidden_gem_score desc, then believability desc
    sort_cols = [c for c in ("hidden_gem_score", "believability_score") if c in gems.columns]
    if sort_cols:
        gems = gems.sort_values(sort_cols, ascending=False)

    gems.to_csv(GEMS_CSV, index=False)
    cli_art.cli_success(
        f"Found {len(gems)} Hidden Gems out of {len(df)} keeper bullets "
        f"({len(gems)/len(df)*100:.1f}%)."
    )
    cli_art.cli_success(f"Wrote {GEMS_CSV}")

    # Preview top 5
    bullet_col = None
    for candidate in ("Bullet Point", "bullet", "achievement"):
        if candidate in gems.columns:
            bullet_col = candidate
            break
    if bullet_col is None:
        bullet_col = gems.columns[0]
    cli_art.cli_info("Top Hidden Gems:")
    for i, (_, row) in enumerate(gems.head(5).iterrows(), 1):
        gem_score = row.get("hidden_gem_score", "?")
        gem_reason = row.get("hidden_gem_reason", "")
        text = str(row[bullet_col])[:100]
        cli_art.cli_info(f"{i}. [score={gem_score}] {text}")
        if gem_reason:
            cli_art.detail(f"Reason: {gem_reason}", level=cli_art.NORMAL)

    cli_art.cli_success("Done.")


if __name__ == "__main__":
    main()
