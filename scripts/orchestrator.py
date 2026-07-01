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
    # bullet-bank-keepers-audited.csv intentionally excluded: it's 1.4MB
    # (~350k tokens), 77% of this entire allowlist, and redundant -- the
    # JD-relevant bullets it contains are already passed to the builder via
    # refined_bullets/combined_contents after Step 2-3 mine and audit them.
    # Including it here blew the builder call past the free-tier's 250k
    # input-tokens-per-minute cap on every single run.
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

# --- TIER 2 FILTERING CONSTANTS ---
# Ported verbatim from rewrite_bullets.py. These are what actually make
# the segment bundle small and relevant instead of a raw file dump.
TREERING_KEYWORDS = ["treering", "tree ring", "yearbook"]
MAX_CLAIMS_ROWS   = 12

# TAG_CONTEXT maps bracketed bullet tags (e.g. "[ops]") to the persona
# roles they target, used by persona_context() below. Bracketed form
# matters -- it's how rewrite_bullets.py avoids accidental substring
# matches (e.g. "ops" inside some unrelated word).
TAG_CONTEXT = {
    "[content]":    "content marketing, editorial strategy, brand voice, or copywriting roles",
    "[ops]":        "marketing operations, RevOps, CRM, automation, or analytics roles",
    "[email]":      "email marketing, lifecycle marketing, or CRM/ESP campaign roles",
    "[demand]":     "demand generation, paid media, or growth marketing roles",
    "[product]":    "product marketing or go-to-market strategy roles",
    "[sales]":      "B2B sales, SDR/AE, or account management roles",
    "[brand]":      "brand marketing, creative direction, or agency roles",
    "[design]":     "graphic design, visual identity, or UX/UI roles",
    "[general]":    "general marketing or cross-functional roles",
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
# TIER 2 SEGMENT HELPERS  (ported verbatim from rewrite_bullets.py)
# ---------------------------------------------------------------------------

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


def get_verified_claims_text(df_claims: pd.DataFrame) -> str:
    if df_claims.empty:
        return ""
    cols = ["Claim / Finding", "Metric(s)", "Confidence", "Evidence / Detail"]
    available = [c for c in cols if c in df_claims.columns]
    return df_claims[available].to_csv(index=False)


def persona_context(tags: str) -> str:
    if not isinstance(tags, str) or not tags.strip():
        return "general marketing roles"
    parts = [TAG_CONTEXT[tag] for tag in TAG_CONTEXT if tag in tags.lower()]
    return ", ".join(parts) if parts else "general marketing roles"


# ---------------------------------------------------------------------------
# BUILD REWRITE PROMPT
# This now actually matches rewrite_bullets.py's build_rewrite_prompt() --
# same "Use only supported facts..." framing, same plain list structure,
# same output reminder. No --- HEADER --- blocks, no character-count
# truncation of kb_context. (The old version here claimed to mirror
# rewrite_bullets.py but didn't, and was never even called.)
# ---------------------------------------------------------------------------

def build_rewrite_prompt(
    bullet: str,
    tags: str,
    weaknesses: str,
    kb_context: str,
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
# CACHE-HIT LOGGING HELPER  (ported verbatim from rewrite_bullets.py so the
# audit loop's terminal report shows Tier 2/3 token + cache-hit stats too,
# not just the Tier 1 static-prefix line.)
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
        self._segment_cache: dict = {}

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
        print("\n📚 Loading knowledge base context (Tier 1)...")
        sections = []

        profile_path = os.path.join(self.kb_dir, "profile.yml")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                print(f"   ✅ Loaded profile.yml ({len(raw):,} chars)")
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
                    print(f"   📝 profile.yml trimmed to {len(trimmed):,} chars")
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
        ]:
            fpath = os.path.join(self.kb_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                    print(f"   ✅ Loaded {fname} ({len(data):,} chars)")
                    sections.append(f"{header}\n{note}\n{data}")
                except Exception as e:
                    print(f"  WARNING: build_audit_static_prefix: could not load {fname}: {e}")

        return "\n\n".join(sections)

    def recruiter_context_block(self) -> str:
        """
        Mirrors rewrite_bullets.py's KnowledgeBase.recruiter_context_block()
        exactly. This belongs in the critique/score system prompt, not in
        the static prefix the rewrite call sees -- that's the actual
        rewrite_bullets.py design, even though the old comment here said
        otherwise.
        """
        fpath = os.path.join(self.kb_dir, "recruiter_memory_patterns.json")
        if not os.path.exists(fpath):
            return ""
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
        except Exception as e:
            print(f"  WARNING: recruiter_context_block: could not load recruiter_memory_patterns.json: {e}")
            return ""
        if not data:
            return ""
        return (
            "=== RECRUITER READING PATTERNS (what hiring managers notice first) ===\n"
            "Use these patterns to calibrate believability and manager_test scoring.\n"
            + data
        )

    def _build_audit_segment_bundle(self, company: str, tags: str) -> str:
        """
        Builds a per-bullet context bundle for the rewrite call (Tier 2).
        Now actually mirrors rewrite_bullets.py's _build_segment_bundle():
        a curated cv.md excerpt + tag-specific background blurb, plus
        (only for Treering bullets) tag-filtered verified claims, capped
        at MAX_CLAIMS_ROWS rows -- not the full unfiltered CSV/JSON dump
        this used to send on every bullet regardless of company or tag.
        """
        sections = []

        cv_path = os.path.join(self.kb_dir, "cv.md")
        cv_full = ""
        if os.path.exists(cv_path):
            try:
                with open(cv_path, "r", encoding="utf-8") as f:
                    cv_full = f.read()
            except Exception as e:
                print(f"  WARNING: _build_audit_segment_bundle: could not load cv.md: {e}")

        cv_section = extract_cv_section(cv_full, company)
        if cv_section:
            label = ("ROLE CONTEXT (cv.md excerpt)"
                     if cv_section != cv_full else "CAREER OVERVIEW (cv.md)")
            sections.append(f"=== {label} ===\n{cv_section}")

        bg_summary = build_background_summary(tags)
        if bg_summary:
            sections.append(f"=== BACKGROUND CONTEXT ===\n{bg_summary}")

        if is_treering_bullet(company):
            claims_path = os.path.join(self.kb_dir, "verified-claims.csv")
            if os.path.exists(claims_path):
                try:
                    df_claims = pd.read_csv(claims_path)
                    if "Use in Resume?" in df_claims.columns:
                        df_claims = df_claims[
                            df_claims["Use in Resume?"].str.strip().str.lower().str.startswith("yes")
                        ]
                    filtered_claims = filter_claims_by_tags(df_claims, tags)
                    claims_text = get_verified_claims_text(filtered_claims)
                    if claims_text:
                        sections.append(
                            "=== VERIFIED CLAIMS & METRICS (Treering — resume-usable, tag-filtered) ===\n"
                            "Use these to inject real, verified metrics where appropriate. "
                            "Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                            + claims_text
                        )
                except Exception as e:
                    print(f"  WARNING: _build_audit_segment_bundle: could not load verified-claims.csv: {e}")

            screenshot_path = os.path.join(self.kb_dir, "extracted-screenshot-metrics.csv")
            if os.path.exists(screenshot_path):
                try:
                    df_screens = pd.read_csv(screenshot_path)
                    screenshot_text = df_screens.to_csv(index=False)
                    if screenshot_text:
                        sections.append(f"=== SCREENSHOT-SOURCED METRICS ===\n{screenshot_text}")
                except Exception as e:
                    print(f"  WARNING: _build_audit_segment_bundle: could not load screenshot metrics: {e}")

            metrics_path = os.path.join(self.kb_dir, "verified_metrics.json")
            if os.path.exists(metrics_path):
                try:
                    with open(metrics_path, "r", encoding="utf-8") as f:
                        verified_metrics = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                    if verified_metrics:
                        sections.append(
                            "=== VERIFIED METRICS (authoritative — use these numbers, not guesses) ===\n"
                            "These are the ONLY numeric metrics that may be cited as hard facts in Treering bullets.\n"
                            + verified_metrics
                        )
                except Exception as e:
                    print(f"  WARNING: _build_audit_segment_bundle: could not load verified_metrics.json: {e}")

        return "\n\n".join(sections)

    def audit_segment_bundle_for(self, company: str, tags: str) -> str:
        """
        Memoized accessor for _build_audit_segment_bundle (Tier 2), keyed by
        (company, tags) -- mirrors rewrite_bullets.py's context_block_for_bullet()
        so repeated (company, tags) pairs reuse the same bundle string instead of
        rebuilding it (and re-reading cv.md / claims csvs) on every bullet.
        """
        key = (company, tags)
        if key not in self._segment_cache:
            print(f"   ⚠️ Cache miss for {key} — building segment on demand.")
            self._segment_cache[key] = self._build_audit_segment_bundle(company, tags)
        return self._segment_cache[key]

    def warm_segment_cache(self, bullet_tuples: List[Tuple[str, str, str]]) -> None:
        """
        Mirrors rewrite_bullets.py's KnowledgeBase.warm_segment_cache(): pre-builds
        every unique (company, tags) segment bundle before the audit loop starts,
        so audit_segment_bundle_for() is a pure dict lookup with no on-demand file
        I/O mid-loop, and the terminal report shows what's cached upfront.
        """
        self._segment_cache = {}
        pairs = sorted({(company, tags) for _, company, tags in bullet_tuples})
        print(f"\n🔥 Warming segment cache for {len(pairs)} unique (company, tags) combos...")
        for company, tags in pairs:
            bundle = self._build_audit_segment_bundle(company, tags)
            self._segment_cache[(company, tags)] = bundle
            treering_flag = " [Treering+claims]" if is_treering_bullet(company) else ""
            print(f"   📦 ({company[:30]!r}, {tags[:40]!r}) → {len(bundle):,} chars{treering_flag}")
        print(f"   ✅ {len(self._segment_cache)} segment bundles ready.\n")

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
        print("   ✅ Rules loaded: manager_test")
        believability_rules = json.dumps(self.load_yaml(self.scoring_dir, "believability.yaml"))
        print("   ✅ Rules loaded: believability")
        style_rules         = json.dumps(self.load_yaml(self.rules_dir,   "style_rules.yaml"))
        print("   ✅ Rules loaded: style_rules")
        language_quality    = json.dumps(self.load_yaml(self.rules_dir,   "language_quality.yaml"))
        print("   ✅ Rules loaded: language_quality")
        verb_taxonomy       = json.dumps(self.load_yaml(self.rules_dir,   "verb_taxonomy.yaml"))
        print("   ✅ Rules loaded: verb_taxonomy")
        verb_intent_mapping = json.dumps(self.load_yaml(self.rules_dir,   "verb_intent_mapping.yaml"))
        print("   ✅ Rules loaded: verb_intent_mapping")
        hard_failures       = json.dumps(self.load_yaml(self.rules_dir,   "hard_failures.yaml"))
        print("   ✅ Rules loaded: hard_failures")
        truthfulness_rules  = json.dumps(self.load_yaml(self.rules_dir,   "truthfulness_rules.yaml"))
        print("   ✅ Rules loaded: truthfulness_rules")
        ats_rules           = json.dumps(self.load_yaml(self.rules_dir,   "ats_rules.yaml"))
        print("   ✅ Rules loaded: ats_rules")

        critique_system = (
            f"{critique_prompt}"
            f"\n\nMANAGER TEST RULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
            f"\n\nHARD FAILURES (any of these = automatic FAIL):\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nATS RULES:\n{ats_rules}"
            f"\n\n{self.recruiter_context_block()}"
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
        print(f"✏️  Rewrite system prompt: {len(rewrite_system):,} chars (stable across ALL calls)")
        print(f"💯 Score system prompt:   {len(critique_system):,} chars")

        self.warm_segment_cache(bullet_tuples)

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

                    segment_bundle = self.audit_segment_bundle_for(company, tags)
                    if segment_bundle:
                        print(f"   📦 segment bundle (Tier 2): {len(segment_bundle):,} chars")

                    active_rewrite_model   = REWRITE_MODEL
                    rewrite_parse_failures = 0
                    rewritten_bullet       = bullet

                    for rw_attempt in range(MAX_REWRITE_PARSE_FAILURES + 1):
                        use_minimal   = GEMMA_MINIMAL_JSON and "gemma" in active_rewrite_model.lower()
                        runner_schema = RewriteMinimalSchema if use_minimal else RewriteSchema

                        # Tier 1 + Tier 2 -> kb_context. build_rewrite_prompt() appends
                        # the Tier 3 tail (persona + weaknesses + bullet + JSON reminder),
                        # exactly like rewrite_bullets.py's process_bullet() does.
                        context_block = f"{static_prefix}\n{segment_bundle}" if segment_bundle else static_prefix

                        rewrite_contents = build_rewrite_prompt(
                            bullet=bullet,
                            tags=tags,
                            weaknesses=critique_data.get("weaknesses", ""),
                            kb_context=context_block,
                            minimal_schema=use_minimal,
                        )

                        try:
                            # No max_output_tokens cap here -- matches rewrite_bullets.py's
                            # rewrite call exactly. Gemma doesn't reliably respect "no
                            # preamble" instructions, so a tight cap (160/300 tokens) was
                            # truncating the JSON mid-object before the closing brace,
                            # which is what produced the non-JSON / empty rewrites.
                            rewrite_text, rw_usage = GeminiClient.generate(
                                model=active_rewrite_model,
                                system_instruction=rewrite_system,
                                contents=rewrite_contents,
                                response_schema=runner_schema,
                                temperature=0.7,
                            )

                            if not rewrite_text:
                                raise ValueError("Empty rewrite response")

                            _log_cache_stats(rw_usage, len(context_block), rw_attempt + 1)

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
        # BUG: this was loading "build_resume.md", which does not exist in
        # resume-engine/prompts/ -- load_prompt() was silently falling back
        # to the placeholder string "Process the text." on every run, so the
        # builder call had almost no real instructions. The actual file is
        # tailor_resume.md, and it already contains the full tailoring
        # hierarchy, archetype rules, and the exact JSON key spec (it even
        # says outright: "Your JSON output MUST use these exact uppercase
        # field names. Any deviation breaks the render pipeline.").
        build_prompt = self.load_prompt("tailor_resume.md")

        kb_context = self.load_knowledge_base()

        # Gap 1: KB goes into system_instruction, not contents.
        # system_instruction is the most cacheable part of the payload --
        # it stays identical across all builder calls on the same run.
        # The variable tail (JD + bullets) sits alone in combined_contents.
        builder_system = f"{build_prompt}\n\n{kb_context}"

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
