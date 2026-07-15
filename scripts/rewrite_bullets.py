#!/usr/bin/env python3
"""
rewrite_bullets.py  —  CACHE-OPTIMIZED VERSION

Agentic rewrite loop for resume bullets.

Pipeline per bullet:
  1. Pull is_representative=True rows where next_action in (REWRITE, REVIEW)
     from bullet-bank-cluster-map.csv
  2. Rewrite using Gemini, guided by weaknesses + Tags persona + knowledge base context
  3. Re-score using the same rubric as bullet-bank-audited.py
  4. If next_action=KEEP AND manager_test=PASS → write to keeper CSV + update cluster map
     Else pick best version (original vs rewrite) and loop with updated notes
  5. Max 3 attempts per bullet. On failure → status=MANUAL
  6. KEEP bullets already in the cluster map are seeded into the keeper CSV at startup
  7. On restart, bullets whose original text already appears in a prior output run
     OR in bullet-bank-keepers.csv are skipped automatically (resumable runs).

CACHE OPTIMIZATION — three-tier prompt structure:

  Tier 1 — static_prefix  (built ONCE at startup, identical for every bullet)
    profile.yml + verified_facts + verified_tools + verified_projects.
    Placed at the TOP of every contents payload so the API can cache-hit the prefix.

  Tier 2 — segment bundles  (built ONCE per unique company+tags combo)
    CV section excerpt + background summary + Treering evidence (claims,
    screenshot metrics, verified metrics). Warmed by warm_segment_cache() before
    the loop. All bullets sharing the same company+tags pair get the same frozen
    string, maximising per-group prefix reuse.

  Tier 3 — per-bullet tail  (the ONLY part that varies per call)
    Persona descriptor + weaknesses + bullet text. No boilerplate here — all
    output-contract instructions live in the system prompt (Tier 0) so the
    merged Gemma payload starts with an identical, stable header on every call.

Cache observability:
  Every rewrite call logs cachedContentTokenCount from the usage dict returned
  by generate() alongside kb_context length so you can verify provider-side
  cache hits directly.

Knowledge base files loaded at startup:
  - cv.md                          → role section matching bullet's company only
  - user-background-guide.md       → tag-keyed summary
  - profile.yml                    → target roles, superpowers, deal-breakers (trimmed)
  - verified-claims.csv            → tag-filtered rows (Treering bullets only, max 15)
  - extracted-screenshot-metrics.csv → screenshot-sourced metrics (Treering only)
  - verified_facts.json            → 18 high-confidence factual claims
  - verified_metrics.json          → verified numeric metrics
  - verified_projects.json         → verified project descriptions and scopes
  - verified_tools.json            → verified tools Morgan actually used (guards HF002)
  - recruiter_memory_patterns.json → recruiter reading patterns (score prompts only)

Rules loaded at startup (resume-engine/rules/):
  - language_quality.yaml   → weak verbs, buzzwords, AI patterns, verb scoring
  - verb_taxonomy.yaml      → verb library by role category + priority tiers
  - verb_intent_mapping.yaml → maps accomplishment intent → correct verb family
  - hard_failures.yaml      → 7 critical fail conditions (HF001–HF007)
  - truthfulness_rules.yaml → 4 truthfulness tests
  - style_rules.yaml        → style guidance
  - ats_rules.yaml          → ATS keyword weights and section placement rules
  - formatting_rules.yaml   → date format and forbidden layout elements

Usage:
  python rewrite_bullets.py                    # process all REWRITE + REVIEW reps
  python rewrite_bullets.py --limit 20         # cap for testing
  python rewrite_bullets.py --dry-run          # print prompts, no API calls
  python rewrite_bullets.py --retry-manual     # re-run all MANUAL bullets
  python rewrite_bullets.py --retry-manual --model gemini-2.5-pro

Outputs (resume-engine/knowledge_base/):
  bullet-bank-cluster-map-updated.csv   updated cluster map with rewrite results
  bullet-bank-keepers.csv               bullets that achieved KEEP + PASS
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Optional

import pandas as pd
import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# PATH RESOLUTION
#
# Layout:
#   resume-builder/          ← PROJECT_ROOT
#     scripts/               ← SCRIPT_DIR  (this file lives here)
#     resume-engine/
#       knowledge_base/
#       rules/
#
# SCRIPT_DIR   = .../resume-builder/scripts
# PROJECT_ROOT = .../resume-builder          (one dirname up, not two)
# ---------------------------------------------------------------------------
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))   # resume-builder/scripts
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)                   # resume-builder/
KB_DIR       = os.path.join(PROJECT_ROOT, "resume-engine", "knowledge_base")
RULES_DIR    = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCORING_DIR  = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")

# orchestrator.py lives in the same scripts/ directory as this file.
# Import GeminiClient only — orchestrator.py has no module-level client object.
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from gemini_client import GeminiClient, SustainedFailureError  # noqa: E402

CLUSTER_MAP_IN  = os.path.join(KB_DIR, "bullet-bank-cluster-map.csv")
CLUSTER_MAP_OUT = os.path.join(KB_DIR, "bullet-bank-cluster-map-updated.csv")
KEEPERS_OUT     = os.path.join(KB_DIR, "bullet-bank-keepers.csv")

KB_CV               = os.path.join(KB_DIR, "cv.md")
KB_BACKGROUND       = os.path.join(KB_DIR, "user-background-guide.md")
KB_PROFILE          = os.path.join(KB_DIR, "profile.yml")
KB_VERIFIED_CLAIMS  = os.path.join(KB_DIR, "verified-claims.csv")
KB_SCREENSHOT_METRICS = os.path.join(KB_DIR, "extracted-screenshot-metrics.csv")
KB_VERIFIED_FACTS   = os.path.join(KB_DIR, "verified_facts.json")
KB_VERIFIED_METRICS = os.path.join(KB_DIR, "verified_metrics.json")
KB_VERIFIED_PROJECTS = os.path.join(KB_DIR, "verified_projects.json")
KB_VERIFIED_TOOLS   = os.path.join(KB_DIR, "verified_tools.json")
KB_RECRUITER_PATTERNS = os.path.join(KB_DIR, "recruiter_memory_patterns.json")
KB_VOICE_ANCHORS    = os.path.join(KB_DIR, "voice-anchors.md")

# ---------------------------------------------------------------------------
# MODEL STRATEGY
#
# REWRITE_MODEL: gemma-4-31b-it — primary rewrite model. Has the largest
#   free-tier daily quota by a wide margin. rewrite_bullets.py is the
#   highest-volume script in the pipeline (up to 3 API calls per bullet),
#   so using the model with the biggest free allotment here is intentional.
#   rewrite_bullets.py (the masterpiece!) was specifically tuned for Gemma.
#
# REWRITE_FALLBACK_MODEL: gemini-3.1-flash-lite — activated automatically
#   after MAX_REWRITE_PARSE_FAILURES consecutive parse failures on a single
#   bullet. Reliable JSON compliance as a safety net.
#
# SCORE_MODEL: gemini-3.1-flash-lite — scoring calls are lower-volume
#   (one per rewrite attempt) and need strict JSON compliance with a
#   7-field schema. Flash-lite handles this cleanly within free-tier limits.
# ---------------------------------------------------------------------------
REWRITE_MODEL          = "gemma-4-31b-it"
REWRITE_FALLBACK_MODEL = "gemini-3.1-flash-lite"
SCORE_MODEL            = "gemini-3.1-flash-lite"
MAX_ATTEMPTS          = 3
MAX_REWRITE_PARSE_FAILURES = 2
GEMMA_MINIMAL_JSON    = True

# ---------------------------------------------------------------------------
# SLEEP CONSTANTS
# ---------------------------------------------------------------------------
SLEEP_BETWEEN_BULLETS = 5
SLEEP_BETWEEN_SCORES  = 5
SLEEP_ON_RETRY        = 8

CSV_FLUSH_EVERY = 5

SCORE_COLS         = ["accuracy_score", "believability_score", "clarity_score",
                      "ats_value", "manager_test"]
NUMERIC_SCORE_COLS = ["accuracy_score", "believability_score", "clarity_score", "ats_value"]
STRING_SCORE_COLS  = ["manager_test", "weaknesses"]

DONE_STATUSES      = {"KEEP", "MANUAL"}
TREERING_KEYWORDS  = ["treering", "tree ring", "yearbook"]
MAX_CLAIMS_ROWS    = 12

TAG_CONTEXT = {
    "[content]":   "content marketing, editorial strategy, brand voice, or copywriting roles",
    "[ops]":       "marketing operations, RevOps, CRM, automation, or analytics roles",
    "[email]":     "email marketing, lifecycle marketing, or CRM/ESP campaign roles",
    "[demand]":    "demand generation, paid media, or growth marketing roles",
    "[product]":   "product marketing or go-to-market strategy roles",
    "[sales]":     "B2B sales, SDR/AE, or account management roles",
    "[brand]":     "brand marketing, creative direction, or agency roles",
    "[design]":    "graphic design, visual identity, or UX/UI roles",
    "[general]":   "general marketing or cross-functional roles",
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
    (["unisource", "udp"],                  "Unisource"),
    (["humane society"],                    "Humane Society"),
    (["mercor"],                            "Mercor"),
]

CLAIM_TAG_KEYWORDS = {
    "[email]":       ["email", "open rate", "reply rate", "sequence", "outreach", "campaign",
                      "pta", "hot zone", "mailchimp", "persistiq"],
    "[ops]":         ["salesforce", "crm", "pipeline", "territory", "hygiene", "data",
                      "hot zone", "import", "outreach", "integration"],
    "[content]":     ["content", "committee", "asset", "library", "governance", "voice",
                      "sequence", "playbook", "onboarding", "training"],
    "[enablement]":  ["training", "onboarding", "playbook", "sdr", "enablement",
                      "committee", "process map", "coaching"],
    "[sales]":       ["revenue", "pipeline", "quota", "close rate", "sourced", "sdr",
                      "outbound", "meeting", "deal"],
    "[brand]":       ["brand", "voice", "tone", "agency", "campaign", "creative"],
    "[design]":      ["design", "deck", "slide", "flyer", "illustrator", "canva"],
    "[generalist]":  [],
    "[mgmt]":        ["team", "coach", "manage", "sdr", "direct report", "training"],
    "[writing]":     ["copy", "writing", "email", "sequence", "campaign", "authored"],
}

# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS
#
# GeminiClient.generate() calls response_schema.model_json_schema() to build
# the responseSchema payload, so the schema argument MUST be a Pydantic model
# class — not a raw dict. These are the two schemas used by rewrite_bullets.py.
# ---------------------------------------------------------------------------

class RewriteOutputSchema(BaseModel):
    rewritten_bullet: str = Field(description="Single rewritten resume bullet sentence.")
    reasoning:        str = Field(default="", description="Explanation of changes made.")
    context_gaps:     str = Field(default="", description="Missing context that limited the rewrite.")


class RewriteOutputMinimalSchema(BaseModel):
    """Minimal schema used for Gemma calls (GEMMA_MINIMAL_JSON=True)."""
    rewritten_bullet: str = Field(description="Single rewritten resume bullet sentence.")


class ScoreOutputSchema(BaseModel):
    accuracy_score:      int = Field(description="0-100: specific, grounded, traceable claim")
    believability_score: int = Field(description="0-100: would a skeptical hiring manager believe this?")
    clarity_score:       int = Field(description="0-100: immediately clear on first read")
    ats_value:           int = Field(description="0-100: high-value ATS keywords without stuffing")
    manager_test:        str = Field(description="Strictly 'PASS' or 'FAIL'")
    weaknesses:          str = Field(description="Specific explanation of flaws. 'None' if all scores high.")
    score_notes:         str = Field(default="", description="1-2 sentences of overall feedback.")


# ---------------------------------------------------------------------------
# RULES LOADER
# ---------------------------------------------------------------------------

def _load_yaml_safe(path: str, label: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        print(f"   ✅ Rules loaded: {label}")
        return data
    except Exception as e:
        print(f"   ⚠️ Could not load rules {label}: {e}")
        return {}


def _yaml_to_str(data: dict) -> str:
    try:
        return yaml.dump(data, default_flow_style=False, allow_unicode=True).strip()
    except Exception:
        return str(data)


class RulesBundle:
    def __init__(self, rules_dir: str, scoring_dir: str = None):
        print("\n📋 Loading rules bundle...")

        # scoring_dir defaults to the sibling "scoring" dir next to rules_dir
        # (resume-engine/rules -> resume-engine/scoring), matching every
        # caller in this codebase; only override for tests/custom layouts.
        if scoring_dir is None:
            scoring_dir = os.path.join(os.path.dirname(rules_dir), "scoring")

        lq  = _load_yaml_safe(os.path.join(rules_dir, "language_quality.yaml"),    "language_quality")
        vt  = _load_yaml_safe(os.path.join(rules_dir, "verb_taxonomy.yaml"),        "verb_taxonomy")
        vim = _load_yaml_safe(os.path.join(rules_dir, "verb_intent_mapping.yaml"),  "verb_intent_mapping")
        hf  = _load_yaml_safe(os.path.join(rules_dir, "hard_failures.yaml"),        "hard_failures")
        tr  = _load_yaml_safe(os.path.join(rules_dir, "truthfulness_rules.yaml"),   "truthfulness_rules")
        sr  = _load_yaml_safe(os.path.join(rules_dir, "style_rules.yaml"),          "style_rules")
        # ats_rules.yaml is documented (see module docstring) but was never
        # created — score_rules_block below references it regardless via
        # `ats`, so load it defensively the same way as the other files;
        # _load_yaml_safe degrades to {} (empty ATS section) if it's absent.
        ats = _load_yaml_safe(os.path.join(rules_dir, "ats_rules.yaml"),            "ats_rules")
        # manager_test.yaml (full scoring/ rubric — hard_fail_conditions incl.
        # scope_inflation, protected_bullets) and believability.yaml (realism/
        # human_language criteria with worked bad-example patterns) were never
        # loaded here even though audit_bullet_bank.py and orchestrator.py's
        # critique loop both correctly pull them from scoring/ — meaning the
        # rewrite step's own accept/reject judgment ran on a much thinner
        # rubric than everything scoring bullets elsewhere in the pipeline.
        mt  = _load_yaml_safe(os.path.join(scoring_dir, "manager_test.yaml"),       "manager_test (scoring)")
        bel = _load_yaml_safe(os.path.join(scoring_dir, "believability.yaml"),      "believability")

        self.rewrite_rules_block = "\n".join([
            "=== VERB INTENT MAP ===",
            "Before choosing a verb, identify the accomplishment intent (creation, implementation,",
            "optimization, automation, analysis, revenue_generation, training, leadership, etc.)",
            "and select from the matching preferred_verbs list below.",
            _yaml_to_str(vim),
            "",
            "=== VERB TAXONOMY (priority tiers) ===",
            "Use elite > strong > acceptable. NEVER use verbs in the avoid list.",
            _yaml_to_str({"priority_tiers": vt.get("priority_tiers", {}), "avoid": vt.get("avoid", [])}),
            "",
            "=== LANGUAGE QUALITY RULES ===",
            "Flag and replace any weak verbs, buzzwords, or AI-pattern phrases listed below.",
            "Verb scoring: elite=100, strong=85, acceptable=70, weak=40, generic=20.",
            _yaml_to_str({
                "weak_verbs":           lq.get("weak_verbs", {}),
                "buzzwords":            lq.get("buzzwords", {}),
                "ai_language_patterns": lq.get("ai_language_patterns", {}),
                "specificity_checks":   lq.get("specificity_checks", {}),
                "final_principle":      lq.get("final_principle", ""),
            }),
            "",
            "=== HARD FAILURE CONDITIONS ===",
            "Any bullet triggering one of these conditions must be rewritten — do NOT pass it:",
            _yaml_to_str(hf),
            "",
            "=== TRUTHFULNESS RULES ===",
            "Apply these four tests before finalising any bullet:",
            _yaml_to_str(tr),
            "",
            "=== SCOPE & BELIEVABILITY GUARDRAILS ===",
            "A rewrite must keep the SAME underlying achievement, scope, ownership, and",
            "seniority as the original bullet — only the phrasing may improve. Making a bullet",
            "sound more impressive by inflating scope, ownership, or scale (even without",
            "inventing a fact) is a hard failure, not a style win. Study the bad-example",
            "patterns below and never produce phrasing that reads like them:",
            _yaml_to_str({"hard_fail_conditions": mt.get("hard_fail_conditions", []),
                          "protected_bullets":    mt.get("protected_bullets", [])}),
            _yaml_to_str({"believability_criteria_and_examples": bel.get("criteria", {}),
                          "believability_penalties":              bel.get("penalties", {}),
                          "context_anchoring":                    bel.get("context_anchoring", {})}),
            "",
            "=== STYLE RULES ===",
            _yaml_to_str(sr),
        ])

        self.score_rules_block = "\n".join([
            "=== SCORING CRITERIA ===",
            "",
            "HARD FAILURES (any of these → automatic believability_score <= 50 AND manager_test=FAIL):",
            _yaml_to_str(hf),
            "",
            "VERB SCORING:",
            _yaml_to_str(lq.get("verb_scoring", {})),
            "",
            "LANGUAGE QUALITY — penalise these:",
            _yaml_to_str({
                "weak_verbs":           lq.get("weak_verbs", {}),
                "buzzwords":            lq.get("buzzwords", {}),
                "ai_language_patterns": lq.get("ai_language_patterns", {}),
            }),
            "",
            "TRUTHFULNESS TESTS — fail any bullet that does not pass all four:",
            _yaml_to_str(tr),
            "",
            "MANAGER TEST:",
            _yaml_to_str(lq.get("manager_test", {})),
            "",
            "SCOPE & BELIEVABILITY — a bullet can be technically true and still fail",
            "believability_score if it inflates scope, ownership, or seniority beyond what",
            "the original supported. Any hard_fail_condition below is an automatic",
            "manager_test=FAIL regardless of other scores:",
            _yaml_to_str(mt),
            _yaml_to_str({"believability_criteria_and_examples": bel.get("criteria", {}),
                          "believability_penalties":              bel.get("penalties", {}),
                          "context_anchoring":                    bel.get("context_anchoring", {})}),
        ])

        print(f"   📐 Rewrite rules block: {len(self.rewrite_rules_block):,} chars")
        print(f"   💯 Score rules block:   {len(self.score_rules_block):,} chars\n")


# ---------------------------------------------------------------------------
# FILE LOADERS
# ---------------------------------------------------------------------------

def load_text_file(path: str, label: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        print(f"   ✅ Loaded {label} ({len(content):,} chars)")
        return content
    except Exception as e:
        print(f"   ⚠️ Could not load {label}: {e}")
        return ""


def load_json_file(path: str, label: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        print(f"   ✅ Loaded {label} ({len(content):,} chars)")
        return content
    except Exception as e:
        print(f"   ⚠️ Could not load {label}: {e}")
        return ""


def trim_profile_yml(raw: str) -> str:
    KEEP_SECTIONS = ["target_roles:", "archetypes:", "narrative:", "superpowers:",
                     "background_context:", "deal_breakers:"]
    STOP_SECTIONS = ["industries_of_genuine_fit:", "companies_previously_applied:",
                     "compensation:", "location:", "cv:", "proof_points:",
                     "key_recommendations:", "management_evidence:"]
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
        print(f"   ✅ Loaded verified-claims ({len(df)} resume-usable rows)")
        return df
    except Exception as e:
        print(f"   ⚠️ Could not load verified-claims: {e}")
        return pd.DataFrame()


def load_screenshot_metrics(path: str) -> str:
    try:
        df = pd.read_csv(path)
        content = df.to_csv(index=False)
        print(f"   ✅ Loaded screenshot metrics ({len(df)} rows)")
        return content
    except Exception as e:
        print(f"   ⚠️ Could not load screenshot metrics: {e}")
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
    mask = df_claims[text_cols].apply(
        lambda col: col.str.contains(pattern, case=False, na=False)
    ).any(axis=1)
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


# ---------------------------------------------------------------------------
# KNOWLEDGE BASE  —  cache-optimised
# ---------------------------------------------------------------------------

class KnowledgeBase:
    def __init__(self):
        print("\n📚 Loading knowledge base context...")
        self.cv_full           = load_text_file(KB_CV,               "cv.md")
        self.bg_raw            = load_text_file(KB_BACKGROUND,        "user-background-guide.md")
        raw_profile            = load_text_file(KB_PROFILE,           "profile.yml")
        self.profile           = trim_profile_yml(raw_profile)
        self.df_claims         = load_verified_claims(KB_VERIFIED_CLAIMS)
        self.screenshot_metrics = load_screenshot_metrics(KB_SCREENSHOT_METRICS)
        self.verified_facts    = load_json_file(KB_VERIFIED_FACTS,    "verified_facts.json")
        self.verified_metrics  = load_json_file(KB_VERIFIED_METRICS,  "verified_metrics.json")
        self.verified_projects = load_json_file(KB_VERIFIED_PROJECTS, "verified_projects.json")
        self.verified_tools    = load_json_file(KB_VERIFIED_TOOLS,    "verified_tools.json")
        self.recruiter_patterns = load_json_file(KB_RECRUITER_PATTERNS, "recruiter_memory_patterns.json")
        self.voice_anchors      = load_text_file(KB_VOICE_ANCHORS,    "voice-anchors.md")

        print(f"   💥 profile.yml trimmed to {len(self.profile):,} chars")

        self.static_prefix = self._build_static_prefix()
        print(f"   📌 Static prefix (Tier 1): {len(self.static_prefix):,} chars — shared across ALL bullets")

        self._segment_cache: dict = {}
        print("   ℹ️  Call warm_segment_cache(df_map) before starting the rewrite loop.\n")

    def _build_static_prefix(self) -> str:
        sections = []
        if self.profile:
            sections.append(
                "=== TARGET ROLES & PROFILE (from profile.yml) ===\n"
                "Use these to understand what roles this bullet needs to appeal to and what to avoid.\n"
                + self.profile
            )
        if self.verified_facts:
            sections.append(
                "=== VERIFIED FACTS (high-confidence claims — use freely) ===\n"
                "These are the only facts about Morgan's career that are evidence-backed.\n"
                "Do NOT invent facts outside this list.\n"
                + self.verified_facts
            )
        if self.verified_tools:
            sections.append(
                "=== VERIFIED TOOLS (HF002 guard — only claim tools listed here) ===\n"
                "Never claim proficiency with any tool not present in this list.\n"
                + self.verified_tools
            )
        if self.verified_projects:
            sections.append(
                "=== VERIFIED PROJECTS ===\n"
                "Use these to add accurate project detail and scope.\n"
                + self.verified_projects
            )
        if self.voice_anchors:
            sections.append(
                "=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n"
                + self.voice_anchors
            )
        return "\n\n".join(sections)

    def _build_segment_bundle(self, role_company: str, tags: str) -> str:
        sections = []
        cv_section = extract_cv_section(self.cv_full, role_company)
        if cv_section:
            label = ("ROLE CONTEXT (cv.md excerpt)"
                     if cv_section != self.cv_full else "CAREER OVERVIEW (cv.md)")
            sections.append(f"=== {label} ===\n{cv_section}")
        bg_summary = build_background_summary(tags)
        if bg_summary:
            sections.append(f"=== BACKGROUND CONTEXT ===\n{bg_summary}")
        if is_treering_bullet(role_company):
            filtered_claims = filter_claims_by_tags(self.df_claims, tags)
            claims_text = get_verified_claims_text(filtered_claims)
            if claims_text:
                sections.append(
                    "=== VERIFIED CLAIMS & METRICS (Treering — resume-usable, tag-filtered) ===\n"
                    "Use these to inject real, verified metrics where appropriate. "
                    "Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                    + claims_text
                )
            if self.screenshot_metrics:
                sections.append(f"=== SCREENSHOT-SOURCED METRICS ===\n{self.screenshot_metrics}")
            if self.verified_metrics:
                sections.append(
                    "=== VERIFIED METRICS (authoritative — use these numbers, not guesses) ===\n"
                    "These are the ONLY numeric metrics that may be cited as hard facts in Treering bullets.\n"
                    + self.verified_metrics
                )
        return "\n\n".join(sections)

    def warm_segment_cache(self, df: pd.DataFrame) -> None:
        self._segment_cache = {}
        pairs = df[["Role / Company", "Tags"]].drop_duplicates()
        print(f"\n🔥 Warming segment cache for {len(pairs)} unique (company, tags) combos...")
        for _, row in pairs.iterrows():
            rc   = str(row["Role / Company"])
            tags = str(row["Tags"])
            key  = (rc, tags)
            bundle = self._build_segment_bundle(rc, tags)
            self._segment_cache[key] = bundle
            treering_flag = " [Treering+claims]" if is_treering_bullet(rc) else ""
            print(f"   📦 ({rc[:30]!r}, {tags[:40]!r}) → {len(bundle):,} chars{treering_flag}")
        print(f"   ✅ {len(self._segment_cache)} segment bundles ready.\n")

    def context_block_for_bullet(self, role_company: str, tags: str) -> str:
        key = (role_company, tags)
        if key not in self._segment_cache:
            print(f"   ⚠️ Cache miss for {key} — building segment on demand.")
            self._segment_cache[key] = self._build_segment_bundle(role_company, tags)
        segment = self._segment_cache[key]
        return f"{self.static_prefix}\n\n{segment}" if segment else self.static_prefix

    def recruiter_context_block(self) -> str:
        if not self.recruiter_patterns:
            return ""
        return (
            "=== RECRUITER READING PATTERNS (what hiring managers notice first) ===\n"
            "Use these patterns to calibrate believability and manager_test scoring.\n"
            + self.recruiter_patterns
        )


# ---------------------------------------------------------------------------
# SYSTEM PROMPTS
# ---------------------------------------------------------------------------

REWRITE_SYSTEM_BASE = """\
You are an industry-leading resume writer specialising in B2B SaaS and marketing careers.

Output rules — apply without exception:
- Your response must begin with {{ and end with }}. No other characters before or after.
- Raw JSON only. No markdown fences, no preamble, no commentary, no labels, no explanations.
- Do not repeat, echo, or paraphrase any part of the input.
- "rewritten_bullet" must be a single resume bullet sentence, never a list.

JSON shape (full schema):
{{"rewritten_bullet": "", "reasoning": "", "context_gaps": ""}}

Minimal schema (Gemma / minimal mode — used when instructed):
{{"rewritten_bullet": ""}}

Rewrite goals:
- Pass the manager test: a hiring manager scanning quickly should understand what was done,
  how it was done, and why it mattered.
- Improve clarity, specificity, and ATS value.
- Sound human and believable, not inflated or AI-written.
- Use a strong past-tense action verb.
- Stay under 30 words where possible; never exceed 40 words.
- Use only information supported by the provided context.
- Use only metrics verified in the provided context.
- Do not invent scope, ownership, tools, or results.

If the context is not strong enough to support an improved claim, keep the rewrite
conservative and explain the limitation in context_gaps.

{rules_block}
"""

SCORE_SYSTEM_BASE = """\
You are a resume quality auditor. Score the following resume bullet on five dimensions.
Respond ONLY with valid JSON, no markdown fences:
{{
  "accuracy_score": <0-100 int>,
  "believability_score": <0-100 int>,
  "clarity_score": <0-100 int>,
  "ats_value": <0-100 int>,
  "manager_test": <"PASS" or "FAIL">,
  "weaknesses": "",
  "score_notes": "<1-2 sentences of overall feedback>"
}}

{rules_block}

{recruiter_block}
"""


def build_system_prompts(rules: RulesBundle, kb: KnowledgeBase) -> tuple:
    rewrite_system = REWRITE_SYSTEM_BASE.format(rules_block=rules.rewrite_rules_block)
    score_system   = SCORE_SYSTEM_BASE.format(
        rules_block=rules.score_rules_block,
        recruiter_block=kb.recruiter_context_block(),
    )
    print(f"   🖊  Rewrite system prompt: {len(rewrite_system):,} chars (stable across ALL calls)")
    print(f"   💯 Score system prompt:   {len(score_system):,} chars")
    return rewrite_system, score_system


# ---------------------------------------------------------------------------
# PERSONA HELPER
# ---------------------------------------------------------------------------

def persona_context(tags: str) -> str:
    if not isinstance(tags, str) or not tags.strip():
        return "general marketing roles"
    parts = [TAG_CONTEXT[tag] for tag in TAG_CONTEXT if tag in tags.lower()]
    return ", ".join(parts) if parts else "general marketing roles"


# ---------------------------------------------------------------------------
# PROMPT BUILDER  (Tier 3 — per-bullet tail only)
# ---------------------------------------------------------------------------

def build_rewrite_prompt(
    bullet: str,
    tags: str,
    weaknesses: str,
    kb_context: str,
    attempt: int,
    prev_scores: dict = None,
    minimal_schema: bool = False,
) -> str:
    persona = persona_context(tags)
    weakness_text = (
        weaknesses.strip()
        if weaknesses and weaknesses.strip()
        else "Improve clarity, specificity, and believability."
    )

    parts = []

    if kb_context:
        parts.extend([
            "Use only supported facts from this context:",
            kb_context,
            "",
        ])

    parts.extend([
        f"Rewrite this bullet for {persona} roles.",
        f"Known weaknesses to fix: {weakness_text}",
        f"Bullet to rewrite: {bullet}",
    ])

    if minimal_schema:
        parts.extend(["", 'Output JSON: {"rewritten_bullet":""}'])
    else:
        parts.extend(["", 'Output JSON: {"rewritten_bullet":"","reasoning":"","context_gaps":""}'])

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CACHE-HIT LOGGING HELPER
# ---------------------------------------------------------------------------

def _log_cache_stats(usage: dict, kb_context_chars: int, attempt: int) -> None:
    if not isinstance(usage, dict):
        usage = {}

    prompt_tokens  = usage.get("promptTokenCount", 0)
    output_tokens  = usage.get("candidatesTokenCount", 0)
    total_tokens   = usage.get("totalTokenCount", 0)
    cached_tokens  = usage.get("cachedContentTokenCount", 0)

    token_part = (
        f"prompt: {prompt_tokens:,} | output: {output_tokens:,} | total: {total_tokens:,}"
    )

    if cached_tokens and cached_tokens > 0:
        print(f"   💫 tokens — {token_part} | ✨ cached: {cached_tokens:,}")
    else:
        print(f"   💫 tokens — {token_part}")


# ---------------------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------------------

def score_bullet(bullet: str, tags: str, score_system: str, dry_run: bool = False) -> dict:
    if dry_run:
        return {
            "accuracy_score": 90, "believability_score": 90, "clarity_score": 90,
            "ats_value": 90, "manager_test": "PASS", "weaknesses": "", "score_notes": "dry-run",
        }

    raw, _ = GeminiClient.generate(
        model=SCORE_MODEL,
        system_instruction=score_system,
        contents=(
            f"--- BULLET ---\n{bullet}\n\n"
            f"--- TARGET PERSONA ---\n{persona_context(tags)}\n\n"
            "Score this bullet. Respond with JSON only."
        ),
        temperature=0.0,
        response_schema=ScoreOutputSchema,
    )
    data = GeminiClient.parse_json(raw)
    time.sleep(SLEEP_BETWEEN_SCORES)

    mgr = str(data.get("manager_test", "")).strip().upper()
    data["manager_test"] = mgr if mgr in ("PASS", "FAIL") else "FAIL"
    for col in ["accuracy_score", "believability_score", "clarity_score", "ats_value"]:
        data[col] = pd.to_numeric(data.get(col, 0), errors="coerce")
    return data


def _is_meaningful_weakness(text: str) -> bool:
    t = str(text or "").strip().lower()
    return t not in ("", "none", "nan", "n/a", "no major weaknesses", "no significant weaknesses")


def decide_action(scores: dict) -> str:
    mgr          = str(scores.get("manager_test", "")).strip().upper()
    accuracy     = pd.to_numeric(scores.get("accuracy_score"),     errors="coerce")
    believability = pd.to_numeric(scores.get("believability_score"), errors="coerce")
    clarity      = pd.to_numeric(scores.get("clarity_score"),      errors="coerce")
    ats_value    = pd.to_numeric(scores.get("ats_value"),          errors="coerce")
    weaknesses   = str(scores.get("weaknesses", "")).strip()

    if pd.isna(accuracy) and pd.isna(believability):
        return "NEEDS_AUDIT"
    if mgr == "FAIL":
        return "REWRITE"
    if pd.notna(believability) and believability < 80:
        return "REWRITE"
    if pd.notna(accuracy) and accuracy < 85:
        return "REWRITE"

    strong_keep = (
        mgr == "PASS"
        and pd.notna(accuracy)      and accuracy      >= 90
        and pd.notna(believability) and believability >= 88
        and pd.notna(clarity)       and clarity       >= 85
    )
    if strong_keep:
        return "KEEP"
    if _is_meaningful_weakness(weaknesses):
        return "REVIEW"
    if pd.notna(ats_value) and ats_value < 75:
        return "REVIEW"
    return "KEEP"


def is_keeper(scores: dict) -> bool:
    return (
        decide_action(scores) == "KEEP"
        and str(scores.get("manager_test", "")).strip().upper() == "PASS"
    )


def best_version(
    original_bullet: str, original_scores: dict,
    rewritten_bullet: str, rewritten_scores: dict,
) -> tuple:
    def composite(s):
        vals = [pd.to_numeric(s.get(c, 0), errors="coerce") or 0
                for c in ["accuracy_score", "believability_score", "clarity_score", "ats_value"]]
        mgr_bonus = 10 if str(s.get("manager_test", "")).upper() == "PASS" else 0
        return sum(vals) + mgr_bonus

    if composite(rewritten_scores) >= composite(original_scores):
        return rewritten_bullet, rewritten_scores
    return original_bullet, original_scores


# ---------------------------------------------------------------------------
# KEEPER CSV
# ---------------------------------------------------------------------------

KEEPER_COLS = [
    "Bullet Point", "Role / Company", "Tags",
    "accuracy_score", "believability_score", "clarity_score", "ats_value", "manager_test",
    "weaknesses", "source", "rewrite_attempts", "rewrite_reasoning", "context_gaps",
    "rewrite_date", "source_cluster_id",
]


def load_or_init_keepers(path: str, df_map: pd.DataFrame) -> pd.DataFrame:
    if os.path.exists(path):
        print(f"   📂 Loading existing keepers: {path}")
        df = pd.read_csv(path)
        for col in KEEPER_COLS:
            if col not in df.columns:
                df[col] = ""
        return df

    print("   🌱 Seeding keeper CSV from existing KEEP+PASS bullets in cluster map...")
    mask = (
        (df_map["next_action"].str.strip().str.upper() == "KEEP")
        & (df_map["manager_test"].str.strip().str.upper() == "PASS")
    )
    df_seed = df_map[mask].copy()
    df_seed["source"]           = "original"
    df_seed["rewrite_attempts"] = 0
    df_seed["rewrite_reasoning"] = ""
    df_seed["context_gaps"]     = ""
    df_seed["rewrite_date"]     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_seed["source_cluster_id"] = df_seed.get("cluster_id", "")
    for col in KEEPER_COLS:
        if col not in df_seed.columns:
            df_seed[col] = ""
    df_keepers = df_seed[KEEPER_COLS].copy()
    df_keepers.to_csv(path, index=False)
    print(f"   ✅ Keeper CSV created with {len(df_keepers)} seed bullets: {path}")
    return df_keepers


def append_keeper(df_keepers: pd.DataFrame, row: dict, path: str) -> pd.DataFrame:
    new_row = {col: row.get(col, "") for col in KEEPER_COLS}
    new_row["rewrite_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_keepers = pd.concat([df_keepers, pd.DataFrame([new_row])], ignore_index=True)
    df_keepers.to_csv(path, index=False)
    return df_keepers


# ---------------------------------------------------------------------------
# DTYPE HELPERS
# ---------------------------------------------------------------------------

def _safe_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    return str(v)


def _safe_numeric(v):
    return pd.to_numeric(v, errors="coerce")


def ensure_writable_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    object_cols = [
        "Bullet Point", "Role / Company", "Tags", "weaknesses",
        "final_bullet", "rewrite_status", "rewrite_reasoning", "context_gaps",
        "next_action", "manager_test",
    ]
    for col in object_cols:
        if col in df.columns:
            df[col] = df[col].astype("object")
    if "rewrite_attempts" in df.columns:
        df["rewrite_attempts"] = pd.to_numeric(df["rewrite_attempts"], errors="coerce")
    return df


def load_already_processed(output_path: str, keepers_path: str, retry_manual: bool = False) -> set:
    done = set()
    skip_statuses = {"KEEP"} if retry_manual else DONE_STATUSES

    if os.path.exists(output_path):
        try:
            df = pd.read_csv(output_path)
            if "rewrite_status" in df.columns and "Bullet Point" in df.columns:
                done_mask = df["rewrite_status"].str.strip().str.upper().isin(skip_statuses)
                done |= set(df.loc[done_mask, "Bullet Point"].dropna().str.strip())
                if "final_bullet" in df.columns:
                    done |= set(df.loc[done_mask, "final_bullet"].dropna().str.strip())
        except Exception as e:
            print(f"   ⚠️ Could not read cluster map output for resume check: {e}")

    if os.path.exists(keepers_path):
        try:
            df_k = pd.read_csv(keepers_path)
            if "Bullet Point" in df_k.columns:
                done |= set(df_k["Bullet Point"].dropna().str.strip())
            if "final_bullet" in df_k.columns:
                done |= set(df_k["final_bullet"].dropna().str.strip())
            print(f"   📚 Keepers CSV: {len(df_k)} rows added to done set.")
        except Exception as e:
            print(f"   ⚠️ Could not read keepers CSV for resume check: {e}")

    return done


# ---------------------------------------------------------------------------
# BULLET PROCESSOR
# ---------------------------------------------------------------------------

def process_bullet(
    row: pd.Series,
    kb: KnowledgeBase,
    rewrite_system: str,
    score_system: str,
    dry_run: bool,
) -> dict:
    original_bullet = str(row["Bullet Point"]).strip()
    tags            = str(row.get("Tags", ""))
    weaknesses      = str(row.get("weaknesses", ""))
    role_company    = str(row.get("Role / Company", ""))
    original_scores = {col: row.get(col) for col in SCORE_COLS + ["weaknesses"]}

    kb_context = kb.context_block_for_bullet(role_company, tags)
    kb_context_chars = len(kb_context)

    current_bullet = original_bullet
    current_scores = original_scores.copy()
    last_rewrite = last_reasoning = last_gaps = ""
    active_rewrite_model   = REWRITE_MODEL
    rewrite_parse_failures = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"   🖊  Attempt {attempt}/{MAX_ATTEMPTS}... (model: {active_rewrite_model})")

        use_minimal_schema = GEMMA_MINIMAL_JSON and "gemma" in active_rewrite_model.lower()
        runner_schema = RewriteOutputMinimalSchema if use_minimal_schema else RewriteOutputSchema

        prompt = build_rewrite_prompt(
            bullet=current_bullet,
            tags=tags,
            weaknesses=str(current_scores.get("weaknesses", "")),
            kb_context=kb_context,
            attempt=attempt,
            prev_scores=current_scores if attempt > 1 else None,
            minimal_schema=use_minimal_schema,
        )

        if dry_run:
            print(f"\n{'='*60}\nDRY RUN PROMPT (attempt {attempt}):\n{prompt}\n{'='*60}\n")
            rewritten = f"[DRY RUN] {original_bullet}"
            reasoning = "dry-run"
            gaps = ""
        else:
            try:
                raw, usage = GeminiClient.generate(
                    model=active_rewrite_model,
                    system_instruction=rewrite_system,
                    contents=prompt,
                    temperature=0.7,
                    response_schema=runner_schema,
                )
                _log_cache_stats(usage, kb_context_chars, attempt)
                parsed = GeminiClient.parse_json(raw)
                rewritten = str(parsed.get("rewritten_bullet", "")).strip()
                reasoning = str(parsed.get("reasoning", "")).strip()
                gaps      = str(parsed.get("context_gaps", "")).strip()

                if not rewritten:
                    raise ValueError("Empty rewritten_bullet in response")

            except SustainedFailureError:
                raise
            except Exception as e:
                rewrite_parse_failures += 1
                print(f"   ⚠️ Rewrite parse error (attempt {attempt}): {e}")
                if rewrite_parse_failures >= MAX_REWRITE_PARSE_FAILURES and active_rewrite_model != REWRITE_FALLBACK_MODEL:
                    print(f"   🔄 Switching to fallback model: {REWRITE_FALLBACK_MODEL}")
                    active_rewrite_model = REWRITE_FALLBACK_MODEL
                time.sleep(SLEEP_ON_RETRY)
                continue

        last_rewrite  = rewritten
        last_reasoning = reasoning
        last_gaps     = gaps

        print(f"   💥 Rewritten: {rewritten[:80]}...")

        new_scores = score_bullet(rewritten, tags, score_system, dry_run)
        action     = decide_action(new_scores)
        print(
            f"   💯 Scores → accuracy={new_scores.get('accuracy_score')} "
            f"bel={new_scores.get('believability_score')} "
            f"clarity={new_scores.get('clarity_score')} "
            f"ats={new_scores.get('ats_value')} "
            f"mgr={new_scores.get('manager_test')} → {action}"
        )

        if action == "KEEP" and new_scores.get("manager_test", "").upper() == "PASS":
            return {
                "final_bullet":      rewritten,
                "rewrite_status":    "KEEP",
                "rewrite_attempts":  attempt,
                "rewrite_reasoning": reasoning,
                "context_gaps":      gaps,
                "source":            "rewrite",
                **{col: new_scores.get(col, "") for col in SCORE_COLS},
                "weaknesses":        new_scores.get("weaknesses", ""),
            }

        current_bullet, current_scores = best_version(
            current_bullet, current_scores, rewritten, new_scores
        )
        current_scores["weaknesses"] = new_scores.get("weaknesses", "")

        if attempt < MAX_ATTEMPTS:
            time.sleep(SLEEP_ON_RETRY)

    print(f"   ⚠️ Max attempts reached. Marking as MANUAL.")
    return {
        "final_bullet":      current_bullet,
        "rewrite_status":    "MANUAL",
        "rewrite_attempts":  MAX_ATTEMPTS,
        "rewrite_reasoning": last_reasoning,
        "context_gaps":      last_gaps,
        "source":            "rewrite",
        **{col: current_scores.get(col, "") for col in SCORE_COLS},
        "weaknesses":        current_scores.get("weaknesses", ""),
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Agentic bullet rewriter")
    parser.add_argument("--limit",        type=int,  default=None,  help="Max bullets to process")
    parser.add_argument("--dry-run",      action="store_true",       help="Print prompts, no API calls")
    parser.add_argument("--retry-manual", action="store_true",       help="Re-run MANUAL bullets")
    parser.add_argument("--model",        type=str,  default=None,   help="Override rewrite model")
    args = parser.parse_args()

    global REWRITE_MODEL
    if args.model:
        REWRITE_MODEL = args.model
        print(f"🔧 Model override: {REWRITE_MODEL}")

    print(f"\n📥 Loading cluster map: {CLUSTER_MAP_IN}")
    df_map = pd.read_csv(CLUSTER_MAP_IN)
    df_map = ensure_writable_dtypes(df_map)

    required_cols = ["Bullet Point", "Role / Company", "Tags", "next_action", "is_representative"]
    for col in required_cols:
        if col not in df_map.columns:
            raise ValueError(f"Missing required column in cluster map: {col}")

    target_actions = {"REWRITE", "REVIEW"}
    if args.retry_manual:
        target_actions.add("MANUAL")

    mask_rep    = df_map["is_representative"].astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
    mask_action = df_map["next_action"].str.strip().str.upper().isin(target_actions)
    df_todo     = df_map[mask_rep & mask_action].copy()

    print(f"   📋 Total cluster map rows:         {len(df_map)}")
    print(f"   🎯 Representative + target action: {len(df_todo)}")

    already_done = load_already_processed(CLUSTER_MAP_OUT, KEEPERS_OUT, retry_manual=args.retry_manual)
    if already_done:
        before = len(df_todo)
        df_todo = df_todo[~df_todo["Bullet Point"].str.strip().isin(already_done)]
        print(f"   ⏭️  Skipping {before - len(df_todo)} already-processed bullets")

    if args.limit:
        df_todo = df_todo.head(args.limit)

    print(f"   ▶️  Bullets to process this run:    {len(df_todo)}\n")

    if df_todo.empty:
        print("✅ Nothing to process. All bullets are already done.")
        return

    rules      = RulesBundle(RULES_DIR, SCORING_DIR)
    kb         = KnowledgeBase()
    kb.warm_segment_cache(df_todo)
    rewrite_system, score_system = build_system_prompts(rules, kb)

    if os.path.exists(CLUSTER_MAP_OUT):
        df_out = pd.read_csv(CLUSTER_MAP_OUT)
        df_out = ensure_writable_dtypes(df_out)
    else:
        df_out = df_map.copy()
        for col in ["final_bullet", "rewrite_status", "rewrite_attempts",
                    "rewrite_reasoning", "context_gaps"]:
            if col not in df_out.columns:
                df_out[col] = ""
        df_out = ensure_writable_dtypes(df_out)

    df_keepers = load_or_init_keepers(KEEPERS_OUT, df_map)

    total       = len(df_todo)
    n_keep      = 0
    n_manual    = 0
    bullets_since_flush = 0

    for i, (idx, row) in enumerate(df_todo.iterrows(), 1):
        bullet_preview = str(row["Bullet Point"])[:60]
        print(f"\n{'─'*60}")
        print(f"[{i}/{total}] {bullet_preview}...")
        print(f"   Tags: {row.get('Tags', '')}  |  Action: {row.get('next_action', '')}")

        result = process_bullet(row, kb, rewrite_system, score_system, dry_run=args.dry_run)

        out_mask = df_out["Bullet Point"].str.strip() == str(row["Bullet Point"]).strip()
        for col, val in result.items():
            if col in df_out.columns:
                df_out.loc[out_mask, col] = _safe_str(val) if col in STRING_SCORE_COLS + ["final_bullet", "rewrite_status", "rewrite_reasoning", "context_gaps"] else _safe_numeric(val) if col in NUMERIC_SCORE_COLS else val

        if result["rewrite_status"] == "KEEP":
            n_keep += 1
            source_cluster_id = ""
            if "cluster_id" in row and pd.notna(row["cluster_id"]):
                try:
                    source_cluster_id = int(float(str(row["cluster_id"])))
                except (ValueError, TypeError):
                    source_cluster_id = str(row["cluster_id"])

            keeper_row = {
                "Bullet Point":      result["final_bullet"],
                "Role / Company":    row.get("Role / Company", ""),
                "Tags":              row.get("Tags", ""),
                "source":            result.get("source", "rewrite"),
                "source_cluster_id": source_cluster_id,
                "rewrite_attempts":  result.get("rewrite_attempts", 0),
                "rewrite_reasoning": result.get("rewrite_reasoning", ""),
                "context_gaps":      result.get("context_gaps", ""),
                **{col: result.get(col, "") for col in SCORE_COLS},
                "weaknesses":        result.get("weaknesses", ""),
            }
            df_keepers = append_keeper(df_keepers, keeper_row, KEEPERS_OUT)
            print(f"   ✅ KEEPER saved (source_cluster_id={source_cluster_id}).")
        else:
            n_manual += 1
            print(f"   🔧 MANUAL — best version retained.")

        bullets_since_flush += 1
        is_last = (i == total)
        if bullets_since_flush >= CSV_FLUSH_EVERY or is_last:
            df_out.to_csv(CLUSTER_MAP_OUT, index=False)
            bullets_since_flush = 0
            print(f"   💾 Flushed cluster map ({i}/{total} bullets processed).")

        if i < total:
            time.sleep(SLEEP_BETWEEN_BULLETS)

    print(f"\n{'='*60}")
    print(f"✅ Run complete: {total} bullets processed")
    print(f"   KEEP:   {n_keep}")
    print(f"   MANUAL: {n_manual}")
    print(f"   Cluster map → {CLUSTER_MAP_OUT}")
    print(f"   Keepers     → {KEEPERS_OUT}")


if __name__ == "__main__":
    main()
