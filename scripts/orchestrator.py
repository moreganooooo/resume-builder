import os
import time
import yaml
import json
import re
import random
import requests
import numpy as np
import pandas as pd
import subprocess
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Tuple
from render_html import render_html


# --- PATH RESOLUTION & ENV SETUP ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)


API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


# --- MODEL STRATEGY ---
# CRITIQUE_MODEL: handles bullet critique (high-frequency) and the post-build
#   holistic resume critique. gemini-3.1-flash-lite gives the best free-tier
#   headroom while reliably following JSON instructions with strict schemas.
#
# REWRITE_MODEL: gemma-4-31b-it -- primary rewrite model for the audit loop.
#   Mirrors rewrite_bullets.py exactly. Has the largest free-tier daily quota
#   by a wide margin. The audit loop rewrites benefit from Gemma's richer
#   generation quality while critiques/scoring stay on Flash-Lite for strict
#   JSON compliance. GEMMA_MINIMAL_JSON=True means Gemma only has to produce
#   {"rewritten_bullet": "..."} -- one key, much less drift.
#
# REWRITE_FALLBACK_MODEL: gemini-3.1-flash-lite -- activated automatically
#   after MAX_REWRITE_PARSE_FAILURES consecutive parse failures on a single
#   bullet. Reliable JSON compliance as a safety net.
#
# BUILDER_MODEL: handles JD keyword extraction and the final resume assembly.
#   gemini-3.1-flash-lite for quota reasons. TemplateSchema is now flattened
#   (List[dict] instead of List[NestedModel]) to avoid the deeply-nested
#   $defs in responseSchema that caused the builder 400.
#
# EMBED_MODEL: gemini-embedding-2 (GA April 2026) -- multimodal, 8k token input.
#   Used ONLY for the one-time offline bullet bank pre-embedding (embed_bullet_bank.py)
#   and for the single JD embedding at runtime in mine_bullet_bank().
#   Native output dimension: 768.
#
# NOTE: orchestrator.py uses raw REST (requests) rather than the google-genai SDK.
#   This avoids SDK versioning headaches on the free tier and gives full explicit
#   control over the payload shape and response parsing.
CRITIQUE_MODEL         = "gemini-3.1-flash-lite"
REWRITE_MODEL          = "gemma-4-31b-it"
REWRITE_FALLBACK_MODEL = "gemini-3.1-flash-lite"
BUILDER_MODEL          = "gemini-3.1-flash-lite"
EMBED_MODEL            = "gemini-embedding-2"
EMBED_DIM              = 768   # gemini-embedding-2 native dimension

# When True, Gemma rewrites use a single-key schema {"rewritten_bullet": "..."}
# instead of the full 3-key schema. Mirrors rewrite_bullets.py's
# GEMMA_MINIMAL_JSON flag. Dramatically improves Gemma JSON compliance.
GEMMA_MINIMAL_JSON         = True
MAX_REWRITE_PARSE_FAILURES = 2

# ---------------------------------------------------------------------------
# SYSTEM PROMPT BASE  (mirrors rewrite_bullets.py exactly)
# ---------------------------------------------------------------------------
# FIX 2: Output rules now match the masterpiece exactly.
# '{{ and }}' renders as literal { and } after .replace() — they ARE the
# instruction and the escape simultaneously. This is the primary coercion
# that keeps Gemma from adding preamble or markdown fences.

REWRITE_SYSTEM_BASE = """\
You are an industry-leading resume writer specialising in B2B SaaS and marketing careers.

Output rules — apply without exception:
- Your response must begin with {{ and end with }}. No other characters before or after.
- Raw JSON only. No markdown fences, no preamble, no commentary, no labels, no explanations.
- Do not repeat, echo, or paraphrase any part of the input.
- \"rewritten_bullet\" must be a single resume bullet sentence, never a list.

JSON shape (full schema):
{{\"rewritten_bullet\": \"\", \"reasoning\": \"\", \"context_gaps\": \"\"}}

Minimal schema (Gemma / minimal mode — used when instructed):
{{\"rewritten_bullet\": \"\"}}

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

# --- TIMING CONSTANTS ---
CRITIQUE_SLEEP = 4    # seconds between critique calls (free-tier: 15 RPM)
REWRITE_SLEEP  = 4    # seconds before the rewrite call after a FAIL
RESCORE_SLEEP  = 8    # seconds before the re-score call after a rewrite
                      # (longer because rescore fires immediately after rewrite)


# --- PIPELINE CONSTANTS ---
TOP_K_BULLETS    = 30    # bullets mined from the bank per run
SEMANTIC_POOL    = 30    # semantic pre-filter pool size (Stage 1)
GEM_BOOST_WEIGHT = 0.15  # additive bonus per hidden_gem_score point above 0


# --- STRENGTH TIER SORT ORDER ---
# Hidden Gems always rank above Strong, Strong above Solid, Solid above Needs Work.
# Bullets without a strength_category column fall to rank 99 (sort last).
STRENGTH_ORDER = {
    "Hidden Gem":  0,
    "Strong":      1,
    "Solid":       2,
    "Needs Work":  3,
}


# --- KNOWLEDGE BASE ALLOWLIST ---
# Only files listed here are stitched into the builder's static context.
# Sorted alphabetically to guarantee byte-for-byte identical prefix across
# every run -> maximises Google's implicit prompt-prefix caching hit rate.
KB_ALLOWLIST = sorted([
    "article-digest.md",
    "bullet-bank.md",
    "bullet-bank-keepers-audited.csv",
    "cv.md",
    "evidence-guide.csv",
    "evidence_graph.json",
    "extracted-screenshot-metrics.csv",
    "morgan-background-guide.md",
    "portals.yml",
    "profile.yml",
    "recruiter_memory_patterns.json",
    "summaries-and-skills-clean.csv",
    "treering-archive-readme.md",
    "verified-claims.csv",
    "verified_facts.json",
    "verified_metrics.json",
    "verified_projects.json",
    "verified_tools.json",
])

# --- AUDIT STATIC PREFIX FILES ---
# Mirrors rewrite_bullets.py's _build_static_prefix() exactly.
# recruiter_memory_patterns.json included for Gap 2 parity.
# Built once per run, shared across all bullet critique/rewrite calls.
# ~5-10k tokens vs ~457k for the full KB.
AUDIT_KB_FILES = [
    "profile.yml",
    "verified_facts.json",
    "verified_tools.json",
    "verified_projects.json",
    "recruiter_memory_patterns.json",  # Gap 2: parity with rewrite_bullets.py scoring context
]

# --- AUDIT SEGMENT FILES ---
# Per-bullet context loaded by _build_audit_segment_bundle().
# Mirrors rewrite_bullets.py's _build_segment_bundle() file list exactly.
# Loaded on-demand per (company, tags) pair -- NOT pre-loaded into static prefix.
AUDIT_SEGMENT_FILES = [
    "cv.md",
    "morgan-background-guide.md",
    "verified-claims.csv",
    "extracted-screenshot-metrics.csv",
    "verified_metrics.json",
]

# profile.yml sections to KEEP in the audit prefix (trimmed for token efficiency).
AUDIT_PROFILE_KEEP = [
    "target_roles:", "archetypes:", "narrative:", "superpowers:",
    "background_context:", "deal_breakers:",
]
AUDIT_PROFILE_STOP = [
    "industries_of_genuine_fit:", "companies_previously_applied:",
    "compensation:", "location:", "cv:", "proof_points:",
    "key_recommendations:", "management_evidence:",
]


# ---------------------------------------------------------------------------
# RETRY / BACKOFF CONSTANTS
# ---------------------------------------------------------------------------
RETRYABLE          = {429, 500, 502, 503, 504}
SERVER_ERRORS      = {500, 502, 503, 504}
HIGH_DEMAND_STATUS = 503
BASE_BACKOFF_SECS  = 8
MAX_BACKOFF_SECS   = 90


# ---------------------------------------------------------------------------
# GEMINI CLIENT  (raw REST)
# ---------------------------------------------------------------------------

from gemini_client import GeminiClient  # replaces the inline class


# ---------------------------------------------------------------------------
# BUILD REWRITE PROMPT
# Mirrors rewrite_bullets.py's build_rewrite_prompt() exactly.
#
# FIX 3: Structure and JSON tail now match the masterpiece exactly.
# The --- HEADERS --- format + tags/persona line + JSON reminder at the tail
# are what actually coerce Gemma to output clean JSON without preamble.
#
# kb_context   = Tier 1 (static_prefix) + Tier 2 (segment_bundle) --
#                assembled by the caller and passed in as a single string.
# Tier 3 tail  = tags/persona + weaknesses + bullet text + JSON reminder.
# ---------------------------------------------------------------------------

def build_rewrite_prompt(
    bullet: str,
    tags: str,
    weaknesses: str,
    kb_context: str,
    attempt: int = 1,
    minimal_schema: bool = False,
    json_reminder: str = 'Output JSON {"rewritten_bullet"}',
) -> str:
    """
    Compose the full contents payload for a single rewrite call.

    kb_context is expected to already contain:
      - Tier 1: static_prefix  (profile, verified facts/tools/projects)
      - Tier 2: segment_bundle (cv.md excerpt, background, claims, metrics)

    This function appends Tier 3: the per-bullet tail that is unique to
    each call (tags/persona + weaknesses + bullet text + output reminder).

    Mirrors rewrite_bullets.py build_rewrite_prompt() exactly.
    """
    # TAG_CONTEXT maps bullet tags to the persona roles they target.
    # Used in the "Rewrite this bullet for X roles" framing that coerces Gemma.
    TAG_CONTEXT = {
        "[content]":   "content marketing, editorial strategy, brand voice, or copywriting roles",
        "[ops]":       "marketing operations, RevOps, CRM, automation, or analytics roles",
        "[email]":     "email marketing, lifecycle marketing, or CRM/ESP campaign roles",
        "[demand]":    "demand generation, paid media, or growth marketing roles",
        "[product]":   "product marketing or go-to-market roles",
        "[enablement]":"sales enablement or revenue enablement roles",
        "[social]":    "social media or community management roles",
        "[project]":   "project management or cross-functional coordination roles",
        "[data]":      "data analysis, reporting, or marketing analytics roles",
        "[ai]":        "AI-assisted workflows, prompt engineering, or marketing technology roles",
    }

    # Resolve persona from tags; fall back to a generic descriptor
    tags_lower = (tags or "").lower()
    persona_parts = [desc for tag, desc in TAG_CONTEXT.items() if tag in tags_lower]
    persona = " and ".join(persona_parts) if persona_parts else "marketing and content roles"


    attempt_note = f" (attempt {attempt})" if attempt > 1 else ""

    # Gemma context cap: trim kb_context to avoid overwhelming the model
    if len(kb_context) > 3500:
        kb_context = kb_context[:3500]

    tail = (
        f"\n\n--- BULLET TO REWRITE{attempt_note} ---\n{bullet}"
        f"\n\n--- REWRITE FOR PERSONA ---\nRewrite this bullet for {persona} roles."
        f"\n\n--- WEAKNESSES TO FIX ---\n{weaknesses if weaknesses else 'No specific weaknesses noted — improve clarity and ATS value.'}"
        f"\n\n--- OUTPUT INSTRUCTION ---\n{json_reminder}"
    )

    return kb_context + tail


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS
# ---------------------------------------------------------------------------

class BulletAuditSchema(BaseModel):
    action_taken:       str       = Field(description="The core objective action or task performed.")
    tools_used:         List[str] = Field(description="Specific software, tools, or hard methodologies named.")
    metrics_claimed:    str       = Field(description="Any specific quantities, percentages, or numbers. Use 'None' if missing.")
    unsupported_claims: List[str] = Field(description="List of generic fluff phrases, buzzwords, or unmeasurable claims.")

class WorkExperience(BaseModel):
    title:        str
    company:      str
    period:       str
    location:     str       = Field(default="", description="City, State or 'Remote'. Leave blank if unknown.")
    achievements: List[str]

class ResumeSchema(BaseModel):
    name:       str
    role:       str
    location:   str
    skills:     List[str]
    experience: List[WorkExperience]

class JDKeywordSchema(BaseModel):
    tools:          List[str] = Field(description="Specific software, platforms, and tech stack e.g., Salesforce, Outreach.io, Figma.")
    hard_skills:    List[str] = Field(description="Specific methodologies, metrics, and frameworks e.g., Lifecycle Marketing, A/B Testing, Pipeline Generation.")
    core_functions: List[str] = Field(description="Primary responsibilities and domain areas e.g., Content Governance, Enablement Training.")

class CritiqueSchema(BaseModel):
    accuracy_score:      int  = Field(description="0-100: specific, grounded, traceable claim")
    believability_score: int  = Field(description="0-100: would a skeptical hiring manager believe this?")
    clarity_score:       int  = Field(description="0-100: immediately clear on first read")
    ats_value:           int  = Field(description="0-100: high-value ATS keywords without stuffing")
    hidden_gem_score:    int  = Field(description="0-100: memorability and evidence rarity")
    hidden_gem_flag:     bool = Field(description="true if hidden_gem_score >= 90")
    manager_test:        str  = Field(description="Strictly 'PASS' or 'FAIL'")
    weaknesses:          str  = Field(description="Specific explanation of flaws. 'None' if PASS with high scores.")
    hidden_gem_reason:   str  = Field(description="One sentence: what makes this a gem, or what holds it back")

class RewriteSchema(BaseModel):
    rewritten_bullet: str = Field(description="Single rewritten resume bullet sentence.")
    reasoning:        str = Field(default="", description="Explanation of changes made.")
    context_gaps:     str = Field(default="", description="Missing context that limited the rewrite.")

class RewriteMinimalSchema(BaseModel):
    rewritten_bullet: str = Field(description="Single rewritten resume bullet sentence.")

class ResumeCritiqueSchema(BaseModel):
    summary_alignment_score: int       = Field(description="0-100: does the Summary match the JD role and tone?")
    skills_relevance_score:  int       = Field(description="0-100: are Skills and Competencies JD-relevant?")
    overall_fit_score:       int       = Field(description="0-100: holistic resume-to-JD fit")
    flags:                   List[str] = Field(description="Specific issues found")
    recommendations:         List[str] = Field(description="Actionable fixes, one per flag")

class ProjectItem(BaseModel):
    title:       str = Field(description="Project name.")
    badge:       str = Field(default="", description="Short type label, e.g. 'Open Source', 'Featured', 'AI'. Leave blank if none.")
    description: str = Field(description="1-2 sentence impact summary.")
    tech:        str = Field(default="", description="Comma-separated tech stack. Leave blank if not applicable.")

class CertItem(BaseModel):
    title: str = Field(description="Full certification or training name.")
    org:   str = Field(description="Issuing organization.")
    year:  str = Field(description="4-digit year, e.g. '2023'. Leave blank if unknown.")

class EducationItem(BaseModel):
    degree:      str = Field(description="Degree or program name.")
    institution: str = Field(description="School or university name.")
    year:        str = Field(default="", description="Graduation year or date range. Leave blank if unknown.")
    description: str = Field(default="", description="Honors, GPA, relevant coursework. Leave blank if none.")

class TemplateSchema(BaseModel):
    """
    Flattened schema for the builder call.
    EXPERIENCE/PROJECTS/EDUCATION/CERTIFICATIONS are List[dict] to avoid
    deeply-nested $defs in responseSchema that caused the builder 400.
    """
    NAME:                   str       = Field(description="Must match candidate name.")
    TAGLINE:                str       = Field(description="Max 80 chars. Follows archetype tagging rules.")
    PHONE:                  str
    EMAIL:                  str
    LINKEDIN_URL:           str
    LINKEDIN_DISPLAY:       str
    PORTFOLIO_URL:          str
    PORTFOLIO_DISPLAY:      str
    LOCATION:               str
    SECTION_SUMMARY:        str       = Field(default="Professional Summary")
    SUMMARY_TEXT:           str       = Field(description="Max 5 lines. First sentence MUST be bolded using <strong> tags. No generic filler.")
    SECTION_COMPETENCIES:   str       = Field(default="Core Competencies")
    COMPETENCIES:           List[str] = Field(min_length=6, max_length=8, description="6-8 exact keywords extracted from JD requirements.")
    SECTION_EXPERIENCE:     str       = Field(default="Work Experience")
    EXPERIENCE:             List[dict] = Field(
        description=(
            "List of work experience objects. Each dict must contain: "
            "title (str), company (str), period (str), location (str, city/state or Remote), "
            "achievements (list of str). "
            "Bullet counts per role must match tailor.md targets exactly: "
            "Mercor 2-3, Treering 6-8, Inside Sales Team 4-5, "
            "Element 8/Strategy LLC 3-4, VML 3-4, Callahan Creek 3-4."
        )
    )
    SECTION_PROJECTS:       str       = Field(default="Projects")
    PROJECTS:               List[dict] = Field(
        min_length=3, max_length=4,
        description=(
            "Top 3-4 most relevant projects. Each dict must contain: "
            "title (str), badge (str, leave blank if none), "
            "description (str, 1-2 sentence impact summary), "
            "tech (str, comma-separated tech stack, leave blank if not applicable)."
        )
    )
    SECTION_EDUCATION:      str       = Field(default="Education")
    EDUCATION:              List[dict] = Field(
        description=(
            "KU, KCKCC, and JCCC items. Each dict must contain: "
            "degree (str), institution (str), year (str), description (str). "
            "KU: exactly 2 bullets. KCKCC: exactly 2 bullets. JCCC: exactly 1 bullet."
        )
    )
    SECTION_CERTIFICATIONS: str       = Field(default="Training & Certifications")
    CERTIFICATIONS:         List[dict] = Field(
        min_length=3, max_length=3,
        description=(
            "Exactly 3 certifications in fixed order. Each dict: title, org, year. "
            "Order: 1) Email Marketing Software Certification | HubSpot | 2026, "
            "2) Video for Sales Certification | Vidyard | 2021, "
            "3) Camp Portfolio | Bernstein Rein, Kansas City | 2008."
        )
    )
    SECTION_SKILLS:         str       = Field(default="Skills")
    SKILLS:                 List[str] = Field(description="Technical skills mapped to JD.")


# ---------------------------------------------------------------------------
# RESUME ENGINE
# ---------------------------------------------------------------------------

class ResumeEngine:

    def __init__(self):
        self.engine_dir      = os.path.join(PROJECT_ROOT, "resume-engine")
        self.prompts_dir     = os.path.join(self.engine_dir, "prompts")
        self.rules_dir       = os.path.join(self.engine_dir, "rules")
        self.scoring_dir     = os.path.join(self.engine_dir, "scoring")
        self.kb_dir          = os.path.join(self.engine_dir, "knowledge_base")
        self.templates_dir   = os.path.join(self.engine_dir, "templates")
        self.output_json_dir = os.path.join(PROJECT_ROOT, "output", "json")
        self.jds_dir         = os.path.join(PROJECT_ROOT, "jds")
        os.makedirs(self.output_json_dir, exist_ok=True)

    def load_yaml(self, dir_path, filename):
        path = os.path.join(dir_path, filename)
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}

    def load_prompt(self, filename):
        path = os.path.join(self.prompts_dir, filename)
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return "Process the text."

    def load_knowledge_base(self):
        """
        Stitches allowlisted KB files into a single static context string.
        KB_ALLOWLIST is pre-sorted so the output is byte-for-byte identical
        across every run, maximising Google implicit prompt-prefix cache hits.
        """
        master_context = "=== SYSTEM KNOWLEDGE BASE ===\n\n"
        if os.path.exists(self.kb_dir):
            for filename in KB_ALLOWLIST:
                filepath = os.path.join(self.kb_dir, filename)
                if not os.path.exists(filepath):
                    print(f"  WARNING: KB allowlist entry not found, skipping: {filename}")
                    continue
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        master_context += f"--- START OF {filename} ---\n{f.read()}\n--- END OF {filename} ---\n\n"
                except Exception as e:
                    print(f"  WARNING: Could not load KB file {filename}: {e}")
        return master_context

    def build_audit_static_prefix(self) -> str:
        """
        Builds the slim Tier-1 context prefix for the audit loop.
        Mirrors rewrite_bullets.py _build_static_prefix() exactly.
        ~5-10k tokens vs ~457k for the full KB.
        """
        sections = []

        profile_path = os.path.join(self.kb_dir, "profile.yml")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                lines = raw.splitlines()
                result = []
                capturing = False
                for line in lines:
                    stripped = line.strip()
                    if any(stripped.startswith(s) for s in AUDIT_PROFILE_KEEP):
                        capturing = True
                    elif any(stripped.startswith(s) for s in AUDIT_PROFILE_STOP):
                        capturing = False
                    if capturing:
                        result.append(line)
                trimmed = "\n".join(result).strip()
                if trimmed:
                    sections.append(
                        "=== TARGET ROLES & PROFILE (from profile.yml) ===\n"
                        "Use these to understand what roles this bullet needs to appeal to and what to avoid.\n"
                        + trimmed
                    )
            except Exception as e:
                print(f"  WARNING: build_audit_static_prefix: could not load profile.yml: {e}")

        for fname, header, note in [
            ("verified_facts.json",
             "=== VERIFIED FACTS (high-confidence claims -- use freely) ===",
             "These are the only facts about Morgan's career that are evidence-backed.\nDo NOT invent facts outside this list."),
            ("verified_tools.json",
             "=== VERIFIED TOOLS (HF002 guard -- only claim tools listed here) ===",
             "Never claim proficiency with any tool not present in this list."),
            ("verified_projects.json",
             "=== VERIFIED PROJECTS ===",
             "Use these to add accurate project detail and scope."),
            ("recruiter_memory_patterns.json",  # Gap 2
             "=== RECRUITER MEMORY PATTERNS (believability lens) ===",
             "Use these patterns to judge whether claims will land with skeptical hiring managers."),
        ]:
            fpath = os.path.join(self.kb_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                    sections.append(f"{header}\n{note}\n{data}")
                except Exception as e:
                    print(f"  WARNING: build_audit_static_prefix: could not load {fname}: {e}")

        return "\n\n".join(sections)

    def _build_audit_segment_bundle(self, company: str, tags: str) -> str:
        """
        Builds a per-bullet context bundle for the rewrite call (Gap 3).
        Mirrors rewrite_bullets.py _build_segment_bundle() exactly.
        Called only on the rewrite path -- critiques stay on slim static_prefix.
        """
        company_lower = company.lower() if company else ""
        tags_lower    = tags.lower()    if tags    else ""
        combined_key  = f"{company_lower} {tags_lower}"
        sections      = []

        for filename in AUDIT_SEGMENT_FILES:
            filepath = os.path.join(self.kb_dir, filename)
            if not os.path.exists(filepath):
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    raw = f.read()
                if filename in ("cv.md", "morgan-background-guide.md"):
                    lines = raw.splitlines()
                    relevant = []
                    in_relevant_section = False
                    for line in lines:
                        if line.startswith("#") or line.startswith("##"):
                            in_relevant_section = any(
                                kw in line.lower() for kw in combined_key.split() if len(kw) > 3
                            )
                        if in_relevant_section:
                            relevant.append(line)
                    content = "\n".join(relevant).strip() if relevant else raw.strip()
                else:
                    content = raw.strip()
                if content:
                    sections.append(f"--- {filename} ---\n{content}")
            except Exception as e:
                print(f"  WARNING: _build_audit_segment_bundle: could not load {filename}: {e}")

        if not sections:
            return ""
        header = (
            f"=== SEGMENT CONTEXT (company: {company or 'unknown'} | tags: {tags or 'none'}) ===\n"
            "Use the evidence below to strengthen the rewrite with accurate, specific claims.\n"
        )
        return header + "\n\n".join(sections)

    @staticmethod
    def critique_composite(scores: dict) -> float:
        numeric = sum(
            pd.to_numeric(scores.get(c, 0), errors="coerce") or 0
            for c in ("accuracy_score", "believability_score", "clarity_score", "ats_value")
        )
        mgr_bonus = 10 if str(scores.get("manager_test", "")).upper() == "PASS" else 0
        return numeric + mgr_bonus

    def audit_and_refine_bullets(
        self,
        bullet_tuples: List[Tuple[str, str, str]],
        static_prefix: str,
    ) -> List[str]:
        """
        Skeptical Editor audit loop.
        Accepts List[Tuple[str, str, str]] -- (bullet_text, company, tags).
        Critiques on slim static_prefix (Tier 1+2 cache architecture).
        Rewrites get segment bundle prepended (Gap 3) but critiques do not.
        """
        print("\n📋 Loading rules bundle...")
        print(f"📌 Static prefix (Tier 1): {len(static_prefix):,} chars — shared across ALL bullets")

        if not isinstance(bullet_tuples, list) or len(bullet_tuples) == 0:
            print("  No bullets to audit -- empty or invalid input. Skipping audit loop.")
            return []

        critique_prompt     = self.load_prompt("critique_bullet.md")
        manager_test_rules  = json.dumps(self.load_yaml(self.scoring_dir, "manager_test.yaml"))
        believability_rules = json.dumps(self.load_yaml(self.scoring_dir, "believability.yaml"))
        style_rules         = json.dumps(self.load_yaml(self.rules_dir,   "style_rules.yaml"))
        language_quality    = json.dumps(self.load_yaml(self.rules_dir,   "language_quality.yaml"))
        verb_taxonomy       = json.dumps(self.load_yaml(self.rules_dir,   "verb_taxonomy.yaml"))
        verb_intent_mapping = json.dumps(self.load_yaml(self.rules_dir,   "verb_intent_mapping.yaml"))
        hard_failures       = json.dumps(self.load_yaml(self.rules_dir,   "hard_failures.yaml"))
        truthfulness_rules  = json.dumps(self.load_yaml(self.rules_dir,   "truthfulness_rules.yaml"))
        ats_rules           = json.dumps(self.load_yaml(self.rules_dir,   "ats_rules.yaml"))

        critique_system = (
            f"{critique_prompt}"
            f"\n\nMANAGER TEST RULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
            f"\n\nHARD FAILURES (any of these = automatic FAIL):\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nATS RULES:\n{ats_rules}"
        )
        rewrite_rules_block = "\n".join([
            "=== VERB INTENT MAP ===",
            "Before choosing a verb, identify the accomplishment intent and select from the matching preferred_verbs list below.",
            verb_intent_mapping,
            "",
            "=== VERB TAXONOMY (priority tiers) ===",
            "Use elite > strong > acceptable. NEVER use verbs in the avoid list.",
            verb_taxonomy,
            "",
            "=== LANGUAGE QUALITY RULES ===",
            "Flag and replace any weak verbs, buzzwords, or AI-pattern phrases listed below.",
            language_quality,
            "",
            "=== HARD FAILURE CONDITIONS ===",
            "Any bullet triggering one of these conditions must be rewritten — do NOT pass it:",
            hard_failures,
            "",
            "=== TRUTHFULNESS RULES ===",
            "Apply these four tests before finalising any bullet:",
            truthfulness_rules,
            "",
            "=== STYLE RULES ===",
            style_rules,
        ])
        # FIX: use .replace() instead of .format() to avoid ValueError when
        # rules YAML content contains literal curly braces { } (e.g. JSON examples).
        rewrite_system = REWRITE_SYSTEM_BASE.replace("{rules_block}", rewrite_rules_block)

        print(f"📐 Rewrite rules block:   {len(rewrite_rules_block):,} chars")
        print(f"✏️  Rewrite system prompt: {len(rewrite_system):,} chars (stable across ALL calls)\n")
        print(f"💯 Score system prompt:   {len(critique_system):,} chars")


        refined_bullets = []
        for i, (bullet, company, tags) in enumerate(bullet_tuples):
            bullet_preview = bullet[:60]
            print(f"\n{'─'*60}")
            print(f"[{i+1}/{len(bullet_tuples)}] {bullet_preview}...")
            print(f"   Tags: {tags}  |  Company: {company}")

            if i > 0:
                time.sleep(CRITIQUE_SLEEP)

            critique_contents = f"{static_prefix}\n\n--- BULLET TO CRITIQUE ---\n{bullet}"

            try:
                critique_text, usage = GeminiClient.generate(
                    model=CRITIQUE_MODEL,
                    system_instruction=critique_system,
                    contents=critique_contents,
                    response_schema=CritiqueSchema,
                    temperature=0.0,
                    max_output_tokens=280,
                )

                if not critique_text:
                    refined_bullets.append(bullet)
                    continue

                critique_data = GeminiClient.parse_json(critique_text)

                gem_score  = critique_data.get("hidden_gem_score", 0)
                gem_flag   = critique_data.get("hidden_gem_flag", False)
                gem_reason = critique_data.get("hidden_gem_reason", "")
                if gem_flag:
                    print(f"   💎 GEM: Hidden Gem! score={gem_score} — {gem_reason}")
                elif gem_score >= 75:
                    print(f"   ⭐ STRONG: gem_score={gem_score} — {gem_reason}")

                if (critique_data.get("manager_test") == "FAIL" or
                        critique_data.get("believability_score", 100) < 80):
                    print(f"   ✏️  Rewriting with {REWRITE_MODEL}...")
                    time.sleep(REWRITE_SLEEP)

                    segment_bundle = self._build_audit_segment_bundle(company, tags)
                    if segment_bundle:
                        print(f"   📦 segment bundle: {len(segment_bundle):,} chars")

                    active_rewrite_model   = REWRITE_MODEL
                    rewrite_parse_failures = 0
                    rewritten_bullet       = bullet

                    for rw_attempt in range(MAX_REWRITE_PARSE_FAILURES + 1):
                        use_minimal   = GEMMA_MINIMAL_JSON and "gemma" in active_rewrite_model.lower()
                        runner_schema = RewriteMinimalSchema if use_minimal else RewriteSchema
                        weaknesses    = critique_data.get("weaknesses", "")

                        # Compose Tier 1 + Tier 2 + Tier 3 via build_rewrite_prompt.
                        # kb_context = static_prefix (Tier 1) + segment_bundle (Tier 2).
                        # build_rewrite_prompt appends the per-bullet tail (Tier 3).
                        # ---- Lean Gemma-safe rewrite contents ----
                        weaknesses_text = (weaknesses or "").strip() or "Improve clarity, specificity, and believability."

                        persona_map = {
                            "content":    "Content marketing, editorial strategy",
                            "ops":        "Marketing operations, CRM, RevOps",
                            "email":      "Email/lifecycle marketing",
                            "demand":     "Demand generation, growth marketing",
                            "sales":      "B2B sales, SDR/AE",
                            "brand":      "Brand marketing, creative",
                            "design":     "Graphic design, UX/UI",
                        }
                        tag_lower = (tags or "").lower()
                        persona = next((v for k, v in persona_map.items() if k in tag_lower), "General marketing roles")

                        if "gemma" in active_rewrite_model.lower() and segment_bundle:
                            segment_bundle = segment_bundle[:2000]   # keep segment lean

                        context_block = f"{static_prefix}\n{segment_bundle}" if segment_bundle else static_prefix

                        parts = [
                            "Return exactly one raw JSON object.",
                            "Do not use markdown.",
                            "Do not explain.",
                            "Do not repeat the prompt.",
                            "Do not add any text before or after the JSON.",
                        ]
                        # Context goes here, BEFORE the bullet/persona/JSON reminder
                        if context_block.strip():
                            parts += ["", "Use only supported facts from this context:", context_block, ""]

                        # Bullet + persona + JSON reminder come LAST
                        parts += [
                            f"Rewrite this bullet for {persona} roles.",
                            f"Weaknesses: {weaknesses_text}",
                            f"Bullet: {bullet}",
                            "",
                            f"Output JSON: {json_schema}",
                        ]

                        rewrite_contents = "\n".join(parts)

                        token_cap = 160 if use_minimal else 300

                        try:
                            rewrite_text, rw_usage = GeminiClient.generate(
                                model=active_rewrite_model,
                                system_instruction=rewrite_system,
                                contents=rewrite_contents,
                                response_schema=runner_schema,
                                temperature=0.7,
                                max_output_tokens=token_cap,
                            )

                            if not rewrite_text:
                                raise ValueError("Empty rewrite response")

                            rw_data = GeminiClient.parse_json(rewrite_text)
                            candidate_bullet = rw_data.get("rewritten_bullet", "").strip()

                            if not candidate_bullet:
                                raise ValueError("Empty rewritten_bullet in response")

                            time.sleep(RESCORE_SLEEP)
                            rescore_contents = f"{static_prefix}\n\n--- BULLET TO CRITIQUE ---\n{candidate_bullet}"
                            rescore_text, _  = GeminiClient.generate(
                                model=CRITIQUE_MODEL,
                                system_instruction=critique_system,
                                contents=rescore_contents,
                                response_schema=CritiqueSchema,
                                temperature=0.0,
                                max_output_tokens=280,
                            )
                            rescore_data       = GeminiClient.parse_json(rescore_text or "")
                            original_composite = ResumeEngine.critique_composite(critique_data)
                            rewrite_composite  = ResumeEngine.critique_composite(rescore_data)

                            if rewrite_composite >= original_composite:
                                rewritten_bullet = candidate_bullet
                                print(f"   ✅ ACCEPTED rewrite (composite {rewrite_composite:.0f} >= {original_composite:.0f})")
                            else:
                                rewritten_bullet = bullet
                                print(f"   🔄 KEPT original (composite {original_composite:.0f} > {rewrite_composite:.0f})")
                            break

                        except Exception as rw_err:
                            rewrite_parse_failures += 1
                            print(f"   ⚠️  Rewrite parse error (attempt {rw_attempt+1}): {rw_err}")
                            if (rewrite_parse_failures >= MAX_REWRITE_PARSE_FAILURES
                                    and active_rewrite_model != REWRITE_FALLBACK_MODEL):
                                print(f"   🔄 FALLBACK: Switching rewrite to {REWRITE_FALLBACK_MODEL}")
                                active_rewrite_model = REWRITE_FALLBACK_MODEL
                            time.sleep(REWRITE_SLEEP)

                    refined_bullets.append(rewritten_bullet)
                else:
                    refined_bullets.append(bullet)

            except Exception as e:
                print(f"   ⚠️  Critique error on bullet {i+1}: {e}")
                refined_bullets.append(bullet)

        print(f"\n{'='*60}")
        print(f"✅ Audit complete: {len(refined_bullets)} bullets refined")
        return refined_bullets

    def mine_bullet_bank(
        self,
        jd_text: str,
        master_resume: dict,
    ) -> List[Tuple[str, str, str]]:
        """
        Semantic + gem-aware retrieval from bullet-bank-keepers-audited.csv.

        Returns List[Tuple[str, str, str]] -- (bullet_text, company, tags) --
        so audit_and_refine_bullets() can build per-bullet segment bundles (Gap 3).

        Stage 1: embed JD, compute cosine similarity against pre-embedded bank,
                 take top SEMANTIC_POOL candidates.
        Stage 2: gem-aware reranking -- adds GEM_BOOST_WEIGHT * hidden_gem_score
                 bonus to similarity score, then sorts by strength_category tier,
                 then takes top TOP_K_BULLETS.
        """
        print("\nMining bullet bank...")
        bank_csv = os.path.join(self.kb_dir, "bullet-bank-keepers-audited.csv")
        emb_npy  = os.path.join(self.kb_dir, "bullet_vectors_ge2_d768.npy")

        if not os.path.exists(bank_csv):
            print("  WARNING: bullet-bank-keepers-audited.csv not found. Skipping mine.")
            return []
        if not os.path.exists(emb_npy):
            print("  WARNING: bullet_vectors_ge2_d768.npy not found. Run embed_bullet_bank.py first. Skipping mine.")
            return []

        try:
            df   = pd.read_csv(bank_csv)
            embs = np.load(emb_npy)
        except Exception as e:
            print(f"  WARNING: Could not load bullet bank: {e}")
            return []

        if "Bullet Point" not in df.columns:
            print("  WARNING: 'Bullet Point' column not found in bullet bank CSV.")
            return []

        if len(df) != len(embs):
            print(f"  WARNING: Row count mismatch -- CSV {len(df)} rows vs embeddings {len(embs)} rows. Skipping mine.")
            return []

        jd_emb = GeminiClient.embed(jd_text[:8000])
        if jd_emb is None:
            print("  WARNING: JD embedding failed. Falling back to first TOP_K_BULLETS rows.")
            bullets_col  = df["Bullet Point"].fillna("").tolist()
            company_col  = df["Role / Company"].fillna("").tolist()  if "Role / Company" in df.columns else ["" ] * len(df)
            tags_col     = df["Tags"].fillna("").tolist()            if "Tags"           in df.columns else ["" ] * len(df)
            return list(zip(bullets_col[:TOP_K_BULLETS], company_col[:TOP_K_BULLETS], tags_col[:TOP_K_BULLETS]))

        jd_vec   = np.array(jd_emb, dtype=np.float32)
        jd_norm  = np.linalg.norm(jd_vec)
        if jd_norm > 0:
            jd_vec = jd_vec / jd_norm

        embs_norm = embs / (np.linalg.norm(embs, axis=1, keepdims=True) + 1e-9)
        sims      = embs_norm @ jd_vec

        pool_size = min(SEMANTIC_POOL, len(df))
        pool_idx  = np.argsort(sims)[::-1][:pool_size]
        pool_df   = df.iloc[pool_idx].copy()
        pool_sims = sims[pool_idx]

        if "hidden_gem_score" in pool_df.columns:
            gem_scores = pd.to_numeric(pool_df["hidden_gem_score"], errors="coerce").fillna(0).values
            boosted    = pool_sims + GEM_BOOST_WEIGHT * gem_scores
        else:
            boosted    = pool_sims

        if "strength_category" in pool_df.columns:
            tier_rank = pool_df["strength_category"].map(STRENGTH_ORDER).fillna(99).values
        else:
            tier_rank = np.zeros(len(pool_df))

        order = np.lexsort(((-boosted), tier_rank))
        pool_df   = pool_df.iloc[order].reset_index(drop=True)

        top_df      = pool_df.head(TOP_K_BULLETS)
        bullets_out = top_df["Bullet Point"].fillna("").tolist()
        company_out = top_df["Role / Company"].fillna("").tolist() if "Role / Company" in top_df.columns else ["" ] * len(top_df)
        tags_out    = top_df["Tags"].fillna("").tolist()            if "Tags"           in top_df.columns else ["" ] * len(top_df)

        print(f"  Mined {len(bullets_out)} bullets from bank (pool={pool_size}, top_k={TOP_K_BULLETS}).")
        return list(zip(bullets_out, company_out, tags_out))

    def build_tailored_resume(
        self,
        jd_path: str,
        master_resume: dict,
        output_filename: str = None,
    ) -> dict:
        """
        Full pipeline: JD -> keywords -> mine bullets -> audit -> build -> critique.

        Gap 1 fix: kb_context is placed in builder_system (system_instruction)
        rather than combined_contents. The full ~457k-token KB now forms a
        stable, cacheable system prefix. Only variable content (JD keywords,
        JD text, master resume JSON, refined bullets) sits in combined_contents,
        so Google can cache-hit the KB prefix on every builder call regardless
        of JD changes.
        """
        print(f"\nBuilding tailored resume for: {jd_path}")

        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        if output_filename is None:
            jd_stem = Path(jd_path).stem
            output_filename = f"{jd_stem}_resume.json"

        # --- Step 1: Extract JD keywords ---
        print("\nStep 1: Extracting JD keywords...")
        extract_prompt = self.load_prompt("extract_keywords.md")
        keyword_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=extract_prompt,
            contents=f"=== JOB DESCRIPTION ===\n{jd_text}",
            response_schema=JDKeywordSchema,
            temperature=0.0,
        )
        jd_keywords: dict = GeminiClient.parse_json(keyword_text or "")
        if not jd_keywords:
            print("  WARNING: JD keyword extraction returned empty. Proceeding with empty keywords.")
        print(f"  Keywords extracted: {json.dumps(jd_keywords, indent=2)[:400]}")

        # --- Step 2: Mine bullet bank ---
        print("\nStep 2: Mining bullet bank...")
        bullet_tuples = self.mine_bullet_bank(jd_text, master_resume)
        print(f"  {len(bullet_tuples)} bullet tuples retrieved.")

        # --- Step 3: Audit and refine bullets ---
        print("\nStep 3: Auditing bullets...")
        static_prefix   = self.build_audit_static_prefix()
        refined_tuples  = self.audit_and_refine_bullets(bullet_tuples, static_prefix)
        refined_bullets = [b for b in refined_tuples if b]  # plain strings for builder
        print(f"  {len(refined_bullets)} bullets after audit.")

        # --- Step 4: Build resume ---
        print("\nStep 4: Building resume...")
        build_prompt = self.load_prompt("build_resume.md")
        # or more explicitly:
        tailor_path = os.path.join(self.rules_dir, "tailor.md")
        try:
            with open(tailor_path, "r") as f:
                tailor_rules = f.read()
        except FileNotFoundError:
            tailor_rules = ""

        kb_context = self.load_knowledge_base()

        # Gap 1: KB goes into system_instruction, not contents.
        # system_instruction is the most cacheable part of the payload --
        # it stays identical across all builder calls on the same run.
        # The variable tail (JD + bullets) sits alone in combined_contents.
        builder_system = (
            f"{build_prompt}\n\n"
            f"TAILOR RULES:\n{tailor_rules}\n\n"
            f"{kb_context}"
        )

        bullets_block = "\n".join(f"- {b}" for b in refined_bullets)
        combined_contents = (
            f"=== JD KEYWORDS ===\n{json.dumps(jd_keywords)}\n\n"
            f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
            f"=== MASTER RESUME ===\n{json.dumps(master_resume, indent=2)}\n\n"
            f"=== REFINED BULLETS ===\n{bullets_block}"
        )

        print(f"  builder_system size: {len(builder_system)} chars / ~{len(builder_system)//4} tokens")
        print(f"  combined_contents size: {len(combined_contents)} chars / ~{len(combined_contents)//4} tokens")

        resume_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=builder_system,
            contents=combined_contents,
            response_schema=TemplateSchema,
            temperature=0.0,
        )

        if not resume_text:
            print("  ERROR: Builder returned empty response.")
            return {}

        resume_data = GeminiClient.parse_json(resume_text)
        if not resume_data:
            print("  ERROR: Could not parse builder JSON.")
            print(f"  Raw response (first 500 chars):\n{resume_text[:500]}")
            return {}

        # --- Step 5: Post-build holistic critique ---
        print("\nStep 5: Running holistic resume critique...")
        critique_prompt = self.load_prompt("critique_resume.md")
        critique_contents = (
            f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
            f"=== RESUME JSON ===\n{json.dumps(resume_data, indent=2)}"
        )
        critique_text, _ = GeminiClient.generate(
            model=CRITIQUE_MODEL,
            system_instruction=critique_prompt,
            contents=critique_contents,
            response_schema=ResumeCritiqueSchema,
            temperature=0.0,
        )
        if critique_text:
            critique_data = GeminiClient.parse_json(critique_text)
            print(f"  Holistic critique scores:")
            print(f"    summary_alignment : {critique_data.get('summary_alignment_score', '?')}")
            print(f"    skills_relevance  : {critique_data.get('skills_relevance_score',  '?')}")
            print(f"    overall_fit       : {critique_data.get('overall_fit_score',        '?')}")
            flags = critique_data.get("flags", [])
            if flags:
                print("  Flags:")
                for flag in flags:
                    print(f"    - {flag}")
            recs = critique_data.get("recommendations", [])
            if recs:
                print("  Recommendations:")
                for rec in recs:
                    print(f"    - {rec}")
            resume_data["_critique"] = critique_data
        else:
            print("  WARNING: Holistic critique returned empty.")

        # --- Step 6: Save output ---
        output_path = os.path.join(self.output_json_dir, output_filename)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(resume_data, f, indent=2, ensure_ascii=False)
            print(f"\n  Resume saved to: {output_path}")
        except Exception as e:
            print(f"  WARNING: Could not save resume JSON: {e}")

        # --- Step 7: Render HTML + Generate PDF ---
        print("\nStep 7: Rendering HTML and generating PDF...")
        jd_stem    = Path(jd_path).stem
        html_out   = os.path.join(PROJECT_ROOT, "output", "html", f"{jd_stem}_resume.html")
        pdf_out    = os.path.join(PROJECT_ROOT, "output", "pdf",  f"{jd_stem}_resume.pdf")
        pdf_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")

        os.makedirs(os.path.dirname(html_out), exist_ok=True)
        os.makedirs(os.path.dirname(pdf_out),  exist_ok=True)

        render_html(resume_data, html_out)

        pdf_result = subprocess.run(
            ["node", pdf_script, html_out, pdf_out, "--format=letter"],
            capture_output=True, text=True
        )
        if pdf_result.returncode == 0:
            print(pdf_result.stdout)
            print(f"  🎉 Pipeline complete! PDF → {pdf_out}")
        else:
            print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")

        return resume_data


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Resume Builder Orchestrator")
    parser.add_argument("jd", help="Path to the job description .txt or .md file")
    parser.add_argument("--master", default=None, help="Path to master resume JSON (optional)")
    parser.add_argument("--output", default=None, help="Output JSON filename (optional)")
    args = parser.parse_args()

    master_resume = {}
    if args.master:
        try:
            with open(args.master, "r", encoding="utf-8") as f:
                master_resume = json.load(f)
            print(f"Loaded master resume from: {args.master}")
        except Exception as e:
            print(f"WARNING: Could not load master resume: {e}. Proceeding with empty dict.")

    engine = ResumeEngine()
    result = engine.build_tailored_resume(
        jd_path=args.jd,
        master_resume=master_resume,
        output_filename=args.output,
    )

    if result:
        print("\nDone! Resume built successfully.")
    else:
        print("\nERROR: Resume build failed. Check output above for details.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
