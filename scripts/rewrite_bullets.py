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
  - formatting_rules.yaml   → date format and forbidden layout elements

Usage:
  python rewrite_bullets.py                    # process all REWRITE + REVIEW reps
  python rewrite_bullets.py --limit 20         # cap for testing
  python rewrite_bullets.py --dry-run          # print prompts, no API calls
  python rewrite_bullets.py --retry-manual     # re-run all MANUAL bullets
  python rewrite_bullets.py --retry-manual --model gemma-4-31b-it

Outputs (profiles/<profile>/knowledge_base/):
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

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402
import cli_art
import theme  # noqa: E402

KB_DIR       = profile_paths.kb_dir()
RULES_DIR    = os.path.join(PROJECT_ROOT, "resume-engine", "rules")
SCORING_DIR  = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")

# orchestrator.py lives in the same scripts/ directory as this file.
# Import GeminiClient only — orchestrator.py has no module-level client object.
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

# Gemma calls use model_fallback=False (see process_bullet) so flash-lite
# never inherits Gemma's slim context via GeminiClient's internal swap.
# That means GeminiClient.generate()'s own max_retries=6 default -- with
# its escalating 8/16/32/64/90/90s backoff -- would burn ~5 minutes of
# guaranteed-fail waiting on any bullet still too large for the 16k TPM
# cap after slimming, before process_bullet()'s own handoff ever fires.
# A tight cap here restores the fast-fail speed the old internal
# 2-consecutive-failure fallback used to provide.
GEMMA_MAX_RETRIES     = 2

# Observed failure mode (2026-07-16): with no cap, a model can produce a
# valid answer up front, then degenerate into repeating a phrase (e.g.
# echoing an instruction back at itself) until it exhausts its output
# budget -- one repro hit 65,520 output tokens on a 3-field JSON schema
# that normally needs ~150. The unterminated JSON was unparseable even
# though the real answer was intact near the start (see parse_json's
# salvage fallback in gemini_client.py). This cap bounds the wasted
# tokens/latency on that failure mode; it does not by itself guarantee
# parseable output, since a capped response can still be truncated
# mid-loop -- the salvage fallback is what actually recovers the answer.
REWRITE_MAX_OUTPUT_TOKENS = 2048

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
MAX_CLAIMS_ROWS         = 12
MAX_GEMMA_FILTER_ROWS   = 5   # tighter cap for Gemma's slim tier -- see docs/superpowers/specs/2026-07-15-gemma-slim-context-design.md

# TAG_CONTEXT/BACKGROUND_IDENTITY/BACKGROUND_TAGS/CV_SECTION_KEYWORDS/
# CLAIM_TAG_KEYWORDS/TREERING_KEYWORDS used to be hardcoded here (this
# file predates the engine/profile split and was never updated when
# orchestrator.py's copies were genericized 2026-07-17) -- all per-profile
# now: TAG_CONTEXT/CLAIM_TAG_KEYWORDS come from profile.yml's tags: (see
# _tag_context_map()/_claim_tag_keywords_map() below and
# profile_paths.tags()'s docstring); BACKGROUND_IDENTITY/BACKGROUND_TAGS/
# CV_SECTION_KEYWORDS come from fixed_content.py (see
# profile_paths.fixed_content_module()); the Treering-only deep-evidence
# gate comes from profile.yml's deep_evidence_keywords: (see
# is_deep_evidence_bullet() below).

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
        cli_art.console.print(f"   {theme.colorize_icon('success')} Rules loaded: {label}", soft_wrap=True)
        return data
    except Exception as e:
        cli_art.console.print(f"   {theme.colorize_icon('warning')} Could not load rules {label}: {e}", soft_wrap=True)
        return {}


def _yaml_to_str(data: dict) -> str:
    try:
        return yaml.dump(data, default_flow_style=False, allow_unicode=True).strip()
    except Exception as e:
        cli_art.friendly_warning(
            e, "formatting the rules for the AI",
            "falling back to a simpler format, which may lower rewrite quality")
        return str(data)


class RulesBundle:
    def __init__(self, rules_dir: str, scoring_dir: str = None):
        cli_art.console.print(f"\n{theme.colorize_icon('hint')} Loading rules bundle...", soft_wrap=True)

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
        # manager_test.yaml (full scoring/ rubric — hard_fail_conditions incl.
        # scope_inflation, protected_bullets) and believability.yaml (realism/
        # human_language criteria with worked bad-example patterns) were never
        # loaded here even though audit_bullet_bank.py and orchestrator.py's
        # critique loop both correctly pull them from scoring/ — meaning the
        # rewrite step's own accept/reject judgment ran on a much thinner
        # rubric than everything scoring bullets elsewhere in the pipeline.
        mt  = _load_yaml_safe(os.path.join(scoring_dir, "manager_test.yaml"),       "manager_test (scoring)")
        bel = _load_yaml_safe(os.path.join(scoring_dir, "believability.yaml"),      "believability")

        # Truthfulness/anti-fabrication guardrails (hard_failures,
        # truthfulness_rules, scope & believability) are identical in both
        # the full and Gemma-slim blocks below -- these are the rules where
        # a miss costs the most (a fabricated or inflated claim reaching a
        # real resume), so they're never candidates for trimming. Only the
        # verb-intent and style-rules payloads vary between variants.
        def _build_rewrite_block(verb_intent_data: dict, style_rules_data: dict, style_heading: str) -> str:
            return "\n".join([
                "=== VERB INTENT MAP ===",
                "Before choosing a verb, identify the accomplishment intent (creation, implementation,",
                "optimization, automation, analysis, revenue_generation, training, leadership, etc.)",
                "and select from the matching preferred_verbs list below.",
                _yaml_to_str(verb_intent_data),
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
                style_heading,
                _yaml_to_str(style_rules_data),
            ])

        self.rewrite_rules_block = _build_rewrite_block(vim, sr, "=== STYLE RULES ===")

        # Gemma-slim variant: gemma-4-31b-it has a 16k TPM cap (confirmed
        # 2026-07-16, not the "unlimited" this account used to have) --
        # the KB static prefix plus the largest per-company segment alone
        # already runs ~10k tokens, leaving only ~4k tokens of headroom
        # for the system prompt before a request exceeds the entire
        # per-minute budget in one shot (verified: Treering [email][brand]
        # at ~16,814 estimated tokens 429'd on every retry across 128s+ of
        # backoff -- not a transient/velocity issue, the request is simply
        # bigger than the whole budget). The full rules block is ~2x that
        # headroom on its own.
        #
        # Cuts below are confined to two categories, NOT to the
        # truthfulness/believability content above:
        #   1. Document-layout rules (typography, page layout, tagline,
        #      skills-section positioning, page-level ATS formatting) --
        #      dead weight for a single bullet-text rewrite regardless of
        #      model; a rewrite call cannot act on "page_count: 2" or
        #      "name_font: DM Serif Display".
        #   2. Verb guidance duplicated elsewhere in this same prompt --
        #      verb_intent_mapping's per-category prose (description +
        #      weak/strong examples) restates what VERB TAXONOMY's
        #      elite/strong tiers and LANGUAGE QUALITY's weak_verbs already
        #      cover structurally; style_rules' domain-organized
        #      verb_upgrades tables (data_and_ops, content_and_comms, etc.)
        #      are the same swap logic VERB INTENT MAP already encodes via
        #      accomplishment-intent -> preferred_verbs.
        def _rule_text(item) -> str:
            # A couple of style_rules.yaml list entries contain an unintended
            # colon (e.g. "Recommended verbs: Architected, Authored, ..."),
            # which YAML parses as a {key: value} dict instead of a plain
            # string like their neighbors. Filtering below needs to match
            # against the text regardless of which shape a given entry took.
            if isinstance(item, dict):
                return next(iter(item.keys()), "")
            return str(item)

        gemma_verb_intent = {
            "intent_categories": {
                intent: {
                    "signals":         data.get("signals", []),
                    "preferred_verbs": data.get("preferred_verbs", {}),
                }
                for intent, data in vim.get("intent_categories", {}).items()
            },
            "selection_rules":   vim.get("selection_rules", {}),
            "verb_replacements": vim.get("verb_replacements", {}),
            "final_principle":   vim.get("final_principle", ""),
        }
        gemma_style_rules = {
            "philosophy": [
                p for p in sr.get("philosophy", [])
                if any(kw in _rule_text(p).lower() for kw in ("bullet", "metric", "verb", "cares test", "systems not tasks"))
            ],
            "writing_style":     sr.get("writing_style", {}),
            "bullet_structure":  sr.get("bullet_structure", {}),
            "verb_rules":        [r for r in sr.get("verb_rules", []) if not _rule_text(r).startswith("Recommended verbs")],
            "vague_verbs":       sr.get("vague_verbs", []),
            "forbidden_openers": sr.get("forbidden_openers", []),
            "forbidden_phrases": sr.get("forbidden_phrases", []),
            "punctuation_rules": sr.get("punctuation_rules", []),
            "metrics_rules":     sr.get("metrics_rules", {}),
            "tool_mention_rules": sr.get("tool_mention_rules", {}),
            "redundancy_rules":  sr.get("redundancy_rules", {}),
        }
        self.rewrite_rules_block_gemma = _build_rewrite_block(
            gemma_verb_intent, gemma_style_rules, "=== STYLE RULES (bullet-level subset) ==="
        )

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
            "",
            "REDUNDANCY — the bullet's own Role/Company is provided in the input below.",
            "If the bullet's text restates that SAME company's name, or includes an unneeded",
            "specific calendar month/season + year, treat it as a clarity_score and",
            "accuracy_score deduction (adjective_padding-level, not a hard fail) per:",
            _yaml_to_str(sr.get("redundancy_rules", {})),
        ])

        cli_art.console.print(f"   {theme.colorize_icon('hint')} Rewrite rules block: {len(self.rewrite_rules_block):,} chars", soft_wrap=True)
        cli_art.console.print(f"   {theme.colorize_icon('hint')} Gemma rules block (slim): {len(self.rewrite_rules_block_gemma):,} chars", soft_wrap=True)
        cli_art.console.print(f"   {theme.colorize_icon('hint')} Score rules block:   {len(self.score_rules_block):,} chars\n", soft_wrap=True)


# ---------------------------------------------------------------------------
# FILE LOADERS
# ---------------------------------------------------------------------------

def load_text_file(path: str, label: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded {label} ({len(content):,} chars)", soft_wrap=True)
        return content
    except Exception as e:
        cli_art.console.print(f"   {theme.colorize_icon('warning')} Could not load {label}: {e}", soft_wrap=True)
        return ""


def load_json_file(path: str, label: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        content = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded {label} ({len(content):,} chars)", soft_wrap=True)
        return content
    except Exception as e:
        cli_art.console.print(f"   {theme.colorize_icon('warning')} Could not load {label}: {e}", soft_wrap=True)
        return ""


def load_json_entries(path: str, list_key: str) -> list:
    """Loads a KB file shaped like {"_meta": {...}, "<list_key>": [...]}
    and returns the parsed list of entry dicts -- unlike load_json_file,
    which returns a pre-serialized compact JSON string for direct prompt
    injection, this keeps the structure so callers can filter entries."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        entries = data.get(list_key, []) if isinstance(data, dict) else []
        cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded {list_key} entries ({len(entries)} rows)", soft_wrap=True)
        return entries
    except Exception as e:
        cli_art.console.print(f"   {theme.colorize_icon('warning')} Could not load {list_key} entries: {e}", soft_wrap=True)
        return []


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
        cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded verified-claims ({len(df)} resume-usable rows)", soft_wrap=True)
        return df
    except Exception as e:
        cli_art.console.print(f"   {theme.colorize_icon('warning')} Could not load verified-claims: {e}", soft_wrap=True)
        return pd.DataFrame()


def load_screenshot_metrics(path: str) -> str:
    try:
        df = pd.read_csv(path)
        content = df.to_csv(index=False)
        cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded screenshot metrics ({len(df)} rows)", soft_wrap=True)
        return content
    except Exception as e:
        cli_art.console.print(f"   {theme.colorize_icon('warning')} Could not load screenshot metrics: {e}", soft_wrap=True)
        return ""


def get_verified_claims_text(df_claims: pd.DataFrame) -> str:
    if df_claims.empty:
        return ""
    cols = ["Claim / Finding", "Metric(s)", "Confidence", "Evidence / Detail"]
    available = [c for c in cols if c in df_claims.columns]
    return df_claims[available].to_csv(index=False)


def is_deep_evidence_bullet(role_company: str, keywords: list) -> bool:
    """Whether role_company matches profile.yml's deep_evidence_keywords --
    see orchestrator.py's identical function for the full rationale. Empty
    keywords (a profile with no deep-evidence archive) means always False."""
    if not isinstance(role_company, str) or not keywords:
        return False
    rc = role_company.lower()
    return any(kw in rc for kw in keywords)


def _tag_context_map() -> dict:
    """Bracket-tag ("[ops]") -> persona_description, from profile.yml's
    tags: -- see orchestrator.py's identical function."""
    return {f"[{t['name']}]": t["persona_description"] for t in profile_paths.tags()}


def _claim_tag_keywords_map() -> dict:
    """Bracket-tag -> keywords, from profile.yml's tags: -- see
    orchestrator.py's identical function."""
    return {f"[{t['name']}]": (t.get("keywords") or []) for t in profile_paths.tags()}


def extract_cv_section(cv_text: str, role_company: str) -> str:
    if not cv_text or not role_company:
        return cv_text
    rc_lower = role_company.lower()
    fixed_content = profile_paths.fixed_content_module()
    matched_heading = None
    for keywords, heading in fixed_content.CV_SECTION_KEYWORDS:
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


def filter_claims_by_tags(df_claims: pd.DataFrame, tags: str, max_rows: int = MAX_CLAIMS_ROWS) -> pd.DataFrame:
    if df_claims.empty:
        return df_claims
    tags_lower = tags.lower() if isinstance(tags, str) else ""
    keywords = []
    include_all = False
    for tag, kws in _claim_tag_keywords_map().items():
        if tag in tags_lower:
            if not kws:
                include_all = True
                break
            keywords.extend(kws)
    if include_all or not keywords:
        return df_claims.head(max_rows)
    text_cols = [c for c in df_claims.columns if df_claims[c].dtype == object]
    pattern = "|".join(re.escape(k) for k in keywords)
    mask = df_claims[text_cols].apply(
        lambda col: col.str.contains(pattern, case=False, na=False)
    ).any(axis=1)
    filtered = df_claims[mask]
    if len(filtered) < 3:
        filtered = df_claims.head(max_rows)
    return filtered.head(max_rows)


def _employer_tokens(s: str) -> list:
    """Splits a company/employer string on common multi-name separators
    ("/", "&", "→", "+") into lowercased tokens, dropping fragments too
    short to be a meaningful name (e.g. stray punctuation). Shared by
    filter_projects_by_employer() to compare a bullet's Role/Company
    value (e.g. "Element 8 / Strategy LLC") against a verified_projects.json
    entry's employer value (e.g. "Element 8 → Strategy LLC") despite the
    two files using different separator conventions."""
    return [t.strip().lower() for t in re.split(r"[/&→+]", s or "") if len(t.strip()) > 2]


def filter_projects_by_employer(projects: list, role_company: str) -> list:
    """Returns only the verified_projects.json entries whose "employer"
    field actually matches this bullet's own Role/Company -- see the
    root-cause note on _build_static_prefix()/_build_segment_bundle():
    verified_projects.json mixes multiple employers (10 Treering entries,
    1 VML, 1 Element 8/Strategy LLC), so including it whole (or filtering
    it by TAG alone, which matches on subject-matter keyword overlap, not
    company) let another employer's real, verified project detail bleed
    into a bullet under a different company -- e.g. a weak Treering
    bullet's rewrite borrowing the more vivid Strategy LLC brand-identity
    project, producing a bullet that's factually accurate but tagged
    under the wrong employer. Every project record already carries an
    "employer" field; this is the only filter that should ever gate
    verified_projects into a rewrite prompt."""
    rc_tokens = _employer_tokens(role_company)
    if not rc_tokens:
        return []
    matched = []
    for p in projects:
        emp_tokens = _employer_tokens(p.get("employer", ""))
        if any(rt in et or et in rt for rt in rc_tokens for et in emp_tokens):
            matched.append(p)
    return matched


def filter_json_entries_by_tags(entries: list, tags: str, max_rows: int) -> list:
    if not entries:
        return entries
    tags_lower = tags.lower() if isinstance(tags, str) else ""
    keywords = []
    include_all = False
    for tag, kws in _claim_tag_keywords_map().items():
        if tag in tags_lower:
            if not kws:
                include_all = True
                break
            keywords.extend(kws)
    if include_all or not keywords:
        return entries[:max_rows]

    def _entry_matches(entry: dict) -> bool:
        haystack = " ".join(str(v) for v in entry.values() if isinstance(v, str)).lower()
        return any(kw in haystack for kw in keywords)

    filtered = [e for e in entries if _entry_matches(e)]
    if len(filtered) < 3:
        filtered = entries[:max_rows]
    return filtered[:max_rows]


def build_background_summary(tags: str) -> str:
    fixed_content = profile_paths.fixed_content_module()
    tags_lower = tags.lower() if isinstance(tags, str) else ""
    sections = [fixed_content.BACKGROUND_IDENTITY]
    for tag, content in fixed_content.BACKGROUND_TAGS.items():
        if tag in tags_lower:
            sections.append(content)
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# KNOWLEDGE BASE  —  cache-optimised
# ---------------------------------------------------------------------------

class KnowledgeBase:
    def __init__(self):
        cli_art.console.print(f"\n{theme.colorize_icon('hint')} Loading knowledge base context...", soft_wrap=True)
        self.cv_full           = load_text_file(KB_CV,               "cv.md")
        self.bg_raw            = load_text_file(KB_BACKGROUND,        "user-background-guide.md")
        raw_profile            = load_text_file(KB_PROFILE,           "profile.yml")
        self.profile           = trim_profile_yml(raw_profile)
        self.df_claims         = load_verified_claims(KB_VERIFIED_CLAIMS)
        self.screenshot_metrics = load_screenshot_metrics(KB_SCREENSHOT_METRICS)
        self.screenshot_df      = load_verified_claims(KB_SCREENSHOT_METRICS)  # same CSV, DataFrame form for Gemma-tier filtering
        self.verified_facts    = load_json_file(KB_VERIFIED_FACTS,    "verified_facts.json")
        self.verified_metrics  = load_json_file(KB_VERIFIED_METRICS,  "verified_metrics.json")
        self.metrics_entries   = load_json_entries(KB_VERIFIED_METRICS, "metrics")
        self.projects_entries  = load_json_entries(KB_VERIFIED_PROJECTS, "projects")
        self.verified_tools    = load_json_file(KB_VERIFIED_TOOLS,    "verified_tools.json")
        self.recruiter_patterns = load_json_file(KB_RECRUITER_PATTERNS, "recruiter_memory_patterns.json")
        self.voice_anchors      = load_text_file(KB_VOICE_ANCHORS,    "voice-anchors.md")
        self.deep_evidence_keywords = (yaml.safe_load(raw_profile) or {}).get("deep_evidence_keywords") or []

        cli_art.console.print(f"   {theme.colorize_icon('hint')} profile.yml trimmed to {len(self.profile):,} chars", soft_wrap=True)

        self.static_prefix = self._build_static_prefix()
        cli_art.console.print(f"   {theme.colorize_icon('hint')} Static prefix (Tier 1): {len(self.static_prefix):,} chars — shared across ALL bullets", soft_wrap=True)

        self.gemma_static_prefix = self._build_gemma_static_prefix()
        cli_art.console.print(f"   {theme.colorize_icon('hint')} Gemma static prefix (slim): {len(self.gemma_static_prefix):,} chars — Gemma-only, flash-lite keeps the full tier", soft_wrap=True)

        self._segment_cache: dict = {}
        self._gemma_segment_cache: dict = {}
        cli_art.console.print("   ℹ️  Call warm_segment_cache(df_map) before starting the rewrite loop.\n", soft_wrap=True)

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
                "These are the only facts about this candidate's career that are evidence-backed.\n"
                "Do NOT invent facts outside this list.\n"
                + self.verified_facts
            )
        if self.verified_tools:
            sections.append(
                "=== VERIFIED TOOLS (HF002 guard — only claim tools listed here) ===\n"
                "Never claim proficiency with any tool not present in this list.\n"
                + self.verified_tools
            )
        # verified_projects is deliberately NOT included here -- it mixes
        # multiple employers (Treering, VML, Element 8/Strategy LLC), so
        # including it in this prefix (shared identically across every
        # bullet regardless of company) was the actual root cause of
        # cross-company content leaking into rewrites -- see
        # filter_projects_by_employer()'s docstring. It's injected per-bullet
        # in _build_segment_bundle()/_build_gemma_segment_bundle() instead,
        # filtered to the bullet's own employer.
        if self.voice_anchors:
            sections.append(
                "=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n"
                + self.voice_anchors
            )
        return "\n\n".join(sections)

    def _build_gemma_static_prefix(self) -> str:
        """Slim static tier for Gemma only -- see docs/superpowers/specs/
        2026-07-15-gemma-slim-context-design.md. Keeps only guardrails
        (verified_facts, verified_tools) and voice_anchors (small, directly
        serves rewrite quality). Drops profile.yml entirely -- that's
        strategic career-positioning content, not needed to rewrite a
        single existing bullet."""
        sections = []
        if self.verified_facts:
            sections.append(
                "=== VERIFIED FACTS (high-confidence claims — use freely) ===\n"
                "These are the only facts about this candidate's career that are evidence-backed.\n"
                "Do NOT invent facts outside this list.\n"
                + self.verified_facts
            )
        if self.verified_tools:
            sections.append(
                "=== VERIFIED TOOLS (HF002 guard — only claim tools listed here) ===\n"
                "Never claim proficiency with any tool not present in this list.\n"
                + self.verified_tools
            )
        if self.voice_anchors:
            sections.append(
                "=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n"
                + self.voice_anchors
            )
        return "\n\n".join(sections)

    def _build_gemma_segment_bundle(self, role_company: str, tags: str) -> str:
        """Slim segment bundle for Gemma only. cv excerpt and background
        summary are unchanged (already small); verified_projects and, for
        Treering bullets, claims/metrics/screenshots are tag-filtered to
        MAX_GEMMA_FILTER_ROWS instead of included whole or at the looser
        MAX_CLAIMS_ROWS cap.

        verified_projects.json mixes multiple employers (10 Treering
        entries, 1 VML, 1 Element 8/Strategy LLC). This used to filter it
        by TAG alone (no company check), which let Treering-specific
        project detail leak into non-Treering bullets purely on keyword
        overlap (e.g. an "Inside Sales Team" bullet tagged [email] still
        matched Treering's "Outreach.io Platform Rollout" project) --
        gating it behind is_deep_evidence_bullet only patched the symptom
        for Treering-tagged bullets, and as a side effect meant VML/
        Strategy LLC bullets never got their own real project detail
        either, since deep_evidence_keywords is Treering-only. Filtering
        by the project's own "employer" field via
        filter_projects_by_employer() (see its docstring) fixes both: any
        company only ever sees its own projects, and every company with
        real project data gets to use it, not just Treering."""
        sections = []
        cv_section = extract_cv_section(self.cv_full, role_company)
        if cv_section:
            label = ("ROLE CONTEXT (cv.md excerpt)"
                     if cv_section != self.cv_full else "CAREER OVERVIEW (cv.md)")
            sections.append(f"=== {label} ===\n{cv_section}")
        bg_summary = build_background_summary(tags)
        if bg_summary:
            sections.append(f"=== BACKGROUND CONTEXT ===\n{bg_summary}")

        filtered_projects = filter_projects_by_employer(self.projects_entries, role_company)[:MAX_GEMMA_FILTER_ROWS]
        if filtered_projects:
            sections.append(
                f"=== VERIFIED PROJECTS ({role_company} only) ===\n"
                "Use these to add accurate project detail and scope. Do NOT use project "
                "detail from any other employer, even if it seems more impressive.\n"
                + json.dumps(filtered_projects, ensure_ascii=False, separators=(",", ":"))
            )

        if is_deep_evidence_bullet(role_company, self.deep_evidence_keywords):
            filtered_claims = filter_claims_by_tags(self.df_claims, tags, max_rows=MAX_GEMMA_FILTER_ROWS)
            claims_text = get_verified_claims_text(filtered_claims)
            if claims_text:
                sections.append(
                    f"=== VERIFIED CLAIMS & METRICS ({role_company} — resume-usable, tag-filtered) ===\n"
                    "Use these to inject real, verified metrics where appropriate. "
                    "Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                    + claims_text
                )
            filtered_screenshots = filter_claims_by_tags(self.screenshot_df, tags, max_rows=MAX_GEMMA_FILTER_ROWS)
            if not filtered_screenshots.empty:
                sections.append(
                    "=== SCREENSHOT-SOURCED METRICS (tag-filtered) ===\n"
                    + filtered_screenshots.to_csv(index=False)
                )
            filtered_metrics = filter_json_entries_by_tags(self.metrics_entries, tags, MAX_GEMMA_FILTER_ROWS)
            if filtered_metrics:
                sections.append(
                    "=== VERIFIED METRICS (authoritative — tag-filtered) ===\n"
                    f"These are the ONLY numeric metrics that may be cited as hard facts in {role_company} bullets.\n"
                    + json.dumps(filtered_metrics, ensure_ascii=False, separators=(",", ":"))
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

        filtered_projects = filter_projects_by_employer(self.projects_entries, role_company)
        if filtered_projects:
            sections.append(
                f"=== VERIFIED PROJECTS ({role_company} only) ===\n"
                "Use these to add accurate project detail and scope. Do NOT use project "
                "detail from any other employer, even if it seems more impressive.\n"
                + json.dumps(filtered_projects, ensure_ascii=False, separators=(",", ":"))
            )

        if is_deep_evidence_bullet(role_company, self.deep_evidence_keywords):
            filtered_claims = filter_claims_by_tags(self.df_claims, tags)
            claims_text = get_verified_claims_text(filtered_claims)
            if claims_text:
                sections.append(
                    f"=== VERIFIED CLAIMS & METRICS ({role_company} — resume-usable, tag-filtered) ===\n"
                    "Use these to inject real, verified metrics where appropriate. "
                    "Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                    + claims_text
                )
            if self.screenshot_metrics:
                sections.append(f"=== SCREENSHOT-SOURCED METRICS ===\n{self.screenshot_metrics}")
            if self.verified_metrics:
                sections.append(
                    "=== VERIFIED METRICS (authoritative — use these numbers, not guesses) ===\n"
                    f"These are the ONLY numeric metrics that may be cited as hard facts in {role_company} bullets.\n"
                    + self.verified_metrics
                )
        return "\n\n".join(sections)

    @staticmethod
    def _normalize_tags(tags_str: str) -> str:
        """Normalize tag string by sorting individual tags alphabetically.
        '[email][content]' and '[content][email]' both normalize to '[content][email]'."""
        tag_list = re.findall(r'\[([^\]]+)\]', tags_str)
        return ''.join(f'[{tag}]' for tag in sorted(tag_list))

    def warm_segment_cache(self, df: pd.DataFrame) -> None:
        self._segment_cache = {}
        self._gemma_segment_cache = {}
        raw_pairs = df[["Role / Company", "Tags"]].drop_duplicates()
        # Normalize tags and deduplicate (same company+tags in different order become one cache entry)
        unique_pairs = {(str(row["Role / Company"]), self._normalize_tags(str(row["Tags"]))) for _, row in raw_pairs.iterrows()}
        pairs = sorted(unique_pairs)
        cli_art.console.print(f"\n{theme.colorize_icon('hint')} Warming segment cache for {len(pairs)} unique (company, tags) combos...", soft_wrap=True)
        for rc, tags in pairs:
            bundle = self._build_segment_bundle(rc, tags)
            self._segment_cache[(rc, tags)] = bundle
            gemma_bundle = self._build_gemma_segment_bundle(rc, tags)
            self._gemma_segment_cache[(rc, tags)] = gemma_bundle
            deep_evidence_flag = " [+claims]" if is_deep_evidence_bullet(rc, self.deep_evidence_keywords) else ""
            cli_art.console.print(f"   {theme.colorize_icon('hint')} ({rc[:30]!r}, {tags[:40]!r}) → {len(bundle):,} chars{deep_evidence_flag} (Gemma: {len(gemma_bundle):,} chars)", soft_wrap=True)
        cli_art.console.print(f"   {theme.colorize_icon('success')} {len(self._segment_cache)} segment bundles ready.\n", soft_wrap=True)

    def context_block_for_bullet(self, role_company: str, tags: str) -> str:
        normalized_tags = self._normalize_tags(tags)
        key = (role_company, normalized_tags)
        if key not in self._segment_cache:
            cli_art.console.print(f"   {theme.colorize_icon('warning')} Cache miss for {key} — building segment on demand.", soft_wrap=True)
            self._segment_cache[key] = self._build_segment_bundle(role_company, normalized_tags)
        segment = self._segment_cache[key]
        return f"{self.static_prefix}\n\n{segment}" if segment else self.static_prefix

    def context_block_for_bullet_gemma(self, role_company: str, tags: str) -> str:
        normalized_tags = self._normalize_tags(tags)
        key = (role_company, normalized_tags)
        if key not in self._gemma_segment_cache:
            cli_art.console.print(f"   {theme.colorize_icon('warning')} Gemma cache miss for {key} — building segment on demand.", soft_wrap=True)
            self._gemma_segment_cache[key] = self._build_gemma_segment_bundle(role_company, normalized_tags)
        segment = self._gemma_segment_cache[key]
        return f"{self.gemma_static_prefix}\n\n{segment}" if segment else self.gemma_static_prefix

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
    rewrite_system       = REWRITE_SYSTEM_BASE.format(rules_block=rules.rewrite_rules_block)
    rewrite_system_gemma = REWRITE_SYSTEM_BASE.format(rules_block=rules.rewrite_rules_block_gemma)
    score_system   = SCORE_SYSTEM_BASE.format(
        rules_block=rules.score_rules_block,
        recruiter_block=kb.recruiter_context_block(),
    )
    cli_art.console.print(f"   {theme.colorize_icon('hint')}  Rewrite system prompt: {len(rewrite_system):,} chars (stable across ALL calls)", soft_wrap=True)
    cli_art.console.print(f"   {theme.colorize_icon('hint')}  Gemma rewrite system prompt (slim): {len(rewrite_system_gemma):,} chars", soft_wrap=True)
    cli_art.console.print(f"   {theme.colorize_icon('hint')} Score system prompt:   {len(score_system):,} chars", soft_wrap=True)
    return rewrite_system, rewrite_system_gemma, score_system


# ---------------------------------------------------------------------------
# PERSONA HELPER
# ---------------------------------------------------------------------------

def persona_context(tags: str) -> str:
    tag_context = _tag_context_map()
    if not isinstance(tags, str) or not tags.strip():
        return "this candidate's target roles"
    parts = [tag_context[tag] for tag in tag_context if tag in tags.lower()]
    return ", ".join(parts) if parts else "this candidate's target roles"


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
        cli_art.console.print(f"   {theme.colorize_icon('hint')} tokens — {token_part} | {theme.colorize_icon('hint')} cached: {cached_tokens:,}", soft_wrap=True)
    else:
        cli_art.console.print(f"   {theme.colorize_icon('hint')} tokens — {token_part}", soft_wrap=True)


# ---------------------------------------------------------------------------
# SCORING
# ---------------------------------------------------------------------------

def score_bullet(bullet: str, tags: str, score_system: str, role_company: str = "", dry_run: bool = False) -> dict:
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
            f"--- ROLE / COMPANY (context only -- flag if the bullet redundantly restates this) ---\n{role_company}\n\n"
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
    "rewrite_date", "source_cluster_id", "audit_status",
]


def load_or_init_keepers(path: str, df_map: pd.DataFrame) -> pd.DataFrame:
    if os.path.exists(path):
        cli_art.console.print(f"   {theme.colorize_icon('hint')} Loading existing keepers: {path}", soft_wrap=True)
        df = pd.read_csv(path)
        for col in KEEPER_COLS:
            if col not in df.columns:
                df[col] = ""
        return df

    cli_art.console.print(f"   {theme.colorize_icon('hint')} Seeding keeper CSV from existing KEEP+PASS bullets in cluster map...", soft_wrap=True)
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
    cli_art.console.print(f"   {theme.colorize_icon('success')} Keeper CSV created with {len(df_keepers)} seed bullets: {path}", soft_wrap=True)
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
            cli_art.console.print(f"   {theme.colorize_icon('warning')} Could not read cluster map output for resume check: {e}", soft_wrap=True)

    if os.path.exists(keepers_path):
        try:
            df_k = pd.read_csv(keepers_path)
            if "Bullet Point" in df_k.columns:
                done |= set(df_k["Bullet Point"].dropna().str.strip())
            if "final_bullet" in df_k.columns:
                done |= set(df_k["final_bullet"].dropna().str.strip())
            cli_art.console.print(f"   {theme.colorize_icon('hint')} Keepers CSV: {len(df_k)} rows added to done set.", soft_wrap=True)
        except Exception as e:
            cli_art.console.print(f"   {theme.colorize_icon('warning')} Could not read keepers CSV for resume check: {e}", soft_wrap=True)

    return done


# ---------------------------------------------------------------------------
# BULLET PROCESSOR
# ---------------------------------------------------------------------------

def process_bullet(
    row: pd.Series,
    kb: KnowledgeBase,
    rewrite_system: str,
    rewrite_system_gemma: str,
    score_system: str,
    dry_run: bool,
    start_model: str = None,
) -> dict:
    """start_model overrides which model the first attempt targets --
    defaults to REWRITE_MODEL (Gemma), matching every existing caller's
    behavior. Pass REWRITE_FALLBACK_MODEL to skip Gemma entirely for
    bullets already known to need it (e.g. audit_keepers.py's
    --auto-rewrite queue, which only ever contains bullets that already
    failed a first Gemma-led pass)."""
    original_bullet = str(row["Bullet Point"]).strip()
    tags            = str(row.get("Tags", ""))
    weaknesses      = str(row.get("weaknesses", ""))
    role_company    = str(row.get("Role / Company", ""))
    original_scores = {col: row.get(col) for col in SCORE_COLS + ["weaknesses"]}

    kb_context_gemma = kb.context_block_for_bullet_gemma(role_company, tags)
    kb_context_full  = kb.context_block_for_bullet(role_company, tags)

    current_bullet = original_bullet
    current_scores = original_scores.copy()
    last_rewrite = last_reasoning = last_gaps = ""
    active_rewrite_model   = start_model or REWRITE_MODEL
    rewrite_parse_failures = 0

    for attempt in range(1, MAX_ATTEMPTS + 1):
        cli_art.console.print(f"   {theme.colorize_icon('hint')} Attempt {attempt}/{MAX_ATTEMPTS}... (model: {active_rewrite_model})", soft_wrap=True)

        is_gemma_attempt = "gemma" in active_rewrite_model.lower()
        kb_context = kb_context_gemma if is_gemma_attempt else kb_context_full
        active_rewrite_system = rewrite_system_gemma if is_gemma_attempt else rewrite_system

        use_minimal_schema = GEMMA_MINIMAL_JSON and is_gemma_attempt
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
            cli_art.console.rule(f"DRY RUN PROMPT (attempt {attempt})", style="dim", align="left")
            cli_art.console.print(cli_art._escape_markup(prompt), soft_wrap=True)
            rewritten = f"[DRY RUN] {original_bullet}"
            reasoning = "dry-run"
            gaps = ""
        else:
            try:
                raw, usage = GeminiClient.generate(
                    model=active_rewrite_model,
                    system_instruction=active_rewrite_system,
                    contents=prompt,
                    temperature=0.7,
                    response_schema=runner_schema,
                    # False for BOTH models here, not just Gemma's attempt --
                    # MODEL_FALLBACKS is bidirectional (flash-lite -> Gemma
                    # too), and a flash-lite call that internally bounced to
                    # Gemma on a transport error would hand Gemma the FULL
                    # context it was built with, right back into the same
                    # oversized-prompt problem this whole feature exists to
                    # prevent. The explicit handoff above is the only path
                    # that's allowed to switch models for this call.
                    model_fallback=False,
                    max_retries=GEMMA_MAX_RETRIES if is_gemma_attempt else 6,
                    max_output_tokens=REWRITE_MAX_OUTPUT_TOKENS,
                )
                _log_cache_stats(usage, len(kb_context), attempt)

                if raw is None and is_gemma_attempt:
                    # Gemma exhausted its own retries (model_fallback=False,
                    # so no internal swap happened) -- a confirmed capacity
                    # exhaustion, not a one-off parse hiccup. Hand off to
                    # flash-lite with the FULL context immediately rather
                    # than retrying Gemma again with the same slim context.
                    cli_art.console.print(f"   {theme.colorize_icon('warning')} Gemma exhausted retries — switching to fallback model: {REWRITE_FALLBACK_MODEL}", soft_wrap=True)
                    active_rewrite_model = REWRITE_FALLBACK_MODEL
                    time.sleep(SLEEP_ON_RETRY)
                    continue

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
                cli_art.console.print(f"   {theme.colorize_icon('warning')} Rewrite parse error (attempt {attempt}): {e}", soft_wrap=True)
                if rewrite_parse_failures >= MAX_REWRITE_PARSE_FAILURES and active_rewrite_model != REWRITE_FALLBACK_MODEL:
                    cli_art.console.print(f"   {theme.colorize_icon('warning')} Switching to fallback model: {REWRITE_FALLBACK_MODEL}", soft_wrap=True)
                    active_rewrite_model = REWRITE_FALLBACK_MODEL
                time.sleep(SLEEP_ON_RETRY)
                continue

        last_rewrite  = rewritten
        last_reasoning = reasoning
        last_gaps     = gaps

        cli_art.console.print(f"   {theme.colorize_icon('hint')} Rewritten: {rewritten[:80]}...", soft_wrap=True)

        new_scores = score_bullet(rewritten, tags, score_system, role_company=role_company, dry_run=dry_run)
        action     = decide_action(new_scores)
        cli_art.console.print(
            f"   {theme.colorize_icon('evaluate')} Scores → accuracy={new_scores.get('accuracy_score')} "
            f"bel={new_scores.get('believability_score')} "
            f"clarity={new_scores.get('clarity_score')} "
            f"ats={new_scores.get('ats_value')} "
            f"mgr={new_scores.get('manager_test')} → {action}"
        , soft_wrap=True)
        cli_art.console.print()

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

    cli_art.console.print(f"   {theme.colorize_icon('warning')} Max attempts reached. Marking as MANUAL.", soft_wrap=True)
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
        cli_art.console.print(f"{theme.colorize_icon('hint')} Model override: {REWRITE_MODEL}", soft_wrap=True)

    cli_art.console.print(f"\n{theme.colorize_icon('hint')} Loading cluster map: {CLUSTER_MAP_IN}", soft_wrap=True)
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

    cli_art.console.print(f"   {theme.colorize_icon('hint')} Total cluster map rows:         {len(df_map)}", soft_wrap=True)
    cli_art.console.print(f"   {theme.colorize_icon('hint')} Representative + target action: {len(df_todo)}", soft_wrap=True)

    already_done = load_already_processed(CLUSTER_MAP_OUT, KEEPERS_OUT, retry_manual=args.retry_manual)
    if already_done:
        before = len(df_todo)
        df_todo = df_todo[~df_todo["Bullet Point"].str.strip().isin(already_done)]
        cli_art.console.print(f"   {theme.colorize_icon('hint')}  Skipping {before - len(df_todo)} already-processed bullets", soft_wrap=True)

    if args.limit:
        df_todo = df_todo.head(args.limit)

    cli_art.console.print(f"   {theme.colorize_icon('hint')}  Bullets to process this run:    {len(df_todo)}\n", soft_wrap=True)

    if df_todo.empty:
        cli_art.console.print(f"{theme.colorize_icon('success')} Nothing to process. All bullets are already done.", soft_wrap=True)
        return

    rules      = RulesBundle(RULES_DIR, SCORING_DIR)
    kb         = KnowledgeBase()
    kb.warm_segment_cache(df_todo)
    rewrite_system, rewrite_system_gemma, score_system = build_system_prompts(rules, kb)

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
        cli_art.console.rule(f"[{i}/{total}] {bullet_preview}...", style="dim", align="left")
        cli_art.console.print(cli_art._escape_markup(f"   Tags: {row.get('Tags', '')}  |  Action: {row.get('next_action', '')}"), soft_wrap=True)

        result = process_bullet(row, kb, rewrite_system, rewrite_system_gemma, score_system, dry_run=args.dry_run)

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
            cli_art.console.print(f"   {theme.colorize_icon('success')} KEEPER saved (source_cluster_id={source_cluster_id}).", soft_wrap=True)
        else:
            n_manual += 1
            cli_art.console.print(f"   {theme.colorize_icon('warning')} MANUAL — best version retained.", soft_wrap=True)

        bullets_since_flush += 1
        is_last = (i == total)
        if bullets_since_flush >= CSV_FLUSH_EVERY or is_last:
            df_out.to_csv(CLUSTER_MAP_OUT, index=False)
            bullets_since_flush = 0
            cli_art.console.print(f"   {theme.colorize_icon('hint')} Flushed cluster map ({i}/{total} bullets processed).", soft_wrap=True)

        if i < total:
            time.sleep(SLEEP_BETWEEN_BULLETS)

    cli_art.console.rule("Run complete", style="dim", align="left")
    cli_art.console.print(f"{theme.colorize_icon('success')} Run complete: {total} bullets processed", soft_wrap=True)
    cli_art.console.print(cli_art._escape_markup(f"   KEEP:   {n_keep}"), soft_wrap=True)
    cli_art.console.print(cli_art._escape_markup(f"   MANUAL: {n_manual}"), soft_wrap=True)
    cli_art.console.print(cli_art._escape_markup(f"   Cluster map → {CLUSTER_MAP_OUT}"), soft_wrap=True)
    cli_art.console.print(cli_art._escape_markup(f"   Keepers     → {KEEPERS_OUT}"), soft_wrap=True)


if __name__ == "__main__":
    main()
