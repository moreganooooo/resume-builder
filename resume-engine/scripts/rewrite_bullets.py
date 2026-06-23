#!/usr/bin/env python3
"""
rewrite_bullets.py

Agentic rewrite loop for resume bullets.

Pipeline per bullet:
  1. Pull is_representative=True rows where next_action in (REWRITE, REVIEW)
     from bullet-bank-cluster-map.csv
  2. Rewrite using Gemini, guided by weaknesses + Tags persona + knowledge base context
  3. Re-score using the same rubric as bullet-bank-audited.py
  4. If next_action=KEEP AND manager_test=PASS  →  write to keeper CSV + update cluster map
     Else pick best version (original vs rewrite) and loop with updated notes
  5. Max 3 attempts per bullet. On failure → status=MANUAL
  6. KEEP bullets already in the cluster map are seeded into the keeper CSV at startup

Knowledge base context injected at startup:
  - cv.md                        → full career narrative (all bullets)
  - morgan-background-guide.md   → deep role context (all bullets)
  - profile.yml                  → target roles, superpowers, deal-breakers (trimmed; all bullets)
  - verified-claims.csv          → role-matched verified metrics (Treering bullets only)
  - extracted-screenshot-metrics.csv → screenshot-sourced metrics (Treering bullets only)

Usage:
  python rewrite_bullets.py                  # process all REWRITE + REVIEW reps
  python rewrite_bullets.py --limit 20       # cap for testing
  python rewrite_bullets.py --dry-run        # print prompts, no API calls

Outputs (resume-engine/knowledge_base/):
  bullet-bank-cluster-map-updated.csv   updated cluster map with rewrite results
  bullet-bank-keepers.csv               bullets that achieved KEEP + PASS
"""

import argparse
import os
import sys
import time
from datetime import datetime

import pandas as pd

# ---------------------------------------------------------------------------
# PATH RESOLUTION
# ---------------------------------------------------------------------------
# resume-engine/scripts/ → resume-engine/ → project root
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

# Add the top-level scripts/ dir to the path so we can import from orchestrator.py
TOP_SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if TOP_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, TOP_SCRIPTS_DIR)

from orchestrator import client, GeminiClient  # noqa: E402  (import after path setup)

# ---------------------------------------------------------------------------
# FILE PATHS
# ---------------------------------------------------------------------------
CLUSTER_MAP_IN  = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
CLUSTER_MAP_OUT = os.path.join(KB_DIR, "bullet-bank-cluster-map-updated.csv")
KEEPERS_OUT     = os.path.join(KB_DIR, "bullet-bank-keepers.csv")

KB_CV                 = os.path.join(KB_DIR, "cv.md")
KB_BACKGROUND         = os.path.join(KB_DIR, "morgan-background-guide.md")
KB_PROFILE            = os.path.join(KB_DIR, "profile.yml")
KB_VERIFIED_CLAIMS    = os.path.join(KB_DIR, "verified-claims.csv")
KB_SCREENSHOT_METRICS = os.path.join(KB_DIR, "extracted-screenshot-metrics.csv")

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
REWRITE_MODEL = "gemini-3.1-flash-lite"
SCORE_MODEL   = "gemini-3.1-flash-lite"
MAX_ATTEMPTS  = 3

# Seconds to sleep between API calls (keeps us inside free-tier rate limits)
SLEEP_BETWEEN_BULLETS = 8    # between each bullet's rewrite call
SLEEP_BETWEEN_SCORES  = 2    # between each scoring call
SLEEP_ON_RETRY        = 12   # extra pause before a retry attempt

SCORE_COLS = ["accuracy_score", "believability_score", "clarity_score",
              "ats_value", "manager_test"]

# Keyword patterns that indicate a Treering bullet (case-insensitive)
TREERING_KEYWORDS = ["treering", "tree ring", "yearbook"]

# ---------------------------------------------------------------------------
# PERSONA TAG MAP  (Tags column values → plain-English role context)
# ---------------------------------------------------------------------------
TAG_CONTEXT = {
    "[content]":  "content marketing, editorial strategy, brand voice, or copywriting roles",
    "[ops]":      "marketing operations, RevOps, CRM, automation, or analytics roles",
    "[email]":    "email marketing, lifecycle marketing, or CRM/ESP campaign roles",
    "[demand]":   "demand generation, paid media, or growth marketing roles",
    "[product]":  "product marketing or go-to-market strategy roles",
    "[sales]":    "B2B sales, SDR/AE, or account management roles",
    "[brand]":    "brand marketing, creative direction, or agency roles",
    "[design]":   "graphic design, visual identity, or UX/UI roles",
    "[general]":  "general marketing or cross-functional roles",
}


# ---------------------------------------------------------------------------
# KNOWLEDGE BASE LOADING
# ---------------------------------------------------------------------------

def load_text_file(path: str, label: str) -> str:
    """Load a text file and return its contents, or empty string on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        print(f"  ✅ Loaded {label} ({len(content):,} chars)")
        return content
    except Exception as e:
        print(f"  ⚠️  Could not load {label}: {e}")
        return ""


def trim_profile_yml(raw: str) -> str:
    """
    Keep only the sections of profile.yml useful for rewriting:
    target_roles, archetypes, narrative, superpowers, background_context, deal_breakers.
    Strips companies_previously_applied, compensation, location, proof_points, etc.
    """
    KEEP_SECTIONS = [
        "target_roles:", "archetypes:", "narrative:", "superpowers:",
        "background_context:", "deal_breakers:"
    ]
    STOP_SECTIONS = [
        "industries_of_genuine_fit:", "companies_previously_applied:",
        "compensation:", "location:", "cv:", "proof_points:",
        "key_recommendations:", "management_evidence:"
    ]
    lines = raw.splitlines()
    result = []
    capturing = False
    for line in lines:
        stripped = line.strip()
        if any(stripped.startswith(s) for s in KEEP_SECTIONS):
            capturing = True
        elif any(stripped.startswith(s) for s in STOP_SECTIONS):
            capturing = False
        if capturing:
            result.append(line)
    return "\n".join(result).strip()


def load_verified_claims(path: str) -> pd.DataFrame:
    """Load verified-claims.csv, keeping only Use in Resume? = Yes rows."""
    try:
        df = pd.read_csv(path)
        if "Use in Resume?" in df.columns:
            df = df[df["Use in Resume?"].str.strip().str.lower().str.startswith("yes")]
        print(f"  ✅ Loaded verified-claims ({len(df)} resume-usable rows)")
        return df
    except Exception as e:
        print(f"  ⚠️  Could not load verified-claims: {e}")
        return pd.DataFrame()


def load_screenshot_metrics(path: str) -> str:
    """Load extracted-screenshot-metrics.csv as a compact string."""
    try:
        df = pd.read_csv(path)
        content = df.to_csv(index=False)
        print(f"  ✅ Loaded screenshot metrics ({len(df)} rows)")
        return content
    except Exception as e:
        print(f"  ⚠️  Could not load screenshot metrics: {e}")
        return ""


def get_verified_claims_text(df_claims: pd.DataFrame) -> str:
    """Return verified claims as a compact CSV string (most useful columns only)."""
    if df_claims.empty:
        return ""
    cols = ["Claim / Finding", "Metric(s)", "Confidence", "Evidence / Detail"]
    available = [c for c in cols if c in df_claims.columns]
    return df_claims[available].to_csv(index=False)


def is_treering_bullet(role_company: str) -> bool:
    """Return True if the bullet is from a Treering role."""
    if not isinstance(role_company, str):
        return False
    rc = role_company.lower()
    return any(kw in rc for kw in TREERING_KEYWORDS)


class KnowledgeBase:
    """Container for all knowledge base context loaded once at startup."""

    def __init__(self):
        print("\n📚 Loading knowledge base context...")
        self.cv          = load_text_file(KB_CV,         "cv.md")
        self.background  = load_text_file(KB_BACKGROUND, "morgan-background-guide.md")
        raw_profile      = load_text_file(KB_PROFILE,    "profile.yml")
        self.profile     = trim_profile_yml(raw_profile)
        self.df_claims   = load_verified_claims(KB_VERIFIED_CLAIMS)
        self.screenshot_metrics = load_screenshot_metrics(KB_SCREENSHOT_METRICS)
        print(f"  📝 profile.yml trimmed to {len(self.profile):,} chars\n")

    def context_block_for_bullet(self, role_company: str) -> str:
        """
        Build the knowledge base context string for a single bullet.
        All bullets get cv + background + profile.
        Treering bullets additionally get verified claims + screenshot metrics.
        """
        sections = []
        if self.cv:
            sections.append(f"=== CAREER OVERVIEW (cv.md) ===\n{self.cv}")
        if self.background:
            sections.append(f"=== BACKGROUND GUIDE ===\n{self.background}")
        if self.profile:
            sections.append(
                f"=== TARGET ROLES & PROFILE (from profile.yml) ===\n"
                f"Use these to understand what roles this bullet needs to appeal to "
                f"and what to avoid.\n{self.profile}"
            )
        if is_treering_bullet(role_company):
            claims_text = get_verified_claims_text(self.df_claims)
            if claims_text:
                sections.append(
                    f"=== VERIFIED CLAIMS & METRICS (Treering — resume-usable) ===\n"
                    f"Use these to inject real, verified metrics where appropriate. "
                    f"Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                    f"{claims_text}"
                )
            if self.screenshot_metrics:
                sections.append(
                    f"=== SCREENSHOT-SOURCED METRICS ===\n{self.screenshot_metrics}"
                )
        return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def persona_context(tags: str) -> str:
    """Convert Tags cell into a readable persona hint for the prompt."""
    if not isinstance(tags, str) or not tags.strip():
        return "general marketing roles"
    parts = [TAG_CONTEXT[tag] for tag in TAG_CONTEXT if tag in tags.lower()]
    return ", ".join(parts) if parts else "general marketing roles"


# ---------------------------------------------------------------------------
# REWRITE PROMPT
# ---------------------------------------------------------------------------

REWRITE_SYSTEM = """
You are an expert resume writer specialising in B2B SaaS and marketing careers.
Your job is to rewrite a single resume bullet point so it:
  - Passes the "manager test" (a hiring manager reading fast can immediately grasp
    WHAT you did, HOW you did it, and WHY it mattered / what the result was)
  - Scores 85+ on accuracy (factually grounded, no inflation)
  - Scores 85+ on believability (sounds like a real human did this, not AI hype)
  - Is strong for the target persona/role context provided
  - Fixes every weakness listed
  - Stays under 30 words where possible; never exceeds 40 words
  - Starts with a strong past-tense action verb
  - Includes a concrete metric or outcome if one can be reasonably inferred
    from the knowledge base context provided — use ONLY verified metrics from
    the Verified Claims section; do NOT invent numbers

If you genuinely lack enough context to fix a specific weakness, note this honestly
in your reasoning — do not fabricate details.

Respond ONLY with valid JSON, no markdown fences:
{
  "rewritten_bullet": "<the new bullet text>",
  "reasoning": "<1-2 sentences explaining what you changed and why>",
  "context_gaps": "<details you couldn't fill due to missing context, or empty string>"
}
"""


def build_rewrite_prompt(bullet: str, tags: str, weaknesses: str,
                         kb_context: str, attempt: int,
                         prev_scores: dict = None) -> str:
    persona = persona_context(tags)

    prev_block = ""
    if prev_scores and attempt > 1:
        prev_block = f"""
--- PREVIOUS ATTEMPT FEEDBACK ---
Your last rewrite scored:
  accuracy_score:      {prev_scores.get('accuracy_score', 'n/a')}
  believability_score: {prev_scores.get('believability_score', 'n/a')}
  clarity_score:       {prev_scores.get('clarity_score', 'n/a')}
  ats_value:           {prev_scores.get('ats_value', 'n/a')}
  manager_test:        {prev_scores.get('manager_test', 'n/a')}
  score_notes:         {prev_scores.get('score_notes', '')}

Use these scores and notes to improve your rewrite.
"""

    kb_block = ""
    if kb_context:
        kb_block = f"""
--- KNOWLEDGE BASE CONTEXT ---
Use the following background information to inform your rewrite.
Draw on verified metrics where they strengthen the bullet.
Do NOT use metrics marked Low confidence as hard facts.

{kb_context}
"""

    return (
        f"{REWRITE_SYSTEM}\n\n"
        f"--- BULLET TO REWRITE ---\n{bullet}\n\n"
        f"--- TARGET PERSONA ---\nThis bullet should resonate for: {persona}\n\n"
        f"--- KNOWN WEAKNESSES (fix these) ---\n"
        f"{weaknesses if weaknesses and weaknesses.strip() else 'None noted — improve clarity and manager-test score generally.'}"
        f"{prev_block}{kb_block}\n"
        f"Now rewrite the bullet. Respond with JSON only."
    )


# ---------------------------------------------------------------------------
# SCORING PROMPT  (mirrors bullet-bank-audited.py rubric)
# ---------------------------------------------------------------------------

SCORE_SYSTEM = """
You are a resume quality auditor. Score the following resume bullet on five dimensions.
Respond ONLY with valid JSON, no markdown fences:
{
  "accuracy_score":      <0-100 int>,
  "believability_score": <0-100 int>,
  "clarity_score":       <0-100 int>,
  "ats_value":           <0-100 int>,
  "manager_test":        <"PASS" or "FAIL">,
  "weaknesses":          "<comma-separated issues, or empty string>",
  "score_notes":         "<1-2 sentences of overall feedback>"
}
"""


def build_score_prompt(bullet: str, tags: str) -> str:
    persona = persona_context(tags)
    return (
        f"{SCORE_SYSTEM}\n\n"
        f"--- BULLET ---\n{bullet}\n\n"
        f"--- TARGET PERSONA ---\n{persona}\n\n"
        f"Score this bullet. Respond with JSON only."
    )


def score_bullet(bullet: str, tags: str, dry_run: bool = False) -> dict:
    """Score a bullet and return a dict of score fields."""
    if dry_run:
        return {
            "accuracy_score": 90, "believability_score": 90, "clarity_score": 90,
            "ats_value": 90, "manager_test": "PASS", "weaknesses": "", "score_notes": "dry-run"
        }

    raw  = client.generate(
        model=SCORE_MODEL,
        system_instruction=SCORE_SYSTEM,
        contents=f"--- BULLET ---\n{bullet}\n\n--- TARGET PERSONA ---\n{persona_context(tags)}\n\nScore this bullet. Respond with JSON only.",
        temperature=0.0
    )
    data = GeminiClient.parse_json(raw)
    time.sleep(SLEEP_BETWEEN_SCORES)

    mgr = str(data.get("manager_test", "")).strip().upper()
    data["manager_test"] = mgr if mgr in ("PASS", "FAIL") else "FAIL"

    for col in ["accuracy_score", "believability_score", "clarity_score", "ats_value"]:
        data[col] = pd.to_numeric(data.get(col, 0), errors="coerce")

    return data


# ---------------------------------------------------------------------------
# ACTION LOGIC  (mirrors cluster_bullet_bank.py decide_action)
# ---------------------------------------------------------------------------

def decide_action(scores: dict) -> str:
    mgr           = str(scores.get("manager_test", "")).strip().upper()
    believability = pd.to_numeric(scores.get("believability_score"), errors="coerce")
    accuracy      = pd.to_numeric(scores.get("accuracy_score"),      errors="coerce")
    weaknesses    = str(scores.get("weaknesses", "")).strip()

    if pd.isna(accuracy) and pd.isna(believability):
        return "NEEDS_AUDIT"
    if mgr == "FAIL" or (pd.notna(believability) and believability < 80):
        return "REWRITE"
    if weaknesses and weaknesses.lower() not in ("", "none", "nan", "n/a"):
        return "REVIEW" if (pd.notna(accuracy) and accuracy >= 85) else "REWRITE"
    return "KEEP"


def is_keeper(scores: dict) -> bool:
    return (
        decide_action(scores) == "KEEP" and
        str(scores.get("manager_test", "")).strip().upper() == "PASS"
    )


def best_version(original_bullet: str, original_scores: dict,
                 rewritten_bullet: str, rewritten_scores: dict) -> tuple:
    """Return (bullet_text, scores) for whichever version scores higher overall."""
    def composite(s):
        vals = [pd.to_numeric(s.get(c, 0), errors="coerce") or 0
                for c in ["accuracy_score", "believability_score", "clarity_score", "ats_value"]]
        mgr_bonus = 10 if str(s.get("manager_test", "")).upper() == "PASS" else 0
        return sum(vals) + mgr_bonus
    if composite(rewritten_scores) >= composite(original_scores):
        return rewritten_bullet, rewritten_scores
    return original_bullet, original_scores


# ---------------------------------------------------------------------------
# KEEPER CSV HELPERS
# ---------------------------------------------------------------------------

KEEPER_COLS = [
    "Bullet Point", "Role / Company", "Tags",
    "accuracy_score", "believability_score", "clarity_score", "ats_value", "manager_test",
    "weaknesses", "source", "rewrite_attempts", "rewrite_reasoning", "context_gaps"
]


def load_or_init_keepers(path: str, df_map: pd.DataFrame) -> pd.DataFrame:
    if os.path.exists(path):
        print(f"  📂 Loading existing keepers: {path}")
        df = pd.read_csv(path)
        for col in KEEPER_COLS:
            if col not in df.columns:
                df[col] = ""
        return df

    print("  🌱 Seeding keeper CSV from existing KEEP+PASS bullets in cluster map...")
    mask = (
        (df_map["next_action"].str.strip().str.upper() == "KEEP") &
        (df_map["manager_test"].str.strip().str.upper() == "PASS")
    )
    df_seed = df_map[mask].copy()
    df_seed["source"]            = "original"
    df_seed["rewrite_attempts"]  = 0
    df_seed["rewrite_reasoning"] = ""
    df_seed["context_gaps"]      = ""
    for col in KEEPER_COLS:
        if col not in df_seed.columns:
            df_seed[col] = ""
    df_keepers = df_seed[KEEPER_COLS].copy()
    df_keepers.to_csv(path, index=False)
    print(f"  ✅ Keeper CSV created with {len(df_keepers)} seed bullets: {path}")
    return df_keepers


def append_keeper(df_keepers: pd.DataFrame, row: dict, path: str) -> pd.DataFrame:
    new_row = {col: row.get(col, "") for col in KEEPER_COLS}
    df_keepers = pd.concat([df_keepers, pd.DataFrame([new_row])], ignore_index=True)
    df_keepers.to_csv(path, index=False)
    return df_keepers


# ---------------------------------------------------------------------------
# MAIN PROCESSING LOOP
# ---------------------------------------------------------------------------

def process_bullet(row: pd.Series, kb: KnowledgeBase, dry_run: bool) -> dict:
    original_bullet = str(row["Bullet Point"]).strip()
    tags            = str(row.get("Tags", ""))
    weaknesses      = str(row.get("weaknesses", ""))
    role_company    = str(row.get("Role / Company", ""))
    original_scores = {col: row.get(col) for col in SCORE_COLS + ["weaknesses"]}

    kb_context     = kb.context_block_for_bullet(role_company)
    current_bullet = original_bullet
    current_scores = original_scores
    last_rewrite   = ""
    last_reasoning = ""
    last_gaps      = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"    ✏️  Attempt {attempt}/{MAX_ATTEMPTS}...")

        # --- REWRITE ---
        rw_prompt = build_rewrite_prompt(
            current_bullet, tags,
            str(current_scores.get("weaknesses", weaknesses)),
            kb_context,
            attempt=attempt,
            prev_scores=current_scores if attempt > 1 else None
        )

        if dry_run:
            rw_data = {
                "rewritten_bullet": f"[DRY RUN] {current_bullet}",
                "reasoning": "dry-run",
                "context_gaps": ""
            }
        else:
            raw = client.generate(
                model=REWRITE_MODEL,
                system_instruction=REWRITE_SYSTEM,
                contents=rw_prompt,
                temperature=0.1
            )
            rw_data = GeminiClient.parse_json(raw)

        rewritten      = rw_data.get("rewritten_bullet", "").strip()
        last_reasoning = rw_data.get("reasoning", "")
        last_gaps      = rw_data.get("context_gaps", "")

        if not rewritten:
            print(f"    ⚠️  Empty rewrite on attempt {attempt} — retrying in {SLEEP_ON_RETRY}s...")
            time.sleep(SLEEP_ON_RETRY)
            continue

        time.sleep(SLEEP_BETWEEN_BULLETS)

        # --- SCORE ---
        print(f"    📊 Scoring rewrite...")
        new_scores = score_bullet(rewritten, tags, dry_run=dry_run)
        new_action = decide_action(new_scores)

        print(f"       acc={new_scores.get('accuracy_score')} "
              f"bel={new_scores.get('believability_score')} "
              f"mgr={new_scores.get('manager_test')} "
              f"→ {new_action}")

        last_rewrite = rewritten

        if is_keeper(new_scores):
            return {
                "final_bullet":      rewritten,
                "final_scores":      new_scores,
                "status":            "KEEP",
                "rewrite_attempts":  attempt,
                "rewrite_reasoning": last_reasoning,
                "context_gaps":      last_gaps,
                "source":            "rewritten",
            }

        current_bullet, current_scores = best_version(
            original_bullet, original_scores, rewritten, new_scores
        )
        current_scores["weaknesses"] = new_scores.get("weaknesses", "")

        if attempt < MAX_ATTEMPTS:
            print(f"    🔄 Not a keeper yet — retrying in {SLEEP_ON_RETRY}s...")
            time.sleep(SLEEP_ON_RETRY)

    # All attempts exhausted — keep best version found
    print(f"    🚩 Max attempts reached — marking MANUAL.")
    final_bullet, final_scores = best_version(
        original_bullet, original_scores,
        last_rewrite if last_rewrite else original_bullet,
        current_scores
    )
    return {
        "final_bullet":      final_bullet,
        "final_scores":      final_scores,
        "status":            "MANUAL",
        "rewrite_attempts":  MAX_ATTEMPTS,
        "rewrite_reasoning": last_reasoning,
        "context_gaps":      last_gaps,
        "source":            "manual_review",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Agentic rewrite loop for resume bullets using Gemini."
    )
    parser.add_argument("--map",     default=CLUSTER_MAP_IN,  help="Input cluster map CSV")
    parser.add_argument("--output",  default=CLUSTER_MAP_OUT, help="Updated cluster map output")
    parser.add_argument("--keepers", default=KEEPERS_OUT,     help="Keeper bullets CSV")
    parser.add_argument("--limit",   type=int, default=None,  help="Cap number of bullets (for testing)")
    parser.add_argument("--dry-run", action="store_true",     help="Skip API calls, use dummy responses")
    args = parser.parse_args()

    print(f"\n📥 Loading cluster map: {args.map}")
    df_map = pd.read_csv(args.map)
    print(f"  ✅ {len(df_map)} rows loaded.")

    for col in ["next_action", "manager_test", "is_representative", "Bullet Point"]:
        if col not in df_map.columns:
            raise ValueError(f"Missing required column '{col}' in cluster map.")

    df_map["is_representative"] = df_map["is_representative"].astype(str).str.strip().str.upper() == "TRUE"
    df_map["next_action"]       = df_map["next_action"].fillna("").str.strip().str.upper()
    df_map["manager_test"]      = df_map["manager_test"].fillna("").str.strip().str.upper()

    # Initialise output columns with object dtype so pandas accepts both str and int
    # values without raising a StringDtype conflict on assignment.
    for col in ["final_bullet", "rewrite_status", "rewrite_attempts", "rewrite_reasoning", "context_gaps"]:
        if col not in df_map.columns:
            df_map[col] = pd.array([""] * len(df_map), dtype=object)
        else:
            df_map[col] = df_map[col].astype(object)

    # Also cast score columns that may have been inferred as StringDtype → object
    for col in SCORE_COLS + ["weaknesses"]:
        if col in df_map.columns:
            df_map[col] = df_map[col].astype(object)

    kb         = KnowledgeBase()
    df_keepers = load_or_init_keepers(args.keepers, df_map)

    mask = (
        df_map["is_representative"] &
        df_map["next_action"].isin(["REWRITE", "REVIEW"])
    )
    targets = df_map[mask].copy()
    if args.limit:
        targets = targets.head(args.limit)

    total = len(targets)
    print(f"\n🎯 Bullets to process: {total}")
    if args.dry_run:
        print("  🧪 DRY RUN — no real API calls will be made.")

    kept = 0
    manual = 0

    for i, (idx, row) in enumerate(targets.iterrows(), 1):
        bullet_preview = str(row["Bullet Point"])[:80]
        role_company   = str(row.get("Role / Company", ""))
        print(f"\n[{i}/{total}] {bullet_preview}...")
        print(f"  Company: {role_company}  |  Tags: {row.get('Tags', '')}")
        print(f"  Action: {row['next_action']}  |  Weaknesses: {str(row.get('weaknesses', ''))[:80]}")
        treering_label = (
            "🌳 Treering — verified claims injected"
            if is_treering_bullet(role_company)
            else "📄 Non-Treering — career context injected"
        )
        print(f"  {treering_label}")

        result = process_bullet(row, kb, dry_run=args.dry_run)

        df_map.at[idx, "final_bullet"]      = result["final_bullet"]
        df_map.at[idx, "rewrite_status"]    = result["status"]
        df_map.at[idx, "rewrite_attempts"]  = result["rewrite_attempts"]
        df_map.at[idx, "rewrite_reasoning"] = result["rewrite_reasoning"]
        df_map.at[idx, "context_gaps"]      = result["context_gaps"]
        df_map.at[idx, "next_action"]        = result["status"]

        for col in SCORE_COLS + ["weaknesses"]:
            df_map.at[idx, col] = result["final_scores"].get(col, "")

        if result["status"] == "KEEP":
            kept += 1
            keeper_row = {
                "Bullet Point":      result["final_bullet"],
                "Role / Company":    row.get("Role / Company", ""),
                "Tags":              row.get("Tags", ""),
                "source":            result["source"],
                "rewrite_attempts":  result["rewrite_attempts"],
                "rewrite_reasoning": result["rewrite_reasoning"],
                "context_gaps":      result["context_gaps"],
                **{col: result["final_scores"].get(col, "") for col in SCORE_COLS + ["weaknesses"]}
            }
            df_keepers = append_keeper(df_keepers, keeper_row, args.keepers)
            print(f"  ✅ KEEPER! Saved to {args.keepers}")
        else:
            manual += 1
            print(f"  🚩 MANUAL — best version kept in cluster map.")

        df_map.to_csv(args.output, index=False)

        if i < total:
            time.sleep(SLEEP_BETWEEN_BULLETS)

    print(f"\n{'='*60}")
    print(f"✨ Done! Processed {total} bullets.")
    print(f"   ✅ Keepers: {kept}")
    print(f"   🚩 Manual review needed: {manual}")
    print(f"   📄 Updated cluster map: {args.output}")
    print(f"   💎 Keeper CSV: {args.keepers}")
    print(f"   Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")


if __name__ == "__main__":
    main()
