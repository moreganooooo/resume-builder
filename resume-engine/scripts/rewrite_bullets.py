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
  7. On restart, bullets whose original text already appears in a prior output run
     OR in bullet-bank-keepers.csv are skipped automatically (resumable runs).

Knowledge base context injected at startup:
  - cv.md                        → role section matching bullet's company only
  - morgan-background-guide.md   → tag-keyed summary (no interview coaching / timeline noise)
  - profile.yml                  → target roles, superpowers, deal-breakers (trimmed; all bullets)
  - verified-claims.csv          → tag-filtered rows (Treering bullets only, max 15 rows)
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
import re
import sys
import time
from datetime import datetime

import pandas as pd

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")

TOP_SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if TOP_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, TOP_SCRIPTS_DIR)

from orchestrator import client, GeminiClient  # noqa: E402

CLUSTER_MAP_IN  = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
CLUSTER_MAP_OUT = os.path.join(KB_DIR, "bullet-bank-cluster-map-updated.csv")
KEEPERS_OUT     = os.path.join(KB_DIR, "bullet-bank-keepers.csv")

KB_CV                 = os.path.join(KB_DIR, "cv.md")
KB_BACKGROUND         = os.path.join(KB_DIR, "morgan-background-guide.md")
KB_PROFILE            = os.path.join(KB_DIR, "profile.yml")
KB_VERIFIED_CLAIMS    = os.path.join(KB_DIR, "verified-claims.csv")
KB_SCREENSHOT_METRICS = os.path.join(KB_DIR, "extracted-screenshot-metrics.csv")

REWRITE_MODEL = "gemini-3.1-flash-lite"
SCORE_MODEL   = "gemini-3.1-flash-lite"
MAX_ATTEMPTS  = 3

SLEEP_BETWEEN_BULLETS = 8
SLEEP_BETWEEN_SCORES  = 2
SLEEP_ON_RETRY        = 12

SCORE_COLS = ["accuracy_score", "believability_score", "clarity_score",
              "ats_value", "manager_test"]
NUMERIC_SCORE_COLS = ["accuracy_score", "believability_score", "clarity_score", "ats_value"]
STRING_SCORE_COLS  = ["manager_test", "weaknesses"]

DONE_STATUSES = {"KEEP", "MANUAL"}
TREERING_KEYWORDS = ["treering", "tree ring", "yearbook"]
MAX_CLAIMS_ROWS = 15

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

BACKGROUND_IDENTITY = """
Morgan is a creative and strategic marketer with 10+ years of experience spanning journalism,
design, agency work, sales, CRM, and lifecycle content. She is the rare combination: writes
campaigns that perform AND operates the stack (Salesforce + Outreach.io). She brings structure
to creative work and energy to technical systems. She is seeking fully remote IC roles — not
management. She has consistently been the person companies come back to: Callahan Creek extended
her from intern to freelance; Element 8's CEO recruited her to lead Strategy LLC branding;
Treering headhunted her directly from IST.
""".strip()

BACKGROUND_TAGS = {
    "[email]": """
Email / Lifecycle context:
- Owned Outreach.io as primary admin: evaluated vendors, led integration with Salesforce, drove
  team-wide adoption for a 20+ person SDR org.
- Built 62+ sequences across 4 major categories (PTA, Hot Zone, Private School, Title 1).
- PTA Council: 74% open / 22% reply / 0 opt-outs. HZ Spring 1st Touch: 85% open / 39% reply.
- Jan 2022 run: 63% avg open across 6 sequences, 8.7% reply, 3,337 prospects added.
- Personalization at scale: variable logic, behavioral triggers, segmentation by district type.
- A/B tested subject lines, CTAs, and send windows systematically.
""".strip(),
    "[ops]": """
Ops / CRM context:
- Salesforce Classic & Lightning: territory management, pipeline reporting, data hygiene at scale.
- Uncovered $3M+ in stale pipeline via systematic CRM scrub; defined KPIs, dashboards, scope.
- National Hot Zone analysis: identified high-propensity districts using Salesforce data;
  trained team on strategy; the program scaled into a dedicated research function.
- Managed 2,000+ accounts simultaneously while also managing a 4-6 person SDR team.
- Led Outreach.io/Salesforce integration: data migration, deduplication, field mapping.
""".strip(),
    "[content]": """
Content / Enablement context:
- Founded and chaired the Content Committee: cross-department body owning brand voice,
  sequence library (100+ assets), campaign QA, and content governance.
- Built voice/tone guidelines adopted team-wide; peers held to Morgan's standard as benchmark.
- Created SDR Process Map (escottmorgan.wixsite.com/processmap) — official new-hire training.
- 100+ email campaigns across niche audiences, each with unique messaging and multi-touch logic.
- Designed branded slide decks for all monthly team trainings (20+ employees); consistently
  received outstanding feedback on quality and engagement.
""".strip(),
    "[enablement]": """
Enablement / Training context:
- Developed and delivered live + async training for 20+ employees on messaging, QA, platforms.
- Created the SDR Process Map website used as official onboarding infrastructure.
- Produced onboarding playbooks, interview guides, and campaign frameworks.
- Coached a remote pod of 4-6 SDRs on sequencing strategy, CRM hygiene, and territory work.
- Content Committee governed all sales content: 100+ assets, 129 sequences, QA checklists.
""".strip(),
    "[sales]": """
Sales / SDR context:
- First outbound hire to surpass $1M in sourced revenue at Treering; exceeded Year 1 target by 17%.
- 2x Top Seller at Inside Sales Team (now Alleyoop); Top 10 company-wide in first 2 months.
- Promoted within 6 months at IST to sole manager of a 12-person SDR team.
- Treering recruited Morgan directly from IST based on exceptional performance.
- Managed 2,000+ accounts; coached a pod of 4-6 SDRs on prospecting and outreach.
""".strip(),
    "[brand]": """
Brand / Agency context:
- VML (global ad agency): campaigns for Gatorade, SAP, HughesNet; pitch deck praised by CEO;
  wrote 200+ page digital strategy report for Carlson Hotels.
- Callahan Creek: worked in a real creative pod (copywriter, art director, designer); 2 campaigns
  selected for client rollout; extended to long-term freelance.
- Built Treering's voice/tone guidelines and Content Committee governance from scratch.
""".strip(),
    "[design]": """
Design context:
- Adobe Illustrator, Photoshop, InDesign: conference flyers, brand decks, COVID response flyer
  (posted on Treering homepage), monthly training decks, Georgia PTA council presentation.
- Element 8 / Strategy LLC: designed complete brand identity from scratch; still in use 15+ years later.
- Lead Graphic Designer title at Strategy LLC; recruited specifically by the CEO for the role.
- Canva, Figma (basic), CMS/WYSIWYG editors also in toolkit.
""".strip(),
    "[generalist]": """
Generalist / cross-functional context:
- Range: journalism foundation (KU BS), agency copywriting (VML, Callahan Creek), graphic design
  (Element 8/Strategy LLC), B2B SaaS sales + CRM (Treering 8 years), AI data work (Mercor).
- Comfortable moving between writing, ops, design, and strategy without losing quality in any lane.
- Non-Treering experience spans EdTech, regulated financial copy (CACU), K-12/education audiences,
  nonprofit (Humane Society of KC), print/publishing.
""".strip(),
}

CV_SECTION_KEYWORDS = [
    (["treering", "tree ring", "yearbook"], "Treering Yearbooks"),
    (["inside sales", "alleyoop", "ist"],   "Inside Sales Team"),
    (["usitek"],                             "USitek"),
    (["element 8", "strategy llc"],         "Element 8"),
    (["vml"],                               "VML"),
    (["callahan"],                          "Callahan Creek"),
    (["unisource", "udp"],                 "Unisource"),
    (["humane society"],                    "Humane Society"),
    (["mercor"],                            "Mercor"),
]

CLAIM_TAG_KEYWORDS = {
    "[email]":      ["email", "open rate", "reply rate", "sequence", "outreach", "campaign", "pta", "hot zone", "mailchimp", "persistiq"],
    "[ops]":        ["salesforce", "crm", "pipeline", "territory", "hygiene", "data", "hot zone", "import", "outreach", "integration"],
    "[content]":    ["content", "committee", "asset", "library", "governance", "voice", "sequence", "playbook", "onboarding", "training"],
    "[enablement]": ["training", "onboarding", "playbook", "sdr", "enablement", "committee", "process map", "coaching"],
    "[sales]":      ["revenue", "pipeline", "quota", "close rate", "sourced", "sdr", "outbound", "meeting", "deal"],
    "[brand]":      ["brand", "voice", "tone", "agency", "campaign", "creative"],
    "[design]":     ["design", "deck", "slide", "flyer", "illustrator", "canva"],
    "[generalist]": [],
    "[mgmt]":       ["team", "coach", "manage", "sdr", "direct report", "training"],
    "[writing]":    ["copy", "writing", "email", "sequence", "campaign", "authored"],
}


def load_text_file(path: str, label: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        print(f"  ✅ Loaded {label} ({len(content):,} chars)")
        return content
    except Exception as e:
        print(f"  ⚠️  Could not load {label}: {e}")
        return ""


def trim_profile_yml(raw: str) -> str:
    KEEP_SECTIONS = ["target_roles:", "archetypes:", "narrative:", "superpowers:", "background_context:", "deal_breakers:"]
    STOP_SECTIONS = ["industries_of_genuine_fit:", "companies_previously_applied:", "compensation:", "location:", "cv:", "proof_points:", "key_recommendations:", "management_evidence:"]
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
    try:
        df = pd.read_csv(path)
        content = df.to_csv(index=False)
        print(f"  ✅ Loaded screenshot metrics ({len(df)} rows)")
        return content
    except Exception as e:
        print(f"  ⚠️  Could not load screenshot metrics: {e}")
        return ""


def get_verified_claims_text(df_claims: pd.DataFrame) -> str:
    if df_claims.empty:
        return ""
    cols = ["Claim / Finding", "Metric(s)", "Confidence", "Evidence / Detail"]
    available = [c for c in cols if c in df_claims.columns]
    return df_claims[available].to_csv(index=False)


def is_treering_bullet(role_company: str) -> bool:
    if not isinstance(role_company, str):
        return False
    rc = role_company.lower()
    return any(kw in rc for kw in TREERING_KEYWORDS)


def extract_cv_section(cv_text: str, role_company: str) -> str:
    if not cv_text or not role_company:
        return cv_text
    rc_lower = role_company.lower()
    matched_heading = None
    for keywords, heading in CV_SECTION_KEYWORDS:
        if any(kw in rc_lower for kw in keywords):
            matched_heading = heading
            break
    if not matched_heading:
        return cv_text
    sections = re.split(r"(?=^### )", cv_text, flags=re.MULTILINE)
    for section in sections:
        if matched_heading.lower() in section[:60].lower():
            return section.strip()
    return cv_text


def filter_claims_by_tags(df_claims: pd.DataFrame, tags: str) -> pd.DataFrame:
    if df_claims.empty:
        return df_claims
    tags_lower = tags.lower() if isinstance(tags, str) else ""
    keywords = []
    include_all = False
    for tag, kws in CLAIM_TAG_KEYWORDS.items():
        if tag in tags_lower:
            if not kws:
                include_all = True
                break
            keywords.extend(kws)
    if include_all or not keywords:
        return df_claims.head(MAX_CLAIMS_ROWS)
    text_cols = [c for c in df_claims.columns if df_claims[c].dtype == object]
    pattern = "|".join(re.escape(k) for k in keywords)
    mask = df_claims[text_cols].apply(lambda col: col.str.contains(pattern, case=False, na=False)).any(axis=1)
    filtered = df_claims[mask]
    if len(filtered) < 3:
        filtered = df_claims.head(MAX_CLAIMS_ROWS)
    return filtered.head(MAX_CLAIMS_ROWS)


def build_background_summary(tags: str) -> str:
    tags_lower = tags.lower() if isinstance(tags, str) else ""
    sections = [BACKGROUND_IDENTITY]
    for tag, content in BACKGROUND_TAGS.items():
        if tag in tags_lower:
            sections.append(content)
    return "\n\n".join(sections)


class KnowledgeBase:
    def __init__(self):
        print("\n📚 Loading knowledge base context...")
        self.cv_full = load_text_file(KB_CV, "cv.md")
        self.bg_raw = load_text_file(KB_BACKGROUND, "morgan-background-guide.md")
        raw_profile = load_text_file(KB_PROFILE, "profile.yml")
        self.profile = trim_profile_yml(raw_profile)
        self.df_claims = load_verified_claims(KB_VERIFIED_CLAIMS)
        self.screenshot_metrics = load_screenshot_metrics(KB_SCREENSHOT_METRICS)
        print(f"  📝 profile.yml trimmed to {len(self.profile):,} chars")
        print(f"  ℹ️  Context slimming active: cv section-only | tag-filtered claims | tag-keyed background\n")

    def context_block_for_bullet(self, role_company: str, tags: str) -> str:
        sections = []
        cv_section = extract_cv_section(self.cv_full, role_company)
        if cv_section:
            label = "ROLE CONTEXT (cv.md excerpt)" if cv_section != self.cv_full else "CAREER OVERVIEW (cv.md)"
            sections.append(f"=== {label} ===\n{cv_section}")
        bg_summary = build_background_summary(tags)
        if bg_summary:
            sections.append(f"=== BACKGROUND CONTEXT ===\n{bg_summary}")
        if self.profile:
            sections.append(
                f"=== TARGET ROLES & PROFILE (from profile.yml) ===\n"
                f"Use these to understand what roles this bullet needs to appeal to and what to avoid.\n{self.profile}"
            )
        if is_treering_bullet(role_company):
            filtered_claims = filter_claims_by_tags(self.df_claims, tags)
            claims_text = get_verified_claims_text(filtered_claims)
            if claims_text:
                sections.append(
                    f"=== VERIFIED CLAIMS & METRICS (Treering — resume-usable, tag-filtered) ===\n"
                    f"Use these to inject real, verified metrics where appropriate. Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                    f"{claims_text}"
                )
            if self.screenshot_metrics:
                sections.append(f"=== SCREENSHOT-SOURCED METRICS ===\n{self.screenshot_metrics}")
        return "\n\n".join(sections)


def persona_context(tags: str) -> str:
    if not isinstance(tags, str) or not tags.strip():
        return "general marketing roles"
    parts = [TAG_CONTEXT[tag] for tag in TAG_CONTEXT if tag in tags.lower()]
    return ", ".join(parts) if parts else "general marketing roles"


def _safe_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    return str(v)


def _safe_numeric(v):
    return pd.to_numeric(v, errors="coerce")


def ensure_writable_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize columns that receive mixed/string values so pandas 3.x / Python 3.14
    doesn't raise dtype upcast errors when assigning with .at/.loc.
    """
    object_cols = [
        "Bullet Point", "Role / Company", "Tags", "weaknesses",
        "final_bullet", "rewrite_status", "rewrite_reasoning", "context_gaps",
        "next_action", "manager_test"
    ]
    for col in object_cols:
        if col in df.columns:
            df[col] = df[col].astype("object")
    if "rewrite_attempts" in df.columns:
        df["rewrite_attempts"] = pd.to_numeric(df["rewrite_attempts"], errors="coerce")
    return df


def load_already_processed(output_path: str, keepers_path: str) -> set:
    """
    Build the set of bullet texts that are already done so they are skipped on resume.

    Sources:
      1. Cluster map output (bullet-bank-cluster-map-updated.csv) — rows whose
         rewrite_status is KEEP or MANUAL from a previous run of this script.
      2. Keepers CSV (bullet-bank-keepers.csv) — ALL rows, both the original seed
         bullets and any bullets written by prior runs. This is the authoritative
         source of truth for "this bullet is done and polished."

    Both the original "Bullet Point" text AND the "final_bullet" rewrite are added
    so a bullet is skipped regardless of which text variant appears in the cluster map.
    """
    done = set()

    # --- Source 1: cluster map output ---
    if os.path.exists(output_path):
        try:
            df = pd.read_csv(output_path)
            if "rewrite_status" in df.columns and "Bullet Point" in df.columns:
                done_mask = df["rewrite_status"].str.strip().str.upper().isin(DONE_STATUSES)
                done |= set(df.loc[done_mask, "Bullet Point"].dropna().str.strip())
                if "final_bullet" in df.columns:
                    done |= set(df.loc[done_mask, "final_bullet"].dropna().str.strip())
        except Exception as e:
            print(f"  ⚠️  Could not read cluster map output for resume check: {e}")

    # --- Source 2: keepers CSV ---
    if os.path.exists(keepers_path):
        try:
            df_k = pd.read_csv(keepers_path)
            if "Bullet Point" in df_k.columns:
                done |= set(df_k["Bullet Point"].dropna().str.strip())
            # Also add the final rewritten text if the column exists
            if "final_bullet" in df_k.columns:
                done |= set(df_k["final_bullet"].dropna().str.strip())
            print(f"  📚 Keepers CSV: {len(df_k)} rows added to done set.")
        except Exception as e:
            print(f"  ⚠️  Could not read keepers CSV for resume check: {e}")

    return done


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


def build_rewrite_prompt(bullet: str, tags: str, weaknesses: str, kb_context: str, attempt: int, prev_scores: dict = None) -> str:
    """
    Build the rewrite prompt for a single bullet.

    IMPLICIT CACHING: kb_context is placed at the TOP of the returned string so it
    forms a stable, byte-for-byte-identical prefix across all 3 attempts on the same
    bullet, and across bullets sharing the same (role_company, tags) pair.
    The variable parts (bullet text, weaknesses, prev_scores feedback) are appended
    AFTER the static prefix — matching the same pattern used in orchestrator.py's
    _load_knowledge_base() / build_tailored_resume().
    """
    persona = persona_context(tags)

    # ── Static cacheable prefix ──────────────────────────────────────────────
    kb_block = ""
    if kb_context:
        kb_block = (
            "--- KNOWLEDGE BASE CONTEXT ---\n"
            "Use the following background information to inform your rewrite.\n"
            "Draw on verified metrics where they strengthen the bullet.\n"
            "Do NOT use metrics marked Low confidence as hard facts.\n\n"
            f"{kb_context}\n\n"
        )

    # ── Variable tail (changes per attempt / bullet) ─────────────────────────
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

    return (
        f"{kb_block}"
        f"--- BULLET TO REWRITE ---\n{bullet}\n\n"
        f"--- TARGET PERSONA ---\nThis bullet should resonate for: {persona}\n\n"
        f"--- KNOWN WEAKNESSES (fix these) ---\n"
        f"{weaknesses if weaknesses and weaknesses.strip() else 'None noted — improve clarity and manager-test score generally.'}"
        f"{prev_block}\n"
        f"Now rewrite the bullet. Respond with JSON only."
    )

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


def score_bullet(bullet: str, tags: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {
            "accuracy_score": 90, "believability_score": 90, "clarity_score": 90,
            "ats_value": 90, "manager_test": "PASS", "weaknesses": "", "score_notes": "dry-run"
        }
    raw = client.generate(
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


def decide_action(scores: dict) -> str:
    mgr = str(scores.get("manager_test", "")).strip().upper()
    believability = pd.to_numeric(scores.get("believability_score"), errors="coerce")
    accuracy = pd.to_numeric(scores.get("accuracy_score"), errors="coerce")
    weaknesses = str(scores.get("weaknesses", "")).strip()
    if pd.isna(accuracy) and pd.isna(believability):
        return "NEEDS_AUDIT"
    if mgr == "FAIL" or (pd.notna(believability) and believability < 80):
        return "REWRITE"
    if weaknesses and weaknesses.lower() not in ("", "none", "nan", "n/a"):
        return "REVIEW" if (pd.notna(accuracy) and accuracy >= 85) else "REWRITE"
    return "KEEP"


def is_keeper(scores: dict) -> bool:
    return decide_action(scores) == "KEEP" and str(scores.get("manager_test", "")).strip().upper() == "PASS"


def best_version(original_bullet: str, original_scores: dict, rewritten_bullet: str, rewritten_scores: dict) -> tuple:
    def composite(s):
        vals = [pd.to_numeric(s.get(c, 0), errors="coerce") or 0 for c in ["accuracy_score", "believability_score", "clarity_score", "ats_value"]]
        mgr_bonus = 10 if str(s.get("manager_test", "")).upper() == "PASS" else 0
        return sum(vals) + mgr_bonus
    if composite(rewritten_scores) >= composite(original_scores):
        return rewritten_bullet, rewritten_scores
    return original_bullet, original_scores


# rewrite_date added so every keeper row has a full audit trail:
# original seed bullets get the script start time; newly written bullets get
# the exact timestamp they were appended.
KEEPER_COLS = [
    "Bullet Point", "Role / Company", "Tags",
    "accuracy_score", "believability_score", "clarity_score", "ats_value", "manager_test",
    "weaknesses", "source", "rewrite_attempts", "rewrite_reasoning", "context_gaps",
    "rewrite_date",
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
    mask = ((df_map["next_action"].str.strip().str.upper() == "KEEP") & (df_map["manager_test"].str.strip().str.upper() == "PASS"))
    df_seed = df_map[mask].copy()
    df_seed["source"] = "original"
    df_seed["rewrite_attempts"] = 0
    df_seed["rewrite_reasoning"] = ""
    df_seed["context_gaps"] = ""
    df_seed["rewrite_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for col in KEEPER_COLS:
        if col not in df_seed.columns:
            df_seed[col] = ""
    df_keepers = df_seed[KEEPER_COLS].copy()
    df_keepers.to_csv(path, index=False)
    print(f"  ✅ Keeper CSV created with {len(df_keepers)} seed bullets: {path}")
    return df_keepers


def append_keeper(df_keepers: pd.DataFrame, row: dict, path: str) -> pd.DataFrame:
    new_row = {col: row.get(col, "") for col in KEEPER_COLS}
    new_row["rewrite_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_keepers = pd.concat([df_keepers, pd.DataFrame([new_row])], ignore_index=True)
    df_keepers.to_csv(path, index=False)
    return df_keepers


def process_bullet(row: pd.Series, kb: KnowledgeBase, dry_run: bool) -> dict:
    original_bullet = str(row["Bullet Point"]).strip()
    tags = str(row.get("Tags", ""))
    weaknesses = str(row.get("weaknesses", ""))
    role_company = str(row.get("Role / Company", ""))
    original_scores = {col: row.get(col) for col in SCORE_COLS + ["weaknesses"]}
    kb_context = kb.context_block_for_bullet(role_company, tags)
    current_bullet = original_bullet
    current_scores = original_scores
    last_rewrite = ""
    last_reasoning = ""
    last_gaps = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"    ✏️  Attempt {attempt}/{MAX_ATTEMPTS}...")
        rw_prompt = build_rewrite_prompt(
            current_bullet, tags,
            str(current_scores.get("weaknesses", weaknesses)),
            kb_context,
            attempt=attempt,
            prev_scores=current_scores if attempt > 1 else None
        )
        if dry_run:
            rw_data = {"rewritten_bullet": f"[DRY RUN] {current_bullet}", "reasoning": "dry-run", "context_gaps": ""}
        else:
            try:
                raw = client.generate(
                    model=REWRITE_MODEL,
                    system_instruction=REWRITE_SYSTEM,
                    contents=rw_prompt,
                    temperature=0.1
                )
                rw_data = GeminiClient.parse_json(raw)
            except Exception as e:
                print(f"    ⚠️  API error on attempt {attempt}: {e}")
                if attempt < MAX_ATTEMPTS:
                    print(f"    🔄 Retrying in {SLEEP_ON_RETRY}s...")
                    time.sleep(SLEEP_ON_RETRY)
                    continue
                else:
                    print(f"    🚩 API error on final attempt — marking MANUAL.")
                    return {
                        "final_bullet": current_bullet,
                        "final_scores": current_scores,
                        "status": "MANUAL",
                        "rewrite_attempts": attempt,
                        "rewrite_reasoning": f"API error: {e}",
                        "context_gaps": "",
                        "source": "manual_review",
                    }

        rewritten = rw_data.get("rewritten_bullet", "").strip()
        last_reasoning = rw_data.get("reasoning", "")
        last_gaps = rw_data.get("context_gaps", "")

        if not rewritten:
            print(f"    ⚠️  Empty rewrite on attempt {attempt} — retrying in {SLEEP_ON_RETRY}s...")
            time.sleep(SLEEP_ON_RETRY)
            continue

        time.sleep(SLEEP_BETWEEN_BULLETS)
        print(f"    📊 Scoring rewrite...")
        try:
            new_scores = score_bullet(rewritten, tags, dry_run=dry_run)
        except Exception as e:
            print(f"    ⚠️  Scoring API error on attempt {attempt}: {e} — using previous scores.")
            new_scores = current_scores

        new_action = decide_action(new_scores)
        print(f"       acc={new_scores.get('accuracy_score')} bel={new_scores.get('believability_score')} mgr={new_scores.get('manager_test')} → {new_action}")
        last_rewrite = rewritten

        if is_keeper(new_scores):
            return {
                "final_bullet": rewritten,
                "final_scores": new_scores,
                "status": "KEEP",
                "rewrite_attempts": attempt,
                "rewrite_reasoning": last_reasoning,
                "context_gaps": last_gaps,
                "source": "rewritten",
            }

        current_bullet, current_scores = best_version(original_bullet, original_scores, rewritten, new_scores)
        current_scores["weaknesses"] = new_scores.get("weaknesses", "")

        if attempt < MAX_ATTEMPTS:
            print(f"    🔄 Not a keeper yet — retrying in {SLEEP_ON_RETRY}s...")
            time.sleep(SLEEP_ON_RETRY)

    print(f"    🚩 Max attempts reached — marking MANUAL.")
    final_bullet, final_scores = best_version(original_bullet, original_scores, last_rewrite if last_rewrite else original_bullet, current_scores)
    return {
        "final_bullet": final_bullet,
        "final_scores": final_scores,
        "status": "MANUAL",
        "rewrite_attempts": MAX_ATTEMPTS,
        "rewrite_reasoning": last_reasoning,
        "context_gaps": last_gaps,
        "source": "manual_review",
    }


def main():
    parser = argparse.ArgumentParser(description="Agentic rewrite loop for resume bullets using Gemini.")
    parser.add_argument("--map", default=CLUSTER_MAP_IN, help="Input cluster map CSV")
    parser.add_argument("--output", default=CLUSTER_MAP_OUT, help="Updated cluster map output")
    parser.add_argument("--keepers", default=KEEPERS_OUT, help="Keeper bullets CSV")
    parser.add_argument("--limit", type=int, default=None, help="Cap number of bullets (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Skip API calls, use dummy responses")
    args = parser.parse_args()

    source_map = args.output if os.path.exists(args.output) else args.map
    print(f"\n📥 Loading cluster map: {source_map}")
    if source_map == args.output:
        print(f"  ℹ️  Resuming from prior run — using updated map as source of truth.")
    df_map = pd.read_csv(source_map)
    df_map = ensure_writable_dtypes(df_map)
    print(f"  ✅ {len(df_map)} rows loaded.")

    for col in ["next_action", "manager_test", "is_representative", "Bullet Point"]:
        if col not in df_map.columns:
            raise ValueError(f"Missing required column '{col}' in cluster map.")

    df_map["is_representative"] = df_map["is_representative"].astype(str).str.strip().str.upper() == "TRUE"
    df_map["next_action"] = df_map["next_action"].fillna("").str.strip().str.upper()
    df_map["manager_test"] = df_map["manager_test"].fillna("").str.strip().str.upper()

    for col in ["final_bullet", "rewrite_status", "rewrite_attempts", "rewrite_reasoning", "context_gaps"]:
        if col not in df_map.columns:
            df_map[col] = ""
    df_map = ensure_writable_dtypes(df_map)

    # load_already_processed now checks BOTH the cluster map output AND the
    # keepers CSV so bullets that are already polished and stored in
    # bullet-bank-keepers.csv are never re-processed on resume.
    already_done = load_already_processed(args.output, args.keepers)
    if already_done:
        print(f"  ⏭️  Resume mode: {len(already_done)} bullet text(s) in done set (cluster map + keepers) — will skip if encountered.")

    kb = KnowledgeBase()
    df_keepers = load_or_init_keepers(args.keepers, df_map)

    mask = df_map["is_representative"] & df_map["next_action"].isin(["REWRITE", "REVIEW"])
    targets = df_map[mask].copy()

    if already_done:
        before = len(targets)
        targets = targets[~targets["Bullet Point"].str.strip().isin(already_done)]
        skipped = before - len(targets)
        if skipped:
            print(f"  ⏭️  Skipping {skipped} already-processed bullet(s) (cluster map + keepers safety net).")

    if args.limit:
        targets = targets.head(args.limit)

    total = len(targets)
    print(f"\n🎯 Bullets to process: {total}")
    if args.dry_run:
        print("  🧪 DRY RUN — no real API calls will be made.")
    if total == 0:
        print("  ✨ Nothing left to process — all bullets are already done!")
        return

    kept = 0
    manual = 0

    for i, (idx, row) in enumerate(targets.iterrows(), 1):
        bullet_preview = str(row["Bullet Point"])[:80]
        role_company = str(row.get("Role / Company", ""))
        tags = str(row.get("Tags", ""))
        print(f"\n[{i}/{total}] {bullet_preview}...")
        print(f"  Company: {role_company}  |  Tags: {tags}")
        print(f"  Action: {row['next_action']}  |  Weaknesses: {str(row.get('weaknesses', ''))[:80]}")
        treering_label = "🌳 Treering — verified claims injected (tag-filtered)" if is_treering_bullet(role_company) else "📄 Non-Treering — career context injected"
        print(f"  {treering_label}")

        result = process_bullet(row, kb, dry_run=args.dry_run)

        df_map.at[idx, "final_bullet"] = _safe_str(result["final_bullet"])
        df_map.at[idx, "rewrite_status"] = _safe_str(result["status"])
        df_map.at[idx, "rewrite_attempts"] = int(result["rewrite_attempts"]) if pd.notna(result["rewrite_attempts"]) else pd.NA
        df_map.at[idx, "rewrite_reasoning"] = _safe_str(result["rewrite_reasoning"])
        df_map.at[idx, "context_gaps"] = _safe_str(result["context_gaps"])
        df_map.at[idx, "next_action"] = _safe_str(result["status"])

        for col in NUMERIC_SCORE_COLS:
            df_map.at[idx, col] = _safe_numeric(result["final_scores"].get(col))
        for col in STRING_SCORE_COLS:
            df_map.at[idx, col] = _safe_str(result["final_scores"].get(col, ""))

        if result["status"] == "KEEP":
            kept += 1
            keeper_row = {
                "Bullet Point": result["final_bullet"],
                "Role / Company": row.get("Role / Company", ""),
                "Tags": tags,
                "source": result["source"],
                "rewrite_attempts": result["rewrite_attempts"],
                "rewrite_reasoning": result["rewrite_reasoning"],
                "context_gaps": result["context_gaps"],
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
