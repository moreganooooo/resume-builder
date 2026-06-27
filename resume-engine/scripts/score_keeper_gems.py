#!/usr/bin/env python3
"""
score_keeper_gems.py

Standalone script that reads bullet-bank-keepers-audited.csv (or any keeper CSV),
scores every CLEAN bullet for hidden gem potential using the Gemini API, and writes
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
  python score_keeper_gems.py --report-only          # print verbose report, skip API calls
  python score_keeper_gems.py --rescore-all          # rescore even rows that already have a score
  python score_keeper_gems.py --dry-run              # show what would be scored, no API calls
  python score_keeper_gems.py --call-delay 6         # sleep 6s between calls (default: 4)
  python score_keeper_gems.py --checkpoint-every 20  # save every 20 bullets (default: 10)

Skips rows that:
  - Already have a numeric hidden_gem_score (unless --rescore-all is passed)
    NOTE: non-numeric values like "Unscored" are treated as un-scored and WILL be processed.
  - Have audit_status != CLEAN  (already failed or pending audit)

Reads GEMINI_API_KEY (or GOOGLE_API_KEY as fallback) from environment.
Model defaults to gemini-3.1-flash-lite — override with --model.

Rate limiting:
  CALL_DELAY_SECONDS (default 4) is slept after every successful API call.
  At 4s/call the script runs at ~15 RPM — right at the free-tier ceiling
  for flash-lite. Increase to 5–6s if you still hit 429s.
  The retry backoff (5s * 2^attempt) kicks in on top of this when a 429
  is actually returned.

Checkpointing:
  The CSV is written to disk every CHECKPOINT_EVERY (default 10) bullets.
  If the script is interrupted, re-run it without --rescore-all and it
  will skip already-scored rows and pick up where it left off.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

# ── Paths (mirrors audit_keepers.py conventions) ────────────────────────────────────────────────
SCRIPT_DIR    = Path(__file__).resolve().parent
ENGINE_DIR    = SCRIPT_DIR.parent
PROJECT_ROOT  = ENGINE_DIR.parent
KB_DIR        = ENGINE_DIR / "knowledge_base"

# Load .env if present (mirrors orchestrator.py)
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=True)
except ImportError:
    pass

DEFAULT_INPUT  = KB_DIR / "bullet-bank-keepers-audited.csv"
DEFAULT_OUTPUT = KB_DIR / "bullet-bank-keepers-audited.csv"   # overwrites in-place
REPORT_OUTPUT  = KB_DIR / "bullet-bank-gems-report.csv"

# ── Gemini API constants ──────────────────────────────────────────────────────────────────
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# ── Scoring / pacing constants ───────────────────────────────────────────────────────────────
GEM_THRESHOLD        = 90
STRONG_THRESHOLD     = 75
DEFAULT_MODEL        = "gemini-3.1-flash-lite"
RETRY_LIMIT          = 4
RETRY_DELAY_SECONDS  = 5    # base for retry backoff: 5s, 10s, 20s, 40s
RETRYABLE_STATUSES   = {429, 500, 502, 503, 504}

# Inter-call pacing: sleep this many seconds after every successful API call.
# 4s ≈ 15 RPM — right at the free-tier ceiling for flash-lite. Raise to 5–6
# if you still see 429s; lower to 2–3 on a paid tier.
CALL_DELAY_SECONDS   = 4

# Write the full CSV to disk after every N successfully scored bullets.
# Keeps at-risk data loss to at most one checkpoint window if interrupted.
CHECKPOINT_EVERY     = 10

# ── Prompt ─────────────────────────────────────────────────────────────────────────────────────
GEM_SYSTEM_PROMPT = """You are an expert resume strategist and recruiter evaluator.
Your job is to identify \"hidden gem\" resume bullets — bullets that are
unexpectedly impressive, highly specific, or reveal rare skills/impact that
most candidates would never think to include.

Score criteria (0–100):
  90–100  Hidden Gem: specific metric or story, emotionally resonant, rare
  75–89   Strong: clear impact, good specificity, above average
  50–74   Solid: competent, but common phrasing or average impact
  0–49    Weak: vague, generic, or doesn\'t add signal

Return ONLY valid JSON with exactly two keys:
  \"hidden_gem_score\": <integer 0-100>
  \"hidden_gem_reason\": <one sentence explaining the score>

No markdown, no extra text, no code fences."""

GEM_USER_TEMPLATE = """Rate this resume bullet for hidden gem potential:

Company: {company}
Role: {role}
Bullet: {bullet}"""


def get_api_key() -> str:
    """Read GEMINI_API_KEY, falling back to GOOGLE_API_KEY. Mirrors orchestrator.py."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        print(
            "❌  GEMINI_API_KEY (or GOOGLE_API_KEY) not set. "
            "Export it before running.",
            file=sys.stderr,
        )
        sys.exit(1)
    return key


def parse_json(text: str) -> dict:
    """Strip markdown fences and <|think|> blocks, then parse JSON.

    Identical to GeminiClient.parse_json() in orchestrator.py.
    """
    if not text or not text.strip():
        raise ValueError("parse_json received an empty string — the model returned no content.")

    cleaned = re.sub(
        r"<\|think\|>.*?(?:</\|think\|>|<\|/think\|>)",
        "",
        text,
        flags=re.DOTALL,
    ).strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    preview = cleaned[:300].replace("\n", " ")
    raise ValueError(
        f"JSON parse failed — could not extract valid JSON.\nRaw preview: {preview!r}"
    )


def score_bullet(api_key: str, company: str, role: str, bullet: str, model: str) -> dict:
    """Call the Gemini generateContent endpoint and return gem scores.

    Retry pattern mirrors GeminiClient.generate(): exponential backoff on
    retryable HTTP status codes (429, 5xx), up to RETRY_LIMIT attempts.
    The inter-call delay (CALL_DELAY_SECONDS / --call-delay) is applied
    by the caller AFTER this function returns successfully.
    """
    url      = f"{BASE_URL}/{model}:generateContent?key={api_key}"
    user_msg = GEM_USER_TEMPLATE.format(company=company, role=role, bullet=bullet)

    body = {
        "systemInstruction": {"parts": [{"text": GEM_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 150,
            "responseMimeType": "application/json",
        },
    }

    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            resp = requests.post(url, json=body, timeout=60)

            if resp.status_code in RETRYABLE_STATUSES:
                wait = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                print(f"   ⏳ HTTP {resp.status_code} — waiting {wait}s (attempt {attempt}/{RETRY_LIMIT})...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()

            candidate = data.get("candidates", [{}])[0]
            finish_reason = candidate.get("finishReason", "UNKNOWN")
            if finish_reason not in ("STOP", "MAX_TOKENS"):
                raise ValueError(f"Unexpected finishReason: {finish_reason}")

            raw = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
            parsed = parse_json(raw)
            return {
                "hidden_gem_score":  int(parsed.get("hidden_gem_score", 0)),
                "hidden_gem_reason": str(parsed.get("hidden_gem_reason", "")),
            }

        except (ValueError, KeyError, json.JSONDecodeError) as e:
            if attempt == RETRY_LIMIT:
                print(f"   ⚠️  Parse/structure error after {RETRY_LIMIT} attempts: {e}")
                return {"hidden_gem_score": 0, "hidden_gem_reason": "parse_error"}
            time.sleep(RETRY_DELAY_SECONDS)

        except requests.exceptions.RequestException as e:
            wait = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
            if attempt == RETRY_LIMIT:
                print(f"   ⚠️  Network error after {RETRY_LIMIT} attempts: {e}")
                return {"hidden_gem_score": 0, "hidden_gem_reason": "api_error"}
            print(f"   ⏳ Network error ({e}) — waiting {wait}s (attempt {attempt}/{RETRY_LIMIT})...")
            time.sleep(wait)

    return {"hidden_gem_score": 0, "hidden_gem_reason": "unknown_error"}


# ── Column detection ─────────────────────────────────────────────────────────────────────────────────────

_NON_BULLET_COLS = frozenset({
    "audit_status", "manager_test", "cluster_id", "company", "role",
    "hidden_gem_reason", "source", "tags", "rewrite_reasoning",
    "context_gaps", "rewrite_date", "source_cluster_id", "rewrite_attempts",
    "weaknesses", "role / company",
})

_BULLET_CANDIDATES = [
    "bullet point",
    "rewritten_bullet",
    "bullet",
    "bullet_text",
    "achievement",
    "text",
    "content",
]


def detect_bullet_column(df: pd.DataFrame) -> str:
    """Return the name of the column that holds bullet text (3-pass strategy)."""
    col_lower = {c.lower(): c for c in df.columns}

    for name in _BULLET_CANDIDATES:
        if name in col_lower:
            return col_lower[name]

    for lower, original in col_lower.items():
        if "bullet" in lower and lower not in _NON_BULLET_COLS:
            return original

    for col in df.columns:
        if df[col].dtype == object and col.lower() not in _NON_BULLET_COLS:
            return col

    raise ValueError(
        f"Cannot detect bullet text column. Columns found: {list(df.columns)}"
    )


_COMBINED_COL = "role / company"


def detect_company_role_columns(df: pd.DataFrame) -> tuple[str, str, bool]:
    """Return (company_col, role_col, is_combined)."""
    col_lower = {c.lower(): c for c in df.columns}

    if _COMBINED_COL in col_lower:
        combined = col_lower[_COMBINED_COL]
        return combined, combined, True

    company_col = next(
        (col_lower[c] for c in col_lower if c in ("company", "employer")), None
    )
    role_col = next(
        (col_lower[c] for c in col_lower if c in ("role", "title", "job_title")), None
    )
    return company_col or "", role_col or "", False


def split_role_company(value: str) -> tuple[str, str]:
    """Split 'Role / Company' string into (role, company)."""
    for sep in (" / ", " - ", " @ ", " at "):
        if sep in value:
            parts = value.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return value.strip(), ""


def build_to_score_mask(df: pd.DataFrame, rescore_all: bool) -> pd.Series:
    """Return boolean mask of rows that need scoring.

    FIX: coerce hidden_gem_score to numeric before checking — non-numeric
    strings like 'Unscored' become NaN and are correctly treated as
    needing a score. The old notna() + != '' check wrongly skipped them.
    """
    if "audit_status" in df.columns:
        eligible = df["audit_status"].str.upper() == "CLEAN"
    else:
        eligible = pd.Series([True] * len(df), index=df.index)

    if rescore_all or "hidden_gem_score" not in df.columns:
        return eligible

    numeric_scores = pd.to_numeric(df["hidden_gem_score"], errors="coerce")
    already_scored = numeric_scores.notna()
    return eligible & ~already_scored


def checkpoint_save(df: pd.DataFrame, output_path: Path, scored_count: int) -> None:
    """Write the full dataframe to disk as a mid-run checkpoint."""
    df.to_csv(output_path, index=False)
    print(f"   💾  Checkpoint saved ({scored_count} scored so far) → {output_path}")


def print_gem_report(
    df: pd.DataFrame,
    bullet_col: str,
    threshold: int,
    company_col: str = "",
    role_col: str = "",
    is_combined: bool = False,
) -> None:
    """Print a quiet summary: gem count + top 10 scores only.

    FIX: the old version printed every gem bullet to stdout on every run,
    flooding the terminal with hundreds of lines. Now prints just the count
    and a top-10 score preview. Full detail is always in the CSV report.
    Use --report-only to get the verbose per-bullet list in the terminal.
    """
    numeric_scores = pd.to_numeric(df["hidden_gem_score"], errors="coerce")
    gem_rows = df[numeric_scores >= threshold].copy()

    if gem_rows.empty:
        print(f"\n💎  No hidden gems found (no bullets scored >= {threshold}).")
        return

    gem_rows["_score_num"] = numeric_scores[gem_rows.index]
    gem_rows = gem_rows.sort_values("_score_num", ascending=False)

    top_scores = gem_rows["_score_num"].head(10).astype(int).tolist()
    print(f"\n✨  {len(gem_rows)} hidden gem(s) found (score >= {threshold}).")
    print(f"   Top scores: {', '.join(str(s) for s in top_scores)}")
    print(f"   Full report → bullet-bank-gems-report.csv\n")


def print_gem_report_verbose(
    df: pd.DataFrame,
    bullet_col: str,
    threshold: int,
    company_col: str = "",
    role_col: str = "",
    is_combined: bool = False,
) -> None:
    """Verbose gem report — prints every gem bullet to stdout.

    Called only when --report-only is passed.
    """
    numeric_scores = pd.to_numeric(df["hidden_gem_score"], errors="coerce")
    gem_rows = df[numeric_scores >= threshold].copy()

    if gem_rows.empty:
        print(f"\n💎  No hidden gems found (no bullets scored >= {threshold}).")
        return

    gem_rows["_score_num"] = numeric_scores[gem_rows.index]
    gem_rows = gem_rows.sort_values("_score_num", ascending=False)

    print(f"\n✨  HIDDEN GEM REPORT — {len(gem_rows)} gem(s) found (score >= {threshold})\n")
    print("-" * 70)
    for _, row in gem_rows.iterrows():
        text   = str(row.get(bullet_col, ""))
        score  = int(row["_score_num"])
        reason = str(row.get("hidden_gem_reason", ""))

        if is_combined and company_col:
            role, company = split_role_company(str(row.get(company_col, "")))
        else:
            company = str(row.get(company_col, "?")) if company_col else "?"
            role    = str(row.get(role_col,    "?")) if role_col    else "?"

        print(f"  [{score}/100] {company} | {role}")
        print(f"     \"{text[:120]}{'...' if len(text) > 120 else ''}\"")
        if reason and reason not in ("parse_error", "api_error"):
            print(f"     Reason: {reason}")
        print()


def save_gems_report(
    df: pd.DataFrame,
    bullet_col: str,
    report_path: Path,
    threshold: int,
    company_col: str = "",
    role_col: str = "",
) -> None:
    id_cols   = [c for c in [company_col, role_col, bullet_col] if c and c in df.columns]
    extra     = [c for c in ["hidden_gem_score", "hidden_gem_reason"] if c in df.columns]
    available = list(dict.fromkeys(id_cols + extra))

    numeric_scores = pd.to_numeric(df["hidden_gem_score"], errors="coerce")
    gem_rows = df[numeric_scores >= threshold][available].copy()
    gem_rows["_sort"] = pd.to_numeric(gem_rows["hidden_gem_score"], errors="coerce")
    gem_rows = gem_rows.sort_values("_sort", ascending=False).drop(columns=["_sort"])
    gem_rows.to_csv(report_path, index=False)
    print(f"📋  Gems report saved: {report_path}  ({len(gem_rows)} rows)")


def main():
    parser = argparse.ArgumentParser(
        description="Score keeper bullets for hidden gem potential and persist scores to CSV."
    )
    parser.add_argument("--input",            default=str(DEFAULT_INPUT),
                        help="Source keeper CSV (default: bullet-bank-keepers-audited.csv)")
    parser.add_argument("--output",           default=str(DEFAULT_OUTPUT),
                        help="Destination CSV (default: overwrites input in-place)")
    parser.add_argument("--report-path",      default=str(REPORT_OUTPUT),
                        help="Path for the gems report CSV")
    parser.add_argument("--threshold",        type=int, default=GEM_THRESHOLD,
                        help=f"Minimum score to flag as a gem (default: {GEM_THRESHOLD})")
    parser.add_argument("--model",            default=DEFAULT_MODEL,
                        help=f"Gemini model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--call-delay",       type=float, default=CALL_DELAY_SECONDS,
                        help=f"Seconds to sleep between API calls (default: {CALL_DELAY_SECONDS}). "
                             f"Increase to 5–6 if you still hit 429s.")
    parser.add_argument("--checkpoint-every", type=int, default=CHECKPOINT_EVERY,
                        help=f"Save CSV to disk every N scored bullets (default: {CHECKPOINT_EVERY}). "
                             f"Script is safely resumable after any interrupt.")
    parser.add_argument("--report-only",      action="store_true",
                        help="Print full verbose gem report from existing scores; skip API calls")
    parser.add_argument("--rescore-all",      action="store_true",
                        help="Re-score rows that already have a hidden_gem_score")
    parser.add_argument("--dry-run",          action="store_true",
                        help="Show which rows would be scored without making API calls")
    args = parser.parse_args()

    api_key = get_api_key()

    # ── Load ───────────────────────────────────────────────────────────────────────────────────────────
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌  Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"🔍  Loading: {input_path}")
    df = pd.read_csv(input_path, low_memory=False)
    print(f"   {len(df)} rows loaded.")
    print(f"   Model          : {args.model}")
    print(f"   Call delay     : {args.call_delay}s between calls")
    print(f"   Checkpoint     : every {args.checkpoint_every} bullets")

    bullet_col                         = detect_bullet_column(df)
    company_col, role_col, is_combined = detect_company_role_columns(df)
    print(f"   Bullet column  : {bullet_col}")
    if is_combined:
        print(f"   Role/Company   : {company_col} (combined — will split on scoring)")
    else:
        print(f"   Company column : {company_col or '(not found)'}")
        print(f"   Role column    : {role_col    or '(not found)'}")

    if "hidden_gem_score" not in df.columns:
        df["hidden_gem_score"]  = pd.NA
    if "hidden_gem_reason" not in df.columns:
        df["hidden_gem_reason"] = ""

    # ── Report-only mode ────────────────────────────────────────────────────────────────────
    if args.report_only:
        df["hidden_gem_score"] = pd.to_numeric(df["hidden_gem_score"], errors="coerce").fillna(0)
        print_gem_report_verbose(df, bullet_col, args.threshold, company_col, role_col, is_combined)
        save_gems_report(df, bullet_col, Path(args.report_path), args.threshold, company_col, role_col)
        return

    # ── Identify rows to score ────────────────────────────────────────────────────────────────────
    to_score_mask = build_to_score_mask(df, args.rescore_all)
    to_score      = df[to_score_mask]
    total_to_score = len(to_score)
    print(f"\n   Rows eligible for scoring : {total_to_score}")
    print(f"   Already scored (skipping) : {(~to_score_mask).sum()}")

    # FIX: removed print_gem_report() + save_gems_report() from this early-exit branch.
    # They were flooding the terminal with hundreds of bullet lines and masking --dry-run.
    # Use --report-only to print/refresh the gems report without re-scoring.
    if to_score.empty:
        print("\n✅  Nothing to score. All CLEAN bullets already have gem scores.")
        print("   Use --rescore-all to force a full rescore.")
        print("   Use --report-only to print/refresh the gems report.")
        return

    if args.dry_run:
        print(f"\n🧪  DRY RUN — would score {total_to_score} bullets with {args.call_delay}s between calls.")
        est_minutes = (total_to_score * args.call_delay) / 60
        print(f"   Estimated wall time: ~{est_minutes:.0f} min at {args.call_delay}s/call "
              f"(checkpoints every {args.checkpoint_every}).")
        for _, row in to_score.head(10).iterrows():
            text   = str(row.get(bullet_col, ""))[:80]
            rc_val = str(row.get(company_col, "?")) if company_col else "?"
            print(f"   • [{rc_val}]  {text}...")
        if total_to_score > 10:
            print(f"   ... and {total_to_score - 10} more.")
        return

    # ── Score loop ─────────────────────────────────────────────────────────────────────────────────────────
    output_path  = Path(args.output)
    est_minutes  = (total_to_score * args.call_delay) / 60
    print(f"\n🚀  Scoring {total_to_score} bullets with {args.model}")
    print(f"   Pacing: {args.call_delay}s between calls — est. ~{est_minutes:.0f} min total")
    print(f"   Checkpointing every {args.checkpoint_every} bullets to {output_path}\n")

    scored_count = 0
    gem_count    = 0

    for idx, row in to_score.iterrows():
        bullet = str(row.get(bullet_col, ""))

        if is_combined and company_col:
            role, company = split_role_company(str(row.get(company_col, "")))
        else:
            company = str(row.get(company_col, "")) if company_col else ""
            role    = str(row.get(role_col,    "")) if role_col    else ""

        if not bullet.strip():
            df.at[idx, "hidden_gem_score"]  = 0
            df.at[idx, "hidden_gem_reason"] = "empty_bullet"
            continue

        result = score_bullet(api_key, company, role, bullet, args.model)
        df.at[idx, "hidden_gem_score"]  = result["hidden_gem_score"]
        df.at[idx, "hidden_gem_reason"] = result["hidden_gem_reason"]

        scored_count += 1
        is_gem    = result["hidden_gem_score"] >= args.threshold
        is_strong = result["hidden_gem_score"] >= STRONG_THRESHOLD
        if is_gem:
            gem_count += 1

        label = "💎 GEM" if is_gem else ("⭐ STR" if is_strong else "   ---")
        print(
            f"  [{scored_count}/{total_to_score}]  {label}  "
            f"[{result['hidden_gem_score']:3d}]  {bullet[:75]}..."
        )

        # ─ Inter-call pacing ─────────────────────────────────────────────────────────────────
        time.sleep(args.call_delay)

        # ─ Checkpoint save ─────────────────────────────────────────────────────────────────
        if scored_count % args.checkpoint_every == 0:
            checkpoint_save(df, output_path, scored_count)

    print(f"\n✅  Scored {scored_count} bullets. {gem_count} hidden gems found (>= {args.threshold}).")

    # ── Final save ───────────────────────────────────────────────────────────────────────────────────────
    if not args.report_only:
        df.to_csv(output_path, index=False)
        print(f"💾  Final CSV saved: {output_path}")

    df["hidden_gem_score"] = pd.to_numeric(df["hidden_gem_score"], errors="coerce").fillna(0)
    print_gem_report(df, bullet_col, args.threshold, company_col, role_col, is_combined)
    save_gems_report(df, bullet_col, Path(args.report_path), args.threshold, company_col, role_col)


if __name__ == "__main__":
    main()
