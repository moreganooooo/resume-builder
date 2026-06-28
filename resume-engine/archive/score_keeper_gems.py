#!/usr/bin/env python3
"""
score_keeper_gems.py

Standalone script that reads bullet-bank-keepers.csv and runs every bullet
through the Gemini critique prompt to populate score columns.  Designed
for the initial bulk-scoring pass when keepers haven't been scored yet.

This file has been SUPERSEDED by the audit loop inside orchestrator.py
(audit_and_refine_bullets) and by rewrite_bullets.py for ongoing rewrite runs.
It is archived here for reference only — do not add it back to scripts/ or
call it from the pipeline.

ARCHIVED: 2026-06-28
REPLACED BY: orchestrator.py → audit_and_refine_bullets()
"""

import os
import json
import time
import urllib.request
import pandas as pd
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # archive is 2 levels deep
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

KEEPERS_CSV = os.path.join(KB_DIR, "bullet-bank-keepers.csv")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
API_KEY      = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL     = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL        = "gemini-2.0-flash-lite"
SLEEP_SECS   = 4

SCORE_COLS = [
    "accuracy_score", "believability_score", "clarity_score",
    "ats_value", "hidden_gem_score", "hidden_gem_flag",
    "manager_test", "weaknesses", "hidden_gem_reason",
]

# ---------------------------------------------------------------------------
# GEMINI CALL
# ---------------------------------------------------------------------------

def critique_bullet(bullet_text: str) -> dict:
    prompt = (
        "You are a skeptical hiring manager reviewing resume bullets. "
        "Score the following bullet on accuracy (0-100), believability (0-100), "
        "clarity (0-100), and ATS value (0-100). "
        "hidden_gem_score (0-100): how memorable and rare is the evidence? "
        "hidden_gem_flag: true if hidden_gem_score >= 90. "
        "manager_test: PASS or FAIL. "
        "weaknesses: what's wrong, or 'None'. "
        "hidden_gem_reason: one sentence.\n\n"
        "Return JSON only with keys: accuracy_score, believability_score, clarity_score, "
        "ats_value, hidden_gem_score, hidden_gem_flag, manager_test, weaknesses, hidden_gem_reason."
    )

    payload = {
        "contents": [{"parts": [{"text": f"{prompt}\n\nBULLET: {bullet_text}"}]}],
        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
    }
    url = f"{BASE_URL}/{MODEL}:generateContent?key={API_KEY}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
            text = body["candidates"][0]["content"]["parts"][0]["text"]
            cleaned = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(cleaned)
    except Exception as e:
        print(f"    API error: {e}")
        return {}


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 60)
    print("  SCORE KEEPER GEMS  [ARCHIVED — for reference only]")
    print("=" * 60)
    print("  WARNING: This script is archived. Use orchestrator.py instead.")
    print("  Proceeding anyway for manual/diagnostic use...")
    print()

    if not os.path.exists(KEEPERS_CSV):
        print(f"  ERROR: {KEEPERS_CSV} not found.")
        return

    df = pd.read_csv(KEEPERS_CSV)
    print(f"  Loaded {len(df)} bullets from {KEEPERS_CSV}")

    # Add score columns if missing
    for col in SCORE_COLS:
        if col not in df.columns:
            df[col] = None

    bullet_col = "bullet" if "bullet" in df.columns else df.columns[0]

    scored = 0
    skipped = 0
    for i, row in df.iterrows():
        # Skip if already scored
        if pd.notna(row.get("accuracy_score")) and str(row.get("accuracy_score")).strip() != "":
            skipped += 1
            continue

        bullet_text = str(row[bullet_col])
        print(f"  [{i+1}/{len(df)}] Scoring: {bullet_text[:80]}...")

        if i > 0:
            time.sleep(SLEEP_SECS)

        result = critique_bullet(bullet_text)
        if result:
            for col in SCORE_COLS:
                if col in result:
                    df.at[i, col] = result[col]
            scored += 1
        else:
            print(f"    Skipping — no result returned.")

    df.to_csv(KEEPERS_CSV, index=False)
    print(f"\n  Scored: {scored}  |  Already scored (skipped): {skipped}")
    print(f"  Wrote updated {KEEPERS_CSV}")
    print("\n  Done.")


if __name__ == "__main__":
    main()
