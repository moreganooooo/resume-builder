import os
import time
import yaml
import json
import re
import random
import requests
import company_research
import situational_roles
import numpy as np
import pandas as pd
import subprocess
import shutil
from pypdf import PdfReader
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Literal, Tuple

# --- PATH RESOLUTION & ENV SETUP ---
# Must run before any local import below: bullet_feedback -> rewrite_bullets
# -> gemini_client, and gemini_client.py reads GEMINI_API_KEY at *import*
# time. If .env hasn't been loaded yet, gemini_client latches onto whatever
# stale key is already sitting in the shell's environment -- override=True
# on load_dotenv() can't fix that after the fact, since it's a plain module
# constant, not re-read per call. This caused every single API call in a run
# to fail with 401 Unauthorized while silently ignoring a correct .env key.
# profile_paths itself is imported first (ahead of the render_html/etc.
# block below) purely so env_path() is available here -- it doesn't touch
# gemini_client, so it doesn't reintroduce the hazard this ordering guards
# against.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
import profile_paths
load_dotenv(profile_paths.env_path(), override=True)

from render_html import render_html
from render_coverletter import render_coverletter
import normalize_resume
import validate_resume
import validate_pdf_text
import validate_coverletter
import jd_manager
import bullet_feedback
import kb_snapshot
from bullet_bank_hash import bullets_sha
import cli_art
import theme


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

# Matches rewrite_bullets.py's REWRITE_MAX_OUTPUT_TOKENS exactly -- bounds
# wasted cost/latency on a real failure mode (2026-07-16) where a model
# produces a valid answer up front, then degenerates into repeating a
# phrase until it exhausts its output budget without ever closing the
# JSON. This alone does not fix parsing (a capped response can still be
# truncated mid-loop) -- GeminiClient.parse_json()'s salvage-fields
# fallback (gemini_client.py, shared by both scripts) is what actually
# recovers the answer from otherwise-unparseable output.
REWRITE_MAX_OUTPUT_TOKENS = 2048

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
# B21 "same class" fix: generate-pdf.mjs's subprocess.run calls had no
# ceiling, so a hung Chromium/font-load (P4F8) blocked the whole pipeline
# forever with capture_output=True swallowing every hint. 180s is generous
# for a single-page render but still a real bound.
PDF_GENERATION_TIMEOUT_SECONDS = 180
CRITIQUE_SLEEP     = 4    # seconds between critique calls (free-tier: 15 RPM)
REWRITE_SLEEP      = 4    # seconds before the rewrite call after a FAIL
RESCORE_SLEEP      = 8    # seconds before the re-score call after a rewrite
RECOMMENDATION_SLEEP = 8  # seconds between Step 5.5's one-recommendation-at-a-time calls
# Step 3's audit loop makes up to 30 calls (several with large segment
# bundles, 16k-24k tokens each per the logs), then Step 4 immediately fires
# one ~105k-token builder call -- cumulative tokens across that window can
# approach the free tier's 250k input-tokens-per-minute cap (see
# KB_ALLOWLIST's comment below for where that cap is already documented),
# producing the timeouts/retries seen in a real run. This pause lets the
# rolling per-minute window recover before the big call.
PRE_BUILDER_SLEEP  = 15
                      # (longer because rescore fires immediately after rewrite)


# --- PIPELINE CONSTANTS ---
TOP_K_BULLETS    = 30    # bullets mined from the bank per run
GEM_BOOST_WEIGHT = 0.15  # additive bonus per hidden_gem_score point above 0

# Bullets whose embedding cosine similarity to an already-selected bullet
# meets or exceeds this are treated as near-duplicates (the same underlying
# achievement, reworded) and skipped during mining -- the bank stores several
# phrasing variants of some achievements, and a real run's per-company
# minimum pulled multiple near-identical "audited CRM data, recovered $3M"
# variants into the same resume instead of finding genuinely distinct
# achievements. 0.93 still let through bullets that reuse the same "100+"
# stat for two different specific activities (sequence library vs. email
# campaigns) -- their embeddings are similar but not that similar, since the
# underlying activities do differ; lowered to catch that case. This is an
# empirical knob: too low starts merging genuinely distinct achievements
# that just share a topic, so nudge it back up if that starts happening.
DEDUP_SIMILARITY_THRESHOLD = 0.85

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
    "detective-findings-trimmed.csv",
    "evidence-guide.csv",
    "evidence_graph.json",
    "extracted-screenshot-metrics.csv",
    "portals.yml",
    "profile.yml",
    "recruiter_memory_patterns.json",
    "summaries-and-skills-clean.csv",
    "treering-archive-readme.md",
    "user-background-guide.md",
    "verified-claims.csv",
    "verified_facts.json",
    "verified_metrics.json",
    "verified_projects.json",
    "verified_tools.json",
    "voice-anchors.md",
])

# --- TIER 2 FILTERING CONSTANTS ---
# Ported verbatim from rewrite_bullets.py. These are what actually make
# the segment bundle small and relevant instead of a raw file dump.
# The keyword list gating which companies get the "deep evidence" file
# bundle (verified-claims.csv, extracted-screenshot-metrics.csv, etc.) is
# per-profile -- see profile.yml's deep_evidence_keywords: -- since it's
# not every profile that has one company with this much audited archive.
MAX_CLAIMS_ROWS   = 12
MAX_GEMMA_FILTER_ROWS = 5   # tighter cap for Gemma's slim tier -- see docs/superpowers/specs/2026-07-15-gemma-slim-context-design.md

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

from gemini_client import GeminiClient, SustainedFailureError  # replaces the inline class


# ---------------------------------------------------------------------------
# TIER 2 SEGMENT HELPERS  (ported verbatim from rewrite_bullets.py)
# ---------------------------------------------------------------------------

def is_deep_evidence_bullet(role_company: str, keywords: list) -> bool:
    """Whether role_company matches profile.yml's deep_evidence_keywords --
    the companies with an extra audited-evidence archive (verified claims,
    screenshot metrics, etc.) beyond the base bullet bank. Empty keywords
    (a profile with no such archive yet) means this is always False."""
    if not isinstance(role_company, str) or not keywords:
        return False
    rc = role_company.lower()
    return any(kw in rc for kw in keywords)


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


def _tag_context_map() -> dict:
    """Bracket-tag ("[ops]") -> persona_description, built from profile.yml's
    tags: (profile_paths.tags(), generated per-profile during bootstrap)
    instead of a hardcoded module constant -- see that function's
    docstring for why. Bracketed form matters -- it's how tag matching
    avoids accidental substring matches (e.g. "ops" inside some unrelated
    word)."""
    return {f"[{t['name']}]": t["persona_description"] for t in profile_paths.tags()}


def _claim_tag_keywords_map() -> dict:
    """Bracket-tag -> keywords, built from profile.yml's tags: the same
    way as _tag_context_map(). An empty keywords list for a tag means
    "matches everything" (the catch-all/generalist convention), not
    "matches nothing" -- see filter_claims_by_tags()'s include_all logic."""
    return {f"[{t['name']}]": (t.get("keywords") or []) for t in profile_paths.tags()}


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


def filter_json_entries_by_tags(entries: list, tags: str, max_rows: int) -> list:
    """Ported verbatim from rewrite_bullets.py -- same tag-keyword logic as
    filter_claims_by_tags, but for a list of dicts (verified_metrics.json's
    "metrics" list, verified_projects.json's "projects" list) rather than
    a DataFrame."""
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


def get_verified_claims_text(df_claims: pd.DataFrame) -> str:
    if df_claims.empty:
        return ""
    cols = ["Claim / Finding", "Metric(s)", "Confidence", "Evidence / Detail"]
    available = [c for c in cols if c in df_claims.columns]
    return df_claims[available].to_csv(index=False)


def persona_context(tags: str) -> str:
    tag_context = _tag_context_map()
    if not isinstance(tags, str) or not tags.strip():
        return "this candidate's target roles"
    parts = [tag_context[tag] for tag in tag_context if tag in tags.lower()]
    return ", ".join(parts) if parts else "this candidate's target roles"


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
        cli_art.console.print(f"   {theme.colorize_icon('hint')} tokens — {token_part} | {theme.colorize_icon('hint')} cached: {cached_tokens:,}", soft_wrap=True)
    else:
        cli_art.console.print(f"   {theme.colorize_icon('hint')} tokens — {token_part}", soft_wrap=True)


def _sanitize_none_for_prompt(value):
    """
    Recursively replaces None with "" throughout a dict/list structure
    before it gets json.dumps()'d into a later fix/trim/critique prompt.

    A real run's trim step correctly blanked WHY_TEXT, but if that value
    was ever a Python None (rather than "") a *later* trim step's prompt
    would render it as the unquoted JSON token null -- the model then
    echoed that back as the literal string "null" instead of leaving it
    blank, producing a visible "null" in the rendered PDF. Stripping None
    before every re-dump means the model never sees a raw null token in
    its own context to mis-copy in the first place.
    """
    if isinstance(value, dict):
        return {k: _sanitize_none_for_prompt(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_none_for_prompt(v) for v in value]
    if value is None:
        return ""
    return value


def _short_widow_bullets(resume_data: dict, companies: set, style_rules: dict) -> list[str]:
    """
    Returns bullets (verbatim achievement text) belonging to `companies`
    that wrap to a second line but leave a short widow there. Detection
    itself lives in validate_resume.bullets_with_short_widow() -- shared
    with validate()'s own pre-render widow check so the trim step here
    (page-overflow only) and the general fix loop (runs on every build,
    independent of page count) can never drift onto different thresholds.
    """
    bullets = [
        bullet
        for job in resume_data.get("EXPERIENCE", [])
        if job.get("company") in companies
        for bullet in job.get("achievements", [])
    ]
    return [
        bullet
        for bullet, _word_count in validate_resume.bullets_with_short_widow(bullets, style_rules)
    ]


def _widow_trim_instruction(resume_data: dict, style_rules: dict) -> str:
    """
    Builds the trim-step instruction for tightening bullets that wrap to a
    short widow second line -- the specific bullets are named explicitly
    so the model tightens only those, not a guess at which ones might
    wrap. Checks every company actually present in this resume (not a
    hardcoded subset) -- a widow line is a rendering artifact of the
    bullet text and page width, not something specific to any one role.
    """
    companies = {job.get("company") for job in resume_data.get("EXPERIENCE", []) if job.get("company")}
    widow_bullets = _short_widow_bullets(resume_data, companies, style_rules)
    if not widow_bullets:
        return (
            "No bullets currently wrap to a short widow second line -- "
            "leave every bullet exactly as-is and change nothing for this "
            "step."
        )
    return (
        "Tighten ONLY these specific bullets, which wrap to a short widow "
        "second line on the rendered PDF: trim adjectives, front-load "
        "keywords, collapse redundant clauses so each either fits on one "
        "line or wraps to a fuller second line. Leave every other bullet "
        "exactly as-is.\n" + "\n".join(f"- {b}" for b in widow_bullets)
    )


def _required_role_roster(profile_data: dict) -> list[str]:
    """profile.yml's roles: names, minus any situational role.

    Situational roles are conditional by design -- they fire only when a JD
    calls for them -- so their absence from a given resume is correct and must
    not read as a violation. Every other declared company is unconditional:
    the profile says the candidate worked there, so the resume has to say so
    too. See validate_resume._check_role_roster() for what happened without
    this.
    """
    situational = set(situational_roles.load_situational_roles()["roles"].keys())
    return [
        name for role in (profile_data.get("roles") or [])
        if (name := str(role.get("name", "")).strip()) and name not in situational
    ]


def _required_role_bullet_minimums(profile_data: dict) -> dict[str, int]:
    """profile.yml's roles: min_bullets, keyed by company name.

    This is the same per-role floor build_role_rules_block()'s "Per-Role
    Bullet Count Targets" table already tells the model -- nothing
    checked it was actually followed, which is how Element 8 / Strategy
    LLC, VML, and Callahan Creek each shipped with 2 bullets against a
    declared min_bullets of 3. Situational roles are excluded for the
    same reason _required_role_roster() excludes them.
    """
    situational = set(situational_roles.load_situational_roles()["roles"].keys())
    return {
        name: role["min_bullets"]
        for role in (profile_data.get("roles") or [])
        if (name := str(role.get("name", "")).strip()) and name not in situational
        and role.get("min_bullets") is not None
    }


def _confirm_continue_without_keywords() -> bool:
    """Single-file interactive escape hatch for the empty-keywords stop. Only
    ever reached with interactive=True, so a non-TTY (batch, `resume sample`,
    tests) can never block on it; treats an unreadable stdin as 'no'."""
    try:
        answer = input("    Build the resume anyway, with no JD keywords? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        cli_art.console.print(markup=False, soft_wrap=True)
        return False
    return answer in ("y", "yes")


def _trim_profile_yaml(raw: str) -> str:
    """Keeps only the AUDIT_PROFILE_KEEP sections of a raw profile.yml (the
    candidate-identity ones: target_roles, archetypes, narrative, superpowers,
    background_context, deal_breakers), dropping everything from the first
    AUDIT_PROFILE_STOP heading onward. Shared by build_audit_static_prefix()
    and evaluate_fit() so both send the model the same view of the candidate."""
    result = []
    capturing = False
    for line in raw.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(s) for s in AUDIT_PROFILE_KEEP):
            capturing = True
        elif any(stripped.startswith(s) for s in AUDIT_PROFILE_STOP):
            capturing = False
        if capturing:
            result.append(line)
    return "\n".join(result).strip()


def _bullet_removal_trim_instruction(profile_data: dict) -> str:
    """
    Builds the last-resort trim step's instruction: remove bullets from
    the lowest-flex_priority roles first, working each toward its
    min_bullets floor, protecting profile.yml's protected_bullets:. Uses
    the exact same flex_priority ordering build_role_rules_block()'s
    "Trim priority" line already promises the model, so this step's actual
    behavior matches what it was already told to expect -- not a
    hardcoded company list, which would be a silent no-op for any profile
    whose companies don't happen to match it.
    """
    roles = profile_data.get("roles") or []
    protected = profile_data.get("protected_bullets") or []
    if not roles:
        return (
            "Remove the least-relevant bullets from any role, working toward "
            "each role's minimum bullet count, while protecting the most "
            "distinctive/differentiated bullets from removal."
        )
    flex_order = sorted(roles, key=lambda r: r.get("flex_priority", 999))
    order_text = ", then ".join(
        f"{r['name']} (can go down to {r['min_bullets']} bullets total)" for r in flex_order
    )
    text = f"Remove the least-relevant bullets, starting with {order_text}"
    if protected:
        text += ", while protecting these specific bullets from removal: " + "; ".join(protected)
    else:
        text += "."
    return text


def _review_recommendations_interactively(recs: list[str], checkpoint: dict, job_key: str) -> list[str]:
    """
    Prompts a y/n approval for each Step 5 critique recommendation before Step
    5.5 is allowed to apply any of them -- so gap-filling content never lands
    in the resume without explicit approval. Approval choices are checkpointed
    under "approved_recommendations" so a resumed run doesn't re-prompt.
    """
    approved_recs = checkpoint.get("approved_recommendations")
    if approved_recs is not None:
        return approved_recs

    cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
    cli_art.console.print("Step 5.5 review: approve which recommendations to attempt "
          "(nothing below is applied until you say yes).", markup=False, soft_wrap=True)
    approved_recs = []
    for idx, rec in enumerate(recs, start=1):
        answer = input(f"  [{idx}/{len(recs)}] {rec}\n    Apply this? [y/N] ").strip().lower()
        if answer in ("y", "yes"):
            approved_recs.append(rec)

    checkpoint["approved_recommendations"] = approved_recs
    jd_manager.save_checkpoint(job_key, checkpoint)
    if not approved_recs:
        cli_art.console.print("  None approved -- skipping Step 5.5.", markup=False, soft_wrap=True)
    return approved_recs


def _parse_pdf_result(stdout: str, pdf_path: str) -> tuple:
    """Extracts (page_count, size_str). page_count is read directly from the
    rendered PDF via pypdf, not regexed out of generate-pdf.mjs's stdout --
    that regex depended on Chromium emitting an uncompressed page tree, and a
    miss silently disabled the 2-page rule instead of failing loud. page_count
    is None only if pypdf itself can't open the file. size_str is still
    cosmetic and comes from stdout."""
    try:
        page_count = len(PdfReader(pdf_path).pages)
    except Exception:
        page_count = None
    size_match = re.search(r"Size:\s*([\d.]+\s*\w+)", stdout)
    size_str = size_match.group(1) if size_match else "unknown size"
    return page_count, size_str


def _summarize_keywords(jd_keywords: dict) -> str:
    """One-line count summary of a JDKeywordSchema-shaped dict (tools,
    hard_skills, core_functions today, but iterates generically over
    whatever keys are present). Full values remain in the checkpoint JSON
    for anyone who needs them."""
    parts = [f"{len(v)} {k.replace('_', ' ')}" for k, v in jd_keywords.items() if v]
    return ", ".join(parts) if parts else "none found"


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

# Weights ported from career-ops's modes/offer.md weighted-match matrix,
# now split into three independent layers instead of one blended
# 10-dimension score: fit ("does this match my background"), interview
# odds ("will a recruiter believe it fast enough to move me forward"),
# and practical pursue ("is this worth my time/energy in real terms").
# These are genuinely different questions -- a role can be a great fit
# with weak interview odds (title history off, crowded funnel) or the
# reverse -- and blending them into one number made it impossible to
# tell *why* a role scored low. All composite math stays in Python
# (never trusted from the model) so a wrong LLM sum can't silently skew
# the recommendation.
FIT_SUBSCORE_WEIGHTS = {
    "functional_alignment":      0.30,
    "north_star_alignment":      0.25,
    "level_plausibility":        0.20,
    "work_style_sustainability": 0.15,
    "tools_process_overlap":     0.10,
}

INTERVIEW_ODDS_WEIGHTS = {
    "title_continuity":     0.25,
    "evidence_match":       0.25,
    "domain_credibility":   0.15,
    "recruiter_legibility": 0.15,
    "narrative_burden":     0.10,
    "funnel_friction":      0.10,
}

PRACTICAL_PURSUE_WEIGHTS = {
    "remote_quality":           0.25,
    "compensation_viability":   0.15,
    "growth_value":             0.10,
    "time_to_offer":            0.15,
    "company_reputation":       0.10,
    "cultural_signals":         0.10,
    "posting_legitimacy_score": 0.15,
}

# Fit and interview odds carry equal primary weight; practical
# constraints matter but shouldn't dominate the decision the way a hard
# blocker does (that's handled separately, via hard_blockers).
COMPOSITE_SCORE_WEIGHTS = {
    "fit_score":              0.40,
    "interview_odds_score":   0.40,
    "practical_pursue_score": 0.20,
}

class FitSubscores(BaseModel):
    functional_alignment:      int = Field(description="1-5: direct match to core demonstrated work vs. weak/missing")
    north_star_alignment:      int = Field(description="1-5: fit to target role families vs. far from desired direction")
    level_plausibility:        int = Field(description="1-5: screen risk, not prestige; overqualified is safer than underqualified")
    work_style_sustainability: int = Field(description="1-5: realistically sustainable/energizing vs. brute-force or burnout-prone")
    tools_process_overlap:     int = Field(description="1-5: overlap with JD's named tools/systems")

class InterviewOddsSubscores(BaseModel):
    title_continuity:     int = Field(description="1-5: does the resume's title path map cleanly onto this posting's title")
    evidence_match:       int = Field(description="1-5: can the resume prove the posting's core asks with concrete specifics")
    domain_credibility:   int = Field(description="1-5: does the company's world feel instantly credible for this candidate")
    recruiter_legibility: int = Field(description="1-5: how quickly a recruiter can understand the match")
    narrative_burden:     int = Field(description="1-5: how little explanation is required before the match makes sense")
    funnel_friction:      int = Field(description="1-5: likely favorable vs. crowded/high-friction funnel")

class PracticalPursueSubscores(BaseModel):
    remote_quality:           int = Field(description="1-5: fully remote and workable vs. onsite/incompatible")
    compensation_viability:   int = Field(description="1-5: vs. stated target/floor, or likely range if unstated")
    growth_value:             int = Field(description="1-5: useful momentum/skill-building vs. likely dead end")
    time_to_offer:            int = Field(description="1-5: likely process speed/friction")
    company_reputation:       int = Field(description="1-5: reputation/red flags")
    cultural_signals:         int = Field(description="1-5: promising vs. concerning signals in the JD's own language")
    posting_legitimacy_score: int = Field(description="1-5: confidence the posting is real, active, and worth energy")

class FitEvaluationSchema(BaseModel):
    archetype:                  str                       = Field(description="Best-matching role archetype, or closest hybrid of two")
    hard_blockers:              List[str]                 = Field(description="Explicit disqualifying constraints found; empty list if none")
    fit_subscores:              FitSubscores
    interview_odds_subscores:   InterviewOddsSubscores
    practical_pursue_subscores: PracticalPursueSubscores
    recommendation:             Literal["Strong pursue", "Selective pursue", "Low-priority pursue", "Skip"]
    why:                        str                       = Field(description="2-4 plain-language sentences justifying the recommendation")
    recruiter_read:             str                       = Field(description="1-2 sentences on how a recruiter is likely to read this candidate for this role at first glance")
    posting_legitimacy:         Literal["High Confidence", "Proceed with Caution", "Suspicious"] = Field(description="Does this posting look real, active, and worth pursuing?")
    posting_legitimacy_notes:   str                       = Field(description="1-2 sentences on the signals behind the posting_legitimacy assessment")


# Applying early matters a lot, and the scanners now pull in enough
# volume that a posting sitting open for weeks shouldn't rank the same
# as one found today. Gentle ramp (not a cliff at day 8) and capped so a
# genuinely strong match a few weeks old still outranks a mediocre fresh
# one -- age is a tiebreaker/prioritization signal, not an override.
STALE_POSTING_THRESHOLD_DAYS = 7
STALE_POSTING_PENALTY_PER_DAY = 0.03
STALE_POSTING_MAX_PENALTY = 0.75


def _weighted_score(subscores: dict, weights: dict) -> float:
    """1-5 weighted average of a subscore dict against its matching
    weight dict (FIT_SUBSCORE_WEIGHTS / INTERVIEW_ODDS_WEIGHTS /
    PRACTICAL_PURSUE_WEIGHTS)."""
    return round(sum(subscores.get(dim, 0) * weight for dim, weight in weights.items()), 2)


def compute_fit_score(fit_subscores: dict) -> float:
    return _weighted_score(fit_subscores, FIT_SUBSCORE_WEIGHTS)


def compute_interview_odds_score(interview_odds_subscores: dict) -> float:
    return _weighted_score(interview_odds_subscores, INTERVIEW_ODDS_WEIGHTS)


def compute_practical_pursue_score(practical_pursue_subscores: dict) -> float:
    return _weighted_score(practical_pursue_subscores, PRACTICAL_PURSUE_WEIGHTS)


def fit_composite_score(fit_score: float, interview_odds_score: float, practical_pursue_score: float, posting_age_days: int = None) -> float:
    """Weighted 1-5 blend of the three independent layer scores, per
    COMPOSITE_SCORE_WEIGHTS, minus an age penalty for postings older than
    STALE_POSTING_THRESHOLD_DAYS (see jd_manager.compute_posting_age_days()
    for how posting_age_days is derived -- None means no age signal at
    all, so no penalty is applied rather than assuming staleness)."""
    base = (
        fit_score * COMPOSITE_SCORE_WEIGHTS["fit_score"]
        + interview_odds_score * COMPOSITE_SCORE_WEIGHTS["interview_odds_score"]
        + practical_pursue_score * COMPOSITE_SCORE_WEIGHTS["practical_pursue_score"]
    )
    penalty = 0.0
    if posting_age_days is not None and posting_age_days > STALE_POSTING_THRESHOLD_DAYS:
        penalty = min(
            (posting_age_days - STALE_POSTING_THRESHOLD_DAYS) * STALE_POSTING_PENALTY_PER_DAY,
            STALE_POSTING_MAX_PENALTY,
        )
    return round(max(base - penalty, 0.0), 2)

class CoverLetterSchema(BaseModel):
    company_name:    str       = Field(description="The hiring company's name, exactly as it appears in the job description.")
    greeting:        str       = Field(description="e.g. 'Dear Hiring Team,' or a named hiring manager if the JD provides one.")
    body_paragraphs: List[str] = Field(description="2-3 first-person paragraphs, each grounded in a real JD requirement and a real fact from the background context.")
    sign_off:        str       = Field(description="e.g. 'Sincerely,'")

class CompanyResearchSchema(BaseModel):
    overall_tone_adjective: str       = Field(description="One short phrase describing the company's overall voice.")
    tone_register:          Literal["formal", "conversational", "mixed"]
    pronoun_framing:        Literal["we-centric", "you-centric", "mixed"]
    sentence_style:         Literal["short and punchy", "long and flowing", "mixed"]
    jargon_density:         Literal["high", "moderate", "low"]
    recurring_keywords:     List[str] = Field(description="1-3 brand words/phrases that genuinely repeat in the source text.")
    company_facts:          List[str] = Field(description="2-3 short, factual statements traceable directly to the source text.")


def _parse_jd_data(jd_text: str) -> dict:
    """Best-effort parse of a JD file's raw text as JSON; {} if it isn't
    (e.g. a plain-text JD, or one without a company_website field)."""
    try:
        data = json.loads(jd_text)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def find_jd_contacts(jd_data: dict) -> list:
    """Flattens a JD's already-scraped social_connections (JobRight's own
    people-search, captured into the JD dict by scan_jobright.py --
    real, named people JobRight itself found, e.g. {"fullName": "Jen
    Dudik", "jobTitle": "Director of Talent Development", "linkedinUrl":
    "https://www.linkedin.com/in/..."}) and personal_social_connections
    (company/school ties to the candidate specifically) into one list of
    {"name", "title", "company", "linkedin_url", "connection_type"}
    dicts. Never generates or guesses a person -- every entry here quotes
    JobRight's own scrape verbatim, matching this system's never-
    fabricate stance. LinkedIn-sourced JDs never have this data today --
    confirmed 2026-07-22 that LinkedIn's "People you can reach out to"
    panel is rendered client-side after page load, not in the HTML a
    plain authenticated fetch (scan_linkedin.py's existing mechanism)
    can see -- so this returns [] for those, not an error."""
    contacts = []

    for entry in (jd_data.get("social_connections") or []):
        name = entry.get("fullName") or entry.get("firstName") or ""
        if not name:
            continue
        contacts.append({
            "name": name, "title": entry.get("jobTitle") or "",
            "company": entry.get("companyName") or "",
            "linkedin_url": entry.get("linkedinUrl") or "",
            "connection_type": "JobRight match",
        })

    personal = jd_data.get("personal_social_connections") or {}
    for tie_type in ("company", "school"):
        for entry in (personal.get(tie_type) or []):
            name = entry.get("fullName") or entry.get("firstName") or ""
            if not name:
                continue
            contacts.append({
                "name": name, "title": entry.get("jobTitle") or "",
                "company": entry.get("companyName") or "",
                "linkedin_url": entry.get("linkedinUrl") or "",
                "connection_type": f"Personal {tie_type} connection",
            })

    return contacts


def _build_output_stem(jd_path: str) -> str:
    """Returns '<CandidateName>[_Title][_Company]' for resume/cover-letter
    output filenames, with the candidate name prefix derived from the
    active profile's profile.yml (candidate.full_name, spaces stripped --
    e.g. "Morgan Escott" -> "MorganEscott"). Role title and company
    segments are each included only when known -- omitted entirely (not a
    placeholder like "Unknown") when missing, since a filename with a
    placeholder in it would always need fixing before sending, whereas
    e.g. "MorganEscott_CampaignManager_Resume" is still sendable as-is."""
    job_title, company_name = jd_manager.extract_job_meta(jd_path)
    parts = [profile_paths.full_name().replace(" ", "")]
    if job_title:
        parts.append(jd_manager.sanitize_for_filename(job_title))
    if company_name:
        parts.append(jd_manager.sanitize_for_filename(company_name))
    return "_".join(parts)


def format_company_research_block(research: dict) -> str:
    """Formats a CompanyResearchSchema-shaped dict into the
    '=== COMPANY RESEARCH ===' context block both build_tailored_coverletter
    and build_tailored_resume fold into their system-instruction context."""
    return (
        "\n\n=== COMPANY RESEARCH ===\n"
        f"Overall tone: {research.get('overall_tone_adjective', '')}\n"
        f"Register: {research.get('tone_register', '')} | Framing: {research.get('pronoun_framing', '')} | "
        f"Sentence style: {research.get('sentence_style', '')} | Jargon: {research.get('jargon_density', '')}\n"
        f"Recurring brand words: {', '.join(research.get('recurring_keywords', []))}\n"
        "Company facts (use at most 1-2, never fabricate beyond these):\n"
        + "\n".join(f"- {fact}" for fact in research.get('company_facts', []))
    )


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
    skills_relevance_score:  int       = Field(description="0-100: are Skills JD-relevant?")
    overall_fit_score:       int       = Field(description="0-100: holistic resume-to-JD fit")
    top_third_score:         int       = Field(description="0-100: does the top third of page one alone communicate fit within a 15-30 second first read (first-impression / above-the-fold test)?")
    flags:                   List[str] = Field(description="Specific issues found")
    recommendations:         List[str] = Field(description="Actionable fixes, one per flag")
    distinctive_moments:     List[str] = Field(description=(
        "2-3 EXACT sentences or achievement bullets already present in the "
        "resume, quoted verbatim, that read as memorable and "
        "personality-forward rather than generic. Protected from later "
        "automated recommendation edits."
    ))
    flat_sections:           List[str] = Field(description=(
        "Section names (e.g. 'Professional Summary', 'VML experience') "
        "that read as competent but generic -- interchangeable with other "
        "candidates' resumes."
    ))
    # Step 1 (professional_identity_score.yaml) -- see B49/B50 in
    # phase-9-backlog.md: these outputs were named by critique_resume.md's
    # evaluation sequence but had no schema field to return them in, so
    # steps 1-6 were being silently discarded at the schema boundary.
    primary_identity:        str       = Field(description="Step 1: the detected primary professional identity/archetype.")
    secondary_identity:      str       = Field(description="Step 1: the detected secondary identity, if any. Empty string if none.")
    tertiary_identity:       str       = Field(description="Step 1: the detected tertiary identity, if any. Empty string if none.")
    competing_narratives:    List[str] = Field(description="Step 1: any competing/conflicting identity narratives found. Empty if none.")
    unsupported_positioning: List[str] = Field(description="Step 1: any positioning claims not supported by the resume content. Empty if none.")
    # Step 2 (resume_cohesion_score.yaml)
    recruiter_takeaway:      str       = Field(description="Step 2: one-sentence recruiter takeaway from the cohesion check.")
    strongest_alignment:     str       = Field(description="Step 2: name of the strongest-passing alignment_check.")
    weakest_alignment:       str       = Field(description="Step 2: name of the weakest-passing (or failing) alignment_check.")
    # Step 5 (skills_scoring.yaml)
    ungrouped_skills:        List[str] = Field(description="Step 5: skills present but not cleanly grouped under a category. Empty if none.")
    unsupported_skills:      List[str] = Field(description="Step 5: skills listed with no evidence elsewhere in the resume. Empty if none.")
    archetype_mismatch:      bool      = Field(description="Step 5: True if the skills grouping/ordering doesn't match the style_rules_archetype from Step 1.")
    # B51: every reject_if.score_below / pass_threshold / hard_failures trip
    # across every attached rubric, so a resume that fails a rubric's own
    # stated bar has a channel to say so instead of shipping silently.
    hard_failures_triggered: List[str] = Field(description=(
        "Every reject_if.score_below, pass_threshold, or hard_failures rule "
        "(from any attached scoring/rules file) that this resume actually "
        "trips, each as '<rubric file>: <specific reason>'. Empty list if "
        "the resume clears every attached rubric's stated bar."
    ))

class CertItem(BaseModel):
    title: str = Field(description="Full certification or training name.")
    org:   str = Field(description="Issuing organization.")
    year:  str = Field(description="4-digit year, e.g. '2023'. Leave blank if unknown.")

class EducationItem(BaseModel):
    degree:      str = Field(description="Degree or program name.")
    institution: str = Field(description="School or university name.")
    year:        str = Field(default="", description="Graduation year or date range. Leave blank if unknown.")
    description: str = Field(default="", description="Honors, GPA, relevant coursework. Leave blank if none.")

class ExperienceEntry(BaseModel):
    """
    A previous version used EXPERIENCE: List[dict] to avoid nested $defs in
    responseSchema, believing Gemini's structured-output API couldn't handle
    them -- but a real run then got EXPERIENCE back as several empty {}
    objects: List[dict]'s per-item schema has no required properties at all,
    so an empty object is entirely valid against what Gemini actually
    receives (the Field description explaining title/company/achievements
    lives only in Pydantic metadata, which GeminiClient.sanitize_schema()
    strips before submission). The real cause of the earlier 400 was
    sanitize_schema() deleting $defs unconditionally, leaving nested models'
    $ref pointers dangling -- fixed by GeminiClient.resolve_refs(), which
    inlines $ref/$defs before sanitize_schema runs. This model now lets
    "required" actually reach the API.
    """
    title:        str       = Field(description="Job title, reframed per this JD's archetype if applicable.")
    company:      str       = Field(description="Company name, exactly as used in tailor_resume.md's per-role bullet targets.")
    period:       str       = Field(description="Employment dates, MM/YYYY - MM/YYYY format.")
    location:     str       = Field(default="", description="City/state or Remote. Leave blank if unknown.")
    achievements: List[str] = Field(description="Achievement bullets for this role. Must not be empty.")
    career_note:  str       = Field(default="", description="Auto-filled after generation for Treering Yearbooks by normalize_resume; always output empty string here.")

class TemplateSchema(BaseModel):
    """
    Flattened schema for the builder call.
    NAME/PHONE/EMAIL/LINKEDIN_DISPLAY/LOCATION are not builder
    fields -- contact info doesn't vary by JD, so it's hard-coded in
    fixed_content.CONTACT_INFO and force-applied by normalize_resume,
    same pattern as Certifications/Education/company facts. There is no
    PORTFOLIO_URL/PORTFOLIO_DISPLAY field at all -- the portfolio link was
    removed resume-wide.
    """
    TAGLINE:                str       = Field(description="Max 80 chars. Follows archetype tagging rules.")
    SECTION_SUMMARY:        str       = Field(default="Professional Summary")
    SUMMARY_TEXT:           str       = Field(description="Max 5 lines. First sentence MUST be bolded using <strong> tags. No generic filler.")
    SECTION_EXPERIENCE:     str       = Field(default="Work Experience")
    EXPERIENCE:             List[ExperienceEntry] = Field(
        description=(
            "One entry per company. Bullet counts per role must match the "
            "ROLE RULES block's Per-Role Bullet Count Targets table exactly."
        )
    )
    # No KU/KCKCC-named achievement-key fields here -- those were Morgan-
    # specific and hardcoded (both the field names and their Literal enum
    # values) directly into this class, which every profile's builder call
    # shares. The generic replacement -- EDU_ACHIEVEMENT_KEY_<n>, one per
    # profile.yml education entry that offers a pre-approved achievement-
    # bullet choice -- is built per-profile at call time by
    # ResumeEngine.build_education_achievement_schema_fields() and merged
    # into this schema via GeminiClient.generate()'s extra_schema_properties/
    # extra_required, not declared as static fields here. See that method's
    # docstring for why a plain str field wouldn't work (sanitize_schema()
    # strips `description`, so only a real `enum` constraint survives to
    # Gemini -- and the valid enum values differ per profile, unknowable at
    # this class's definition time).
    SECTION_SKILLS:         str       = Field(default="Skills")
    SKILLS:                 List[str] = Field(description="Technical skills mapped to JD.")
    SECTION_WHY:            str       = Field(
        default="",
        description=(
            "'Why [Real Company Name]?' -- ONLY set if space allows on a 2-page "
            "resume; leave blank ('') to omit the section entirely."
        ),
    )
    WHY_TEXT:                str       = Field(
        default="",
        description=(
            "Two short paragraphs (as HTML <p> tags), max 8 lines total, "
            "first-person voice -- the only section where pronouns are allowed. "
            "Only the first sentence of the first paragraph and the last "
            "sentence of the last paragraph are wrapped in <em> tags. Must "
            "reference specific company research connected to verified facts. "
            "Leave blank ('') to omit the section entirely if it would push "
            "the resume to 3 pages."
        ),
    )


class RecommendationApplySchema(TemplateSchema):
    """
    Same shape as a normal builder/trim call (TemplateSchema), plus three
    tracking lists so the holistic critique's recommendations can be acted
    on without silently doing something the recommendation never asked for.
    Only recommendations that are concrete edits to this resume's own
    content belong in applied_recommendations -- anything describing an
    action outside the document (networking, referrals, applying elsewhere)
    must go in skipped_recommendations untouched. A recommendation phrased
    as a reflective question about personal motivation/meaning that can't
    be grounded in the provided background context goes in
    needs_personal_input instead of being fabricated.
    """
    applied_recommendations: List[str] = Field(
        default_factory=list,
        description="Exact text of each recommendation that was a resume-content edit and was applied.",
    )
    skipped_recommendations: List[str] = Field(
        default_factory=list,
        description="Exact text of each recommendation that was not a resume-content edit, so nothing was changed for it.",
    )
    needs_personal_input: List[str] = Field(
        default_factory=list,
        description=(
            "Recommendations that ARE actionable edits to this resume's own "
            "content, phrased as a reflective question about personal "
            "motivation/meaning, but for which the provided background context "
            "does not already contain a grounded, verified answer. Left "
            "unapplied rather than inventing an answer -- exact original text "
            "here so Morgan can address it herself (e.g. via `resume polish`)."
        ),
    )


# ---------------------------------------------------------------------------
# BULLET SORTING
# ---------------------------------------------------------------------------

def _bullet_sort_key(bullet_result: dict) -> tuple:
    """PASS before FAIL, then descending believability_score. Ported from the
    retired rank_bullets.md prompt -- this is a deterministic sort over data
    the audit loop already computes, not a judgment call, so it needs no LLM
    call. (ai_risk is not included: CritiqueSchema has no ai_risk field.)"""
    manager_test_rank = 0 if bullet_result.get("manager_test") == "PASS" else 1
    return (manager_test_rank, -bullet_result.get("believability_score", 0))


# ---------------------------------------------------------------------------
# RESUME ENGINE
# ---------------------------------------------------------------------------

class ResumeEngine:

    def __init__(self):
        self.engine_dir      = os.path.join(PROJECT_ROOT, "resume-engine")
        self.prompts_dir     = os.path.join(self.engine_dir, "prompts")
        self.rules_dir       = os.path.join(self.engine_dir, "rules")
        self.scoring_dir     = os.path.join(self.engine_dir, "scoring")
        self.kb_dir          = profile_paths.kb_dir()
        self.templates_dir   = os.path.join(self.engine_dir, "templates")
        self.output_json_dir = os.path.join(profile_paths.output_dir(), "json")
        self.output_html_dir = os.path.join(profile_paths.output_dir(), "html")
        self.output_pdf_dir  = os.path.join(profile_paths.output_dir(), "pdf")
        self.jds_dir         = profile_paths.jds_dir()
        os.makedirs(self.output_json_dir, exist_ok=True)
        self._segment_cache: dict = {}
        self._gemma_segment_cache: dict = {}
        self.deep_evidence_keywords = (
            self.load_yaml(self.kb_dir, "profile.yml").get("deep_evidence_keywords") or []
        )

    def load_yaml(self, dir_path, filename):
        path = os.path.join(dir_path, filename)
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def load_prompt(self, filename):
        path = os.path.join(self.prompts_dir, filename)
        with open(path, "r") as f:
            return f.read()

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
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} KB allowlist entry not found, skipping: {filename}", soft_wrap=True)
                    continue
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        master_context += f"--- START OF {filename} ---\n{f.read()}\n--- END OF {filename} ---\n\n"
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} Could not load KB file {filename}: {e}", soft_wrap=True)
        return master_context

    def build_role_rules_block(self, profile_data: dict) -> str:
        """Formats profile.yml's roles/protected_bullets/fixed_credentials/
        voice_calibration_example into the '=== ROLE RULES ===' context
        block tailor_resume.md references generically. Returns "" if the
        profile has no roles: defined yet (e.g. a freshly-bootstrapped
        profile) -- tailor_resume.md falls back to general judgment in
        that case."""
        roles = profile_data.get("roles") or []
        protected = profile_data.get("protected_bullets") or []
        credentials = profile_data.get("fixed_credentials") or {}
        certs = credentials.get("certifications") or []
        education = credentials.get("education") or []
        voice_example = profile_data.get("voice_calibration_example")

        if not roles and not protected and not certs and not education and not voice_example:
            return ""

        lines = ["\n\n=== ROLE RULES ==="]

        if roles:
            lines.append("Per-Role Bullet Count Targets:")
            lines.append("| Company | Min | Target | Page |")
            lines.append("| --- | --- | --- | --- |")
            for role in roles:
                lines.append(f"| {role['name']} | {role['min_bullets']} | {role['target_bullets']} | {role['page']} |")

            must_fit_page_1 = [r["name"] for r in roles if r.get("must_fit_page_1")]
            if must_fit_page_1:
                lines.append(f"\nThe following roles must fit entirely on page 1: {', '.join(must_fit_page_1)}.")

            flex_order = sorted(roles, key=lambda r: r.get("flex_priority", 999))
            lines.append(
                "\nTrim priority (lowest-priority roles trimmed toward their Min first, before any "
                f"higher-priority role loses a bullet): {', '.join(r['name'] for r in flex_order)}."
            )

        if protected:
            lines.append("\nProtected Bullets -- Do Not Aggressively Shorten:")
            for bullet in protected:
                lines.append(f"- {bullet}")

        if certs:
            lines.append("\nTraining & Certifications -- Fixed Order:")
            for i, cert in enumerate(certs, 1):
                lines.append(f"{i}. {cert['name']} | {cert['issuer']} | {cert['year']}")

        if education:
            lines.append("\nEducation -- Fixed Order and Bullet Counts:")
            for i, ed in enumerate(education, 1):
                lines.append(f"{i}. {ed['institution']} -- {ed['credential']}: exactly {ed['bullet_count']} bullet(s)")

            edu_slots = profile_paths.education_achievement_slots()
            if edu_slots:
                lines.append(
                    "\nEducation Achievement Bullet Choices -- for each entry below, set the "
                    "matching EDU_ACHIEVEMENT_KEY_<n> field (numbered in this same order) to "
                    "whichever key's framing best fits the archetype you detected:"
                )
                for i, (institution, options) in enumerate(edu_slots, 1):
                    lines.append(f"EDU_ACHIEVEMENT_KEY_{i} ({institution}):")
                    for key, framing in options.items():
                        lines.append(f"  - `{key}`: {framing}")

        if roles:
            page_1_roles = [r["name"] for r in roles if r.get("page") == 1]
            page_2_roles = [r["name"] for r in roles if r.get("page") == 2]
            if page_1_roles or page_2_roles:
                lines.append(
                    f"\nSection Order (Page 1 -> Page 2): Page 1 Work Experience: {', '.join(page_1_roles)}. "
                    f"Page 2 Work Experience: {', '.join(page_2_roles)}."
                )

        if voice_example:
            lines.append(f"\nVoice Calibration Example (this candidate's authentic voice): \"{voice_example}\"")

        return "\n".join(lines)

    def build_education_achievement_schema_fields(self) -> Tuple[dict, list]:
        """Per-profile Gemini responseSchema additions for education
        achievement-bullet selection: one enum-typed EDU_ACHIEVEMENT_KEY_<n>
        property per profile.yml education entry that offers a pre-approved
        choice (profile_paths.education_achievement_slots()), numbered in
        that same order so normalize_resume.py can map each answer back to
        its institution unambiguously. Returns ({}, []) for a profile with
        no such entries (e.g. a freshly-bootstrapped one) -- the builder
        call just gets no extra fields.

        These can't be static Literal-typed fields on TemplateSchema (the
        way e.g. ExperienceEntry's fields are) because the valid keys differ
        per profile and aren't known at that class's definition time. They
        also can't be a plain str field with the options only described in
        prose: GeminiClient.sanitize_schema() strips every field's
        `description` before the schema ever reaches Gemini's
        responseSchema (see test_orchestrator_schema_cleanup.py's
        regression test for this), so only an actual JSON-schema `enum`
        constraint reliably constrains the model to a valid key -- hence
        building real enum-typed properties here, per call, and merging
        them into TemplateSchema's schema via GeminiClient.generate()'s
        extra_schema_properties/extra_required rather than baking them into
        the class."""
        properties: dict = {}
        required: list = []
        for i, (institution, options) in enumerate(profile_paths.education_achievement_slots(), 1):
            field_name = f"EDU_ACHIEVEMENT_KEY_{i}"
            properties[field_name] = {
                "type": "string",
                "enum": list(options.keys()),
                "description": (
                    f"Pre-approved achievement-bullet choice for {institution} -- "
                    + "; ".join(f"{key} = {framing}" for key, framing in options.items())
                ),
            }
            required.append(field_name)
        return properties, required

    def build_audit_static_prefix(self, include_evidence_guide: bool = False) -> str:
        """
        Builds the slim Tier-1 context prefix for the audit loop and (with
        include_evidence_guide=True) cover letters. Mirrors
        rewrite_bullets.py _build_static_prefix() exactly for the base
        profile/verified_* sections. ~5-10k tokens vs ~457k for the full KB
        -- include_evidence_guide adds ~17k tokens more, only when the
        caller opts in (cover letters), never for the per-bullet audit
        loop, which reuses this same function across many calls per resume
        build and must not have that cost multiply across them.
        """
        cli_art.console.print(f"\n{theme.colorize_icon('hint')} Loading knowledge base context (Tier 1)...", soft_wrap=True)
        sections = []

        profile_path = os.path.join(self.kb_dir, "profile.yml")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded profile.yml ({len(raw):,} chars)", soft_wrap=True)
                trimmed = _trim_profile_yaml(raw)
                if trimmed:
                    cli_art.console.print(f"   {theme.colorize_icon('hint')} profile.yml trimmed to {len(trimmed):,} chars", soft_wrap=True)
                    sections.append(
                        "=== TARGET ROLES & PROFILE (from profile.yml) ===\n"
                        "Use these to understand what roles this bullet needs to appeal to and what to avoid.\n"
                        + trimmed
                    )
            except Exception as e:
                cli_art.console.print(f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load profile.yml: {e}", soft_wrap=True)

        for fname, header, note in [
            ("verified_facts.json",
             "=== VERIFIED FACTS (high-confidence claims -- use freely) ===",
             "These are the only facts about this candidate's career that are evidence-backed.\nDo NOT invent facts outside this list."),
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
                    cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded {fname} ({len(data):,} chars)", soft_wrap=True)
                    sections.append(f"{header}\n{note}\n{data}")
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load {fname}: {e}", soft_wrap=True)

        voice_anchors_path = os.path.join(self.kb_dir, "voice-anchors.md")
        if os.path.exists(voice_anchors_path):
            try:
                with open(voice_anchors_path, "r", encoding="utf-8") as f:
                    data = f.read()
                cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded voice-anchors.md ({len(data):,} chars)", soft_wrap=True)
                sections.append(f"=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n{data}")
            except Exception as e:
                cli_art.console.print(f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load voice-anchors.md: {e}", soft_wrap=True)

        if include_evidence_guide:
            evidence_guide_path = os.path.join(self.kb_dir, "evidence-guide.csv")
            if os.path.exists(evidence_guide_path):
                try:
                    with open(evidence_guide_path, "r", encoding="utf-8") as f:
                        data = f.read()
                    cli_art.console.print(f"   {theme.colorize_icon('success')} Loaded evidence-guide.csv ({len(data):,} chars)", soft_wrap=True)
                    sections.append(f"=== EVIDENCE GUIDE (thematic career-proof clusters) ===\n{data}")
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load evidence-guide.csv: {e}", soft_wrap=True)

        return "\n\n".join(sections)

    def build_audit_static_prefix_gemma(self) -> str:
        """Slim static tier for Gemma only -- mirrors rewrite_bullets.py's
        KnowledgeBase._build_gemma_static_prefix() exactly (2026-07-16).
        Keeps only guardrails (verified_facts, verified_tools) and
        voice_anchors (small, directly serves rewrite quality). Drops
        profile.yml (strategic career-positioning content, not needed to
        rewrite a single existing bullet) and verified_projects.json
        (re-added tag-filtered, at MAX_GEMMA_FILTER_ROWS, in
        _build_audit_segment_bundle_gemma() instead of included whole)."""
        sections = []

        for fname, header, note in [
            ("verified_facts.json",
             "=== VERIFIED FACTS (high-confidence claims -- use freely) ===",
             "These are the only facts about this candidate's career that are evidence-backed.\nDo NOT invent facts outside this list."),
            ("verified_tools.json",
             "=== VERIFIED TOOLS (HF002 guard -- only claim tools listed here) ===",
             "Never claim proficiency with any tool not present in this list."),
        ]:
            fpath = os.path.join(self.kb_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                    sections.append(f"{header}\n{note}\n{data}")
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} build_audit_static_prefix_gemma: could not load {fname}: {e}", soft_wrap=True)

        voice_anchors_path = os.path.join(self.kb_dir, "voice-anchors.md")
        if os.path.exists(voice_anchors_path):
            try:
                with open(voice_anchors_path, "r", encoding="utf-8") as f:
                    data = f.read()
                sections.append(f"=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n{data}")
            except Exception as e:
                cli_art.console.print(f"  {theme.colorize_icon('warning')} build_audit_static_prefix_gemma: could not load voice-anchors.md: {e}", soft_wrap=True)

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
            cli_art.console.print(f"  {theme.colorize_icon('warning')} recruiter_context_block: could not load recruiter_memory_patterns.json: {e}", soft_wrap=True)
            return ""
        if not data:
            return ""
        return (
            "=== RECRUITER READING PATTERNS (what hiring managers notice first) ===\n"
            "Use these patterns to calibrate believability and manager_test scoring.\n"
            + data
        )

    def build_bullet_critique_system(self) -> str:
        """
        Builds the complete critique system prompt for bullet auditing.
        Loads all rule files and concatenates them with the critique_bullet.md prompt.
        This is extracted into a separate testable method so tests can verify
        the final prompt structure without running the full audit loop.
        """
        critique_prompt     = self.load_prompt("critique_bullet.md")
        manager_test_rules  = json.dumps(self.load_yaml(self.scoring_dir, "manager_test.yaml"))
        believability_rules = json.dumps(self.load_yaml(self.scoring_dir, "believability.yaml"))
        style_rules         = json.dumps(self.load_yaml(self.rules_dir,   "style_rules.yaml"))
        language_quality    = json.dumps(self.load_yaml(self.rules_dir,   "language_quality.yaml"))
        verb_taxonomy       = json.dumps(self.load_yaml(self.rules_dir,   "verb_taxonomy.yaml"))
        verb_intent_mapping = json.dumps(self.load_yaml(self.rules_dir,   "verb_intent_mapping.yaml"))
        hard_failures       = json.dumps(self.load_yaml(self.rules_dir,   "hard_failures.yaml"))
        truthfulness_rules  = json.dumps(self.load_yaml(self.rules_dir,   "truthfulness_rules.yaml"))

        critique_system = (
            f"{critique_prompt}"
            f"\n\nMANAGER TEST RULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
            f"\n\nHARD FAILURES (any of these = automatic FAIL):\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nSTYLE RULES (includes ATS rules):\n{style_rules}"
            f"\n\n{self.recruiter_context_block()}"
        )
        return critique_system

    def _build_audit_segment_bundle(self, company: str, tags: str) -> str:
        """
        Builds a per-bullet context bundle for the rewrite call (Tier 2).
        Now actually mirrors rewrite_bullets.py's _build_segment_bundle():
        a curated cv.md excerpt + tag-specific background blurb, plus
        (only for deep-evidence-archive companies, per profile.yml's
        deep_evidence_keywords:) tag-filtered verified claims, capped
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
                cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle: could not load cv.md: {e}", soft_wrap=True)

        cv_section = extract_cv_section(cv_full, company)
        if cv_section:
            label = ("ROLE CONTEXT (cv.md excerpt)"
                     if cv_section != cv_full else "CAREER OVERVIEW (cv.md)")
            sections.append(f"=== {label} ===\n{cv_section}")

        bg_summary = build_background_summary(tags)
        if bg_summary:
            sections.append(f"=== BACKGROUND CONTEXT ===\n{bg_summary}")

        if is_deep_evidence_bullet(company, self.deep_evidence_keywords):
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
                            f"=== VERIFIED CLAIMS & METRICS ({company} — resume-usable, tag-filtered) ===\n"
                            "Use these to inject real, verified metrics where appropriate. "
                            "Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                            + claims_text
                        )
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle: could not load verified-claims.csv: {e}", soft_wrap=True)

            screenshot_path = os.path.join(self.kb_dir, "extracted-screenshot-metrics.csv")
            if os.path.exists(screenshot_path):
                try:
                    df_screens = pd.read_csv(screenshot_path)
                    screenshot_text = df_screens.to_csv(index=False)
                    if screenshot_text:
                        sections.append(f"=== SCREENSHOT-SOURCED METRICS ===\n{screenshot_text}")
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle: could not load screenshot metrics: {e}", soft_wrap=True)

            metrics_path = os.path.join(self.kb_dir, "verified_metrics.json")
            if os.path.exists(metrics_path):
                try:
                    with open(metrics_path, "r", encoding="utf-8") as f:
                        verified_metrics = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                    if verified_metrics:
                        sections.append(
                            "=== VERIFIED METRICS (authoritative — use these numbers, not guesses) ===\n"
                            f"These are the ONLY numeric metrics that may be cited as hard facts in {company} bullets.\n"
                            + verified_metrics
                        )
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle: could not load verified_metrics.json: {e}", soft_wrap=True)

        return "\n\n".join(sections)

    def _build_audit_segment_bundle_gemma(self, company: str, tags: str) -> str:
        """Slim segment bundle for Gemma only -- mirrors rewrite_bullets.py's
        KnowledgeBase._build_gemma_segment_bundle() (2026-07-16). cv excerpt
        and background summary are unchanged (already small); claims and,
        for deep-evidence-archive companies, screenshot metrics + verified
        metrics are tag-filtered to MAX_GEMMA_FILTER_ROWS instead of included at the
        looser MAX_CLAIMS_ROWS cap or (screenshots/metrics) unfiltered.
        verified_projects.json, dropped entirely from the Gemma static
        prefix, is added back here tag-filtered rather than as the full
        12-entry file."""
        sections = []

        cv_path = os.path.join(self.kb_dir, "cv.md")
        cv_full = ""
        if os.path.exists(cv_path):
            try:
                with open(cv_path, "r", encoding="utf-8") as f:
                    cv_full = f.read()
            except Exception as e:
                cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load cv.md: {e}", soft_wrap=True)

        cv_section = extract_cv_section(cv_full, company)
        if cv_section:
            label = ("ROLE CONTEXT (cv.md excerpt)"
                     if cv_section != cv_full else "CAREER OVERVIEW (cv.md)")
            sections.append(f"=== {label} ===\n{cv_section}")

        bg_summary = build_background_summary(tags)
        if bg_summary:
            sections.append(f"=== BACKGROUND CONTEXT ===\n{bg_summary}")

        if is_deep_evidence_bullet(company, self.deep_evidence_keywords):
            projects_path = os.path.join(self.kb_dir, "verified_projects.json")
            if os.path.exists(projects_path):
                try:
                    with open(projects_path, "r", encoding="utf-8") as f:
                        projects_entries = json.load(f).get("projects", [])
                    filtered_projects = filter_json_entries_by_tags(projects_entries, tags, MAX_GEMMA_FILTER_ROWS)
                    if filtered_projects:
                        sections.append(
                            "=== VERIFIED PROJECTS (tag-filtered) ===\n"
                            "Use these to add accurate project detail and scope.\n"
                            + json.dumps(filtered_projects, ensure_ascii=False, separators=(",", ":"))
                        )
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load verified_projects.json: {e}", soft_wrap=True)

            claims_path = os.path.join(self.kb_dir, "verified-claims.csv")
            if os.path.exists(claims_path):
                try:
                    df_claims = pd.read_csv(claims_path)
                    if "Use in Resume?" in df_claims.columns:
                        df_claims = df_claims[
                            df_claims["Use in Resume?"].str.strip().str.lower().str.startswith("yes")
                        ]
                    filtered_claims = filter_claims_by_tags(df_claims, tags, max_rows=MAX_GEMMA_FILTER_ROWS)
                    claims_text = get_verified_claims_text(filtered_claims)
                    if claims_text:
                        sections.append(
                            f"=== VERIFIED CLAIMS & METRICS ({company} — resume-usable, tag-filtered) ===\n"
                            "Use these to inject real, verified metrics where appropriate. "
                            "Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                            + claims_text
                        )
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load verified-claims.csv: {e}", soft_wrap=True)

            screenshot_path = os.path.join(self.kb_dir, "extracted-screenshot-metrics.csv")
            if os.path.exists(screenshot_path):
                try:
                    df_screens = pd.read_csv(screenshot_path)
                    filtered_screens = filter_claims_by_tags(df_screens, tags, max_rows=MAX_GEMMA_FILTER_ROWS)
                    screenshot_text = filtered_screens.to_csv(index=False)
                    if screenshot_text:
                        sections.append(f"=== SCREENSHOT-SOURCED METRICS (tag-filtered) ===\n{screenshot_text}")
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load screenshot metrics: {e}", soft_wrap=True)

            metrics_path = os.path.join(self.kb_dir, "verified_metrics.json")
            if os.path.exists(metrics_path):
                try:
                    with open(metrics_path, "r", encoding="utf-8") as f:
                        metrics_entries = json.load(f).get("metrics", [])
                    filtered_metrics = filter_json_entries_by_tags(metrics_entries, tags, MAX_GEMMA_FILTER_ROWS)
                    if filtered_metrics:
                        sections.append(
                            "=== VERIFIED METRICS (authoritative — tag-filtered) ===\n"
                            f"These are the ONLY numeric metrics that may be cited as hard facts in {company} bullets.\n"
                            + json.dumps(filtered_metrics, ensure_ascii=False, separators=(",", ":"))
                        )
                except Exception as e:
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load verified_metrics.json: {e}", soft_wrap=True)

        return "\n\n".join(sections)

    def audit_segment_bundle_for(self, company: str, tags: str) -> str:
        """
        Memoized accessor for _build_audit_segment_bundle (Tier 2), keyed by
        (company, tags) -- mirrors rewrite_bullets.py's context_block_for_bullet()
        so repeated (company, tags) pairs reuse the same bundle string instead of
        rebuilding it (and re-reading cv.md / claims csvs) on every bullet.
        """
        normalized_tags = self._normalize_tags(tags)
        key = (company, normalized_tags)
        if key not in self._segment_cache:
            cli_art.console.print(f"   {theme.colorize_icon('warning')} Cache miss for {key} — building segment on demand.", soft_wrap=True)
            self._segment_cache[key] = self._build_audit_segment_bundle(company, normalized_tags)
        return self._segment_cache[key]

    def audit_segment_bundle_for_gemma(self, company: str, tags: str) -> str:
        """Memoized accessor for _build_audit_segment_bundle_gemma (Tier 2,
        Gemma-slim) -- mirrors rewrite_bullets.py's
        context_block_for_bullet_gemma()."""
        normalized_tags = self._normalize_tags(tags)
        key = (company, normalized_tags)
        if key not in self._gemma_segment_cache:
            cli_art.console.print(f"   {theme.colorize_icon('warning')} Gemma cache miss for {key} — building segment on demand.", soft_wrap=True)
            self._gemma_segment_cache[key] = self._build_audit_segment_bundle_gemma(company, normalized_tags)
        return self._gemma_segment_cache[key]

    @staticmethod
    def _normalize_tags(tags_str: str) -> str:
        """Normalize tag string by sorting individual tags alphabetically.
        '[email][content]' and '[content][email]' both normalize to '[content][email]'."""
        tag_list = re.findall(r'\[([^\]]+)\]', tags_str)
        return ''.join(f'[{tag}]' for tag in sorted(tag_list))

    def warm_segment_cache(self, bullet_tuples: List[Tuple[str, str, str]]) -> None:
        """
        Mirrors rewrite_bullets.py's KnowledgeBase.warm_segment_cache(): pre-builds
        every unique (company, tags) segment bundle before the audit loop starts,
        so audit_segment_bundle_for() is a pure dict lookup with no on-demand file
        I/O mid-loop, and the terminal report shows what's cached upfront.
        """
        self._segment_cache = {}
        self._gemma_segment_cache = {}
        pairs = sorted({(company, self._normalize_tags(tags)) for _, company, tags in bullet_tuples})
        cli_art.console.print(f"\n{theme.colorize_icon('hint')} Warming segment cache for {len(pairs)} unique (company, tags) combos...", soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)
        for company, tags in pairs:
            bundle = self._build_audit_segment_bundle(company, tags)
            self._segment_cache[(company, tags)] = bundle
            gemma_bundle = self._build_audit_segment_bundle_gemma(company, tags)
            self._gemma_segment_cache[(company, tags)] = gemma_bundle
            deep_evidence_flag = " [+claims]" if is_deep_evidence_bullet(company, self.deep_evidence_keywords) else ""
            cli_art.console.print(f"   {theme.colorize_icon('hint')} ({company[:30]!r}, {tags[:40]!r}) → {len(bundle):,} chars{deep_evidence_flag} (Gemma: {len(gemma_bundle):,} chars)", soft_wrap=True)
        cli_art.console.print(f"   {theme.colorize_icon('success')} {len(self._segment_cache)} segment bundles ready.\n", soft_wrap=True)

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
        resume_from: List[str] = None,
        on_bullet_complete=None,
    ) -> List[str]:
        """
        Skeptical Editor audit loop.
        Accepts List[Tuple[str, str, str]] -- (bullet_text, company, tags).
        Critiques on slim static_prefix (Tier 1+2 cache architecture).
        Rewrites get segment bundle prepended (Gap 3) but critiques do not.
        """
        cli_art.console.print(f"\n{theme.colorize_icon('hint')} Loading rules bundle...", soft_wrap=True)
        cli_art.console.print(f"{theme.colorize_icon('hint')} Static prefix (Tier 1): {len(static_prefix):,} chars — shared across ALL bullets", soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)

        if not isinstance(bullet_tuples, list) or len(bullet_tuples) == 0:
            cli_art.console.print("  No bullets to audit -- empty or invalid input. Skipping audit loop.", markup=False, soft_wrap=True)
            return []

        refined_bullets = list(resume_from) if resume_from else []
        if len(refined_bullets) >= len(bullet_tuples):
            cli_art.console.print(f"  Resuming: all {len(bullet_tuples)} bullets already refined in a prior run. "
                  f"Skipping audit loop.", markup=False, soft_wrap=True)
            return refined_bullets

        critique_system = self.build_bullet_critique_system()
        cli_art.console.print(f"   {theme.colorize_icon('success')} Rules loaded: manager_test, believability, style_rules, language_quality, verb_taxonomy, verb_intent_mapping, hard_failures, truthfulness_rules", soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)

        # Gemma-slim Tier 1 -- see build_audit_static_prefix_gemma(). Cheap
        # to build (2 small JSON files + voice-anchors.md), so it's built
        # here rather than threaded through as another caller-supplied
        # parameter the way static_prefix is.
        static_prefix_gemma = self.build_audit_static_prefix_gemma()
        cli_art.console.print(f"{theme.colorize_icon('hint')} Gemma static prefix (slim): {len(static_prefix_gemma):,} chars — Gemma-only, flash-lite keeps the full tier", soft_wrap=True)

        # Load rules needed for rewrite prompt
        verb_intent_mapping = self.load_yaml(self.rules_dir, "verb_intent_mapping.yaml")
        verb_taxonomy       = self.load_yaml(self.rules_dir, "verb_taxonomy.yaml")
        language_quality    = self.load_yaml(self.rules_dir, "language_quality.yaml")
        hard_failures       = self.load_yaml(self.rules_dir, "hard_failures.yaml")
        truthfulness_rules  = self.load_yaml(self.rules_dir, "truthfulness_rules.yaml")
        style_rules         = self.load_yaml(self.rules_dir, "style_rules.yaml")

        # Curated subsets mirror rewrite_bullets.py's RulesBundle exactly
        # (2026-07-16) -- this block used to json.dumps() each YAML file's
        # FULL raw contents, including large sections (verb_taxonomy's
        # complete per-role verb library, language_quality's verb_scoring/
        # manager_test blocks that are only used by the *scoring* prompt
        # elsewhere) never actually referenced by the instruction text
        # immediately above them -- "Use elite > strong > acceptable.
        # NEVER use verbs in the avoid list." only needs priority_tiers +
        # avoid, not the whole ~10KB file. That drift was inflating every
        # rewrite call's token count well past what the prompt's own
        # instructions needed, a real contributor to Gemma's 16k TPM cap
        # getting blown -- not just a cosmetic difference from
        # rewrite_bullets.py.
        verb_taxonomy_curated = {
            "priority_tiers": verb_taxonomy.get("priority_tiers", {}),
            "avoid":          verb_taxonomy.get("avoid", []),
        }
        language_quality_curated = {
            "weak_verbs":           language_quality.get("weak_verbs", {}),
            "buzzwords":            language_quality.get("buzzwords", {}),
            "ai_language_patterns": language_quality.get("ai_language_patterns", {}),
            "specificity_checks":   language_quality.get("specificity_checks", {}),
            "final_principle":      language_quality.get("final_principle", ""),
        }

        def _rewrite_block(verb_intent_data: dict, style_data: dict, style_heading: str) -> str:
            return "\n".join([
                "=== VERB INTENT MAP ===",
                "Before choosing a verb, identify the accomplishment intent and select from the matching preferred_verbs list below.",
                json.dumps(verb_intent_data),
                "",
                "=== VERB TAXONOMY (priority tiers) ===",
                "Use elite > strong > acceptable. NEVER use verbs in the avoid list.",
                json.dumps(verb_taxonomy_curated),
                "",
                "=== LANGUAGE QUALITY RULES ===",
                "Flag and replace any weak verbs, buzzwords, or AI-pattern phrases listed below.",
                json.dumps(language_quality_curated),
                "",
                "=== HARD FAILURE CONDITIONS ===",
                "Any bullet triggering one of these conditions must be rewritten — do NOT pass it:",
                json.dumps(hard_failures),
                "",
                "=== TRUTHFULNESS RULES ===",
                "Apply these four tests before finalising any bullet:",
                json.dumps(truthfulness_rules),
                "",
                style_heading,
                json.dumps(style_data),
            ])

        rewrite_rules_block = _rewrite_block(verb_intent_mapping, style_rules, "=== STYLE RULES ===")

        # Gemma-slim variant -- mirrors rewrite_bullets.py's
        # rewrite_rules_block_gemma (2026-07-16): gemma-4-31b-it's 16k TPM
        # cap leaves little headroom once the KB context is added, so this
        # additionally drops (a) document-layout style_rules content
        # (typography/page layout/tagline/skills-section/ATS formatting),
        # a no-op for rewriting one bullet's text regardless of model, and
        # (b) verb_intent_mapping's per-category prose (description +
        # weak/strong examples), which restates what VERB TAXONOMY's
        # elite/strong tiers already cover structurally. Truthfulness/
        # anti-fabrication content (HARD FAILURE CONDITIONS, TRUTHFULNESS
        # RULES) is byte-identical between variants -- never a candidate
        # for trimming.
        def _rule_text(item) -> str:
            # Guards a real YAML quirk in style_rules.yaml: a couple of
            # list entries contain an unintended colon (e.g. "Recommended
            # verbs: Architected, ..."), which YAML parses as a
            # {key: value} dict instead of a plain string like their
            # neighbors.
            if isinstance(item, dict):
                return next(iter(item.keys()), "")
            return str(item)

        gemma_verb_intent = {
            "intent_categories": {
                intent: {
                    "signals":         data.get("signals", []),
                    "preferred_verbs": data.get("preferred_verbs", {}),
                }
                for intent, data in verb_intent_mapping.get("intent_categories", {}).items()
            },
            "selection_rules":   verb_intent_mapping.get("selection_rules", {}),
            "verb_replacements": verb_intent_mapping.get("verb_replacements", {}),
            "final_principle":   verb_intent_mapping.get("final_principle", ""),
        }
        gemma_style_rules = {
            "philosophy": [
                p for p in style_rules.get("philosophy", [])
                if any(kw in _rule_text(p).lower() for kw in ("bullet", "metric", "verb", "cares test", "systems not tasks"))
            ],
            "writing_style":      style_rules.get("writing_style", {}),
            "bullet_structure":   style_rules.get("bullet_structure", {}),
            "verb_rules":         [r for r in style_rules.get("verb_rules", []) if not _rule_text(r).startswith("Recommended verbs")],
            "vague_verbs":        style_rules.get("vague_verbs", []),
            "forbidden_openers":  style_rules.get("forbidden_openers", []),
            "forbidden_phrases":  style_rules.get("forbidden_phrases", []),
            "punctuation_rules":  style_rules.get("punctuation_rules", []),
            "metrics_rules":      style_rules.get("metrics_rules", {}),
            "tool_mention_rules": style_rules.get("tool_mention_rules", {}),
            "redundancy_rules":   style_rules.get("redundancy_rules", {}),
        }
        rewrite_rules_block_gemma = _rewrite_block(
            gemma_verb_intent, gemma_style_rules, "=== STYLE RULES (bullet-level subset) ==="
        )

        # FIX: use .replace() instead of .format() to avoid ValueError when
        # rules YAML content contains literal curly braces { } (e.g. JSON examples).
        rewrite_system       = REWRITE_SYSTEM_BASE.replace("{rules_block}", rewrite_rules_block)
        rewrite_system_gemma = REWRITE_SYSTEM_BASE.replace("{rules_block}", rewrite_rules_block_gemma)

        cli_art.console.print(f"{theme.colorize_icon('hint')} Rewrite rules block:   {len(rewrite_rules_block):,} chars", soft_wrap=True)
        cli_art.console.print(f"{theme.colorize_icon('hint')} Gemma rules block (slim): {len(rewrite_rules_block_gemma):,} chars", soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)
        cli_art.console.print(f"{theme.colorize_icon('hint')}  Rewrite system prompt: {len(rewrite_system):,} chars (stable across ALL calls)", soft_wrap=True)
        cli_art.console.print(f"{theme.colorize_icon('hint')}  Gemma rewrite system prompt (slim): {len(rewrite_system_gemma):,} chars", soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)
        cli_art.console.print(f"{theme.colorize_icon('hint')} Score system prompt:   {len(critique_system):,} chars", soft_wrap=True)

        self.warm_segment_cache(bullet_tuples)

        # Track critique data parallel to refined_bullets (same length, same
        # order, always appended -- including None entries) so no bullet can
        # be silently dropped when sorting below. A None entry sorts last via
        # _bullet_sort_key({}) (worst manager_test tier, 0 believability).
        bullet_critique_list = []  # List[Optional[dict]], parallel to refined_bullets

        start_index = len(refined_bullets)
        if start_index:
            cli_art.console.print(f"  Resuming audit loop at bullet {start_index + 1}/{len(bullet_tuples)} "
                  f"(already refined: {start_index}).", markup=False, soft_wrap=True)

        def _record(refined_bullet: str, critique_data: dict = None) -> None:
            refined_bullets.append(refined_bullet)
            bullet_critique_list.append(critique_data)
            if on_bullet_complete:
                on_bullet_complete(list(refined_bullets))

        for i, (bullet, company, tags) in enumerate(bullet_tuples):
            if i < start_index:
                continue

            bullet_preview = bullet[:60]
            cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
            cli_art.console.print(f"[{i+1}/{len(bullet_tuples)}] {bullet_preview}...", markup=False, soft_wrap=True)
            cli_art.console.print(f"   Tags: {tags}  |  Company: {company}", markup=False, soft_wrap=True)
            cli_art.console.print(markup=False, soft_wrap=True)

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
                    _record(bullet, None)
                    continue

                critique_data = GeminiClient.parse_json(critique_text)

                gem_score  = critique_data.get("hidden_gem_score", 0)
                gem_flag   = critique_data.get("hidden_gem_flag", False)
                gem_reason = critique_data.get("hidden_gem_reason", "")
                if gem_flag:
                    cli_art.console.print(f"   {theme.colorize_icon('success')} GEM: Hidden Gem! score={gem_score} — {gem_reason}", soft_wrap=True)
                elif gem_score >= 75:
                    cli_art.console.print(f"   {theme.colorize_icon('success')} STRONG: gem_score={gem_score} — {gem_reason}", soft_wrap=True)

                if (critique_data.get("manager_test") == "FAIL" or
                        critique_data.get("believability_score", 100) < 80):
                    cli_art.console.print(f"   {theme.colorize_icon('hint')}  Rewriting with {REWRITE_MODEL}...", soft_wrap=True)
                    time.sleep(REWRITE_SLEEP)

                    segment_bundle       = self.audit_segment_bundle_for(company, tags)
                    segment_bundle_gemma = self.audit_segment_bundle_for_gemma(company, tags)
                    if segment_bundle:
                        cli_art.console.print(f"   {theme.colorize_icon('hint')} segment bundle (Tier 2): {len(segment_bundle):,} chars (Gemma: {len(segment_bundle_gemma):,} chars)", soft_wrap=True)

                    active_rewrite_model   = REWRITE_MODEL
                    rewrite_parse_failures = 0
                    rewritten_bullet       = bullet

                    for rw_attempt in range(MAX_REWRITE_PARSE_FAILURES + 1):
                        is_gemma_attempt = "gemma" in active_rewrite_model.lower()
                        use_minimal      = GEMMA_MINIMAL_JSON and is_gemma_attempt
                        runner_schema    = RewriteMinimalSchema if use_minimal else RewriteSchema
                        active_rewrite_system = rewrite_system_gemma if is_gemma_attempt else rewrite_system

                        # Tier 1 + Tier 2 -> kb_context. build_rewrite_prompt() appends
                        # the Tier 3 tail (persona + weaknesses + bullet + JSON reminder),
                        # exactly like rewrite_bullets.py's process_bullet() does. Gemma
                        # gets the slim static prefix + slim segment bundle (2026-07-16
                        # fix for its 16k TPM cap); flash-lite keeps the full tier.
                        active_static_prefix = static_prefix_gemma if is_gemma_attempt else static_prefix
                        active_segment_bundle = segment_bundle_gemma if is_gemma_attempt else segment_bundle
                        context_block = (
                            f"{active_static_prefix}\n{active_segment_bundle}"
                            if active_segment_bundle else active_static_prefix
                        )

                        rewrite_contents = build_rewrite_prompt(
                            bullet=bullet,
                            tags=tags,
                            weaknesses=critique_data.get("weaknesses", ""),
                            kb_context=context_block,
                            minimal_schema=use_minimal,
                        )

                        try:
                            # model_fallback=False: active_rewrite_system was just
                            # picked to match active_rewrite_model (slim for Gemma,
                            # full for flash-lite). GeminiClient's own internal
                            # fallback swaps models mid-call without knowing which
                            # system_instruction was sent -- an internal swap here
                            # would hand the wrong-sized context to whichever model
                            # actually ends up serving the request. The explicit
                            # rewrite_parse_failures handoff below is the only path
                            # allowed to switch models for this call. Matches
                            # rewrite_bullets.py's process_bullet() exactly.
                            rewrite_text, rw_usage = GeminiClient.generate(
                                model=active_rewrite_model,
                                system_instruction=active_rewrite_system,
                                contents=rewrite_contents,
                                response_schema=runner_schema,
                                temperature=0.7,
                                max_output_tokens=REWRITE_MAX_OUTPUT_TOKENS,
                                model_fallback=False,
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
                                cli_art.console.print(f"   {theme.colorize_icon('success')} ACCEPTED rewrite (composite {rewrite_composite:.0f} >= {original_composite:.0f})", soft_wrap=True)
                                # Use the rescore data for the rewritten bullet
                                critique_to_record = rescore_data
                                try:
                                    if bullet_feedback.queue_accepted_rewrite(
                                        bullet, rewritten_bullet, company, tags, critique_to_record
                                    ):
                                        cli_art.console.print(f"   {theme.colorize_icon('hint')} Queued for bank review (needs-review.csv)", soft_wrap=True)
                                except Exception as feedback_err:
                                    cli_art.console.print(f"   {theme.colorize_icon('warning')}  Could not queue bullet for bank review: {feedback_err}", soft_wrap=True)
                            else:
                                rewritten_bullet = bullet
                                cli_art.console.print(f"   {theme.colorize_icon('hint')} KEPT original (composite {original_composite:.0f} > {rewrite_composite:.0f})", soft_wrap=True)
                                # Use the original critique data
                                critique_to_record = critique_data
                            break

                        except Exception as rw_err:
                            rewrite_parse_failures += 1
                            cli_art.console.print(f"   {theme.colorize_icon('warning')}  Rewrite parse error (attempt {rw_attempt+1}): {rw_err}", soft_wrap=True)
                            if (rewrite_parse_failures >= MAX_REWRITE_PARSE_FAILURES
                                    and active_rewrite_model != REWRITE_FALLBACK_MODEL):
                                cli_art.console.print(f"   {theme.colorize_icon('warning')} FALLBACK: Switching rewrite to {REWRITE_FALLBACK_MODEL}", soft_wrap=True)
                                active_rewrite_model = REWRITE_FALLBACK_MODEL
                            time.sleep(REWRITE_SLEEP)

                    _record(rewritten_bullet, critique_to_record)
                else:
                    _record(bullet, critique_data)

            except Exception as e:
                cli_art.console.print(f"   {theme.colorize_icon('warning')}  Critique error on bullet {i+1}: {e}", soft_wrap=True)
                _record(bullet, None)

        cli_art.console.print(f"\n{'='*60}", markup=False, soft_wrap=True)
        cli_art.console.print(f"{theme.colorize_icon('success')} Audit complete: {len(refined_bullets)} bullets refined", soft_wrap=True)

        # Sort bullets deterministically by manager_test and believability_score.
        # Only apply sorting to bullets processed in this run (not resumed bullets).
        # Every bullet in refined_bullets is paired with its critique (or None,
        # which sorts last) so no bullet is ever dropped by this step.
        if start_index == 0 and refined_bullets:
            paired = list(zip(refined_bullets, bullet_critique_list))
            sorted_pairs = sorted(paired, key=lambda pair: _bullet_sort_key(pair[1] or {}))
            refined_bullets = [bullet for bullet, critique in sorted_pairs]

        return refined_bullets

    def mine_bullet_bank(
        self,
        jd_text: str,
        master_resume: dict,
        extra_company_minimums: dict = None,
    ) -> List[Tuple[str, str, str]]:
        """
        Semantic + gem-aware retrieval from bullet-bank-keepers-audited.csv, with
        a per-company floor so no target company is starved of material.

        Returns List[Tuple[str, str, str]] -- (bullet_text, company, tags) --
        so audit_and_refine_bullets() can build per-bullet segment bundles (Gap 3).

        1. Embed JD, compute cosine similarity against the whole pre-embedded bank.
        2. Rank the whole bank by gem-boosted similarity, then strength_category tier.
        3. Guarantee each company in profile.yml's roles: (min_bullets) its
           minimum from within its own bullets (ranked the same way) -- a pure global top-K let one
           company's high-scoring bullets crowd out every other company entirely
           (a real run mined 0 Mercor and 0 Callahan Creek bullets out of 30).
        4. Fill the remaining TOP_K_BULLETS - guaranteed slots from the overall
           ranking, skipping bullets already guaranteed.
        Both 3 and 4 skip any candidate whose embedding is a near-duplicate
        (DEDUP_SIMILARITY_THRESHOLD) of a bullet already selected -- the bank
        stores several reworded variants of some achievements, and without
        this a company's guaranteed minimum could fill entirely with
        near-identical bullets about the same underlying achievement.
        """
        cli_art.console.print("\nMining bullet bank...", markup=False, soft_wrap=True)
        bank_csv  = os.path.join(self.kb_dir, "bullet-bank-keepers-audited.csv")
        emb_npy   = os.path.join(self.kb_dir, "bullet_vectors_ge2_d768.npy")
        emb_meta  = os.path.join(self.kb_dir, "bullet_vectors_ge2_d768.meta")

        if not os.path.exists(bank_csv):
            cli_art.console.print("  WARNING: bullet-bank-keepers-audited.csv not found. Skipping mine.", markup=False, soft_wrap=True)
            return []
        if not os.path.exists(emb_npy):
            cli_art.console.print("  WARNING: bullet_vectors_ge2_d768.npy not found. Run embed_bullet_bank.py first. Skipping mine.", markup=False, soft_wrap=True)
            return []

        try:
            df   = pd.read_csv(bank_csv)
            embs = np.load(emb_npy)
        except Exception as e:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} Could not load bullet bank: {e}", soft_wrap=True)
            return []

        if "Bullet Point" not in df.columns:
            cli_art.console.print("  WARNING: 'Bullet Point' column not found in bullet bank CSV.", markup=False, soft_wrap=True)
            return []

        if len(df) != len(embs):
            cli_art.console.print(f"  {theme.colorize_icon('warning')} Row count mismatch -- CSV {len(df)} rows vs embeddings {len(embs)} rows. Skipping mine.", soft_wrap=True)
            return []

        # H26/B20 (phase-9-backlog.md): the row-count check above can't catch
        # a same-length bank whose content silently changed since embedding
        # (e.g. a bullet edited during a rate-limit pause) -- only a content
        # hash can. embed_bullet_bank.py writes this same hash into the
        # .meta sidecar it's always written alongside the .npy; enforced
        # here at read time, not only at write time, since a stale .npy
        # from before this check existed is exactly the case it must catch.
        try:
            with open(emb_meta, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception as e:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} Could not read {emb_meta}: {e}. Skipping mine.", soft_wrap=True)
            return []
        current_sha = bullets_sha(df["Bullet Point"].fillna("").tolist())
        if meta.get("bullets_sha") != current_sha:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} bullet_vectors_ge2_d768.npy is stale (bullet bank content "
                  "changed since it was built) -- run embed_bullet_bank.py again. Skipping mine.", soft_wrap=True)
            return []

        jd_emb = GeminiClient.embed(jd_text[:8000])
        if jd_emb is None:
            cli_art.console.print("  WARNING: JD embedding failed. Falling back to first TOP_K_BULLETS rows.", markup=False, soft_wrap=True)
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

        if "hidden_gem_score" in df.columns:
            gem_scores = pd.to_numeric(df["hidden_gem_score"], errors="coerce").fillna(0).values
            boosted    = sims + GEM_BOOST_WEIGHT * gem_scores
        else:
            boosted    = sims

        if "strength_category" in df.columns:
            tier_rank = df["strength_category"].map(STRENGTH_ORDER).fillna(99).values
        else:
            tier_rank = np.zeros(len(df))

        # Full-bank ranking, best first: lower tier_rank wins, then higher boosted score.
        ranked_idx = np.lexsort((-boosted, tier_rank))

        selected_idx: list = []
        selected_set: set = set()
        guaranteed_count = 0

        def _is_near_duplicate(idx: int) -> bool:
            if not selected_idx:
                return False
            return bool((embs_norm[selected_idx] @ embs_norm[idx]).max() >= DEDUP_SIMILARITY_THRESHOLD)

        if "Role / Company" in df.columns:
            company_values = df["Role / Company"].values
            profile_roles = self.load_yaml(self.kb_dir, "profile.yml").get("roles") or []
            company_min_bullets = {
                r["name"]: r["min_bullets"] for r in profile_roles if "min_bullets" in r
            }
            combined_minimums = {**company_min_bullets, **(extra_company_minimums or {})}
            for company, min_count in combined_minimums.items():
                company_ranked = [int(i) for i in ranked_idx if company_values[i] == company]
                taken = 0
                for i in company_ranked:
                    if taken >= min_count:
                        break
                    if i in selected_set or _is_near_duplicate(i):
                        continue
                    selected_idx.append(i)
                    selected_set.add(i)
                    guaranteed_count += 1
                    taken += 1

        for i in ranked_idx:
            if len(selected_idx) >= TOP_K_BULLETS:
                break
            i = int(i)
            if i in selected_set or _is_near_duplicate(i):
                continue
            selected_idx.append(i)
            selected_set.add(i)

        top_df      = df.iloc[selected_idx]
        bullets_out = top_df["Bullet Point"].fillna("").tolist()
        company_out = top_df["Role / Company"].fillna("").tolist() if "Role / Company" in top_df.columns else ["" ] * len(top_df)
        tags_out    = top_df["Tags"].fillna("").tolist()            if "Tags"           in top_df.columns else ["" ] * len(top_df)

        cli_art.console.print(f"  Mined {len(bullets_out)} bullets from bank "
              f"({guaranteed_count} from guaranteed per-company minimums, top_k={TOP_K_BULLETS}).", markup=False, soft_wrap=True)
        return list(zip(bullets_out, company_out, tags_out))

    def build_fit_evaluation_context(self, jd_text: str) -> str:
        """
        Builds evaluate_fit()'s user-content block: the candidate first, then
        the JD.

        This exists because evaluate_fit.md tells the model to consult
        "target_roles and archetypes ... in your knowledge base context" and
        for the entire life of the tool no such context was ever constructed
        -- the call was the JD alone. A fit score computed against no
        candidate isn't a weak fit score, it's a summary of the posting, and
        those scores rank the whole Browse & Manage queue. Symptom: the
        evaluator would write confidently about experience the JD had merely
        asserted it wanted.

        Two blocks, both cheap:
          - profile.yml, trimmed to the identity sections, so "does this
            candidate fit" has a candidate.
          - role_dna.yaml, so the returned `archetype` is drawn from the
            project's own controlled vocabulary rather than freeformed. It is
            the archetype library and, per the review, is loaded by nothing
            else today.

        Both are optional: a freshly-bootstrapped profile with neither still
        evaluates, just without the corresponding block, matching how
        build_role_rules_block() degrades.
        """
        sections = []

        profile_path = os.path.join(self.kb_dir, "profile.yml")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    trimmed = _trim_profile_yaml(f.read())
                if trimmed:
                    sections.append(
                        "=== CANDIDATE PROFILE (from profile.yml) ===\n"
                        "This is the candidate you are scoring the job against. "
                        "The target_roles and archetypes referenced by your "
                        "instructions are here.\n" + trimmed
                    )
            except Exception as e:
                cli_art.console.print(f"  {theme.colorize_icon('warning')} evaluate_fit: could not load profile.yml: {e}", soft_wrap=True)

        try:
            role_dna = self.load_yaml(self.scoring_dir, "role_dna.yaml")
            if role_dna:
                sections.append(
                    "=== ROLE ARCHETYPE LIBRARY (from role_dna.yaml) ===\n"
                    "Choose the returned `archetype` from these keys. Do not invent one.\n"
                    + json.dumps(role_dna)
                )
        except Exception as e:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} evaluate_fit: could not load role_dna.yaml: {e}", soft_wrap=True)

        if not sections:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} evaluate_fit: no candidate profile "
                  "or archetype library found -- scoring the JD in isolation.", soft_wrap=True)

        sections.append(f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===")
        return "\n\n".join(sections)

    def evaluate_fit(self, jd_path: str) -> dict:
        """
        Standalone go/no-go fit check for a JD -- independent of the tailor+
        render pipeline (no checkpoint, no output files, no applications.md
        write). Ports career-ops's weighted-match rubric (see
        prompts/evaluate_fit.md); returns {} if the JD can't be read or the
        model call fails to parse.
        """
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            cli_art.console.print(f"  {theme.colorize_icon('error')} JD file not found: {jd_path}", soft_wrap=True)
            return {}

        eval_prompt = self.load_prompt("evaluate_fit.md")
        eval_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=eval_prompt,
            contents=self.build_fit_evaluation_context(jd_text),
            response_schema=FitEvaluationSchema,
            temperature=0.0,
        )
        evaluation = GeminiClient.parse_json(eval_text or "")
        if not evaluation:
            cli_art.console.print("  ERROR: Fit evaluation returned no parseable result.", markup=False, soft_wrap=True)
            return {}

        posting_age_days = jd_manager.compute_posting_age_days(jd_path)
        fit_score = compute_fit_score(evaluation.get("fit_subscores", {}))
        interview_odds_score = compute_interview_odds_score(evaluation.get("interview_odds_subscores", {}))
        practical_pursue_score = compute_practical_pursue_score(evaluation.get("practical_pursue_subscores", {}))

        evaluation["posting_age_days"] = posting_age_days
        evaluation["fit_score"] = fit_score
        evaluation["interview_odds_score"] = interview_odds_score
        evaluation["practical_pursue_score"] = practical_pursue_score
        evaluation["composite_score"] = fit_composite_score(
            fit_score, interview_odds_score, practical_pursue_score, posting_age_days,
        )
        return evaluation

    def research_company(self, jd_data: dict) -> dict | None:
        """
        Fetches a company's About/Mission/Careers pages (if a
        company_website is known in jd_data, or found via a Google Search
        grounding fallback lookup keyed on company_name) and extracts tone
        signals + traceable facts via one Gemini call. Returns None (with a
        printed, non-alarming notice) if no website is known or findable,
        pages are unreachable/too thin, or the model response can't be
        parsed -- callers must treat None as "proceed exactly as if this
        feature didn't exist." See
        docs/superpowers/specs/2026-07-04-company-research-design.md.
        """
        company_website = jd_data.get("company_website")
        if not company_website:
            company_website = company_research.find_company_website(jd_data.get("company_name"))
            if company_website:
                cli_art.console.print(f"  ℹ️  No company website on file -- found one via search: {company_website}", markup=False, soft_wrap=True)
        if not company_website:
            cli_art.console.print("  ℹ️  Company research skipped: no company website known for this JD.", markup=False, soft_wrap=True)
            return None

        scraped_text = company_research.fetch_company_pages(company_website)
        if len(scraped_text) < company_research.MIN_USEFUL_CHARS:
            cli_art.console.print(f"  ℹ️  Company research skipped: couldn't find enough usable content on {company_website}.", markup=False, soft_wrap=True)
            return None

        research_prompt = self.load_prompt("research_company.md")
        research_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=research_prompt,
            contents=f"=== SCRAPED COMPANY PAGE TEXT ===\n{scraped_text}",
            response_schema=CompanyResearchSchema,
            temperature=0.0,
        )
        research_data = GeminiClient.parse_json(research_text or "")
        if not research_data:
            cli_art.console.print("  ℹ️  Company research skipped: model response couldn't be parsed.", markup=False, soft_wrap=True)
            return None

        cli_art.console.print(f"  {theme.colorize_icon('success')} Company research complete for {company_website}.", soft_wrap=True)
        return research_data

    def draft_outreach_message(self, jd_path: str, contact: dict) -> str | None:
        """
        Drafts a short, specific outreach message to a real contact
        already surfaced by find_jd_contacts() -- never invents a person;
        contact must already be one JobRight's own scrape (or a personal
        connection) confirmed exists. Returns None if the JD can't be
        read or the model call fails to return anything.
        """
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            return None

        contact_block = (
            f"Name: {contact.get('name', '')}\n"
            f"Title: {contact.get('title', '')}\n"
            f"Company: {contact.get('company', '')}\n"
            f"Connection type: {contact.get('connection_type', '')}"
        )
        prompt = self.load_prompt("draft_outreach.md")
        text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=prompt,
            contents=f"=== CONTACT ===\n{contact_block}\n\n=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===",
            temperature=0.3,
        )
        return text.strip() if text else None

    def draft_followup_message(self, jd_path: str, follow_up_count: int, contact: dict = None) -> str | None:
        """
        Drafts a short, specific follow-up message for an application
        genuinely due for one -- callers gate on
        followup.compute_urgency() being "overdue" (never "waiting" or
        "cold") before calling this; it doesn't re-derive urgency itself.
        follow_up_count is _application's existing count (0 before the
        first follow-up, 1 before the second) -- career-ops's original
        mode never drafts a third, so neither does this; that's a caller-
        side gate, not something enforced here.

        Grounded in cv.md only, not the full knowledge base -- a 2-4
        sentence follow-up doesn't need ~250k tokens of context, and
        cv.md is already the distilled, curated summary of real,
        traceable achievements the prompt is told to draw its one proof
        point from. contact is optional (unlike draft_outreach_message(),
        which requires one) -- career-ops's own spec drafts a generic-
        address email when no contact is known, it just doesn't skip
        the follow-up entirely. Returns None if the JD can't be read or
        the model call fails to return anything.
        """
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            return None

        cv_path = os.path.join(self.kb_dir, "cv.md")
        cv_text = ""
        if os.path.exists(cv_path):
            with open(cv_path, "r", encoding="utf-8") as f:
                cv_text = f.read()

        if contact:
            contact_block = (
                f"Name: {contact.get('name', '')}\n"
                f"Title: {contact.get('title', '')}\n"
                f"Connection type: {contact.get('connection_type', '')}"
            )
        else:
            contact_block = "No specific contact known -- address generically (e.g. the hiring team)."

        prompt = self.load_prompt("draft_followup.md")
        contents = (
            f"=== FOLLOW-UP NUMBER ===\n{follow_up_count + 1}\n\n"
            f"=== CONTACT ===\n{contact_block}\n\n"
            f"=== CANDIDATE BACKGROUND (cv.md) ===\n{cv_text}\n\n"
            f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ==="
        )
        text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=prompt,
            contents=contents,
            temperature=0.3,
        )
        return text.strip() if text else None

    def build_tailored_coverletter(self, jd_path: str) -> dict:
        """
        Standalone cover letter generation -- independent of
        build_tailored_resume (no checkpoint, no resume required to exist
        first, no page-fit trim loop -- a cover letter has none of the
        resume's page-count constraints). One Gemini call, validated by
        validate_coverletter.py, with one automatic retry on violations.
        Folds in company research (see
        docs/superpowers/specs/2026-07-04-company-research-design.md) when
        available; falls back to the original, pre-research behavior
        otherwise. Returns the filled cover letter dict plus _output_paths
        (json/html/pdf), or {} on failure.
        """
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            cli_art.console.print(f"  {theme.colorize_icon('error')} JD file not found: {jd_path}", soft_wrap=True)
            return {}

        jd_data = _parse_jd_data(jd_text)
        research = self.research_company(jd_data)
        research_block = format_company_research_block(research) if research else ""

        coverletter_prompt = self.load_prompt("tailor_coverletter.md")
        background_context = self.build_audit_static_prefix(include_evidence_guide=True)
        system_instruction = f"{coverletter_prompt}\n\n{background_context}{research_block}"

        letter_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=system_instruction,
            contents=f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===",
            response_schema=CoverLetterSchema,
            temperature=0.0,
        )
        letter_data = GeminiClient.parse_json(letter_text or "")
        if not letter_data:
            cli_art.console.print("  ERROR: Cover letter generation returned no parseable result.", markup=False, soft_wrap=True)
            return {}

        style_rules = self.load_yaml(self.rules_dir, "style_rules.yaml")
        # kb_corpus=background_context: the same grounding corpus the model
        # was given in system_instruction, re-used here so validate() can
        # check that specific factual claims (metrics, years-of-experience,
        # date ranges) in the letter actually trace back to it -- see B14.
        violations = validate_coverletter.validate(letter_data, style_rules, kb_corpus=background_context)

        if violations:
            cli_art.console.print(f"  Validator found {len(violations)} issue(s), retrying once:", markup=False, soft_wrap=True)
            for v in violations:
                cli_art.console.print(f"    - {v}", markup=False, soft_wrap=True)
            fix_contents = (
                f"=== ORIGINAL COVER LETTER JSON ===\n{json.dumps(letter_data, indent=2)}\n\n"
                f"=== ISSUES TO FIX (change nothing else) ===\n" + "\n".join(f"- {v}" for v in violations)
            )
            fix_text, _ = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=system_instruction,
                contents=fix_contents,
                response_schema=CoverLetterSchema,
                temperature=0.0,
            )
            fixed_data = GeminiClient.parse_json(fix_text or "")
            if fixed_data:
                letter_data = fixed_data
                violations = validate_coverletter.validate(letter_data, style_rules, kb_corpus=background_context)
            if violations:
                cli_art.console.print(f"  {theme.colorize_icon('warning')} {len(violations)} issue(s) remain after retry, proceeding anyway:", soft_wrap=True)
                for v in violations:
                    cli_art.console.print(f"    - {v}", markup=False, soft_wrap=True)

        stem     = _build_output_stem(jd_path)
        json_out = os.path.join(self.output_json_dir, f"{stem}_CoverLetter.json")
        html_out = os.path.join(self.output_html_dir, f"{stem}_CoverLetter.html")
        pdf_out  = os.path.join(self.output_pdf_dir,  f"{stem}_CoverLetter.pdf")

        os.makedirs(os.path.dirname(json_out), exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(letter_data, f, indent=2, ensure_ascii=False)
        cli_art.console.print(f"  Cover letter saved to: {json_out}", markup=False, soft_wrap=True)

        render_coverletter(letter_data, html_out)

        pdf_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")
        try:
            pdf_result = subprocess.run(
                ["node", pdf_script, html_out, pdf_out, "--format=letter"],
                capture_output=True, text=True, timeout=PDF_GENERATION_TIMEOUT_SECONDS,
                env={**os.environ, "RESUME_BUILDER_ICONS": theme.icon_set_name()},
            )
        except subprocess.TimeoutExpired:
            cli_art.console.print(f"  {theme.colorize_icon('warning')}  PDF generation timed out after "
                  f"{PDF_GENERATION_TIMEOUT_SECONDS}s.", soft_wrap=True)
            return {}
        if pdf_result.returncode != 0:
            cli_art.console.print(f"  {theme.colorize_icon('warning')}  PDF generation failed:\n{pdf_result.stderr}", soft_wrap=True)
            return {}
        cli_art.console.print(pdf_result.stdout, markup=False, soft_wrap=True)

        cl_text_warnings = validate_pdf_text.validate_coverletter_pdf_text(pdf_out, letter_data)
        if cl_text_warnings:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} Cover-letter PDF text-layer check found "
                  f"{len(cl_text_warnings)} potential issue(s) (what an ATS would actually parse "
                  f"from the file, not just the pre-render JSON):", soft_wrap=True)
            for w in cl_text_warnings:
                cli_art.console.print(f"    - {w}", markup=False, soft_wrap=True)

        letter_data["_output_paths"] = {"json": json_out, "html": html_out, "pdf": pdf_out}
        cli_art.console.print(f"  {theme.colorize_icon('success')} Cover letter complete! PDF → {pdf_out}", soft_wrap=True)
        return letter_data

    def build_tailored_resume(
        self,
        jd_path: str,
        master_resume: dict,
        output_filename: str = None,
        job_key: str = None,
        interactive: bool = False,
    ) -> dict | None:
        """
        Full pipeline: JD -> keywords -> mine bullets -> audit -> build -> critique.

        interactive=True (single-file `resume run <path>` only -- never batch mode,
        `resume sample`, or tests) gates Step 5.5's critique-driven recommendations
        behind an explicit per-recommendation y/n before any of them are applied,
        so gap-filling content never lands in the resume without approval. Approval
        choices are checkpointed so a resumed run doesn't re-prompt.

        Gap 1 fix: kb_context is placed in builder_system (system_instruction)
        rather than combined_contents. The full ~457k-token KB now forms a
        stable, cacheable system prefix. Only variable content (JD keywords,
        JD text, master resume JSON, refined bullets) sits in combined_contents,
        so Google can cache-hit the KB prefix on every builder call regardless
        of JD changes.
        """
        cli_art.console.print(f"\nBuilding tailored resume for: {jd_path}", markup=False, soft_wrap=True)

        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            cli_art.console.print(f"  {theme.colorize_icon('error')} JD file not found: {jd_path}", soft_wrap=True)
            return {}

        situational_candidates = situational_roles.detect_situational_candidates(jd_text)
        if situational_candidates:
            cli_art.console.print(f"  Situational role candidate(s) cleared the keyword gate: {', '.join(situational_candidates)}", markup=False, soft_wrap=True)

        if job_key is None:
            job_key = jd_manager.compute_job_key(jd_path)
        checkpoint = jd_manager.load_checkpoint(job_key)

        if output_filename is None:
            output_filename = f"{_build_output_stem(jd_path)}_Resume.json"

        # --- Step 1: Extract JD keywords ---
        cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
        cli_art.console.print("Step 1: Extracting JD keywords...", markup=False, soft_wrap=True)
        jd_keywords = checkpoint.get("jd_keywords")
        if jd_keywords is not None:
            cli_art.console.print("  Resuming: using JD keywords from checkpoint.", markup=False, soft_wrap=True)
        else:
            extract_prompt = self.load_prompt("extract_keywords.md")
            keyword_text, _ = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=extract_prompt,
                contents=f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===",
                response_schema=JDKeywordSchema,
                temperature=0.0,
            )
            jd_keywords = GeminiClient.parse_json(keyword_text or "")
            if not jd_keywords:
                # Stop here, deliberately. Empty keyword extraction is a strong,
                # already-paid-for signal that this file isn't a job description
                # -- and the very next step is a 30-bullet Gemma audit gated at
                # GEMMA_MIN_INTERVAL_SECS, i.e. half an hour of wall clock and
                # real spend before anything JD-specific happens. Pointing the
                # tool at the wrong file is an ordinary mistake; it shouldn't
                # cost that. Interactive callers may override; batch marks the
                # JD failed and moves to the next one.
                cli_art.console.print(f"  {theme.colorize_icon('error')} JD keyword extraction returned nothing.", soft_wrap=True)
                cli_art.console.print("    This usually means the file isn't a job description "
                      "(wrong path, an empty export, or a login/error page saved as text).", markup=False, soft_wrap=True)
                if not (interactive and _confirm_continue_without_keywords()):
                    cli_art.console.print("    Stopping before the bullet audit. Nothing was spent on this file beyond Step 1.", markup=False, soft_wrap=True)
                    return None
                cli_art.console.print("    Continuing at your request, with empty keywords.", markup=False, soft_wrap=True)
            checkpoint["jd_keywords"] = jd_keywords
            jd_manager.save_checkpoint(job_key, checkpoint)
        cli_art.console.print(f"  Keywords extracted: {_summarize_keywords(jd_keywords)}", markup=False, soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)

        # --- Step 2: Mine bullet bank ---
        cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
        cli_art.console.print("Step 2: Mining bullet bank...", markup=False, soft_wrap=True)
        bullet_tuples = checkpoint.get("bullet_tuples")
        if bullet_tuples is not None:
            cli_art.console.print(f"  Resuming: using {len(bullet_tuples)} bullet tuples from checkpoint.", markup=False, soft_wrap=True)
        else:
            bullet_tuples = self.mine_bullet_bank(
                jd_text, master_resume,
                extra_company_minimums=situational_roles.bank_minimums_for(situational_candidates),
            )
            checkpoint["bullet_tuples"] = bullet_tuples
            jd_manager.save_checkpoint(job_key, checkpoint)
        cli_art.console.print(f"  {len(bullet_tuples)} bullet tuples retrieved.", markup=False, soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)

        # --- Step 3: Audit and refine bullets ---
        cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
        cli_art.console.print("Step 3: Auditing bullets...", markup=False, soft_wrap=True)
        static_prefix = self.build_audit_static_prefix()

        def _save_bullets_checkpoint(partial_bullets):
            checkpoint["refined_bullets"] = partial_bullets
            jd_manager.save_checkpoint(job_key, checkpoint)

        refined_tuples = self.audit_and_refine_bullets(
            bullet_tuples,
            static_prefix,
            resume_from=checkpoint.get("refined_bullets", []),
            on_bullet_complete=_save_bullets_checkpoint,
        )
        refined_bullets = [b for b in refined_tuples if b]  # plain strings for builder
        checkpoint["refined_bullets"] = refined_tuples
        jd_manager.save_checkpoint(job_key, checkpoint)
        cli_art.console.print(f"  {len(refined_bullets)} bullets after audit.", markup=False, soft_wrap=True)
        cli_art.console.print(markup=False, soft_wrap=True)

        # audit_and_refine_bullets emits exactly one output bullet per input
        # tuple, in order, so re-pairing by index recovers each bullet's
        # source company without changing that function's return contract or
        # the checkpoint format. Without this, the builder saw a flat list of
        # bullet text with no company attribution at all and had to guess
        # which company each bullet belonged to -- a likely contributor to it
        # giving up and emitting empty Experience entries.
        bullet_companies = [company for (_, company, _) in bullet_tuples[:len(refined_bullets)]]

        # --- Step 4: Build resume ---
        cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
        cli_art.console.print("Step 4: Building resume...", markup=False, soft_wrap=True)
        # BUG: this was loading "build_resume.md", which does not exist in
        # resume-engine/prompts/ -- load_prompt() was silently falling back
        # to the placeholder string "Process the text." on every run, so the
        # builder call had almost no real instructions. The actual file is
        # tailor_resume.md, and it already contains the full tailoring
        # hierarchy, archetype rules, and the exact JSON key spec (it even
        # says outright: "Your JSON output MUST use these exact uppercase
        # field names. Any deviation breaks the render pipeline.").
        # build_prompt is loaded unconditionally (not just in the fresh-build
        # branch below) because Step 7's trim loop references it regardless
        # of whether this run resumed resume_data from a checkpoint.
        build_prompt = self.load_prompt("tailor_resume.md")

        # Computed once and reused at every response_schema=TemplateSchema
        # call below (build, fix, trim) -- see
        # build_education_achievement_schema_fields()'s docstring for why
        # these can't just be static fields on TemplateSchema itself.
        edu_schema_properties, edu_schema_required = self.build_education_achievement_schema_fields()

        # Loaded unconditionally (not just in the fresh-build branch below)
        # for the same reason build_prompt is: Step 7's trim loop re-validates
        # every trim attempt regardless of whether this run resumed resume_data
        # from a checkpoint, so style_rules_for_validation must be in scope
        # even when the fresh-build branch below never executes.
        style_rules_for_validation = self.load_yaml(self.rules_dir, "style_rules.yaml")
        # Same reason, same place: the post-trim gate runs on the resumed path
        # too, so the roster can't be computed inside the fresh-build branch.
        role_roster = _required_role_roster(self.load_yaml(self.kb_dir, "profile.yml"))
        role_bullet_minimums = _required_role_bullet_minimums(self.load_yaml(self.kb_dir, "profile.yml"))

        resume_data = checkpoint.get("resume_data")
        if resume_data is not None:
            cli_art.console.print("  Resuming: using resume JSON from checkpoint.", markup=False, soft_wrap=True)
        else:
            kb_context = self.load_knowledge_base()

            jd_data = _parse_jd_data(jd_text)
            research = self.research_company(jd_data)
            research_block = format_company_research_block(research) if research else ""

            situational_block = ""
            if situational_candidates:
                situational_block = (
                    "\n\n=== SITUATIONAL ROLE CANDIDATES ===\n"
                    f"The JD's language matched a deterministic keyword gate for: "
                    f"{', '.join(situational_candidates)}. These are NOT automatically "
                    "included -- use your own judgment on whether including ONE of them "
                    "(as a small, 2-bullet supporting entry) would genuinely help this "
                    "specific JD, per the Situational/Optional Work History Entries rules. "
                    "If none would genuinely help, don't include any of them -- this "
                    "should be rare by construction, not a default."
                )

            role_rules_block = self.build_role_rules_block(self.load_yaml(self.kb_dir, "profile.yml"))

            # Gap 1: KB goes into system_instruction, not contents, so the
            # ~105k-token kb_context forms a stable, cacheable prefix if
            # Gemini's automatic caching kicks in across nearby calls (e.g.
            # consecutive JDs in batch mode reusing the same kb_context
            # bytes) -- NOT within this one call, and NOT reused by the
            # retry/fix loop or trim loop below, both of which deliberately
            # use build_prompt alone (no kb_context) to keep those calls
            # cheap. The variable tail (JD + bullets) sits alone in
            # combined_contents. research_block/situational_block are
            # appended after kb_context for the same reason -- they're
            # per-JD variable content, but small enough that keeping them
            # out of the cacheable prefix costs little and keeps the
            # prefix identical across JDs targeting different companies.
            builder_system = f"{build_prompt}\n\n{kb_context}{research_block}{situational_block}{role_rules_block}"

            bullets_block = "\n".join(
                f"- [{company or 'unknown company'}] {b}"
                for b, company in zip(refined_bullets, bullet_companies)
            )
            combined_contents = (
                f"=== JD KEYWORDS ===\n{json.dumps(jd_keywords)}\n\n"
                f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===\n\n"
                f"=== MASTER RESUME ===\n{json.dumps(master_resume, indent=2)}\n\n"
                f"=== REFINED BULLETS ===\n{bullets_block}"
            )

            cli_art.console.print(f"  builder_system size: {len(builder_system)} chars / ~{len(builder_system)//4} tokens", markup=False, soft_wrap=True)
            cli_art.console.print(f"  combined_contents size: {len(combined_contents)} chars / ~{len(combined_contents)//4} tokens", markup=False, soft_wrap=True)

            # Step 3's audit loop just made up to 30 calls; give the free
            # tier's rolling per-minute token window a moment to recover
            # before this ~105k-token call (see PRE_BUILDER_SLEEP above).
            cli_art.console.print(f"  Pausing {PRE_BUILDER_SLEEP}s before the builder call to avoid tripping the per-minute token cap...", markup=False, soft_wrap=True)
            time.sleep(PRE_BUILDER_SLEEP)

            resume_text, usage = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=builder_system,
                contents=combined_contents,
                response_schema=TemplateSchema,
                extra_schema_properties=edu_schema_properties,
                extra_required=edu_schema_required,
                temperature=0.0,
            )
            _log_cache_stats(usage, 0, 0)

            if not resume_text:
                cli_art.console.print("  ERROR: Builder returned empty response.", markup=False, soft_wrap=True)
                return {}

            resume_data = GeminiClient.parse_json(resume_text)
            if not resume_data:
                cli_art.console.print("  ERROR: Could not parse builder JSON.", markup=False, soft_wrap=True)
                cli_art.console.print(f"  Raw response (first 500 chars):\n{resume_text[:500]}", markup=False, soft_wrap=True)
                return {}

            resume_data = normalize_resume.normalize(resume_data)

            violations = validate_resume.validate(resume_data, style_rules_for_validation, role_roster, role_bullet_minimums)
            max_fix_attempts = 4
            fix_attempt = 0
            while violations and fix_attempt < max_fix_attempts:
                fix_attempt += 1
                cli_art.console.print(f"  Validator found {len(violations)} issue(s), attempt {fix_attempt}/{max_fix_attempts}:", markup=False, soft_wrap=True)
                for v in violations:
                    cli_art.console.print(f"    - {v}", markup=False, soft_wrap=True)
                fix_contents = (
                    f"=== ORIGINAL RESUME JSON ===\n{json.dumps(_sanitize_none_for_prompt(resume_data), indent=2)}\n\n"
                    f"=== REFINED BULLETS (source material if an issue requires populating "
                    f"or fixing Experience/achievements) ===\n{bullets_block}\n\n"
                )
                if any(v.startswith("Opening verb") for v in violations):
                    # Naming only the 2 colliding bullets per violation risks
                    # whack-a-mole: a replacement verb picked to fix one pair
                    # can collide with some other, unflagged bullet, since
                    # uniqueness is a whole-CV constraint, not a pairwise one.
                    current_verbs = validate_resume.get_opening_verbs(resume_data)
                    fix_contents += (
                        f"=== ALL OPENING VERBS CURRENTLY USED ACROSS THE CV ===\n"
                        f"{', '.join(current_verbs)}\n"
                        f"When fixing a duplicate-opening-verb issue, the replacement verb must not "
                        f"appear anywhere in this full list -- not just avoid the two bullets named "
                        f"in the issue below.\n\n"
                    )
                if any(v.startswith("Role roster") for v in violations):
                    # An absent employer is the one violation the model can't
                    # fix from the resume JSON alone: the entry it needs to add
                    # isn't in the document to be edited, and the refined-bullets
                    # block alone doesn't tell it what title or period to use.
                    # Observed live -- the roster rule in tailor_resume.md
                    # restored VML and Callahan Creek across attempts but never
                    # Element 8 / Strategy LLC, and the loop then exhausted.
                    # Same idiom as the two blocks around this one: when a
                    # violation keeps surviving retries, restate what fixing it
                    # actually requires, here rather than in a huge prompt.
                    missing = [
                        v.split("'")[1] for v in violations
                        if v.startswith("Role roster") and "'" in v
                    ]
                    roster_lines = []
                    for company in missing:
                        available = [b for b, c, _t in bullet_tuples if c == company]
                        roster_lines.append(
                            f"- {company}: {len(available)} refined bullet(s) already available "
                            f"for it in the block above. Add the EXPERIENCE entry using them."
                        )
                    fix_contents += (
                        "=== MISSING EMPLOYERS -- ADD THESE ENTRIES ===\n"
                        "These companies are in the candidate's declared work history but have no\n"
                        "EXPERIENCE entry in the JSON above. This is not a relevance judgment and\n"
                        "not a way to save space: omitting a real employer leaves an unexplained\n"
                        "gap in the work history. Add a complete entry for each, with its title,\n"
                        "period and bullets, in correct reverse-chronological position. Keep every\n"
                        "entry that is already present.\n"
                        + "\n".join(roster_lines) + "\n\n"
                    )
                if any(v.startswith("Skills line wraps") for v in violations):
                    # Repeated Skills-widow violations across retry attempts
                    # suggest the model needs the fix options spelled out
                    # again here, not just relying on tailor_resume.md's
                    # Skills Section Rules buried earlier in a huge prompt.
                    fix_contents += (
                        f"=== FIXING A SKILLS LINE WIDOW ===\n"
                        f"In order of preference: (1) add or remove an item within the category; "
                        f"(2) shorten or lengthen the category label itself, as long as it still "
                        f"fairly describes the items (e.g. 'CRM Strategy & Operations' -> 'CRM & "
                        f"Operations'); (3) pull in 1-2 more genuinely-held skills from "
                        f"summaries-and-skills-clean.csv or verified_tools.json, even if the JD "
                        f"didn't ask for them, as long as they fit the category and archetype.\n\n"
                    )
                fix_contents += (
                    f"=== ISSUES TO FIX (change nothing else) ===\n" + "\n".join(f"- {v}" for v in violations)
                )
                fix_text, fix_usage = GeminiClient.generate(
                    model=BUILDER_MODEL,
                    system_instruction=build_prompt,
                    contents=fix_contents,
                    response_schema=TemplateSchema,
                    extra_schema_properties=edu_schema_properties,
                    extra_required=edu_schema_required,
                    temperature=0.0,
                )
                _log_cache_stats(fix_usage, 0, 0)
                fixed = GeminiClient.parse_json(fix_text or "")
                if not fixed:
                    # A transient failure here (e.g. all of GeminiClient.generate()'s
                    # own inner retries/fallback exhausted) shouldn't burn the whole
                    # outer fix loop -- fix_attempt was already incremented above, so
                    # continuing just moves on to the next outer attempt with the
                    # same (unchanged) violations, rather than giving up after one
                    # network hiccup with attempts still remaining.
                    cli_art.console.print(f"  {theme.colorize_icon('warning')} Fix attempt {fix_attempt}/{max_fix_attempts} returned unparseable JSON; keeping prior resume_data and retrying if attempts remain.", soft_wrap=True)
                    continue
                resume_data = normalize_resume.normalize(fixed)
                violations = validate_resume.validate(resume_data, style_rules_for_validation, role_roster, role_bullet_minimums)

            if violations:
                cli_art.console.print(f"  {theme.colorize_icon('error')} Validator still found {len(violations)} issue(s) after {max_fix_attempts} attempts:", soft_wrap=True)
                for v in violations:
                    cli_art.console.print(f"    - {v}", markup=False, soft_wrap=True)
                return {}

            checkpoint["resume_data"] = resume_data
            jd_manager.save_checkpoint(job_key, checkpoint)

        # --- Step 5: Post-build holistic critique ---
        cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
        cli_art.console.print("Step 5: Running holistic resume critique...", markup=False, soft_wrap=True)
        critique_data = checkpoint.get("critique_data")
        if critique_data is not None:
            cli_art.console.print("  Resuming: using holistic critique from checkpoint.", markup=False, soft_wrap=True)
            resume_data["_critique"] = critique_data
        else:
            critique_prompt = self.load_prompt("critique_resume.md")
            # B49 (phase-9-backlog.md): critique_resume.md's "Load and Apply"
            # list names 18 files; only summary_score.yaml/top_third_score.yaml
            # were ever attached, so its own evaluation Steps 1-6 had no
            # rubric to score against. `static_prefix` (already built above
            # for the bullet audit loop) covers item 1 -- profile.yml,
            # trimmed -- plus voice-anchors.md as a bonus. The remaining 16
            # named files are attached raw below, not hand-curated per file
            # the way audit_and_refine_bullets curates its rules bundle:
            # this call fires once per resume build, not once per bullet, so
            # the extra ~80KB doesn't multiply the way a per-bullet cost would.
            rubric_files = [
                (self.rules_dir,   "style_rules.yaml",                 "STYLE RULES"),
                (self.scoring_dir, "professional_identity_score.yaml", "PROFESSIONAL IDENTITY SCORING RUBRIC"),
                (self.scoring_dir, "resume_cohesion_score.yaml",       "RESUME COHESION SCORING RUBRIC"),
                (self.scoring_dir, "believability.yaml",               "BELIEVABILITY SCORING RUBRIC"),
                (self.scoring_dir, "experience_structure_score.yaml",  "EXPERIENCE STRUCTURE SCORING RUBRIC"),
                (self.scoring_dir, "manager_test.yaml",                "MANAGER TEST SCORING RUBRIC"),
                (self.scoring_dir, "skills_scoring.yaml",              "SKILLS SCORING RUBRIC"),
                (self.scoring_dir, "role_dna.yaml",                    "ROLE DNA SCORING RUBRIC"),
                (self.scoring_dir, "ats_match.yaml",                   "ATS MATCH SCORING RUBRIC"),
                (self.scoring_dir, "ai_risk.yaml",                     "AI RISK SCORING RUBRIC"),
                (self.scoring_dir, "evidence_alignment.yaml",          "EVIDENCE ALIGNMENT SCORING RUBRIC"),
                (self.scoring_dir, "summary_patterns.yaml",            "SUMMARY PATTERNS SCORING RUBRIC"),
                (self.scoring_dir, "certifications_score.yaml",        "CERTIFICATIONS SCORING RUBRIC"),
                (self.scoring_dir, "recruiter_score.yaml",             "RECRUITER SCORE SCORING RUBRIC"),
                (self.scoring_dir, "specificity.yaml",                 "SPECIFICITY SCORING RUBRIC"),
                (self.scoring_dir, "summary_score.yaml",               "SUMMARY SCORING RUBRIC"),
                (self.scoring_dir, "top_third_score.yaml",             "TOP-THIRD-OF-PAGE-ONE SCORING RUBRIC"),
            ]
            rubric_blocks = "".join(
                f"\n\n{label}:\n{json.dumps(self.load_yaml(dir_path, filename))}"
                for dir_path, filename, label in rubric_files
            )
            critique_system = (
                f"{critique_prompt}"
                f"\n\n=== CANDIDATE PROFILE & VOICE (from knowledge base) ===\n{static_prefix}"
                f"{rubric_blocks}"
            )
            critique_contents = (
                f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===\n\n"
                f"=== RESUME JSON ===\n{json.dumps(_sanitize_none_for_prompt(resume_data), indent=2)}"
            )
            critique_text, _ = GeminiClient.generate(
                model=CRITIQUE_MODEL,
                system_instruction=critique_system,
                contents=critique_contents,
                response_schema=ResumeCritiqueSchema,
                temperature=0.0,
            )
            if critique_text:
                critique_data = GeminiClient.parse_json(critique_text)

                # B51 (phase-9-backlog.md): fold any rubric hard-failure/
                # threshold trip into recommendations so it re-enters the
                # pipeline through the same apply-and-validate loop Step 5.5
                # already runs on every other recommendation. Previously
                # only `recommendations` and `distinctive_moments` re-entered
                # the pipeline -- a resume tripping a rubric's own stated bar
                # shipped unchanged.
                hard_failures = critique_data.get("hard_failures_triggered", []) or []
                if hard_failures:
                    critique_data["recommendations"] = list(critique_data.get("recommendations", []) or []) + [
                        f"Fix rubric hard failure -- {hf}" for hf in hard_failures
                    ]

                cli_art.console.print(f"  Holistic critique scores:", markup=False, soft_wrap=True)
                cli_art.console.print(f"    summary_alignment : {critique_data.get('summary_alignment_score', '?')}", markup=False, soft_wrap=True)
                cli_art.console.print(f"    skills_relevance  : {critique_data.get('skills_relevance_score',  '?')}", markup=False, soft_wrap=True)
                cli_art.console.print(f"    top_third         : {critique_data.get('top_third_score',         '?')}", markup=False, soft_wrap=True)
                cli_art.console.print(f"    overall_fit       : {critique_data.get('overall_fit_score',        '?')}", markup=False, soft_wrap=True)
                identity_line = critique_data.get('primary_identity', '?')
                if critique_data.get('secondary_identity'):
                    identity_line += f" / {critique_data['secondary_identity']}"
                cli_art.console.print(f"    identity          : {identity_line}", markup=False, soft_wrap=True)
                cli_art.console.print(markup=False, soft_wrap=True)
                if hard_failures:
                    cli_art.console.print(f"  {theme.colorize_icon('error')} Hard rubric failures (added to recommendations):", soft_wrap=True)
                    for hf in hard_failures:
                        cli_art.console.print(f"    - {hf}", markup=False, soft_wrap=True)
                    cli_art.console.print(markup=False, soft_wrap=True)
                flags = critique_data.get("flags", [])
                if flags:
                    cli_art.console.print("  Flags:", markup=False, soft_wrap=True)
                    for flag in flags:
                        cli_art.console.print(f"    - {flag}", markup=False, soft_wrap=True)
                    cli_art.console.print(markup=False, soft_wrap=True)
                recs = critique_data.get("recommendations", [])
                if recs:
                    cli_art.console.print("  Recommendations:", markup=False, soft_wrap=True)
                    for rec in recs:
                        cli_art.console.print(f"    - {rec}", markup=False, soft_wrap=True)
                    cli_art.console.print(markup=False, soft_wrap=True)
                moments = critique_data.get("distinctive_moments", [])
                if moments:
                    cli_art.console.print("  Distinctive moments (protected):", markup=False, soft_wrap=True)
                    for m in moments:
                        cli_art.console.print(f"    - {m}", markup=False, soft_wrap=True)
                    cli_art.console.print(markup=False, soft_wrap=True)
                flat = critique_data.get("flat_sections", [])
                if flat:
                    cli_art.console.print("  Flat sections:", markup=False, soft_wrap=True)
                    for f in flat:
                        cli_art.console.print(f"    - {f}", markup=False, soft_wrap=True)
                    cli_art.console.print(markup=False, soft_wrap=True)
                resume_data["_critique"] = critique_data
                checkpoint["critique_data"] = critique_data
                jd_manager.save_checkpoint(job_key, checkpoint)
            else:
                cli_art.console.print("  WARNING: Holistic critique returned empty.", markup=False, soft_wrap=True)

        # --- Step 5.5: Apply actionable recommendations, one at a time ---
        # Only recommendations that are concrete edits to this resume's own
        # content get applied (e.g. "name the specific AI tools used" or
        # "emphasize the target title in the summary") -- anything the
        # holistic critique recommended that describes an action outside the
        # document itself (networking, referrals, applying elsewhere) is left
        # alone. Each recommendation gets its own call and its own
        # validate-or-discard check (same safety net as the trim loop below)
        # -- a violation introduced by one recommendation only throws away
        # that one attempt, not the other recommendations already applied
        # earlier in the same run.
        recs = (resume_data.get("_critique") or {}).get("recommendations", [])
        # Questions are never edits. critique_resume.md deliberately phrases its
        # voice recommendations as questions aimed at Morgan ("What did you
        # actually change about how the team worked?"), and the only way a model
        # can "apply" a question is to paraphrase its own noun phrases into the
        # document -- which is exactly what happened, producing the flattest
        # sentence in the shipped resume. The model-side needs_personal_input
        # guard below only catches *emotional* questions, so route every
        # question-shaped recommendation to needs_polish here, before the call.
        # Deterministic, and it saves an API round-trip per question.
        question_recs = [r for r in recs if str(r).strip().endswith("?")]
        recs = [r for r in recs if not str(r).strip().endswith("?")]
        if question_recs:
            cli_art.console.print(f"\n  {theme.colorize_icon('hint')} {len(question_recs)} recommendation(s) "
                  "are questions for you, not edits -- saved for `resume polish`, not applied.", soft_wrap=True)
        distinctive_moments = (resume_data.get("_critique") or {}).get("distinctive_moments", [])
        protected_block = (
            "=== PROTECTED DISTINCTIVE MOMENTS (preserve verbatim unless THIS "
            "recommendation specifically targets them) ===\n"
            + "\n".join(f"- {m}" for m in distinctive_moments) + "\n\n"
        ) if distinctive_moments else ""

        if recs and interactive:
            recs = _review_recommendations_interactively(recs, checkpoint, job_key)

        if recs or question_recs:
            state = checkpoint.get("recommendation_actions") or {
                # Seeded, not appended later: question_recs must survive even
                # when they were the *only* recommendations, in which case the
                # apply loop below never runs.
                "resume_data": resume_data, "applied": [], "skipped": [],
                "needs_polish": list(question_recs), "next_index": 0,
            }
            start_index = state["next_index"]
            if not recs:
                pass
            elif start_index >= len(recs):
                cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
                cli_art.console.print("Step 5.5: Resuming: recommendation pass already complete from checkpoint.", markup=False, soft_wrap=True)
            else:
                cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
                cli_art.console.print(f"Step 5.5: Applying actionable recommendations one at a time "
                      f"({start_index}/{len(recs)} already done)...", markup=False, soft_wrap=True)
            resume_data = state["resume_data"]
            applied, skipped = state["applied"], state["skipped"]
            needs_polish = state.get("needs_polish", [])

            for i in range(start_index, len(recs)):
                rec = recs[i]
                if i > 0:
                    time.sleep(RECOMMENDATION_SLEEP)
                cli_art.console.print(f"\n  [{i + 1}/{len(recs)}] {rec[:70]}...", markup=False, soft_wrap=True)
                rec_contents = (
                    f"=== CURRENT RESUME JSON ===\n{json.dumps(_sanitize_none_for_prompt(resume_data), indent=2)}\n\n"
                    f"{protected_block}"
                    f"=== RECOMMENDATION TO CONSIDER ===\n{rec}\n\n"
                    f"=== INSTRUCTIONS ===\n"
                    f"Decide whether the recommendation above is a concrete, actionable edit to "
                    f"THIS resume's own content (e.g. naming a specific tool, rewording a title/"
                    f"summary/skills phrase to mirror the JD). If so, apply ONLY this one "
                    f"recommendation and put its exact original text in applied_recommendations. "
                    f"If it describes something outside the document itself -- networking, "
                    f"referrals, applying elsewhere, or any action a person would take rather than "
                    f"an edit to this resume's text -- change nothing and put its exact original "
                    f"text in skipped_recommendations instead. If the recommendation asks you to "
                    f"reveal something personal (e.g. why a project mattered, what felt "
                    f"satisfying) and the provided background context does NOT already contain a "
                    f"grounded, verified answer, do not invent one -- change nothing and put its "
                    f"exact original text in needs_personal_input instead. Return the complete "
                    f"resume JSON with every field -- change only what this one recommendation "
                    f"asked for, if anything; leave everything else untouched."
                )
                rec_text, rec_usage = GeminiClient.generate(
                    model=BUILDER_MODEL,
                    # Unlike the fix/trim loops above (deliberately bare
                    # build_prompt, no KB, to stay cheap on structural
                    # fixes), these calls make content-quality edits --
                    # e.g. rewording the Summary -- so they need the same
                    # voice-anchors.md grounding the critique that produced
                    # this recommendation already had (B29,
                    # phase-9-backlog.md). static_prefix is small (~5-10k
                    # tokens, already built above for the audit loop), not
                    # the full ~105k-token kb_context.
                    system_instruction=f"{build_prompt}\n\n{static_prefix}",
                    contents=rec_contents,
                    response_schema=RecommendationApplySchema,
                    # B40: without these, EDU_ACHIEVEMENT_KEY_<n> isn't part
                    # of this call's schema, so the model never echoes back
                    # resume_data's existing choice -- normalize_resume.py
                    # then defaults to "", and fixed_content.build_education()
                    # silently reverts KU/KCKCC to each school's first option
                    # (plus a spurious warning) on every single recommendation
                    # applied, not just ones that touch Education.
                    extra_schema_properties=edu_schema_properties,
                    extra_required=edu_schema_required,
                    temperature=0.0,
                )
                _log_cache_stats(rec_usage, 0, 0)
                rec_result = GeminiClient.parse_json(rec_text or "")
                if not rec_result:
                    cli_art.console.print("    WARNING: unparseable JSON; leaving resume as-is for this recommendation.", markup=False, soft_wrap=True)
                else:
                    this_applied = rec_result.pop("applied_recommendations", [])
                    this_skipped = rec_result.pop("skipped_recommendations", [])
                    this_needs_input = rec_result.pop("needs_personal_input", [])
                    candidate_resume_data = normalize_resume.normalize(rec_result)
                    rec_violations = validate_resume.validate(candidate_resume_data, style_rules_for_validation, role_roster, role_bullet_minimums)
                    if rec_violations:
                        cli_art.console.print(f"    WARNING: introduced {len(rec_violations)} validator violation(s); "
                              f"discarding just this recommendation:", markup=False, soft_wrap=True)
                        for v in rec_violations:
                            cli_art.console.print(f"      - {v}", markup=False, soft_wrap=True)
                        skipped.append(f"{rec} (attempted, discarded: introduced a validator violation)")
                    elif this_applied:
                        resume_data = candidate_resume_data
                        applied.append(rec)
                        cli_art.console.print(f"    Applied.", markup=False, soft_wrap=True)
                    elif this_needs_input:
                        needs_polish.append(rec)
                        cli_art.console.print(f"    Needs your input -- left unchanged (try `resume polish`).", markup=False, soft_wrap=True)
                    else:
                        skipped.append(rec)
                        cli_art.console.print(f"    Skipped (not a resume-content edit).", markup=False, soft_wrap=True)

                checkpoint["recommendation_actions"] = {
                    "resume_data": resume_data, "applied": applied, "skipped": skipped,
                    "needs_polish": needs_polish, "next_index": i + 1,
                }
                jd_manager.save_checkpoint(job_key, checkpoint)

            checkpoint["recommendation_actions"] = {
                "resume_data": resume_data, "applied": applied, "skipped": skipped,
                "needs_polish": needs_polish, "next_index": len(recs),
            }
            jd_manager.save_checkpoint(job_key, checkpoint)

            resume_data["_recommendation_actions"] = {"applied": applied, "skipped": skipped, "needs_polish": needs_polish}
            if applied:
                cli_art.console.print("\n  Applied:", markup=False, soft_wrap=True)
                for a in applied:
                    cli_art.console.print(f"    - {a}", markup=False, soft_wrap=True)
            if skipped:
                cli_art.console.print("  Skipped:", markup=False, soft_wrap=True)
                for s in skipped:
                    cli_art.console.print(f"    - {s}", markup=False, soft_wrap=True)
            if needs_polish:
                cli_art.console.print("  Needs your input -- good candidates for `resume polish`:", markup=False, soft_wrap=True)
                for n in needs_polish:
                    cli_art.console.print(f"    - {n}", markup=False, soft_wrap=True)

        # --- Step 6: Save output ---
        output_path = os.path.join(self.output_json_dir, output_filename)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(resume_data, f, indent=2, ensure_ascii=False)
            cli_art.console.print(f"\n  Resume saved to: {output_path}", markup=False, soft_wrap=True)
        except Exception as e:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} Could not save resume JSON: {e}", soft_wrap=True)

        # --- Step 7: Render HTML + Generate PDF ---
        cli_art.console.print(f"\n{'─'*60}", markup=False, soft_wrap=True)
        cli_art.console.print("Step 7: Rendering HTML and generating PDF...", markup=False, soft_wrap=True)
        stem       = _build_output_stem(jd_path)
        html_out   = os.path.join(self.output_html_dir, f"{stem}_Resume.html")
        pdf_out    = os.path.join(self.output_pdf_dir,  f"{stem}_Resume.pdf")
        pdf_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")

        os.makedirs(os.path.dirname(html_out), exist_ok=True)
        os.makedirs(os.path.dirname(pdf_out),  exist_ok=True)

        render_html(resume_data, html_out)

        trim_instructions = [
            lambda rd: (
                "Remove the Why section entirely (set SECTION_WHY and WHY_TEXT to empty strings). "
                "It only belongs on the resume if it fits without pushing the page count past 2 -- "
                "when space is tight, it is the first thing to go."
            ),
            lambda rd: "Trim the Summary to its 5-line limit.",
            lambda rd: _widow_trim_instruction(rd, style_rules_for_validation),
            lambda rd: _bullet_removal_trim_instruction(self.load_yaml(self.kb_dir, "profile.yml")),
        ]
        max_trim_attempts = len(trim_instructions)
        trim_attempt = 0
        page_count = None
        dropped_optional_clients = False

        while True:
            try:
                pdf_result = subprocess.run(
                    ["node", pdf_script, html_out, pdf_out, "--format=letter"],
                    capture_output=True, text=True, timeout=PDF_GENERATION_TIMEOUT_SECONDS,
                    env={**os.environ, "RESUME_BUILDER_ICONS": theme.icon_set_name()},
                )
            except subprocess.TimeoutExpired:
                cli_art.console.print(f"  {theme.colorize_icon('warning')}  PDF generation timed out after "
                      f"{PDF_GENERATION_TIMEOUT_SECONDS}s.", soft_wrap=True)
                return {}
            if pdf_result.returncode != 0:
                cli_art.console.print(f"  {theme.colorize_icon('warning')}  PDF generation failed:\n{pdf_result.stderr}", soft_wrap=True)
                return {}

            page_count, size_str = _parse_pdf_result(pdf_result.stdout, pdf_out)
            if page_count is None:
                cli_art.console.print(f"  {theme.colorize_icon('error')} Could not verify PDF page count via pypdf -- "
                      "treating as a failure rather than silently passing the 2-page rule.", soft_wrap=True)
                return {}
            is_final = page_count <= 2 or trim_attempt >= max_trim_attempts
            if is_final:
                cli_art.console.print(pdf_result.stdout, markup=False, soft_wrap=True)
                break

            if not dropped_optional_clients:
                dropped_optional_clients = True
                fixed_content = profile_paths.fixed_content_module()
                has_optional_clients = any(
                    fixed_content.CLIENTS.get(job.get("company"), {}).get("essential") is False
                    and job.get("clients")
                    for job in resume_data.get("EXPERIENCE", [])
                )
                if has_optional_clients:
                    # Free, non-LLM trim step: drop the Inside Sales Team
                    # client roster (fixed_content.CLIENTS marks it
                    # non-essential) before spending an LLM-driven
                    # trim_instructions attempt.
                    cli_art.console.print(f"  PDF is {page_count} pages ({size_str}), dropping optional client rosters...", markup=False, soft_wrap=True)
                    resume_data = normalize_resume.normalize(resume_data, include_optional_clients=False)
                    render_html(resume_data, html_out)
                    continue

            cli_art.console.print(f"  PDF is {page_count} pages ({size_str}), applying trim step {trim_attempt + 1}/{max_trim_attempts}...", markup=False, soft_wrap=True)
            trim_contents = (
                f"=== ORIGINAL RESUME JSON ===\n{json.dumps(_sanitize_none_for_prompt(resume_data), indent=2)}\n\n"
                f"=== TRIM INSTRUCTION (apply only this step) ===\n{trim_instructions[trim_attempt](resume_data)}"
            )
            trim_text, trim_usage = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=build_prompt,
                contents=trim_contents,
                response_schema=TemplateSchema,
                extra_schema_properties=edu_schema_properties,
                extra_required=edu_schema_required,
                temperature=0.0,
            )
            _log_cache_stats(trim_usage, 0, 0)
            trimmed = GeminiClient.parse_json(trim_text or "")
            if not trimmed:
                # A transient failure here (e.g. all of GeminiClient.generate()'s
                # own inner retries/fallback exhausted) shouldn't burn the whole
                # trim loop -- unlike the violations-found branch below, this
                # point is reached before trim_attempt is incremented, so it
                # must be bumped here too or `continue` would spin on the same
                # index forever.
                cli_art.console.print(f"  {theme.colorize_icon('warning')} Trim attempt {trim_attempt + 1}/{max_trim_attempts} returned unparseable JSON; "
                      f"keeping prior resume_data and retrying if attempts remain.", soft_wrap=True)
                trim_attempt += 1
                continue

            trimmed_resume_data = normalize_resume.normalize(trimmed)
            trim_violations = validate_resume.validate(trimmed_resume_data, style_rules_for_validation, role_roster, role_bullet_minimums)
            if trim_violations:
                cli_art.console.print(f"  {theme.colorize_icon('warning')}  WARNING: Trim attempt {trim_attempt + 1} introduced {len(trim_violations)} "
                      f"validator violation(s); discarding this trim and keeping the prior resume_data:", soft_wrap=True)
                for v in trim_violations:
                    cli_art.console.print(f"    - {v}", markup=False, soft_wrap=True)
                trim_attempt += 1
                continue

            resume_data = trimmed_resume_data
            render_html(resume_data, html_out)
            trim_attempt += 1

        if page_count > 2:
            cli_art.console.print(f"  {theme.colorize_icon('error')} PDF still {page_count} pages after {max_trim_attempts} trim attempts.", soft_wrap=True)
            return {}

        final_companies = {job.get("company") for job in resume_data.get("EXPERIENCE", [])}
        fired_situational_roles = final_companies & set(situational_roles.load_situational_roles()["roles"].keys())
        if fired_situational_roles:
            cli_art.console.print(f"  {theme.colorize_icon('hint')} Situational role fired: {', '.join(sorted(fired_situational_roles))}", soft_wrap=True)

        pdf_fatal, pdf_text_warnings = validate_pdf_text.validate_pdf_text(pdf_out, resume_data)
        if pdf_fatal:
            cli_art.console.print(f"  {theme.colorize_icon('error')} PDF text-layer check could not verify the rendered file "
                  f"-- treating this as a failed build, not a warning:", soft_wrap=True)
            for f in pdf_fatal:
                cli_art.console.print(f"    - {f}", markup=False, soft_wrap=True)
            return {}
        if pdf_text_warnings:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} PDF text-layer check found {len(pdf_text_warnings)} potential issue(s) "
                  f"(what an ATS would actually parse from the file, not just the pre-render JSON):", soft_wrap=True)
            for w in pdf_text_warnings:
                cli_art.console.print(f"    - {w}", markup=False, soft_wrap=True)
        else:
            cli_art.console.print(f"  {theme.colorize_icon('success')} PDF text-layer check: 0 issues.", soft_wrap=True)

        # B18 (phase-9-backlog.md): reported before the pipeline claims
        # success, per the backlog item's own wording -- not gated. See
        # validate_resume.check_keyword_coverage()'s docstring for why a
        # missing keyword doesn't block the build.
        ats_match_rules = self.load_yaml(self.scoring_dir, "ats_match.yaml")
        coverage = validate_resume.check_keyword_coverage(resume_data, jd_keywords, ats_match_rules)
        coverage_icon = 'success' if coverage["band"] in ("excellent_match", "good_match") else 'warning'
        cli_art.console.print(f"  {theme.colorize_icon(coverage_icon)} JD-keyword coverage: {coverage['score']}% "
              f"({coverage['band']}, {len(coverage['matched'])}/{len(coverage['matched']) + len(coverage['missing'])})", soft_wrap=True)
        if coverage["missing"]:
            cli_art.console.print(f"    Missing: {', '.join(coverage['missing'])}", markup=False, soft_wrap=True)

        # B29 (phase-9-backlog.md): same non-blocking, report-not-gate
        # treatment as the coverage check above, and for the same class of
        # reason -- see validate_resume.check_summary_specificity()'s
        # docstring for the real build failure that made this non-blocking.
        specificity_notes = validate_resume.check_summary_specificity(resume_data)
        for note in specificity_notes:
            cli_art.console.print(f"  {theme.colorize_icon('warning')} {note}", soft_wrap=True)

        # Belt-and-suspenders on top of the fatal check above: don't claim
        # success or record output paths unless the PDF is actually on disk
        # (ResumeDesignSystem.md's guarantee -- the system must never claim a
        # resume exists when generation failed).
        if not os.path.exists(pdf_out):
            cli_art.console.print(f"  {theme.colorize_icon('error')} Pipeline did not complete -- expected PDF not found on disk: {pdf_out}", soft_wrap=True)
            return {}

        cli_art.console.print(f"  {theme.colorize_icon('success')} Pipeline complete! PDF → {pdf_out}", soft_wrap=True)
        jd_manager.delete_checkpoint(job_key)
        resume_data["_output_paths"] = {"json": output_path, "html": html_out, "pdf": pdf_out}
        resume_data["_page_count"] = page_count

        return resume_data


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run_pipeline(jd_path=None, master_resume_path=None, output_filename=None):
    """Runs the tailor+render pipeline.

    jd_path=None means batch mode (every pending JD in jds/). Returns
    (completed_count, failed_count) rather than exiting, so callers other
    than the CLI (e.g. scripts/cli.py) can decide how to report failure.
    """
    kb_snapshot.snapshot_kb()

    master_resume = {}
    if master_resume_path:
        try:
            with open(master_resume_path, "r", encoding="utf-8") as f:
                master_resume = json.load(f)
            cli_art.console.print(f"Loaded master resume from: {master_resume_path}", markup=False, soft_wrap=True)
        except Exception as e:
            cli_art.console.print(f"WARNING: Could not load master resume: {e}. Proceeding with empty dict.", markup=False, soft_wrap=True)

    engine = ResumeEngine()
    tracker = jd_manager.JDTracker()

    if jd_path:
        jd_paths = [jd_path]
    else:
        jd_paths = jd_manager.get_pending_jds()
        if not jd_paths:
            cli_art.console.print("\nNo pending JDs found in jds/. Nothing to do.", markup=False, soft_wrap=True)
            return 0, 0

    completed_count = 0
    failed_count = 0
    aborted_remaining = 0

    for index, path in enumerate(jd_paths):
        try:
            job_key = jd_manager.compute_job_key(path)
        except OSError as e:
            cli_art.console.print(f"  {theme.colorize_icon('error')} Could not read JD file {path}: {e}", soft_wrap=True)
            tracker.mark_failed(
                job_key=f"unreadable:{os.path.basename(path)}",
                source_file=os.path.basename(path),
                error_message=str(e),
            )
            failed_count += 1
            continue

        job_title, company_name = jd_manager.extract_job_meta(path)
        source_url = jd_manager.extract_source_url(path)
        evaluation = jd_manager.read_evaluation(path)

        try:
            result = engine.build_tailored_resume(
                jd_path=path,
                master_resume=master_resume,
                output_filename=output_filename if jd_path else None,
                job_key=job_key,
                interactive=jd_path is not None,
            )
        except SustainedFailureError as e:
            # Caught ahead of the blanket handler on purpose. This exception
            # means "quota, not weather" -- retries and the model fallback are
            # already exhausted. Treating it as a per-JD failure would make a
            # revoked key run the full 6-attempt/90s-backoff cycle once per
            # pending JD (1,100+ of them), scrolling the one actionable
            # instruction past hundreds of times over several hours. Stop, and
            # say how much work is still waiting.
            tracker.mark_failed(
                job_key=job_key,
                job_title=job_title,
                company_name=company_name,
                source_file=os.path.basename(path),
                error_message=str(e),
            )
            failed_count += 1
            aborted_remaining = len(jd_paths) - (index + 1)
            cli_art.console.print(f"\n  {theme.colorize_icon('error')} Sustained API failure -- stopping the batch.", soft_wrap=True)
            cli_art.console.print(f"    {e}", markup=False, soft_wrap=True)
            if aborted_remaining:
                cli_art.console.print(f"    {aborted_remaining} JD(s) left untouched; re-run to pick up where this stopped.", markup=False, soft_wrap=True)
            break
        except Exception as e:
            result = None
            cli_art.console.print(f"  {theme.colorize_icon('error')} Unhandled exception building resume for {path}: {e}", soft_wrap=True)

        if result:
            output_paths = result.get("_output_paths", {})
            os.makedirs(jd_manager.COMPLETED_DIR, exist_ok=True)
            dest = os.path.join(jd_manager.COMPLETED_DIR, os.path.basename(path))
            shutil.move(path, dest)
            tracker.mark_completed(
                job_key=job_key,
                job_title=job_title,
                company_name=company_name,
                source_file=os.path.basename(path),
                output_json=output_paths.get("json", ""),
                output_pdf=output_paths.get("pdf", ""),
            )
            jd_manager.append_application_row(
                company_name=company_name,
                job_title=job_title,
                has_pdf=os.path.exists(output_paths.get("pdf", "")),
                source_url=source_url,
                evaluation=evaluation,
            )
            completed_count += 1
            cli_art.console.print(f"\nDone! Resume built successfully for {path}.", markup=False, soft_wrap=True)
        else:
            tracker.mark_failed(
                job_key=job_key,
                job_title=job_title,
                company_name=company_name,
                source_file=os.path.basename(path),
                error_message="Resume build failed. Check output above for details.",
            )
            failed_count += 1
            cli_art.console.print(f"\nERROR: Resume build failed for {path}. It stays pending and will be retried next run.", markup=False, soft_wrap=True)

    summary = f"\nBatch summary: {completed_count} completed, {failed_count} failed."
    if aborted_remaining:
        summary += f" Aborted early on sustained API failure -- {aborted_remaining} JD(s) not attempted."
    cli_art.console.print(summary, markup=False, soft_wrap=True)
    return completed_count, failed_count


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Resume Builder Orchestrator")
    parser.add_argument(
        "jd", nargs="?", default=None,
        help="Path to a specific JD file. Omit to batch-process everything pending in jds/.",
    )
    parser.add_argument("--master", default=None, help="Path to master resume JSON (optional)")
    parser.add_argument("--output", default=None, help="Output JSON filename (single-JD mode only)")
    args = parser.parse_args()

    completed_count, failed_count = run_pipeline(
        jd_path=args.jd, master_resume_path=args.master, output_filename=args.output,
    )

    if args.jd and failed_count and not completed_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
