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
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# PATH RESOLUTION
# ---------------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import profile_paths  # noqa: E402
from atomic_write import atomic_write  # noqa: E402

KB_DIR       = Path(profile_paths.kb_dir())
SCORING_DIR  = PROJECT_ROOT / "resume-engine" / "scoring"

load_dotenv(profile_paths.env_path())

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from gemini_client import GeminiClient  # noqa: E402
import cli_art
import theme

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
DEFAULT_INPUT  = KB_DIR / "bullet-bank-keepers-audited.csv"
DEFAULT_OUTPUT = KB_DIR / "bullet-bank-keepers-audited.csv"   # in-place update
GEMS_OUTPUT    = KB_DIR / "hidden-gems.csv"

GEM_THRESHOLD  = 90    # hidden_gem_score >= 90 → hidden_gem_flag = True
SLEEP_SECONDS  = 4     # politeness delay between API calls
GEM_FLUSH_EVERY = 5    # flush scored CSV to disk every N bullets
MODEL          = "gemma-4-31b-it"   # Gemma 4 31B — best free-tier allotment

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
            cli_art.console.print(f"  {theme.colorize_icon('warning')}  '{BULLET_COL}' not found — using '{col}' instead.", soft_wrap=True)
            return col
    raise ValueError(f"Cannot find bullet text column. Headers: {headers}")


def build_system_prompt() -> str:
    """Load hidden_gem scoring rules from the scoring YAML if available."""
    rules_path = SCORING_DIR / "believability.yaml"
    rules_blob = ""
    if rules_path.exists():
        try:
            rules_blob = rules_path.read_text(encoding="utf-8")
        except Exception as e:
            cli_art.friendly_warning(
                e, "reading your scoring rules file",
                "scoring without your custom rules, so results may not match your preferences")

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


def score_bullet(system_prompt: str, bullet: str) -> dict | None:
    """Score a single bullet. Returns a dict or None on failure. Uses the
    shared GeminiClient (gemini_client.py) instead of a separate client
    library -- inherits its retry/backoff/model-fallback/sustained-
    failure detection for free. SustainedFailureError is intentionally
    not caught here -- it should propagate straight up."""
    raw, _usage = GeminiClient.generate(
        model=MODEL,
        system_instruction=system_prompt,
        contents=bullet,
        response_schema=HiddenGemSchema,
        temperature=0.0,
    )
    if raw is None:
        return None
    return GeminiClient.parse_json(raw)


def _write_scored_csv(path: str, rows: list, final_headers: list) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with atomic_write(path, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=final_headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


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

    cli_art.console.print(f"\n{theme.colorize_icon('discovery')} Loading: {args.input}", soft_wrap=True)
    rows: list[dict] = []
    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []
        rows    = list(reader)

    if not rows:
        cli_art.console.print(f"{theme.colorize_icon('warning')}  No rows found. Exiting.", soft_wrap=True)
        return

    bullet_col = detect_col(list(headers))
    cli_art.console.print(f"  {theme.colorize_icon('success')} {len(rows)} rows loaded. Bullet column: '{bullet_col}'", soft_wrap=True)

    # Determine which rows need scoring
    to_score_idx = [
        i for i, row in enumerate(rows)
        if not row.get("hidden_gem_score")  # skip already-scored rows
    ]

    if args.limit > 0:
        to_score_idx = to_score_idx[:args.limit]

    cli_art.console.print(f"  {theme.colorize_icon('evaluate')} Rows needing scoring: {len(to_score_idx)}", soft_wrap=True)

    if args.dry_run:
        cli_art.console.print(f"\n{theme.colorize_icon('discovery')} Dry-run mode — first 5 bullets that would be scored:", soft_wrap=True)
        for i in to_score_idx[:5]:
            cli_art.cli_info(f"[{i}] {rows[i].get(bullet_col, '')[:100]}")
        return

    if not to_score_idx:
        cli_art.console.print(f"{theme.colorize_icon('success')}  All rows already scored. Nothing to do.", soft_wrap=True)
        return

    system_prompt = build_system_prompt()

    # Build final header (add new cols if not present) -- computed before
    # the loop so the incremental flush below can use the same headers.
    new_cols = ["hidden_gem_score", "hidden_gem_flag", "hidden_gem_reason"]
    final_headers = list(headers) + [c for c in new_cols if c not in headers]

    gem_count    = 0
    strong_count = 0
    error_count  = 0
    scored_since_flush = 0

    for n, i in enumerate(to_score_idx, start=1):
        bullet = rows[i].get(bullet_col, "").strip()
        if not bullet:
            rows[i]["hidden_gem_score"]  = ""
            rows[i]["hidden_gem_flag"]   = ""
            rows[i]["hidden_gem_reason"] = ""
            continue

        cli_art.cli_info(f"[{n}/{len(to_score_idx)}] Scoring: {bullet[:80]}...")

        if n > 1:
            time.sleep(SLEEP_SECONDS)

        result = score_bullet(system_prompt, bullet)
        if result:
            score  = result.get("hidden_gem_score", 0)
            flag   = score >= GEM_THRESHOLD
            reason = result.get("hidden_gem_reason", "")

            rows[i]["hidden_gem_score"]  = score
            rows[i]["hidden_gem_flag"]   = flag
            rows[i]["hidden_gem_reason"] = reason

            if flag:
                gem_count += 1
                cli_art.console.print(f"    {theme.colorize_icon('gem')} GEM [{score}] {reason}", soft_wrap=True)
            elif score >= 75:
                strong_count += 1
                cli_art.console.print(f"    {theme.colorize_icon('gem')} Strong [{score}]", soft_wrap=True)
            else:
                cli_art.console.print(f"    {theme.colorize_icon('evaluate')} Score: {score}", soft_wrap=True)
        else:
            rows[i]["hidden_gem_score"]  = ""
            rows[i]["hidden_gem_flag"]   = ""
            rows[i]["hidden_gem_reason"] = "ERROR: scoring failed"
            error_count += 1

        scored_since_flush += 1
        is_last = (n == len(to_score_idx))
        if scored_since_flush >= GEM_FLUSH_EVERY or is_last:
            _write_scored_csv(args.output, rows, final_headers)
            scored_since_flush = 0
            cli_art.console.print(f"    {theme.colorize_icon('save')} Flushed scored CSV ({n}/{len(to_score_idx)} processed).", soft_wrap=True)

    cli_art.console.print(f"\n{theme.colorize_icon('success')} Scored CSV saved: {args.output}", soft_wrap=True)
    cli_art.console.print(f"   {theme.colorize_icon('gem')} Hidden Gems:  {gem_count}", soft_wrap=True)
    cli_art.console.print(f"   {theme.colorize_icon('gem')} Strong:        {strong_count}", soft_wrap=True)
    cli_art.console.print(f"   {theme.colorize_icon('error')} Errors:        {error_count}", soft_wrap=True)

    # Write gems-only CSV
    gem_rows = [r for r in rows if str(r.get("hidden_gem_flag", "")).lower() == "true"]
    if gem_rows:
        Path(args.gems).parent.mkdir(parents=True, exist_ok=True)
        with atomic_write(args.gems, newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=final_headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(gem_rows)
        cli_art.console.print(f"   {theme.colorize_icon('gem')} Gems-only CSV: {args.gems} ({len(gem_rows)} rows)", soft_wrap=True)


if __name__ == "__main__":
    main()
