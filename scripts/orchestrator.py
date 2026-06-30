import os
import time
import yaml
import json
import re
import random
import requests
import numpy as np
import pandas as pd
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

    json_reminder = (
        'Output ONLY: {"rewritten_bullet": "..."}'
        if minimal_schema
        else 'Output ONLY: {"rewritten_bullet": "...", "reasoning": "...", "context_gaps": "..."}'
    )

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
    COMPETENCIES:           List[str] = Field(min_length=6, max_length=8, description="6-8 exact keywords