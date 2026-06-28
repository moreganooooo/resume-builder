#!/usr/bin/env python3
"""
score_keeper_gems.py

Standalone script that reads bullet-bank-keepers-audited.csv (or any keeper CSV),
scores every CLEAN bullet for hidden gem potential using the Gemini API, and writes
two outputs:

  1. The original CSV with two new columns appended:
       hidden_gem_score   (int 0–100)
       hidden_gem_flag    (True / False)

  2. A filtered hidden-gems-only CSV for quick review.

Usage:
  python score_keeper_gems.py
  python score_keeper_gems.py --input path/to/bullets.csv --output path/to/scored.csv
  python score_keeper_gems.py --dry-run   # preview first 5 bullets, no writes
"""

import argparse
import csv
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# PATH RESOLUTION
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
KB_DIR       = PROJECT_ROOT / "resume-engine" / "knowledge_base"
SCORING_DIR  = PROJECT_ROOT / "resume-engine" / "scoring"

load_dotenv(PROJECT_ROOT / ".env")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DEFAULT_INPUT  = KB_DIR / "bullet-bank-keepers-audited.csv"
DEFAULT_OUTPUT = KB_DIR / "bullet-bank-keepers-audited.csv"   # in-place update
GEMS_OUTPUT    = KB_DIR / "hidden-gems.csv"

GEM_THRESHOLD  = 90    # hidden_gem_score >= 90 → hidden_gem_flag = True
SLEEP_SECONDS  = 4     # politeness delay between API calls
MODEL          = "gemma-4-27b-it"   # Gemma 4 31B — best free-tier allotment

BULLET_COL     = "Bullet Point"
FALLBACK_COLS  = ["bullet", "achievement", "text", "Bullet", "Achievement"]

# ---------------------------------------------------------------------------
# SCHEMA
# ---------------------------------------------------------------------------
class HiddenGemSchema(BaseModel):
    hidden_gem_score:  int  = Field(description="0-100: how memorable, rare, and evidence-rich is this bullet?")
    hidden_gem_flag:   bool = Field(description="True if hidden_gem_score >= 90")
    hidden_gem_reason: str  = Field(description="One sentence: what makes this a gem, or what holds it back")

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def detect_col(headers: list[str]) -> str:
    if BULLET_COL in headers:
        return BULLET_COL
    for col in FALLBACK_COLS:
        if col in headers:
            print(f"  ⚠️  '{BULLET_COL}' not found — using '{col}' instead.")
            return col
    raise ValueError(f"Cannot find bullet text column. Headers: {headers}")


def build_system_prompt() -> str:
    """Load hidden_gem scoring rules from the scoring YAML if available."""
    rules_path = SCORING_DIR / "believability.yaml"
    rules_blob = ""
    if rules_path.exists():
        try:
            rules_blob = rules_path.read_text(encoding="utf-8")
        except Exception:
            pass

    return f"""You are a senior resume coach and hiring manager who has reviewed thousands of resumes.

Your job is to evaluate a single resume bullet and score it for HIDDEN GEM potential.

A Hidden Gem bullet is one that:
- Contains a rare, specific, and memorable detail that most candidates would omit
- Uses concrete evidence (numbers, tools, named outcomes) that is hard to fabricate
- Would make a hiring manager pause, lean in, and think "I want to talk to this person"
- Is NOT generic, buzzword-heavy, or interchangeable with another candidate's bullet

Scoring guide:
  90-100  → Hidden Gem: rare detail, strong evidence, instantly memorable
  75-89   → Strong: specific and solid, but not stand-out rare
  50-74   → Solid: acceptable but generic or missing key evidence
  0-49    → Needs Work: vague, buzzword-heavy, or unbelievable

Additional context from scoring rules:
{rules_blob}

Return ONLY valid JSON matching the schema. Be strict — most bullets are NOT hidden gems.
"""


def score_bullet(client: genai.Client, system_prompt: str, bullet: str) -> dict | None:
    """Score a single bullet. Returns a dict or None on failure."""
    from google.genai import types
    try:
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=HiddenGemSchema,
            temperature=0.0,
        )
        response = client.models.generate_content(
            model=MODEL,
            contents=bullet,
            config=config,
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"    ⚠️  API error: {e}")
        return None


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Score keeper bullets for hidden gem potential.")
    parser.add_argument("--input",   default=str(DEFAULT_INPUT),  help="Input CSV path")
    parser.add_argument("--output",  default=str(DEFAULT_OUTPUT), help="Output CSV path (default: in-place)")
    parser.add_argument("--gems",    default=str(GEMS_OUTPUT),    help="Hidden-gems-only CSV path")
    parser.add_argument("--dry-run", action="store_true",          help="Preview first 5 bullets, no API calls")
    parser.add_argument("--limit",   type=int, default=0,          help="Only score N bullets (0 = all)")
    args = parser.parse_args()

    print(f"\n📥 Loading: {args.input}")
    rows: list[dict] = []
    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows    = list(reader)

    if not rows:
        print("⚠️  No rows found. Exiting.")
        return

    bullet_col = detect_col(list(headers))
    print(f"  ✅ {len(rows)} rows loaded. Bullet column: '{bullet_col}'")

    # Determine which rows need scoring
    to_score_idx = [
        i for i, row in enumerate(rows)
        if not row.get("hidden_gem_score")  # skip already-scored rows
    ]

    if args.limit > 0:
        to_score_idx = to_score_idx[:args.limit]

    print(f"  🎯 Rows needing scoring: {len(to_score_idx)}")

    if args.dry_run:
        print("\n🔍 Dry-run mode — first 5 bullets that would be scored:")
        for i in to_score_idx[:5]:
            print(f"  [{i}] {rows[i].get(bullet_col, '')[:100]}")
        return

    if not to_score_idx:
        print("✅  All rows already scored. Nothing to do.")
        return

    # Init client
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    client  = genai.Client(api_key=api_key)
    system_prompt = build_system_prompt()

    gem_count    = 0
    strong_count = 0
    error_count  = 0

    for n, i in enumerate(to_score_idx, start=1):
        bullet = rows[i].get(bullet_col, "").strip()
        if not bullet:
            rows[i]["hidden_gem_score"]  = ""
            rows[i]["hidden_gem_flag"]   = ""
            rows[i]["hidden_gem_reason"] = ""
            continue

        print(f"  [{n}/{len(to_score_idx)}] Scoring: {bullet[:80]}...")

        if n > 1:
            time.sleep(SLEEP_SECONDS)

        result = score_bullet(client, system_prompt, bullet)
        if result:
            score  = result.get("hidden_gem_score", 0)
            flag   = score >= GEM_THRESHOLD
            reason = result.get("hidden_gem_reason", "")

            rows[i]["hidden_gem_score"]  = score
            rows[i]["hidden_gem_flag"]   = flag
            rows[i]["hidden_gem_reason"] = reason

            if flag:
                gem_count += 1
                print(f"    💎 GEM [{score}] {reason}")
            elif score >= 75:
                strong_count += 1
                print(f"    ✨ Strong [{score}]")
            else:
                print(f"    📋 Score: {score}")
        else:
            rows[i]["hidden_gem_score"]  = ""
            rows[i]["hidden_gem_flag"]   = ""
            rows[i]["hidden_gem_reason"] = "ERROR: scoring failed"
            error_count += 1

    # Build final header (add new cols if not present)
    new_cols = ["hidden_gem_score", "hidden_gem_flag", "hidden_gem_reason"]
    final_headers = list(headers) + [c for c in new_cols if c not in headers]

    # Write main output
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=final_headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅ Scored CSV saved: {args.output}")
    print(f"   💎 Hidden Gems:  {gem_count}")
    print(f"   ✨ Strong:        {strong_count}")
    print(f"   ❌ Errors:        {error_count}")

    # Write gems-only CSV
    gem_rows = [r for r in rows if str(r.get("hidden_gem_flag", "")).lower() == "true"]
    if gem_rows:
        Path(args.gems).parent.mkdir(parents=True, exist_ok=True)
        with open(args.gems, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=final_headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(gem_rows)
        print(f"   💎 Gems-only CSV: {args.gems} ({len(gem_rows)} rows)")


if __name__ == "__main__":
    main()
