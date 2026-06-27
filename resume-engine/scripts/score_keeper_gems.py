#!/usr/bin/env python3
"""
score_keeper_gems.py

Standalone script that reads bullet-bank-keepers-audited.csv (or any keeper CSV),
scores every CLEAN bullet for hidden gem potential using the OpenAI API, and writes
two outputs:

  1. The original CSV with two new columns appended:
       hidden_gem_score   (int 0–100)
       hidden_gem_reason  (str, brief rationale from the model)

  2. A human-readable gems report: bullet-bank-gems-report.csv
       Filtered to bullets scoring >= GEM_THRESHOLD (default 90),
       sorted by score descending, grouped by company/role.

Usage:
  python score_keeper_gems.py
  python score_keeper_gems.py --threshold 85
  python score_keeper_gems.py --input path/to/custom.csv --output path/to/out.csv
  python score_keeper_gems.py --report-only          # print report, skip writing CSV
  python score_keeper_gems.py --rescore-all          # rescore even rows that already have a score
  python score_keeper_gems.py --dry-run              # show what would be scored, no API calls

Skips rows that:
  - Already have a hidden_gem_score (unless --rescore-all is passed)
  - Have audit_status != CLEAN  (already failed or pending audit)

Reads OPENAI_API_KEY from environment (same as the rest of the pipeline).
Model defaults to gpt-4o-mini for cost efficiency — override with --model.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
from openai import OpenAI

# ── Paths (mirrors audit_keepers.py conventions) ──────────────────────────────
_SCRIPT_DIR   = Path(__file__).resolve().parent
_ENGINE_DIR   = _SCRIPT_DIR.parent
KB_DIR        = _ENGINE_DIR / "knowledge_base"

DEFAULT_INPUT  = KB_DIR / "bullet-bank-keepers-audited.csv"
DEFAULT_OUTPUT = KB_DIR / "bullet-bank-keepers-audited.csv"   # overwrites in-place
REPORT_OUTPUT  = KB_DIR / "bullet-bank-gems-report.csv"

# ── Scoring constants ──────────────────────────────────────────────────────────
GEM_THRESHOLD         = 90
STRONG_THRESHOLD      = 75
DEFAULT_MODEL         = "gpt-4o-mini"
RETRY_LIMIT           = 3
RETRY_DELAY_SECONDS   = 2

# ── Prompt ─────────────────────────────────────────────────────────────────────
GEM_SYSTEM_PROMPT = """You are an expert resume strategist and recruiter evaluator.
Your job is to identify "hidden gem" resume bullets — bullets that are
unexpectedly impressive, highly specific, or reveal rare skills/impact that
most candidates would never think to include.

Score criteria (0–100):
  90–100  Hidden Gem: specific metric or story, emotionally resonant, rare
  75–89   Strong: clear impact, good specificity, above average
  50–74   Solid: competent, but common phrasing or average impact
  0–49    Weak: vague, generic, or doesn't add signal

Return ONLY valid JSON with exactly two keys:
  "hidden_gem_score": <integer 0-100>
  "hidden_gem_reason": <one sentence explaining the score>

No markdown, no extra text, no code fences."""

GEM_USER_TEMPLATE = """Rate this resume bullet for hidden gem potential:

Company: {company}
Role: {role}
Bullet: {bullet}"""


def build_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print("❌  OPENAI_API_KEY not set. Export it before running.", file=sys.stderr)
        sys.exit(1)
    return OpenAI(api_key=api_key)


def score_bullet(client: OpenAI, company: str, role: str, bullet: str, model: str) -> dict:
    """Call the API and return {'hidden_gem_score': int, 'hidden_gem_reason': str}."""
    user_msg = GEM_USER_TEMPLATE.format(company=company, role=role, bullet=bullet)

    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": GEM_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=120,
            )
            raw = response.choices[0].message.content.strip()
            parsed = json.loads(raw)
            return {
                "hidden_gem_score":  int(parsed.get("hidden_gem_score", 0)),
                "hidden_gem_reason": str(parsed.get("hidden_gem_reason", "")),
            }
        except (json.JSONDecodeError, KeyError) as e:
            if attempt == RETRY_LIMIT:
                print(f"   ⚠️  Parse error after {RETRY_LIMIT} attempts: {e}")
                return {"hidden_gem_score": 0, "hidden_gem_reason": "parse_error"}
            time.sleep(RETRY_DELAY_SECONDS)
        except Exception as e:
            if attempt == RETRY_LIMIT:
                print(f"   ⚠️  API error after {RETRY_LIMIT} attempts: {e}")
                return {"hidden_gem_score": 0, "hidden_gem_reason": "api_error"}
            time.sleep(RETRY_DELAY_SECONDS * attempt)

    return {"hidden_gem_score": 0, "hidden_gem_reason": "unknown_error"}


def detect_bullet_column(df: pd.DataFrame) -> str:
    """Return the name of the column that holds bullet text."""
    for candidate in ("rewritten_bullet", "bullet", "bullet_text", "text", "content"):
        if candidate in df.columns:
            return candidate
    # fallback: first string column that isn't an id/status column
    for col in df.columns:
        if df[col].dtype == object and col not in (
            "audit_status", "manager_test", "cluster_id", "company", "role",
            "hidden_gem_reason", "source",
        ):
            return col
    raise ValueError(
        f"Cannot detect bullet text column. Columns found: {list(df.columns)}"
    )


def detect_company_role_columns(df: pd.DataFrame) -> tuple[str, str]:
    company_col = next((c for c in df.columns if c.lower() in ("company", "employer")), None)
    role_col    = next((c for c in df.columns if c.lower() in ("role", "title", "job_title")), None)
    return company_col or "", role_col or ""


def build_to_score_mask(df: pd.DataFrame, rescore_all: bool) -> pd.Series:
    """Return boolean mask of rows that need scoring."""
    # Only score CLEAN rows (already passed audit)
    if "audit_status" in df.columns:
        eligible = df["audit_status"].str.upper() == "CLEAN"
    else:
        eligible = pd.Series([True] * len(df), index=df.index)

    if rescore_all or "hidden_gem_score" not in df.columns:
        return eligible

    # Skip rows that already have a valid score
    already_scored = df["hidden_gem_score"].notna() & (df["hidden_gem_score"] != "")
    return eligible & ~already_scored


def print_gem_report(df: pd.DataFrame, bullet_col: str, threshold: int) -> None:
    gem_rows = df[df["hidden_gem_score"] >= threshold].copy()
    if gem_rows.empty:
        print(f"\n💎  No hidden gems found (no bullets scored >= {threshold}).")
        return

    gem_rows = gem_rows.sort_values("hidden_gem_score", ascending=False)
    print(f"\n✨  HIDDEN GEM REPORT — {len(gem_rows)} gem(s) found (score >= {threshold})\n")
    print("-" * 70)
    for _, row in gem_rows.iterrows():
        text = str(row.get(bullet_col, ""))
        company = str(row.get("company", row.get("employer", "?")))
        role    = str(row.get("role",    row.get("title",    "?")))
        score   = int(row["hidden_gem_score"])
        reason  = str(row.get("hidden_gem_reason", ""))
        print(f"  [{score}/100] {company} | {role}")
        print(f"     \"{text[:120]}{'...' if len(text) > 120 else ''}\"")
        if reason and reason not in ("parse_error", "api_error"):
            print(f"     Reason: {reason}")
        print()


def save_gems_report(df: pd.DataFrame, bullet_col: str, report_path: Path, threshold: int) -> None:
    cols = ["company", "role", bullet_col, "hidden_gem_score", "hidden_gem_reason"]
    available = [c for c in cols if c in df.columns]
    gem_rows = df[df["hidden_gem_score"] >= threshold][available].copy()
    gem_rows = gem_rows.sort_values("hidden_gem_score", ascending=False)
    gem_rows.to_csv(report_path, index=False)
    print(f"📋  Gems report saved: {report_path}  ({len(gem_rows)} rows)")


def main():
    parser = argparse.ArgumentParser(
        description="Score keeper bullets for hidden gem potential and persist scores to CSV."
    )
    parser.add_argument("--input",       default=str(DEFAULT_INPUT),
                        help="Source keeper CSV (default: bullet-bank-keepers-audited.csv)")
    parser.add_argument("--output",      default=str(DEFAULT_OUTPUT),
                        help="Destination CSV (default: overwrites input in-place)")
    parser.add_argument("--report-path", default=str(REPORT_OUTPUT),
                        help="Path for the gems report CSV")
    parser.add_argument("--threshold",   type=int, default=GEM_THRESHOLD,
                        help=f"Minimum score to flag as a gem (default: {GEM_THRESHOLD})")
    parser.add_argument("--model",       default=DEFAULT_MODEL,
                        help=f"OpenAI model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--report-only", action="store_true",
                        help="Print gem report from existing scores; skip API calls")
    parser.add_argument("--rescore-all", action="store_true",
                        help="Re-score rows that already have a hidden_gem_score")
    parser.add_argument("--dry-run",     action="store_true",
                        help="Show which rows would be scored without making API calls")
    args = parser.parse_args()

    # ── Load ──────────────────────────────────────────────────────────────────
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌  Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"🔍  Loading: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)
    print(f"   {len(df)} rows loaded.")

    bullet_col               = detect_bullet_column(df)
    company_col, role_col    = detect_company_role_columns(df)
    print(f"   Bullet column  : {bullet_col}")
    print(f"   Company column : {company_col or '(not found)'}")
    print(f"   Role column    : {role_col    or '(not found)'}")

    # Ensure score columns exist
    if "hidden_gem_score" not in df.columns:
        df["hidden_gem_score"]  = pd.NA
    if "hidden_gem_reason" not in df.columns:
        df["hidden_gem_reason"] = ""

    # ── Report-only mode ──────────────────────────────────────────────────────
    if args.report_only:
        df["hidden_gem_score"] = pd.to_numeric(df["hidden_gem_score"], errors="coerce").fillna(0)
        print_gem_report(df, bullet_col, args.threshold)
        save_gems_report(df, bullet_col, Path(args.report_path), args.threshold)
        return

    # ── Identify rows to score ─────────────────────────────────────────────────
    to_score_mask = build_to_score_mask(df, args.rescore_all)
    to_score      = df[to_score_mask]
    print(f"\n   Rows eligible for scoring : {to_score_mask.sum()}")
    print(f"   Already scored (skipping) : {(~to_score_mask).sum()}")

    if to_score.empty:
        print("\n✅  Nothing to score. All CLEAN bullets already have gem scores.")
        print("   Use --rescore-all to force a full rescore.")
        print_gem_report(df, bullet_col, args.threshold)
        save_gems_report(df, bullet_col, Path(args.report_path), args.threshold)
        return

    if args.dry_run:
        print(f"\n🧪  DRY RUN — would score {len(to_score)} bullets. No API calls made.")
        for _, row in to_score.head(10).iterrows():
            text    = str(row.get(bullet_col, ""))[:80]
            company = str(row.get(company_col, "?")) if company_col else "?"
            print(f"   • [{company}]  {text}...")
        if len(to_score) > 10:
            print(f"   ... and {len(to_score) - 10} more.")
        return

    # ── Score ─────────────────────────────────────────────────────────────────
    client = build_client()
    print(f"\n🚀  Scoring {len(to_score)} bullets with {args.model} ...\n")

    scored_count = 0
    gem_count    = 0

    for idx, row in to_score.iterrows():
        bullet  = str(row.get(bullet_col, ""))
        company = str(row.get(company_col, "")) if company_col else ""
        role    = str(row.get(role_col,    "")) if role_col    else ""

        if not bullet.strip():
            df.at[idx, "hidden_gem_score"]  = 0
            df.at[idx, "hidden_gem_reason"] = "empty_bullet"
            continue

        result = score_bullet(client, company, role, bullet, args.model)
        df.at[idx, "hidden_gem_score"]  = result["hidden_gem_score"]
        df.at[idx, "hidden_gem_reason"] = result["hidden_gem_reason"]

        scored_count += 1
        is_gem = result["hidden_gem_score"] >= args.threshold
        if is_gem:
            gem_count += 1

        label = "💎 GEM" if is_gem else ("⭐ STR" if result["hidden_gem_score"] >= STRONG_THRESHOLD else "   ---")
        print(f"  {label}  [{result['hidden_gem_score']:3d}]  {bullet[:80]}...")

        # Brief pause to avoid rate limits
        time.sleep(0.3)

    print(f"\n✅  Scored {scored_count} bullets. {gem_count} hidden gems found (>= {args.threshold}).")

    # ── Save ──────────────────────────────────────────────────────────────────
    if not args.report_only:
        output_path = Path(args.output)
        df.to_csv(output_path, index=False)
        print(f"💾  Saved updated CSV: {output_path}")

    df["hidden_gem_score"] = pd.to_numeric(df["hidden_gem_score"], errors="coerce").fillna(0)
    print_gem_report(df, bullet_col, args.threshold)
    save_gems_report(df, bullet_col, Path(args.report_path), args.threshold)


if __name__ == "__main__":
    main()
