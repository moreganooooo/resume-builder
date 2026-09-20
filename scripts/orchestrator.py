import ast
import collections
import copy
import datetime
import inspect
import json
import logging
import os
import random
import re
import shutil
import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any, List, Literal, Tuple

if TYPE_CHECKING:  # annotations only -- see the lazy imports below
    import pandas as pd

# _LAZY_HEAVY_DEPS -- why pandas and numpy are NOT imported here.
# Lite Mode (requirements-lite.txt, for Android/Termux and for desktops
# that only tailor and sync rather than render) deliberately omits both:
# they are heavy to build on Termux and only python-jobspy needs them.
# But orchestrator.py is imported by every entry point, including cli.py,
# so a module-level `import numpy` meant a Lite install died at
# `ModuleNotFoundError: No module named 'numpy'` when the user ran plain
# `resume` -- before any pipeline logic, and before any message that could
# explain what was wrong. Both are now imported inside the seven functions
# that actually use them. Keep it that way: anything imported at this level
# becomes a hard dependency of the whole CLI. (master_audit_document F20.)

import company_research
import questionary
import requests
import situational_roles
import yaml
from dotenv import load_dotenv
from pypdf import PdfReader

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

import bullet_feedback
import charm_prompt
import cli_art
import jd_manager
import kb_snapshot
import liveness
import location_filter
import normalize_resume
import scan_ats
import theme
import validate_coverletter
import validate_pdf_text
import validate_resume
from bullet_bank_hash import bullets_sha
from render_coverletter import render_coverletter
from render_coverletter_docx import render_coverletter_docx
from render_html import render_html
from render_resume_docx import render_resume_docx

# This module had its own copy, and it was the STALE one: it matched only
# via fixed_content.CV_SECTION_KEYWORDS (scaffolded empty for every
# bootstrapped profile and never auto-populated) and split only on "### "
# headings, while bootstrap_profile._assemble_cv_draft() writes "## Title
# — Company (dates)". Both conditions failed for any normally-generated
# profile, so it returned the WHOLE cv.md unconditionally -- which is the
# input that let a rewrite borrow another job's numbers. rewrite_bullets'
# version keeps the hand-curated override and falls back to matching the
# company against each heading, so it works with no manual setup. No
# circular-import risk: rewrite_bullets imports only profile_paths, and
# bullet_feedback above already pulls it into this chain.
from rewrite_bullets import (
    compact_tools_text,
    date_anchors,
    extract_cv_section,
)

# --- MODEL STRATEGY ---
# CRITIQUE_MODEL: handles bullet critique (high-frequency) and the post-build
#   holistic resume critique. gemini-3.5-flash-lite gives the best free-tier
#   headroom while reliably following JSON instructions with strict schemas.
#
# REWRITE_MODEL: gemma-4-31b-it -- primary rewrite model for the audit loop.
#   Mirrors rewrite_bullets.py exactly. Has the largest free-tier daily quota
#   by a wide margin. The audit loop rewrites benefit from Gemma's richer
#   generation quality while critiques/scoring stay on Flash-Lite for strict
#   JSON compliance. GEMMA_MINIMAL_JSON=True means Gemma only has to produce
#   {"rewritten_bullet": "..."} -- one key, much less drift.
#
# REWRITE_FALLBACK_MODEL: gemini-3.5-flash-lite -- activated automatically
#   after MAX_REWRITE_PARSE_FAILURES consecutive parse failures on a single
#   bullet. Reliable JSON compliance as a safety net.
#
# BUILDER_MODEL: handles JD keyword extraction and the final resume assembly.
#   gemini-3.5-flash-lite for quota reasons. Nested response models are fine
#   here -- TemplateSchema was briefly flattened to List[dict] on the theory
#   that nested $defs caused a builder 400, but that was disproven and
#   reverted (see ExperienceEntry's docstring: the real cause was
#   sanitize_schema() dropping $defs, fixed by GeminiClient.resolve_refs()).
#
# EMBED_MODEL: gemini-embedding-2 (GA April 2026) -- multimodal, 8k token input.
#   Used ONLY for the one-time offline bullet bank pre-embedding (embed_bullet_bank.py)
#   and for the single JD embedding at runtime in mine_bullet_bank().
#   Native output dimension: 768.
#
# NOTE: orchestrator.py uses raw REST (requests) rather than the google-genai SDK.
#   This avoids SDK versioning headaches on the free tier and gives full explicit
#   control over the payload shape and response parsing.
CRITIQUE_MODEL = "gemini-3.5-flash-lite"
REWRITE_MODEL = "gemma-4-31b-it"
REWRITE_FALLBACK_MODEL = "gemini-3.5-flash-lite"
BUILDER_MODEL = "gemini-3.5-flash-lite"
# Fit scoring stays on 3.1: 3.5-flash-lite's scores for the same roles moved
# well past run-to-run noise (2026-09-15). Paired with SCORING_FALLBACKS so a
# 503 streak can never route a score through 3.5 either.
EVAL_MODEL = "gemini-3.1-flash-lite"
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM = 768  # gemini-embedding-2 native dimension

# When True, Gemma rewrites use a single-key schema {"rewritten_bullet": "..."}
# instead of the full 3-key schema. Mirrors rewrite_bullets.py's
# GEMMA_MINIMAL_JSON flag. Dramatically improves Gemma JSON compliance.
GEMMA_MINIMAL_JSON = True
MAX_REWRITE_PARSE_FAILURES = 2

# A sick Gemma used to cost over an hour PER BULLET: rewrites run with
# model_fallback=False, so one call retried Gemma alone 6 times -- each try
# paying GEMMA_MIN_INTERVAL_SECS (65s), up to a 180s timeout and up to 90s
# of backoff -- and the handoff needed two such calls to fail. Probed
# 2026-09-16: both flash-lites answering in <1s while gemma-4-31b-it took
# 21s, 500'd, then took 59s. So a Gemma rewrite gets few retries, a Gemma
# call that fails hands off at once, and the failure benches Gemma for the
# rest of the build (and later builds in the same process) for a while --
# via gemini_client's shared bench, which the Bullet Bank stages use too.
GEMMA_REWRITE_MAX_RETRIES = 2


def _starting_rewrite_model() -> str:
    if gemini_client.is_benched(REWRITE_MODEL):
        return REWRITE_FALLBACK_MODEL
    return REWRITE_MODEL


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
- Do not anchor achievements to school years, calendar dates, or seasons (e.g. "in the
  2020-21 school year", "during Q3") — the role's period line already carries the
  timeframe. Drop such qualifiers entirely rather than rewording them.
- Do not append filler purpose clauses ("ensuring optimal performance and accuracy",
  "to support high-value campaign execution") — end on the concrete outcome instead.

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
_IS_TEST_OR_CI = (
    os.environ.get("CI") == "true" or os.environ.get("RESUME_BUILDER_TESTING") == "1"
)
CRITIQUE_SLEEP = 0 if _IS_TEST_OR_CI else 4
REWRITE_SLEEP = 0 if _IS_TEST_OR_CI else 4
RESCORE_SLEEP = 0 if _IS_TEST_OR_CI else 8
RECOMMENDATION_SLEEP = 0 if _IS_TEST_OR_CI else 8
PRE_BUILDER_SLEEP = 0 if _IS_TEST_OR_CI else 15
# (longer because rescore fires immediately after rewrite)


# --- PIPELINE CONSTANTS ---
TOP_K_BULLETS = 30  # bullets mined from the bank per run
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
    "Hidden Gem": 0,
    "Strong": 1,
    "Solid": 2,
    "Needs Work": 3,
}


# --- KNOWLEDGE BASE ALLOWLIST ---
# Only files listed here are stitched into the builder's static context.
# Sorted alphabetically to guarantee byte-for-byte identical prefix across
# every run -> maximises Google's implicit prompt-prefix caching hit rate.
KB_ALLOWLIST = sorted(
    [
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
        # Hand-curated register anchor: verbatim summaries from resumes the
        # candidate wrote and liked (see voice-favorites.md itself). Lives
        # next to voice-anchors.md deliberately -- build_voice_anchors.py
        # regenerates that file from application-answers-index.csv and would
        # clobber anything merged into it, so the favorites stay in their own
        # regeneration-proof file. Full tier / builder only: never add this
        # to build_audit_static_prefix_gemma() -- gemma-4-31b-it's 16k TPM
        # cap leaves little headroom once the segment bundle is added, and
        # this file costs ~1.1k tokens per call. Absence is fine:
        # get_active_kb_files() skips missing files, and no bootstrap flow
        # claims to write this.
        "voice-favorites.md",
        "voice-anchors.md",
    ]
)


# Subset of KB_ALLOWLIST that `bootstrap_profile.run_profile_setup()`
# actually guarantees, in its default (all-targets) run:
# write_profile_yml/write_portals_yml (profile.yml, portals.yml),
# write_background_guide/write_voice_anchors (user-background-guide.md,
# voice-anchors.md), write_cv_md (cv.md), and write_verified_ledger
# (verified_metrics/tools/projects.json). Everything else in
# KB_ALLOWLIST is either the output of a separate, optional deep-evidence
# extraction pass this profile may never run (verified_facts.json needs
# a staged-facts review; verified-claims.csv/evidence-guide.csv/
# evidence_graph.json/extracted-screenshot-metrics.csv/
# recruiter_memory_patterns.json all come from that same optional flow --
# see the `deep_evidence_keywords`/"not every profile has one company
# with this much audited archive" note elsewhere in this file), or a
# hand-curated, profile-specific research artifact no bootstrap flow
# writes at all (bullet-bank.md, detective-findings-trimmed.csv,
# article-digest.md, summaries-and-skills-clean.csv,
# treering-archive-readme.md -- the last of those is literally named
# after one profile's own former employer and was never meant to
# generalize). doctor.check_kb_allowlist() only reports a file as
# "missing" when it's in THIS set, so a profile that hasn't done (or will
# never do) the optional deep-research pass isn't told its knowledge base
# is broken -- KB_ALLOWLIST itself is unchanged and still includes all of
# these, since get_active_kb_files() already treats absence gracefully
# for the builder's own context assembly.
KB_REQUIRED_FILES = frozenset(
    [
        "cv.md",
        "profile.yml",
        "user-background-guide.md",
        "verified_metrics.json",
        "verified_projects.json",
        "verified_tools.json",
        "voice-anchors.md",
    ]
)


def get_active_kb_files(kb_dir: str) -> list:
    """Returns the sorted list of curated KB_ALLOWLIST files present in kb_dir,
    guaranteeing deterministic, prompt-cacheable context and preventing token overflow.
    """
    if not os.path.isdir(kb_dir):
        return sorted(KB_ALLOWLIST)

    return [f for f in sorted(KB_ALLOWLIST) if os.path.isfile(os.path.join(kb_dir, f))]


# --- TIER 2 FILTERING CONSTANTS ---
# Ported verbatim from rewrite_bullets.py. These are what actually make
# the segment bundle small and relevant instead of a raw file dump.
# The keyword list gating which companies get the "deep evidence" file
# bundle (verified-claims.csv, extracted-screenshot-metrics.csv, etc.) is
# per-profile -- see profile.yml's deep_evidence_keywords: -- since it's
# not every profile that has one company with this much audited archive.
MAX_CLAIMS_ROWS = 12
MAX_GEMMA_FILTER_ROWS = 5  # tighter cap for Gemma's slim tier -- see docs/superpowers/specs/2026-07-15-gemma-slim-context-design.md

# profile.yml sections to KEEP in the audit prefix (trimmed for token efficiency).
AUDIT_PROFILE_KEEP = [
    "target_roles:",
    "archetypes:",
    "narrative:",
    "superpowers:",
    "background_context:",
    "deal_breakers:",
    # evaluate_recruiter.md asks the model to flag "a required degree the
    # candidate doesn't hold" as a hard_blocker -- but the candidate's
    # degrees and certifications live here, and this list is the only
    # thing that puts them in front of the model. Without it the prompt
    # was asking a question it had no data to answer, so a posting
    # demanding a credential Morgan does not hold scored like any other.
    # Same shape as the bug this whole trim exists to describe: an
    # evaluation running against the JD alone.
    "fixed_credentials:",
    # evaluate_recruiter.md's gap assessment reads this per profile; it
    # used to hardcode one candidate's 2024-25 gap for every profile.
    "career_gap:",
]
AUDIT_PROFILE_STOP = [
    "industries_of_genuine_fit:",
    "companies_previously_applied:",
    "compensation:",
    "location:",
    "cv:",
    "proof_points:",
    "key_recommendations:",
    "management_evidence:",
    # Bounds fixed_credentials above; it is the last top-level key, so
    # without a stop the trim would run to end of file and quietly grow
    # what every evaluation sends.
    "voice_calibration_example:",
]


# ---------------------------------------------------------------------------
# RETRY / BACKOFF CONSTANTS
# ---------------------------------------------------------------------------
RETRYABLE = {429, 500, 502, 503, 504}
SERVER_ERRORS = {500, 502, 503, 504}
HIGH_DEMAND_STATUS = 503
BASE_BACKOFF_SECS = 8
MAX_BACKOFF_SECS = 90


# ---------------------------------------------------------------------------
# GEMINI CLIENT  (raw REST)
# ---------------------------------------------------------------------------

import gemini_client
from gemini_client import (  # replaces the inline class
    SCORING_FALLBACKS,
    GeminiClient,
    SustainedFailureError,
)

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


def filter_claims_by_tags(
    df_claims: "pd.DataFrame", tags: str, max_rows: int = MAX_CLAIMS_ROWS
) -> "pd.DataFrame":
    # Lazy pandas/numpy -- see _LAZY_HEAVY_DEPS note at the top of this module.
    import pandas as pd

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
    mask = (
        df_claims[text_cols]
        .apply(lambda col: col.str.contains(pattern, case=False, na=False))
        .any(axis=1)
    )
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
        haystack = " ".join(
            str(v) for v in entry.values() if isinstance(v, str)
        ).lower()
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


def get_verified_claims_text(df_claims: "pd.DataFrame") -> str:
    # Lazy pandas/numpy -- see _LAZY_HEAVY_DEPS note at the top of this module.
    import pandas as pd

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
    vocabulary_substitutions: list | None = None,
    already_written_bullets: list | None = None,
    other_cv_bullets: list | None = None,
) -> str:
    persona = persona_context(tags)
    weakness_text = (
        weaknesses.strip()
        if weaknesses and weaknesses.strip()
        else "Improve clarity, specificity, and believability."
    )

    parts = []

    if kb_context:
        parts.extend(
            [
                "Use only supported facts from this context:",
                kb_context,
                "",
            ]
        )

    parts.extend(
        [
            f"Rewrite this bullet for {persona} roles.",
            f"Bullet tags: {tags or '(none)'} -- used by the VERB TAXONOMY's archetype_allows exception.",
            f"Known weaknesses to fix: {weakness_text}",
            f"Bullet to rewrite: {bullet}",
        ]
    )

    if already_written_bullets or other_cv_bullets:
        avoid_parts = []
        if already_written_bullets:
            # Filters out empty or None values
            valid_written = [b for b in already_written_bullets if b]
            if valid_written:
                avoid_parts.extend(
                    [
                        "",
                        "=== ALREADY WRITTEN BULLETS FOR THIS SAME ROLE ===",
                        "You MUST NOT repeat any verbs, phrasing structures, or specific metric claims already used in these bullets. Vary your vocabulary and sentence structure:",
                        "\n".join(f"- {b}" for b in valid_written),
                    ]
                )
        if other_cv_bullets:
            valid_other = [b for b in other_cv_bullets if b]
            if valid_other:
                avoid_parts.extend(
                    [
                        "",
                        "=== ALREADY WRITTEN BULLETS FOR OTHER ROLES IN THE CV ===",
                        "Ensure your rewritten bullet does not repeat verbs or duplicate key claims from other parts of the resume:",
                        "\n".join(f"- {b}" for b in valid_other),
                    ]
                )
        if avoid_parts:
            parts.extend(avoid_parts)

    if vocabulary_substitutions:
        pairs = [
            f"{p.get('generic_term')} -> {p.get('company_term')}"
            for p in vocabulary_substitutions
            if isinstance(p, dict) and p.get("generic_term") and p.get("company_term")
        ]
        if pairs:
            parts.extend(
                [
                    "",
                    "=== PREFERRED VOCABULARY ===",
                    "You MUST integrate the following vocabulary substitutions where applicable. "
                    "Integrate them naturally into your sentence, ensuring perfect grammatical alignment, "
                    "correct pluralization/singularization, and smooth flow:",
                    "\n".join(f"- {pair}" for pair in pairs),
                ]
            )

    if minimal_schema:
        parts.extend(["", 'Output JSON: {"rewritten_bullet":""}'])
    else:
        parts.extend(
            [
                "",
                'Output JSON: {"rewritten_bullet":"","reasoning":"","context_gaps":""}',
            ]
        )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CACHE-HIT LOGGING HELPER  (ported verbatim from rewrite_bullets.py so the
# audit loop's terminal report shows Tier 2/3 token + cache-hit stats too,
# not just the Tier 1 static-prefix line.)
# ---------------------------------------------------------------------------


def _log_cache_stats(usage: dict, kb_context_chars: int, attempt: int) -> None:
    if not isinstance(usage, dict):
        usage = {}

    prompt_tokens = usage.get("promptTokenCount", 0)
    output_tokens = usage.get("candidatesTokenCount", 0)
    total_tokens = usage.get("totalTokenCount", 0)
    cached_tokens = usage.get("cachedContentTokenCount", 0)

    token_part = f"prompt: {prompt_tokens:,} | output: {output_tokens:,} | total: {total_tokens:,}"

    # Cache hit/miss is the ONE piece of engine internals that stays
    # visible at NORMAL. It survives the verbosity cut because it answers
    # "did this call cost me full price?" -- a question a non-engineer can
    # act on -- in a single line. The token breakdown sitting behind it is
    # VERBOSE-only: prompt/output/total counts are meaningless to anyone
    # not tuning prompts.
    #
    # Gated to the first attempt so a retried call doesn't repeat the same
    # cache verdict two or three times for one bullet.
    if attempt <= 1:
        if cached_tokens and cached_tokens > 0:
            cli_art.detail(
                f"   {theme.colorize_icon('success')} cache hit — {cached_tokens:,} tokens reused",
                level=cli_art.NORMAL,
                soft_wrap=True,
            )
        else:
            cli_art.detail(
                f"   {theme.colorize_icon('hint')} cache miss — full prompt sent",
                level=cli_art.NORMAL,
                soft_wrap=True,
            )

    cli_art.detail(
        f"   {theme.colorize_icon('hint')} tokens — {token_part}", soft_wrap=True
    )


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


def _short_widow_bullets(
    resume_data: dict, companies: set, style_rules: dict
) -> list[str]:
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
        for bullet, _word_count in validate_resume.bullets_with_short_widow(
            bullets, style_rules
        )
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
    companies = {
        job.get("company")
        for job in resume_data.get("EXPERIENCE", [])
        if job.get("company")
    }
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


def _is_skills_line_violation(violation: str) -> bool:
    """Matches validate_resume._check_skills_line_lengths() output (both the
    widow and the 3rd-line variants). Named rather than inlined at the call
    site because it couples to that function's message text through nothing
    but a prose prefix -- tests/test_orchestrator_retry_hints.py pins it to
    real validator output so a reworded message can't silently switch the
    retry hint off."""
    return violation.startswith("Skills line")


def _is_bullet_widow_violation(violation: str) -> bool:
    """Matches validate_resume._check_bullet_widows() output. See
    _is_skills_line_violation() for why this isn't inlined."""
    return violation.startswith("Bullet is") and "widow" in violation


def _condensed_violation(violation: str, max_len: int = 100) -> str:
    """Truncates a validator violation message for on-screen display only.

    The full message -- exact char counts, the illegal dead-band, the
    complete quoted bullet -- is written for the model reading it out of
    fix_contents, and callers must keep passing the untouched original
    there. Printed to the terminal verbatim on every retry attempt, that
    same verbosity is what a live run got complained about as "a wall of
    text" (2026-08-22): 8-20 violations, each a full instructional
    sentence plus a 100+ char quoted bullet, repeated on every attempt.
    """
    violation = violation.split("\n")[0]
    if len(violation) <= max_len:
        return violation
    return violation[: max_len - 1].rstrip() + "…"


def _needs_metric_inventory(violations: list[str]) -> bool:
    """True when the retry prompt should carry the full list of metrics
    already used in the CV.

    Deliberately fires ONLY on an existing duplicate-Metric violation.
    Widening this to widow violations was tried on 2026-08-12 (the theory
    being that lengthening a line is when the model reaches for a filler
    number) and was reverted: injecting the whole-CV metric list on nearly
    every retry reads as "don't use any number in this list", and the run
    after it showed the model deleting bullets to dodge collisions,
    tripping the per-role minimums instead. Duplicate metrics are now
    prevented at selection time in mine_bullet_bank() rather than repaired
    here.
    """
    return any(v.startswith("Metric") for v in violations)


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
        name
        for role in (profile_data.get("roles") or [])
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
        if (name := str(role.get("name", "")).strip())
        and name not in situational
        and role.get("min_bullets") is not None
    }


def _required_role_bullet_maximums(profile_data: dict) -> dict[str, int]:
    """profile.yml's roles: max_bullets, keyed by company name -- the ceiling
    counterpart to _required_role_bullet_minimums(). Absent for a role means
    no ceiling (min_bullets/target_bullets alone don't imply one, since a
    role can legitimately grow past its target when space allows). Only
    roles that declare an explicit max_bullets (e.g. Mercor, pinned to
    exactly 2 bullets -- never 1, never 3) are constrained."""
    situational = set(situational_roles.load_situational_roles()["roles"].keys())
    return {
        name: role["max_bullets"]
        for role in (profile_data.get("roles") or [])
        if (name := str(role.get("name", "")).strip())
        and name not in situational
        and role.get("max_bullets") is not None
    }


def _confirm_continue_without_keywords() -> bool:
    """Single-file interactive escape hatch for the empty-keywords stop. Only
    ever reached with interactive=True, so a non-TTY (batch, `resume sample`,
    tests) can never block on it. cli_art.confirm() already returns False
    (not None) on an interrupted/unreadable stdin -- the bool() wrapper is
    just defensive."""
    return bool(
        cli_art.confirm(
            "Build the resume anyway, with no JD keywords?",
            default=False,
        )
    )


# A verified-skills ledger at or below this many names is sent to the
# evaluator whole; above it, only the names the posting mentions are sent
# (see relevant_skill_names()).
SKILLS_CONTEXT_FILTER_MIN = 120
# OFF until a revised filter passes an A/B against the full list. Measured
# 2026-09-13 on 8 pending roles: filtering moved composite by a mean 0.19 and
# interview odds by 0.31 -- mostly down -- including one role 4.30 -> 3.50
# with two new capability gaps. Whether that is the full 1,387-name list
# inflating overlap or the filter under-crediting synonyms is unresolved;
# a profile owner happy with its calibration should not get either change
# silently. CLAUDE.md records the A/B method and the bar a revision must clear.
SKILLS_CONTEXT_FILTER_ENABLED = False
# A token shared by at least this many ledger names ("marketing", "data",
# "campaign") says nothing about any one skill, so it can't match alone.
_GENERIC_SKILL_TOKEN_DF = 4


def _skill_text(text: str) -> str:
    """Lowercase, punctuation to spaces (keeping + and # for C++/C#, and a
    dot only inside a token like outreach.io), padded so a phrase can be
    found on word boundaries with a plain `in`."""
    t = re.sub(r"[^a-z0-9+#.]+", " ", str(text).lower())
    t = re.sub(r"(?<![a-z0-9])\.|\.(?![a-z0-9])", " ", t)
    return " " + " ".join(t.split()) + " "


def _skill_phrases(name: str) -> list:
    """The ways a skill can appear in a posting: its full name, each
    parenthetical alias ("Customer relationship management (CRM) systems"
    -> "crm"), and each slash-separated part ("ETL / pipeline automation")."""
    outer = re.sub(r"\([^)]*\)", " ", name)
    parts = [outer] + re.findall(r"\(([^)]*)\)", name)
    phrases = []
    for p in parts:
        for piece in re.split(r"[,/;]| or ", p):
            s = _skill_text(piece).strip()
            if s:
                phrases.append(s)
    return phrases


def relevant_skill_names(names, jd_text: str) -> list:
    """The ledger names this posting mentions. A name matches when any of
    its phrases appears in the posting on word boundaries, or when one of
    its DISTINCTIVE tokens does -- "salesforce" in "Salesforce CRM" -- where
    distinctive means shared by fewer than _GENERIC_SKILL_TOKEN_DF names and
    at least 3 characters long. Lexical on purpose: deterministic and free
    per evaluation, where an embedding match would add an uncached API call
    to every one."""
    names = [n for n in names if str(n).strip()]
    jd = _skill_text(jd_text)
    if not jd.strip():
        return sorted(names, key=str.lower)
    tokens_by_name = {n: set(_skill_text(n).split()) for n in names}
    df = collections.Counter(t for toks in tokens_by_name.values() for t in toks)
    matched = []
    for n in names:
        if any(len(p) >= 2 and f" {p} " in jd for p in _skill_phrases(n)):
            matched.append(n)
            continue
        if any(
            len(t) >= 3 and df[t] < _GENERIC_SKILL_TOKEN_DF and f" {t} " in jd
            for t in tokens_by_name[n]
        ):
            matched.append(n)
    return sorted(matched, key=str.lower)


# Semantic half of the (disabled, see SKILLS_CONTEXT_FILTER_ENABLED) filter.
# Measured 2026-09-13 on a 1,387-name ledger: two UNRELATED skill names score
# above 0.806 only 1% of the time, while a skill's nearest other skill has a
# median of 0.887 -- so 0.82 admits near-synonyms ("CRM platform" ->
# "Salesforce CRM"), not topical neighbours.
SEMANTIC_SKILL_MATCH_THRESHOLD = 0.82
SEMANTIC_SKILL_MATCHES_PER_JD_SKILL = 3


def semantic_skill_matches(jd_skill_names) -> list:
    """Ledger skills close in MEANING to the posting's own extracted skills --
    what the lexical relevant_skill_names() misses when a posting and the
    ledger name the same skill differently. Uses embed_verified_skills.py's
    cached ledger vectors, only when their names_sha matches the current
    ledger, plus one embedding call for the posting's skills. Any failure
    returns [] -- lexical matching still applies."""
    if not jd_skill_names:
        return []
    try:
        import embed_verified_skills as evs
        import numpy as np
        from embed_bullet_bank import BATCH_SIZE, embed_batch

        names = evs.load_verified_skill_names()
        with open(evs.META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("names_sha") != evs._names_sha(names):
            return []
        ledger = np.load(evs.NPY_PATH)
        if len(ledger) != len(names):
            return []
        queries = list(jd_skill_names)
        vecs = []
        for i in range(0, len(queries), BATCH_SIZE):
            vecs.extend(embed_batch(queries[i : i + BATCH_SIZE], max_retries=2))
        q = np.array(vecs, dtype=np.float32)
        if q.ndim != 2 or q.shape[1] != ledger.shape[1]:
            return []
        q = q / (np.linalg.norm(q, axis=1, keepdims=True) + 1e-9)
        led = ledger / (np.linalg.norm(ledger, axis=1, keepdims=True) + 1e-9)
        sims = q @ led.T
        picked = set()
        for row in sims:
            for j in np.argsort(-row)[:SEMANTIC_SKILL_MATCHES_PER_JD_SKILL]:
                if row[j] >= SEMANTIC_SKILL_MATCH_THRESHOLD:
                    picked.add(names[int(j)])
        return sorted(picked, key=str.lower)
    except Exception:
        return []


def build_verified_skills_context(
    jd_text: str = "", jd_skill_names: list | None = None
) -> str:
    """The candidate's own confirmed tools/skills for evaluate_fit()'s user
    content, or "" when there is nothing to say.

    Ledgers only grow -- every skill-gap scan adds the posting skills the
    candidate confirms -- so above SKILLS_CONTEXT_FILTER_MIN names only the
    ones this posting mentions are sent. A skill the posting never names
    cannot raise tools_process_overlap or close a capability gap, and a
    1,407-name ledger cost ~7,500 tokens on every evaluation. The ledger can
    keep growing; the block stays the size of what the posting asks for.

    `tools_process_overlap` and `capability_gaps` used to be scored purely
    from profile.yml's narrative sections (target_roles/archetypes/
    narrative/superpowers) -- the candidate's real, concrete tool list
    (verified_tools.json, built up via Settings & Upkeep's skill-gap scans
    and skills menu) never reached this prompt at all, only the tailoring
    pipeline's knowledge-base load did. That meant "does this candidate
    know Salesforce" was an inference from prose, not a lookup against a
    list the candidate had actually confirmed. Sourced the same way
    find_unverified_jd_skill_gaps() already builds its "known" set, so the
    two can't disagree about what counts as verified.
    """
    try:
        import skills_menu
    except ImportError:
        return ""

    names = set()
    try:
        for t in (skills_menu._load_verified_tools() or {}).get("tools", []):
            name = (t.get("name") or "").strip()
            if name:
                names.add(name)
    except Exception:
        pass

    try:
        profile_data = profile_paths.profile_yaml() or {}
    except Exception:
        profile_data = {}
    for skills in (profile_data.get("skills") or {}).values():
        if isinstance(skills, list):
            for s in skills:
                s = str(s).strip()
                if s:
                    names.add(s)

    if not names:
        return ""

    instructions = (
        "This is the candidate's own confirmed toolset -- ground `tools_process_overlap` "
        "in this list rather than inferring it from narrative alone, and do not list "
        "something here as a `capability_gaps`/`stretch_evidence` item.\n"
    )
    if (
        not SKILLS_CONTEXT_FILTER_ENABLED
        or len(names) <= SKILLS_CONTEXT_FILTER_MIN
        or not str(jd_text).strip()
    ):
        return (
            "=== VERIFIED SKILLS & TOOLS (from verified_tools.json + profile.yml) ===\n"
            + instructions
            + ", ".join(sorted(names, key=str.lower))
        )

    matched = sorted(
        set(relevant_skill_names(names, jd_text))
        | set(semantic_skill_matches(jd_skill_names)),
        key=str.lower,
    )
    # No "N of M" count: v1's "65 of the candidate's 1,387" framing was the
    # likeliest reason one A/B role lost 0.8 interview odds with its overlap
    # subscore unchanged -- it reads as thin coverage, not as filtering.
    return (
        "=== VERIFIED SKILLS & TOOLS relevant to this posting (from verified_tools.json + profile.yml) ===\n"
        + instructions
        + "These are the candidate's confirmed skills that match this posting, by name or "
        "close meaning. A requirement not listed here may still be covered under another "
        "name -- weigh the narrative and background before listing it as a gap.\n"
        + (
            ", ".join(matched)
            if matched
            else "(none of the confirmed skills are named in this posting)"
        )
    )


def build_compensation_context(jd_text: str) -> str:
    """The pay block for evaluate_fit()'s user content, or "" when there is
    nothing useful to say.

    `compensation_viability` is 15% of the Practical Pursue score, and its
    schema field reads "vs. stated target/floor" -- but no floor was ever
    passed, so the model scored 15% of that dimension against a threshold
    it could not see, and its rubric ("5 = likely strong and viable")
    invited it to guess. Meanwhile compensation.py parses real figures
    deterministically and knows the configured floor exactly. This block
    is the wire between them.

    Three states, kept distinct on purpose. "Below your floor" and "not
    stated" are opposite facts, and collapsing them is what the old
    speculate-a-likely-range instruction did: about 73% of postings
    disclose nothing, so a model that guesses is inventing most of this
    subscore. An undisclosed salary is a real unknown and scores the
    middle -- it is not evidence of a bad offer.
    """
    try:
        import compensation
        import content_settings
    except ImportError:
        return ""

    try:
        config = (content_settings.read_settings() or {}).get("compensation") or {}
    except Exception:
        config = {}

    parsed = compensation.parse_compensation(jd_text or "")

    lines = []
    floor = compensation.floor_to_annual(config)
    if floor:
        lines.append(
            f"The candidate's minimum acceptable pay is ${floor:,.0f}/year "
            "(or the hourly equivalent)."
        )

    if parsed:
        lines.append(f"The posting states: {parsed.get('text') or 'a pay figure'}.")
        annual = parsed.get("annualized_max")
        if annual:
            lines.append(f"Annualized, the TOP of that range is ${annual:,.0f}/year.")
            if floor:
                verdict = "AT OR ABOVE" if annual >= floor else "BELOW"
                lines.append(f"That is {verdict} the candidate's floor.")
    else:
        lines.append(
            "The posting does NOT state pay. This is the normal case -- about "
            "73% of postings disclose nothing -- and it is NOT evidence that "
            "the pay is low. Score compensation_viability 3 (unknown) unless "
            "the posting itself gives real evidence about pay level. Do not "
            "infer a salary from the job title, seniority, or industry."
        )

    if not lines:
        return ""
    return "=== COMPENSATION (parsed deterministically, not by you) ===\n" + "\n".join(
        lines
    )


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
        f"{r['name']} (can go down to {r['min_bullets']} bullets total)"
        for r in flex_order
    )
    text = f"Remove the least-relevant bullets, starting with {order_text}"
    if protected:
        text += ", while protecting these specific bullets from removal: " + "; ".join(
            protected
        )
    else:
        text += "."
    return text


def _page1_condense_instruction(
    resume_data: dict, profile_data: dict, overflow_roles: list[str]
) -> str:
    """Builds the wording-only trim step used when a must_fit_page_1 role
    spilled onto page 2 despite the resume already being <=2 pages total
    (see _page1_overflow_roles) -- the fix the user wants isn't fewer
    bullets, it's a couple of the longest bullets on page 1 wrapping to one
    line instead of two, reclaiming just enough vertical space for the
    whole entry to fit. Targets the longest achievements among page-1
    roles by character count, since bullet length (not bullet count) is
    the wasted space causing the spill.
    """
    top = _page1_condense_targets(resume_data, profile_data)
    bullet_list = "\n".join(f'- ({company}) "{bullet}"' for _, company, bullet in top)
    roles_str = ", ".join(overflow_roles)
    return (
        f"{roles_str} must fit entirely on page 1 but is currently spilling onto page 2, "
        "even though the resume is already 2 pages or fewer overall -- each job entry is "
        "kept intact and never split across a page break, so the page-1 content above it "
        "just needs to run a little shorter. Tighten the wording of 1-2 of these longest "
        "page-1 bullets so each fits on ONE line (108 characters or fewer) -- shorten "
        "phrasing only, keep every metric, keyword, and the core claim intact, and do not "
        f"remove any bullet or change any other section:\n{bullet_list}"
    )


def _page1_overflow_trim(resume_data: dict, profile_data: dict):
    """Drops one bullet from profile.yml's `page1_overflow_trim_role` so a
    must_fit_page_1 role below it can rise onto page 1. Returns
    (new_resume_data, removed_bullet), or None when that role is unset,
    absent, already at its min_bullets, or has nothing unprotected to give.

    Condensing wording reclaims a line or two; a spilled job block is
    usually far taller (one profile's was ~10 lines, and five condense
    calls never moved it). A metric-free bullet goes first, then the
    longest, since it frees the most space."""
    trim_role = str((profile_data or {}).get("page1_overflow_trim_role") or "").strip()
    if not trim_role:
        return None
    key = validate_resume._normalize_company(trim_role)
    role_cfg: dict[str, Any] = next(
        (
            r
            for r in profile_data.get("roles") or []
            if validate_resume._normalize_company(str(r.get("name", ""))) == key
        ),
        {},
    )
    minimum = int(role_cfg.get("min_bullets") or 0)
    protected = [
        validate_resume._normalize_company(str(p).split(":")[0])
        for p in profile_data.get("protected_bullets") or []
    ]
    for j_index, job in enumerate(resume_data.get("EXPERIENCE") or []):
        company = validate_resume._normalize_company(job.get("company", ""))
        if key not in company and company not in key:
            continue
        bullets = list(job.get("achievements") or [])
        if len(bullets) <= minimum:
            return None
        candidates = [
            b
            for b in bullets
            if not any(
                p and p in validate_resume._normalize_company(b) for p in protected
            )
        ]
        if not candidates:
            return None
        victim = min(candidates, key=lambda b: (bool(re.search(r"\d", b)), -len(b)))
        trimmed = copy.deepcopy(resume_data)
        trimmed["EXPERIENCE"][j_index]["achievements"] = [
            b for b in bullets if b is not victim
        ]
        return trimmed, victim
    return None


def _page1_condense_targets(resume_data: dict, profile_data: dict) -> list:
    """The longest page-1 bullets, as (length, company, bullet)."""
    page1_companies = {
        str(role.get("name", "")).strip()
        for role in (profile_data.get("roles") or [])
        if role.get("page", 1) == 1
    }
    candidates = []
    for job in resume_data.get("EXPERIENCE", []):
        company = job.get("company", "")
        normalized = validate_resume._normalize_company(company)
        if not any(
            validate_resume._normalize_company(c) == normalized for c in page1_companies
        ):
            continue
        for bullet in job.get("achievements") or []:
            candidates.append((len(bullet), company, bullet))
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[:4]


def _merge_condensed_bullets(original: dict, condensed: dict, targets: set) -> dict:
    """Keeps only the condense call's edits to the targeted bullets.

    The call returns a whole resume, and wording drift in bullets it was never
    asked to touch added a dozen fresh widow violations per attempt, so every
    attempt of a 2026-09-16 build was discarded. A bullet is taken from the
    condensed copy only when it was a target and the job/position lines up."""
    merged = copy.deepcopy(original)
    new_jobs = condensed.get("EXPERIENCE") or []
    for i, job in enumerate(merged.get("EXPERIENCE") or []):
        if i >= len(new_jobs):
            break
        new_bullets = new_jobs[i].get("achievements") or []
        bullets = job.get("achievements") or []
        if len(new_bullets) != len(bullets):
            continue
        for j, bullet in enumerate(bullets):
            if bullet in targets and new_bullets[j]:
                bullets[j] = new_bullets[j]
    return merged


def _keep_clean_bullet_edits(original: dict, edited: dict, new_violations) -> dict:
    """Applies edited bullets one at a time, keeping each that introduces no
    violation (`new_violations(data)` returns the list). Bullets are aligned
    by job and position, as in _merge_condensed_bullets."""
    kept = copy.deepcopy(original)
    edited_jobs = edited.get("EXPERIENCE") or []
    for i, job in enumerate(kept.get("EXPERIENCE") or []):
        if i >= len(edited_jobs):
            break
        new_bullets = edited_jobs[i].get("achievements") or []
        bullets = job.get("achievements") or []
        if len(new_bullets) != len(bullets):
            continue
        for j, bullet in enumerate(list(bullets)):
            if not new_bullets[j] or new_bullets[j] == bullet:
                continue
            bullets[j] = new_bullets[j]
            if new_violations(kept):
                bullets[j] = bullet
    return kept


def _newly_introduced(violations: list, baseline: list) -> list:
    """Violations absent before an edit. Judging an edit by ALL violations
    rejected every condense attempt on a resume that already carried four
    leftover widows the edit never touched."""
    before = set(str(v) for v in baseline)
    return [v for v in violations if str(v) not in before]


def _why_backfill_instruction(resume_data: dict, research_block: str) -> str:
    """Builds the dedicated-call instruction used when the main builder call
    left WHY_TEXT blank but the rendered PDF turned out to have room for it
    (see the page-count-driven `needs_why_backfill` check in
    build_tailored_resume's Step 7 trim loop). Mirrors
    _page1_condense_instruction's shape: a targeted ask against the
    already-built resume_data, not a full re-generation.
    """
    tagline = resume_data.get("TAGLINE", "")
    summary = resume_data.get("SUMMARY_TEXT", "")
    return (
        "This resume currently has no 'Why [Company]?' section, and the rendered "
        "PDF has room for one -- write it now. Follow the Why [Company]? Section "
        "rules from the system instructions exactly (two short paragraphs, max 8 "
        "lines, first-person voice, only the first and last sentences italicized, "
        "grounded in the company research below and connected to this candidate's "
        "verified history). Do not change any other field.\n\n"
        f"=== CANDIDATE CONTEXT ===\nTagline: {tagline}\nSummary: {summary}\n\n"
        f"{research_block}"
    )


def build_verb_synonym_graph(style_rules: dict) -> dict[str, list[str]]:
    """Builds a mapping of verb -> list of strong alternatives from style_rules.yaml."""
    graph: dict[str, list[str]] = {}
    upgrades = style_rules.get("verb_upgrades", {})
    for _category, cat_data in upgrades.items():
        for item in cat_data.get("upgrades", []):
            strong_list = [
                v.lower() for v in item.get("strong", []) if isinstance(v, str)
            ]
            for verb in strong_list:
                for sibling in strong_list:
                    if sibling != verb:
                        graph.setdefault(verb, []).append(sibling)

    recommended = [
        v.lower()
        for v in style_rules.get("recommended_verbs", [])
        if isinstance(v, str)
    ]
    for verb, siblings in graph.items():
        seen = set(siblings)
        for rec in recommended:
            if rec != verb and rec not in seen:
                siblings.append(rec)
                seen.add(rec)
        graph[verb] = list(dict.fromkeys(siblings))

    for rec in recommended:
        if rec not in graph:
            graph[rec] = [v for v in recommended if v != rec]

    return graph


def auto_fix_duplicate_opening_verbs(
    resume_data: dict, style_rules: dict
) -> tuple[dict, bool]:
    """Deterministically swaps duplicate opening verbs using style_rules synonyms."""
    graph = build_verb_synonym_graph(style_rules)
    used_verbs: set[str] = set()
    modified = False

    for job in resume_data.get("EXPERIENCE", []):
        new_achievements = []
        for bullet in job.get("achievements", []):
            verb = validate_resume.opening_verb(bullet)
            if not verb:
                new_achievements.append(bullet)
                continue
            v_lower = verb.lower()
            if v_lower in used_verbs:
                candidates = graph.get(v_lower, [])
                chosen = next(
                    (cand for cand in candidates if cand.lower() not in used_verbs),
                    None,
                )
                if chosen:
                    orig_first_word = bullet.split()[0]
                    replacement = (
                        chosen.capitalize() if orig_first_word[0].isupper() else chosen
                    )
                    new_bullet = replacement + bullet[len(orig_first_word) :]
                    new_achievements.append(new_bullet)
                    used_verbs.add(chosen.lower())
                    modified = True
                    continue
            used_verbs.add(v_lower)
            new_achievements.append(bullet)
        job["achievements"] = new_achievements
    return resume_data, modified


def auto_fix_experience_order(
    resume_data: dict, role_roster: list[str] | None = None
) -> tuple[dict, bool]:
    """Deterministically restores EXPERIENCE reverse-chronological order from role_roster."""
    if not role_roster:
        return resume_data, False
    exp = resume_data.get("EXPERIENCE", [])
    if len(exp) <= 1:
        return resume_data, False

    normalized_roster = [validate_resume._normalize_company(c) for c in role_roster]

    def get_order_key(job: dict) -> int:
        entry = validate_resume._normalize_company(job.get("company", ""))
        if not entry:
            return 999
        if "career break" in entry or "professional development" in entry:
            return 998
        for i, needle in enumerate(normalized_roster):
            if needle and (needle in entry or entry in needle):
                return i
        return 999

    sorted_exp = sorted(exp, key=get_order_key)
    if sorted_exp != exp:
        resume_data["EXPERIENCE"] = sorted_exp
        return resume_data, True
    return resume_data, False


def auto_fix_forbidden_openers(
    resume_data: dict, style_rules: dict
) -> tuple[dict, bool]:
    """Deterministically strips or fixes forbidden openers in experience achievements."""
    openers = [o.lower() for o in style_rules.get("forbidden_openers", [])]
    if not openers:
        return resume_data, False
    modified = False
    for job in resume_data.get("EXPERIENCE", []):
        achievements = job.get("achievements", [])
        for idx, bullet in enumerate(achievements):
            for opener in openers:
                if bullet.lower().startswith(opener):
                    remainder = bullet[len(opener) :].strip()
                    if remainder:
                        repaired = remainder[0].upper() + remainder[1:]
                        achievements[idx] = repaired
                        modified = True
                        break
    return resume_data, modified


def _micro_refactor_single_bullet(bullet: str, style_rules: dict) -> str:
    """Uses a lightweight LLM call to rewrite a single bullet to satisfy length/widow bounds."""
    limits = style_rules.get("bullet_structure", {})
    max_chars = limits.get("one_liner_max_chars", 108)
    min_words = limits.get("widow_min_words", 5)

    prompt = f"""You are a professional resume editor. Rewrite this single bullet to satisfy ONE of these two strict layout rules:
Option 1: Trim to <= {max_chars} characters total so it fits cleanly on ONE printed line.
Option 2: Lengthen so the portion past character {max_chars} contains at least {min_words} words (a complete second line, not a short widow).

Current bullet ({len(bullet)} chars, leaves a short widow past char {max_chars}):
"{bullet}"

Return ONLY the rewritten bullet text with no quotes, commentary, or markdown."""
    try:
        repaired, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction="",
            contents=prompt,
            temperature=0.2,
        )
        cleaned = repaired.strip().strip('"').strip("'") if repaired else bullet
        return cleaned if cleaned else bullet
    except Exception:
        return bullet


def _micro_refactor_skills_line(line: str, style_rules: dict) -> str:
    """Uses a lightweight LLM call to rewrite a single skills line out of the dead band."""
    skills_section = style_rules.get("skills_section", {})
    max_chars = skills_section.get("line_max_chars", 110)
    widow_min_chars = skills_section.get("widow_min_chars", 25)
    wrap_min = max_chars + widow_min_chars

    prompt = f"""You are a resume editor. The following skills line is in an illegal dead band (between {max_chars + 1} and {wrap_min - 1} characters) where it wraps to a 2nd line but leaves a short widow:
"{line}"

Rewrite this line to satisfy ONE of these constraints:
Option 1 (preferred): Trim items or shorten category label so total length is <= {max_chars} characters (1 printed line).
Option 2: Lengthen the SAME items (spell out an abbreviation, name a sub-area of a skill already listed) so total length is >= {wrap_min} characters and <= {2 * max_chars} characters (2 full lines).

Never add a tool, platform or skill that is not already in the line -- every item must be one the candidate is already credited with.
Keep the **Category Name:** format. Return ONLY the rewritten skills line."""
    try:
        repaired, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction="",
            contents=prompt,
            temperature=0.2,
        )
        cleaned = repaired.strip().strip('"').strip("'") if repaired else line
    except Exception:
        return line
    if not cleaned:
        return line
    # This step used to be told to "add 1-2 relevant skills" with no list of
    # what the candidate actually has, so it padded lines with tools they'd
    # never used (Snowflake, Spark, Docker) -- which the hallucination check
    # then rejected, failing whole builds (2026-09-14). Keep the original
    # line rather than accept a rewrite that introduces an unverified item.
    try:
        before = len(validate_resume._check_hallucinated_tools({"SKILLS": [line]}))
        after = len(validate_resume._check_hallucinated_tools({"SKILLS": [cleaned]}))
    except Exception:
        return cleaned
    return line if after > before else cleaned


# Header under which build_recruiter_resume.build_target_brief() appends the
# candidate's whole cv.md. Shared so the writer and the gate below can never
# disagree about where the brief ends and the supporting evidence begins.
RECRUITER_CV_MARKER = "=== CANDIDATE CV (supporting evidence) ==="


def _situational_gate_text(jd_text: str) -> str:
    """The part of a JD the situational-role keyword gate may read.

    For a real posting that is all of it. A recruiter brief, though, embeds
    the candidate's entire CV as supporting evidence -- and a CV describes
    every situational job the candidate has held, so its trigger words
    ("payroll", "newspaper", "graphic design") are all there by definition.
    Gating on it cleared every situational role on every recruiter build: 7
    of 7 on one profile, versus 0 from the brief's own role list. The gate
    asks whether the ROLES being targeted call for that experience; the CV
    is the answer to a different question."""
    return (jd_text or "").split(RECRUITER_CV_MARKER, 1)[0]


_SKILLS_LINE_LABEL = re.compile(r"^\s*\*\*(?P<label>[^*]+?):\*\*\s*(?P<items>.*)$")


def _parse_cv_skill_groups(cv_text: str) -> dict:
    """Maps each skill in cv.md's "## Core Skills" block to its own category
    label, casefolded -> label. That grouping is the only trustworthy source
    for WHERE a skill belongs: verified_tools.json's `category` is None for
    the large majority of entries (58 of 71 on the profile this was built
    for), so routing on it would silently place almost everything nowhere --
    or, worse, anywhere."""
    groups: dict[str, str] = {}
    in_block = False
    parent = None
    for raw in (cv_text or "").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_block = line[3:].strip().casefold() == "core skills"
            continue
        if not in_block:
            continue
        # A bare "**Email & Lifecycle Marketing**" heads nested
        # "* **Operations & Stack:** ..." rows. The resume's skills lines use
        # the heading, so its sub-rows' skills belong to it; reading only
        # one-line groups left every nested skill with no home at all.
        heading = re.match(r"^\*\*(?P<label>[^*:]+)\*\*$", line)
        if heading:
            parent = heading.group("label").strip()
            continue
        nested = re.match(r"^[*-]\s+", line)
        if not nested:
            parent = None
        match = _SKILLS_LINE_LABEL.match(line[nested.end() :] if nested else line)
        if not match:
            continue
        label = parent if (nested and parent) else match.group("label").strip()
        # "AWS (Glue, SageMaker, S3, RDS)" is four skills, not one: a naive
        # comma split yields "AWS (Glue" and "RDS)", so S3 gets a group and
        # RDS silently does not -- which is what made RDS look structurally
        # unplaceable when it was only ever a parsing bug.
        for item in re.sub(r"[()]", " ", match.group("items")).split(","):
            # Collapsed, because stripping the parens leaves "AWS  Glue"
            # double-spaced and these keys are looked up against items as
            # they are RENDERED on a skills line ("AWS Glue").
            item = re.sub(r"\s+", " ", item).strip()
            if item:
                groups.setdefault(item.casefold(), label)
    return groups


def _skill_tokens(text: str) -> set:
    return {t.casefold() for t in re.findall(r"[A-Za-z0-9]+", text or "")}


def _skill_line_items(line: str) -> tuple:
    match = _SKILLS_LINE_LABEL.match(line or "")
    if not match:
        return None, []
    items = [i.strip() for i in match.group("items").split(",") if i.strip()]
    return match.group("label").strip(), items


def _compose_skills_line(label: str, items: list) -> str:
    return f"**{label}:** " + ", ".join(items)


def _plain_skills_line(line: str) -> str:
    """The line as it is PRINTED -- the bold markup around the label is not
    rendered, so it must not be measured. Deliberately the same substitution
    validate_resume._check_skills_line_lengths applies, because a geometry
    judgment made here and a violation reported there must agree about how
    wide a line is."""
    return re.sub(r"\*\*(.+?)\*\*", r"\1", line or "")


def _skills_line_legal(line: str, max_chars: int, wrap_min: int) -> bool:
    """One printed line, or two full ones -- never the widow dead band in
    between (the same geometry _micro_refactor_skills_line repairs).

    Measured on the PRINTED width. Counting the label's four asterisks made
    every line read 4 chars longer than it renders, so an append could be
    refused for crossing a limit the rendered line never reaches -- and the
    validator, which strips the markup, would then have passed the very line
    this step declined to produce."""
    length = len(_plain_skills_line(line))
    return length <= max_chars or (wrap_min <= length <= 2 * max_chars)


def _title_case_skill(name: str) -> str:
    """ "supervised & unsupervised learning" -> "Supervised & Unsupervised
    Learning", but "spaCy" and "NLTK" are left exactly as the ledger spells
    them. Skills lines are Title Case by style rule, and the validator
    reports lowercase words on them as a violation -- so appending a
    ledger name verbatim would fix a coverage miss by introducing a style
    one. A token carrying any uppercase of its own is already spelled the
    way its owner spells it; only all-lowercase words are touched."""
    return " ".join(
        word.capitalize() if word.islower() else word
        for word in (name or "").split(" ")
    )


def _label_tokens(label: str) -> set:
    return {t for t in re.findall(r"[A-Za-z]+", label or "") if len(t) > 3}


# A ledger name longer than this is a sentence, not a skills-line item
# ("Technical documentation for cross-functional/non-technical
# stakeholders"). It still proves the skill is verified; the concise form
# of the keyword itself is what gets rendered.
_LEDGER_FORM_MAX_CHARS = 45


def _resolve_verified_skill(
    keyword: str, ledger_names: list, cv_groups: dict
) -> tuple | None:
    """Returns (render_forms, cv_label) for a keyword the candidate can be
    shown to already have, else None.

    Evidence is deliberately looser than an exact ledger-name match -- "S3"
    is verified by the ledger's "AWS S3", and "technical documentation" by
    a cv.md entry that spells out the audience -- because nothing here is
    trusted on the strength of the match alone: the caller re-runs the
    coverage check and keeps the append only if the keyword actually moved
    to matched. That verification is what makes the looseness safe.

    A keyword with evidence but no cv.md group still returns None: knowing
    the candidate has a skill is not knowing where it belongs."""
    keyword_tokens = _skill_tokens(keyword)
    if not keyword_tokens:
        return None

    forms = []
    verified = False
    for name in ledger_names:
        name_tokens = _skill_tokens(name)
        if keyword_tokens == name_tokens:
            verified = True
            forms.append(name)
        elif keyword_tokens < name_tokens:
            verified = True
            if len(name) <= _LEDGER_FORM_MAX_CHARS:
                forms.append(name)

    label = None
    for item, group in cv_groups.items():
        item_tokens = _skill_tokens(item)
        if keyword_tokens == item_tokens or keyword_tokens < item_tokens:
            verified = True
            label = group
            break

    if not verified or not label:
        return None

    forms.append(str(keyword).strip())
    ordered, seen = [], set()
    for form in forms:
        cased = _title_case_skill(form)
        if cased.casefold() not in seen:
            seen.add(cased.casefold())
            ordered.append(cased)
    return ordered, label


# How many one-line skills rows the top-up may grow into two in one build.
MAX_SKILLS_ROWS_NEWLY_WRAPPED = 2


def _ledger_verifies(keyword: str, ledger_names: list) -> bool:
    keyword_tokens = _skill_tokens(keyword)
    return bool(keyword_tokens) and any(
        keyword_tokens <= _skill_tokens(name) for name in ledger_names
    )


def _assign_skill_groups_with_model(keywords: list, labels: list) -> dict:
    """One small call: which of these existing skills rows does each verified
    skill belong on? Returns {keyword: label}; unsure answers are omitted."""
    prompt = (
        "Place each skill on the resume skills row it most naturally belongs to. "
        "Use ONLY the row labels given, spelled exactly. If no row clearly fits a "
        "skill, leave that skill out rather than forcing it.\n\n"
        "ROWS:\n"
        + "\n".join(f"- {l}" for l in labels)
        + "\n\nSKILLS:\n"
        + "\n".join(f"- {k}" for k in keywords)
        + '\n\nReturn JSON: {"placements": [{"skill": "...", "row": "..."}]}'
    )
    text, _usage = GeminiClient.generate(
        model=BUILDER_MODEL,
        system_instruction="You organize resume skills sections. Return only JSON.",
        contents=prompt,
        temperature=0.0,
        max_retries=2,
    )
    data = GeminiClient.parse_json(text or "") or {}
    return {
        str(p.get("skill", "")).strip(): str(p.get("row", "")).strip()
        for p in data.get("placements") or []
        if isinstance(p, dict)
    }


def _place_verified_skill(
    lines: list,
    form: str,
    label: str,
    targets: list,
    cv_groups: dict,
    max_chars: int,
    wrap_min: int,
) -> list | None:
    """Returns a new SKILLS list with `form` placed under `label`, or None
    when it cannot be placed legally."""
    new_lines = list(lines)
    if targets:
        index = targets[0]
        candidate = f"{new_lines[index].rstrip().rstrip(',')}, {form}"
        if not _skills_line_legal(candidate, max_chars, wrap_min):
            return None
        new_lines[index] = candidate
        return new_lines

    # The cv.md group has no line on the page at all, so make one -- and
    # bring home the items already rendered elsewhere that belong to it.
    # Relocation is deliberately limited to this case: moving an item whose
    # group ALREADY has a line only shuffles crowding around, and on a real
    # build it pushed a line that was exactly at the limit into the dead
    # band, losing two keywords to gain none.
    moved = []
    for i, line in enumerate(new_lines):
        line_label, items = _skill_line_items(line)
        if line_label is None:
            continue
        belongs = [it for it in items if cv_groups.get(it.casefold()) == label]
        keep = [it for it in items if cv_groups.get(it.casefold()) != label]
        # Never strip a line empty to fill a new one.
        if not belongs or not keep:
            continue
        rebuilt = _compose_skills_line(line_label, keep)
        if not _skills_line_legal(rebuilt, max_chars, wrap_min):
            continue
        new_lines[i] = rebuilt
        moved.extend(belongs)

    created = _compose_skills_line(label, moved + [form])
    if not _skills_line_legal(created, max_chars, wrap_min):
        return None
    new_lines.append(created)
    return new_lines


def _skills_add_hallucinated_tool(old_lines: list, new_lines: list) -> bool:
    try:
        before = len(validate_resume._check_hallucinated_tools({"SKILLS": old_lines}))
        after = len(validate_resume._check_hallucinated_tools({"SKILLS": new_lines}))
    except Exception:
        return True
    return after > before


def _keyword_now_credited(
    resume_data: dict, new_lines: list, jd_keywords: dict, keyword: str
) -> bool:
    """The whole safety model: an edit is kept only if the check it exists
    to satisfy agrees the keyword is now present."""
    trial = dict(resume_data)
    trial["SKILLS"] = new_lines
    try:
        still = (
            validate_resume.check_keyword_coverage(trial, jd_keywords, {}).get(
                "missing"
            )
            or []
        )
    except Exception:
        return False
    target = str(keyword).strip().casefold()
    return not any(str(m).strip().casefold() == target for m in still)


def _drop_target_role_titles(jd_keywords, profile_data: dict):
    """Removes keywords that are just one of the candidate's target_roles.

    The recruiter build's brief lists those titles, and extraction read them
    as skills: "Email Marketing Specialist" can never be matched by a resume,
    so each one was a guaranteed miss (16 of 28 on 2026-09-16) and an item
    the post-build prompt offered to add to the verified ledger. A title is
    not a skill in a real posting either."""
    if not isinstance(jd_keywords, dict):
        return jd_keywords
    targets = (profile_data or {}).get("target_roles") or {}
    titles = set()
    for group in (targets.values() if isinstance(targets, dict) else [targets]):
        for title in group if isinstance(group, list) else [group]:
            if isinstance(title, str) and title.strip():
                titles.add(title.strip().casefold())
    if not titles:
        return jd_keywords
    cleaned = dict(jd_keywords)
    for key in ("tools", "hard_skills", "core_functions"):
        if isinstance(cleaned.get(key), list):
            cleaned[key] = [
                k
                for k in cleaned[key]
                if not (isinstance(k, str) and k.strip().casefold() in titles)
            ]
    return cleaned


def verified_jd_skills(jd_keywords, verified_names: list) -> list:
    """JD tools/hard skills the ledger verifies, in JD order. Handed to the
    builder so it fills SKILLS with these first -- the post-build top-up can
    only squeeze items into space the builder already spent."""
    if not isinstance(jd_keywords, dict):
        return []
    ledger = [str(n).strip() for n in verified_names or [] if str(n or "").strip()]
    seen, out = set(), []
    for key in ("tools", "hard_skills"):
        for k in jd_keywords.get(key) or []:
            if isinstance(k, str) and k.strip() and k.casefold() not in seen:
                if _ledger_verifies(k, ledger):
                    seen.add(k.casefold())
                    out.append(k.strip())
    return out


def _top_up_verified_skills(
    resume_data: dict,
    jd_keywords: dict,
    style_rules: dict,
    cv_text: str,
    verified_names: list,
    assign_groups=None,
) -> tuple:
    """Appends JD keywords the candidate is ALREADY verified for, but which
    the finished resume happens not to say, onto the matching SKILLS line.
    Returns (new_resume_data, added_names); never mutates its input.

    Deterministic and LLM-free. The keyword-coverage check is the thing
    being satisfied, so this asks that same function which keywords are
    missing -- and then re-asks it to confirm each edit actually landed,
    so the fix and the check it satisfies cannot disagree about what
    counts as present.

    Every candidate is evidenced by the verified ledger or the candidate's
    own cv.md, which is what makes this safe where the old "add 1-2
    relevant skills" prompt was not (see _micro_refactor_skills_line):
    there is nothing here to invent. Evidence alone is not enough, though.
    An edit is kept only when the coverage check credits the keyword
    afterwards, which is what lets the match be loose enough to see that
    "S3" is the ledger's "AWS S3" without a loose match ever talking
    itself into a placement.

    Skips rather than guesses: an unevidenced keyword, a skill cv.md
    doesn't group, and a group with two plausible homes are all left
    alone. A resume silent about spaCy is a small loss; one listing spaCy
    under "Visualization & Communication" because that line had room is a
    wrong resume."""
    skills = resume_data.get("SKILLS")
    if not skills or not jd_keywords:
        return resume_data, []
    try:
        missing = (
            validate_resume.check_keyword_coverage(resume_data, jd_keywords, {}).get(
                "missing"
            )
            or []
        )
    except Exception:
        return resume_data, []
    if not missing:
        return resume_data, []

    ledger = [str(n).strip() for n in verified_names if str(n or "").strip()]
    cv_groups = _parse_cv_skill_groups(cv_text)
    skills_section = (style_rules or {}).get("skills_section", {})
    max_chars = skills_section.get("line_max_chars", 110)
    wrap_min = max_chars + skills_section.get("widow_min_chars", 25)

    lines = list(skills)
    # cv.md cannot group every ledger skill, so verified keywords it does not
    # group are handed to `assign_groups` (one model call at the build site):
    # it picks a home among the rows already on the page, or none. Its answer
    # only supplies a LOCATION -- the ledger still has to verify the skill,
    # and the coverage check still has to credit the edit.
    if assign_groups:
        ungrouped = [
            k
            for k in missing
            if _ledger_verifies(k, ledger)
            and not _resolve_verified_skill(k, ledger, cv_groups)
        ]
        labels = [
            _skill_line_items(line)[0] for line in lines if _skill_line_items(line)[0]
        ]
        if ungrouped and labels:
            try:
                assigned = assign_groups(ungrouped, labels) or {}
            except Exception:
                assigned = {}
            cv_groups = dict(cv_groups)
            for keyword, label in assigned.items():
                if label in labels and keyword in ungrouped:
                    cv_groups.setdefault(str(keyword).casefold(), label)

    added = []
    deferred = []
    for keyword in missing:
        resolved = _resolve_verified_skill(keyword, ledger, cv_groups)
        if not resolved:
            continue
        forms, label = resolved
        wanted = _label_tokens(label)
        # The row already holding this group's own skills is its home, even
        # when the model renamed the row ("CRM & RevOps" lists Data Hygiene,
        # which cv.md files under "CRM & Marketing Operations") -- a shared
        # word like "Marketing" would otherwise point at the wrong row.
        kin = {
            i: sum(
                1
                for item in _skill_line_items(line)[1]
                if cv_groups.get(item.casefold()) == label
            )
            for i, line in enumerate(lines)
        }
        # One stray item is a misplacement to move, not a home; two is a home.
        best_kin = max(kin.values(), default=0)
        if best_kin >= 2:
            targets = [i for i in kin if kin[i] == best_kin]
        else:
            targets = [
                i
                for i, line in enumerate(lines)
                if wanted & _label_tokens(_skill_line_items(line)[0])
            ]
        # A shared word ("Marketing" in both "Email & Lifecycle Marketing" and
        # "CRM & Marketing Operations") is not a tie when one label matches
        # far better; keep only the strongest overlap before judging.
        if len(targets) > 1:
            overlap = {
                i: len(wanted & _label_tokens(_skill_line_items(lines[i])[0]))
                for i in targets
            }
            best = max(overlap.values())
            targets = [i for i in targets if overlap[i] == best]
        # Two plausible homes is not a placement.
        if len(targets) > 1:
            continue
        # Forms run most-specific first (the ledger's own name), falling back
        # to the keyword's concise form when the ledger spells it as a
        # sentence. The first one that places legally and earns credit wins.
        placed = False
        for form in forms:
            trial = _place_verified_skill(
                lines, form, label, targets, cv_groups, max_chars, wrap_min
            )
            if trial is None:
                continue
            if _skills_add_hallucinated_tool(lines, trial):
                continue
            if not _keyword_now_credited(resume_data, trial, jd_keywords, keyword):
                continue
            lines = trial
            added.append(form)
            placed = True
            break
        if not placed and len(targets) == 1:
            deferred.append((targets[0], keyword, forms[-1]))

    # One item rarely fits a nearly-full row: it lands in the widow dead band.
    # Several together can FILL a second line, which is legal. Only
    # MAX_SKILLS_ROWS_NEWLY_WRAPPED rows may grow this way, so a keyword-heavy
    # posting cannot turn every row into two.
    wrapped = 0
    by_row: dict[int, list[tuple[str, str]]] = {}
    for index, keyword, form in deferred:
        by_row.setdefault(index, []).append((keyword, form))
    for index, items in sorted(by_row.items(), key=lambda kv: -len(kv[1])):
        if wrapped >= MAX_SKILLS_ROWS_NEWLY_WRAPPED:
            break
        base = lines[index]
        if len(_plain_skills_line(base)) > max_chars:
            continue
        kept, trial = [], list(lines)
        for keyword, form in items:
            attempt = list(trial)
            attempt[index] = f"{attempt[index].rstrip().rstrip(',')}, {form}"
            if len(_plain_skills_line(attempt[index])) > 2 * max_chars:
                break
            if _skills_add_hallucinated_tool(trial, attempt):
                continue
            if not _keyword_now_credited(resume_data, attempt, jd_keywords, keyword):
                continue
            trial = attempt
            kept.append(form)
        if kept and _skills_line_legal(trial[index], max_chars, wrap_min):
            lines = trial
            added.extend(kept)
            wrapped += 1

    if not added:
        return resume_data, []
    result = dict(resume_data)
    result["SKILLS"] = lines
    return result, added


def _micro_dedupe_metric(
    text: str, number: str, other_metrics: list[str], field_label: str
) -> str:
    """Uses a lightweight LLM call to remove one duplicated metric from a
    single resume field, leaving everything else in it unchanged.

    Same narrow, single-field idiom as _micro_refactor_single_bullet/
    _micro_refactor_skills_line above -- a full-resume regenerate already
    proved unable to fix this: a real 2026-09-03 build returned the exact
    same "Metric '100+' should appear only once ... Summary and a bullet"
    violation across all 4 fix attempts (see the stall-escalation comment
    in build_tailored_resume, and gemini_client.generate's
    temperature-forced-to-0.0-under-response_schema bug this exposed).
    """
    other = ", ".join(m for m in other_metrics if m != number) or "none"
    prompt = f"""You are a professional resume editor. This {field_label} states the figure '{number}', which is ALSO stated in another part of the resume -- the same fact should not be repeated verbatim in two places.

Current {field_label}:
"{text}"

Rewrite it so it no longer states '{number}'. Either drop that clause/figure entirely if the sentence reads fine without it, or replace it with different, true, non-numeric language describing the same accomplishment -- do not invent a new number and do not use any of these figures already used elsewhere in the resume: {other}

Return ONLY the rewritten text, no quotes or commentary."""
    try:
        repaired, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction="",
            contents=prompt,
            temperature=0.2,
        )
        cleaned = repaired.strip().strip('"').strip("'") if repaired else text
        return cleaned if cleaned else text
    except Exception:
        return text


def _micro_strip_pronoun(text: str) -> str:
    """Uses a lightweight LLM call to rewrite a single Summary/Skills/bullet
    field so it no longer contains a first- or third-person pronoun (I, me,
    my, we, our, she, her, hers, he, him, his), preserving every fact.

    Same narrow, single-field idiom as _micro_dedupe_metric above -- no
    repair existed for validate_resume._check_pronouns_outside_why()'s
    violation at all until now, and a real 2026-09-04 build reduced every
    other fatal violation to zero across 4 fix attempts while this one
    ("Recruited by the CEO to lead brand design at his next venture...")
    alone survived unchanged, since the LLM full-resume retry loop had no
    narrower instruction than to restate the same global rule.
    """
    prompt = f"""You are a professional resume editor. This resume text contains a pronoun (I, me, my, we, our, she, her, hers, he, him, or his), which is not allowed outside the Why section.

Current text:
"{text}"

Rewrite it so it contains no such pronoun, preserving every fact (who did what, to whom, with what result) -- usually this means naming the person/entity the pronoun referred to instead of using the pronoun, or rephrasing the clause so no pronoun is needed. Do not invent new facts.

Return ONLY the rewritten text, no quotes or commentary."""
    try:
        repaired, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction="",
            contents=prompt,
            temperature=0.2,
        )
        cleaned = repaired.strip().strip('"').strip("'") if repaired else text
        return cleaned if cleaned else text
    except Exception:
        return text


def _micro_fix_metric_provenance(
    bullet: str, company: str, bullet_tuples: list[tuple[str, str, str]]
) -> str:
    """Uses a lightweight LLM call to rewrite a single bullet that cites a
    metric absent from its own company's bullet-bank source -- see
    validate_resume._check_metric_provenance()'s docstring for the real
    2026-09-04 case this covers (a fabricated cross-company "100+" figure
    that only ever appeared in an unrelated Treering Yearbooks bullet).
    Grounds the rewrite in that company's OWN real bullets only, so the
    model can't repeat the mistake by reaching for a different bullet's
    number again."""
    # Loose containment, matching _check_metric_provenance()'s own lookup:
    # the builder writes cv.md's company ("mIQroTech Inc.") while the bank
    # tags one specific stint ("mIQroTech Inc. — Lead Data Scientist"). Exact
    # equality found no source bullets at all, so this repair silently
    # returned the bullet unchanged and the retry loop burned all four
    # attempts on a metric that was sitting in the bank the whole time.
    needle = validate_resume._normalize_company(company)
    source_bullets = [
        b
        for b, c, _tags in bullet_tuples
        if needle
        and (
            needle in validate_resume._normalize_company(c)
            or validate_resume._normalize_company(c) in needle
        )
    ]
    if not source_bullets:
        return bullet
    source_block = "\n".join(f"- {b}" for b in source_bullets)
    prompt = f"""You are a professional resume editor. This bullet cites a metric or figure that does not appear anywhere in this candidate's own verified source bullets for this same company -- it may have been fabricated or borrowed from an unrelated bullet.

Bullet to fix:
"{bullet}"

This candidate's REAL verified source bullets for this exact company (the only material you may draw facts, scope, or metrics from):
{source_block}

Rewrite the bullet so every metric and factual claim in it is grounded in the source bullets above -- either select/lightly adapt one of them directly, or remove the unverifiable metric/claim entirely rather than keep it. Do not invent a new number. Preserve the original bullet's general topic if a matching source bullet supports it.

Return ONLY the rewritten bullet text, no quotes or commentary."""
    try:
        repaired, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction="",
            contents=prompt,
            temperature=0.2,
        )
        cleaned = repaired.strip().strip('"').strip("'") if repaired else bullet
        return cleaned if cleaned else bullet
    except Exception:
        return bullet


def _fields_containing_word(
    current_data: dict, word: str
) -> list[tuple[str, int, int, str]]:
    """Returns (field, job_idx, bullet_idx, text) for every Summary/Why/
    Experience-bullet field containing `word` (whole-word, case-
    insensitive). job_idx/bullet_idx are only meaningful for
    'ACHIEVEMENT'. The SKILLS section is deliberately excluded -- see
    _micro_trim_keyword_density's docstring."""
    pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
    hits: list[tuple[str, int, int, str]] = []
    summary = current_data.get("SUMMARY_TEXT", "") or ""
    if pattern.search(summary):
        hits.append(("SUMMARY_TEXT", -1, -1, summary))
    why = current_data.get("WHY_TEXT", "") or ""
    if pattern.search(why):
        hits.append(("WHY_TEXT", -1, -1, why))
    for j_idx, job in enumerate(current_data.get("EXPERIENCE", [])):
        for b_idx, bullet in enumerate(job.get("achievements", [])):
            if pattern.search(bullet):
                hits.append(("ACHIEVEMENT", j_idx, b_idx, bullet))
    return hits


def _micro_trim_keyword_density(
    current_data: dict, word: str, reduce_by: int
) -> tuple[dict, bool]:
    """Uses one lightweight LLM call to reword just enough occurrences of
    an overused keyword to bring its density back under the ATS ceiling.

    Scoped to SUMMARY_TEXT/WHY_TEXT/Experience bullets only -- the SKILLS
    section is left untouched, since an exact keyword match there is the
    point of that section (what a recruiter's ATS search actually scans
    for), not the prose repetition this check exists to catch. Same
    single-call, narrow-scope idiom as _micro_refactor_single_bullet
    above: a full-resume regenerate already proved unable to fix this --
    a real 2026-09-03 build returned the exact same "Keyword 'content'
    appears 16 times (3.8%)" violation across all 4 fix attempts.
    """
    hits = _fields_containing_word(current_data, word)
    if not hits or reduce_by <= 0:
        return current_data, False

    fields_block = "\n".join(
        f"{i}. [{field}] {text!r}" for i, (field, _, _, text) in enumerate(hits)
    )
    prompt = f"""You are a professional resume editor. The keyword '{word}' is overused across this resume ({len(hits)} field(s) below contain it) and needs at least {reduce_by} fewer total occurrence(s) to pass an ATS keyword-density check.

Fields containing '{word}':
{fields_block}

Rewrite as few of these fields as necessary -- using natural, true synonyms in place of some occurrences of '{word}' -- so the TOTAL number of times '{word}' appears across all fields drops by at least {reduce_by}. Leave every field you don't need to touch completely unchanged. Do not change anything else about the fields you do edit besides replacing the word.

Return ONLY a JSON array with exactly {len(hits)} strings, one per field above in the same order (unchanged fields repeated verbatim), no commentary."""
    try:
        repaired, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction="",
            contents=prompt,
            temperature=0.2,
        )
        new_texts = GeminiClient.parse_json(repaired or "")
        if not isinstance(new_texts, list) or len(new_texts) != len(hits):
            return current_data, False
    except Exception:
        return current_data, False

    modified = False
    for (field, j_idx, b_idx, old_text), new_text in zip(hits, new_texts):
        if not isinstance(new_text, str) or new_text == old_text:
            continue
        if field == "SUMMARY_TEXT":
            current_data["SUMMARY_TEXT"] = new_text
        elif field == "WHY_TEXT":
            current_data["WHY_TEXT"] = new_text
        else:
            current_data["EXPERIENCE"][j_idx]["achievements"][b_idx] = new_text
        modified = True
    return current_data, modified


# Mirrors normalize_resume._RENAME_SUFFIX_PATTERN (private to that module) --
# cv.md spells a renamed company as "Callahan Creek (Now Callahan)"; this
# strips the parenthetical before matching against profile.yml's plain name.
_RENAME_SUFFIX_PATTERN = re.compile(r"\s*\(Now [^)]+\)$")


def _parse_cv_role_metadata(cv_text: str) -> dict[str, dict]:
    r"""Parses cv.md's '### Title\n**Company** · Location · Period' blocks into
    a normalized-company -> {title, period, location} lookup.

    Exists so a missing EXPERIENCE entry (a 'Role roster' violation the LLM
    fix loop failed to restore -- see the Role roster block in
    repair_violations_surgically) can be synthesized deterministically, with
    real title/period/location, instead of either failing the whole build or
    burning another LLM call on a single missing entry. cv.md is hand-
    maintained and this exact header shape is a stable convention, not
    inferred -- see cv.md itself.
    """
    metadata: dict[str, dict] = {}
    pattern = re.compile(
        r"^###\s+(?P<title>.+?)\s*\n\*\*(?P<company>[^*]+?)\*\*\s*(?P<rest>.*)$",
        re.MULTILINE,
    )
    for m in pattern.finditer(cv_text or ""):
        title = m.group("title").strip()
        company_raw = _RENAME_SUFFIX_PATTERN.sub("", m.group("company").strip())
        parts = [p.strip() for p in m.group("rest").split("·") if p.strip()]
        location, period = "", ""
        if len(parts) >= 2:
            location, period = parts[0], parts[1]
        elif len(parts) == 1:
            # A period always contains a year; a bare location never does.
            if any(ch.isdigit() for ch in parts[0]):
                period = parts[0]
            else:
                location = parts[0]
        key = validate_resume._normalize_company(company_raw)
        if key:
            metadata[key] = {"title": title, "location": location, "period": period}
    return metadata


def _lookup_role_metadata(role_metadata: dict, company: str) -> dict:
    """Loose containment match, mirroring validate_resume._normalize_company's
    matching rules -- profile.yml and cv.md don't always spell a company
    identically ('Element 8 / Strategy LLC' vs 'Element 8 + Strategy, LLC')."""
    needle = validate_resume._normalize_company(company)
    if needle in role_metadata:
        return role_metadata[needle]
    for key, meta in role_metadata.items():
        if key and (needle in key or key in needle):
            return meta
    return {}


def partition_violations(violations: list[str]) -> tuple[list[str], list[str]]:
    """Partitions violations into (fatal_blockers, soft_warnings).
    Soft warnings are purely aesthetic line-wrap/widow warnings. All content,
    schema, keyword, roster, role, and integrity violations are fatal blockers."""
    soft = []
    fatal = []
    for v in violations:
        if (
            "wraps to a 2nd line" in v
            or "short widow" in v
            or "dead band" in v
            or "wrap to a 3rd line" in v
            # A wording-quality nudge: worth a fix attempt, never a failed build.
            or v.startswith("Vague magnitude")
            or v.startswith("Vague count")
            or v.startswith("Generic filler line")
            or v.startswith("Prose rhythm")
            or v.startswith("Date anchor")
            or v.startswith("Advisory word")
        ):
            soft.append(v)
        else:
            fatal.append(v)
    return fatal, soft


def repair_violations_surgically(
    resume_data: dict,
    violations: list[str],
    style_rules: dict,
    role_roster: list[str] | None = None,
    role_bullet_minimums: dict[str, int] | None = None,
    bullet_tuples: list[tuple[str, str, str]] | None = None,
    role_bullet_maximums: dict[str, int] | None = None,
    role_metadata: dict | None = None,
) -> tuple[dict, list[str]]:
    """Mutates only the specific violating fields in-place, avoiding full-document resynthesis."""
    current_data = copy.deepcopy(resume_data)

    # 1. Deterministic Swaps First (0ms, zero tokens)
    current_data, verb_modified = auto_fix_duplicate_opening_verbs(
        current_data, style_rules
    )
    current_data, order_modified = auto_fix_experience_order(current_data, role_roster)
    current_data, opener_modified = auto_fix_forbidden_openers(
        current_data, style_rules
    )

    # 1b. Deterministic Trailing-Punctuation Strip (0ms, zero tokens).
    # _check_bullet_trailing_punctuation's fix -- a 2026-09-17 sample build
    # shipped "Coached a remote pod of SDRs ... benchmarks." -- is pure
    # text surgery, so it never needs the LLM loop.
    punct_modified = False
    punct_violations = [
        v for v in violations if v.startswith("Bullet ends with trailing punctuation")
    ]
    if punct_violations:
        for container_key, list_key in (
            ("EXPERIENCE", "achievements"),
            ("EDUCATION", "bullets"),
        ):
            for entry in current_data.get(container_key, []):
                texts = entry.get(list_key, [])
                for idx, bullet in enumerate(texts):
                    stripped = bullet.strip()
                    if validate_resume._TRAILING_PUNCTUATION_RE.search(stripped):
                        new_text = stripped.rstrip()
                        while validate_resume._TRAILING_PUNCTUATION_RE.search(new_text):
                            new_text = validate_resume._TRAILING_PUNCTUATION_RE.sub(
                                "", new_text
                            ).rstrip()
                        if new_text and new_text != bullet:
                            entry[list_key][idx] = new_text
                            punct_modified = True

    # 1c. Surgical Skills Fragment Removal (0ms, zero tokens). "Assets"
    # alone as a skills item is truncated filler, not a skill -- the
    # hallucinated-tool check passes it because the verified ledger has
    # compound names bearing the word ("derivative content assets"). Drop
    # the bare fragment item and keep the rest of the line byte-identical;
    # if the shortened line falls into the wrap dead band, the dead-band
    # repair in step 3 below re-fits it.
    fragment_modified = False
    fragment_violations = [
        v for v in violations if v.startswith("Skills line contains fragment item")
    ]
    if fragment_violations:
        for idx, line in enumerate(current_data.get("SKILLS", [])):
            fragments = validate_resume.skills_fragment_items(line)
            if not fragments:
                continue
            match = validate_resume._SKILLS_LINE_RE.match(line.strip())
            if not match:
                continue
            items = [
                p.strip() for p in re.split(r"[,;|]", match.group("items")) if p.strip()
            ]
            kept = [
                p
                for p in items
                if p.lower() not in validate_resume._SKILLS_FRAGMENT_WORDS
            ]
            if kept and kept != items:
                current_data["SKILLS"][idx] = (
                    f"**{match.group('label')}:** " + ", ".join(kept)
                )
                fragment_modified = True

    # 2. Surgical Bullet Widow Repair
    widow_violations = [
        v for v in violations if "wraps to a 2nd line" in v or "short widow" in v
    ]
    widow_modified = False
    if widow_violations:
        for job in current_data.get("EXPERIENCE", []):
            achievements = job.get("achievements", [])
            for idx, bullet in enumerate(achievements):
                if validate_resume.bullets_with_short_widow([bullet], style_rules):
                    repaired = _micro_refactor_single_bullet(bullet, style_rules)
                    if repaired != bullet:
                        job["achievements"][idx] = repaired
                        widow_modified = True

    # 3. Surgical Skills Line Dead-Band Repair
    skills_violations = [
        v for v in violations if "dead band" in v or "wrap to a 3rd line" in v
    ]
    skills_modified = False
    if skills_violations:
        skills = current_data.get("SKILLS", [])
        for idx, line in enumerate(skills):
            if validate_resume._check_skills_line_lengths(
                {"SKILLS": [line]}, style_rules
            ):
                repaired_line = _micro_refactor_skills_line(line, style_rules)
                if repaired_line != line:
                    skills[idx] = repaired_line
                    skills_modified = True

    # 4. Surgical Hallucinated Skill Removal from SKILLS
    hallucinated_skill_violations = [
        v
        for v in violations
        if "Strict Semantic Guardrail: Hallucinated skill or tool detected:" in v
    ]
    hallucination_modified = False
    if hallucinated_skill_violations:
        hallucinated_terms = []
        for v in hallucinated_skill_violations:
            match = re.search(r"detected:\s*'([^']+)'", v)
            if match:
                hallucinated_terms.append(match.group(1))

        if hallucinated_terms:
            skills = current_data.get("SKILLS", [])
            for idx, line in enumerate(skills):
                new_line = line
                for term in hallucinated_terms:
                    if re.search(
                        r"\b" + re.escape(term) + r"\b", new_line, re.IGNORECASE
                    ):
                        header_match = re.match(
                            r"^(\*\*.+?\*\*[:\-]?\s*)(.*)$", new_line
                        )
                        if header_match:
                            header, items_str = header_match.groups()
                            items = [
                                p.strip()
                                for p in re.split(r"[,;|]", items_str)
                                if p.strip()
                            ]
                            filtered_items = [
                                p for p in items if p.lower() != term.lower()
                            ]
                            new_line = header + ", ".join(filtered_items)
                        else:
                            items = [
                                p.strip()
                                for p in re.split(r"[,;|]", new_line)
                                if p.strip()
                            ]
                            filtered_items = [
                                p for p in items if p.lower() != term.lower()
                            ]
                            new_line = ", ".join(filtered_items)
                if new_line != line:
                    skills[idx] = new_line
                    hallucination_modified = True

    # 5. Deterministic Role Roster Repair
    # The LLM retry loop (build_tailored_resume's "MISSING EMPLOYERS -- ADD
    # THESE ENTRIES" block) restates the same instruction on every attempt --
    # observed live to restore some missing companies but not others across
    # all 4 attempts (e.g. Element 8 / Strategy LLC), which fails the whole
    # build (partition_violations treats "Role roster" as fatal). This
    # builds the missing EXPERIENCE entry directly from data already in
    # hand -- bullet_tuples for achievements, role_metadata (parsed from
    # cv.md, see _parse_cv_role_metadata) for title/period/location -- so a
    # company that survives to this point never costs the build entirely.
    roster_modified = False
    roster_violations = [v for v in violations if v.startswith("Role roster")]
    if roster_violations and bullet_tuples:
        present = {
            validate_resume._normalize_company(job.get("company", ""))
            for job in current_data.get("EXPERIENCE", [])
        }
        for v in roster_violations:
            if "'" not in v:
                continue
            company = v.split("'")[1]
            needle = validate_resume._normalize_company(company)
            if any(needle in p or p in needle for p in present if p):
                continue  # a prior violation in this batch already added it
            # Loose containment for the same reason _micro_fix_metric_provenance
            # uses it: a roster name can tag one stint of an employer whose
            # rendered company is the plain name, and exact equality then finds
            # nothing to build the entry from.
            achievements = [
                b
                for b, c, _t in bullet_tuples
                if needle
                and (
                    needle in validate_resume._normalize_company(c)
                    or validate_resume._normalize_company(c) in needle
                )
            ]
            if not achievements:
                continue  # nothing to build the entry from -- leave for the LLM loop
            max_b = (role_bullet_maximums or {}).get(company)
            if max_b:
                achievements = achievements[:max_b]
            meta = _lookup_role_metadata(role_metadata or {}, company)
            current_data.setdefault("EXPERIENCE", []).append(
                {
                    "title": meta.get("title", ""),
                    "company": company,
                    "period": meta.get("period", ""),
                    "location": meta.get("location", ""),
                    "achievements": achievements,
                    "career_note": "",
                }
            )
            present.add(needle)
            roster_modified = True
        if roster_modified:
            current_data, _ = auto_fix_experience_order(current_data, role_roster)

    # 6. Targeted Metric Deduplication Repair
    # Same rationale as step 5: the LLM full-resume retry loop returned the
    # exact same "Metric '100+' should appear only once ... Summary and a
    # bullet" violation across all 4 fix attempts in a real 2026-09-03 build
    # (see build_tailored_resume's stall-escalation comment). Bullets are
    # the source of truth for exact figures (same convention as the Role
    # roster block), so only the OTHER occurrence -- the Summary, or a
    # later-added bullet if the duplicate is bullet-to-bullet -- gets
    # rewritten, via a single narrowly-scoped LLM call per violation
    # rather than another full-document regenerate.
    metric_modified = False
    metric_violations = [v for v in violations if v.startswith("Metric '")]
    if metric_violations:
        for v in metric_violations:
            match = re.match(r"^Metric '([^']+)'", v)
            if not match:
                continue
            number = match.group(1)
            other_metrics = validate_resume.get_all_metrics(current_data)
            summary = current_data.get("SUMMARY_TEXT", "") or ""
            if number.lower() in summary.lower():
                new_summary = _micro_dedupe_metric(
                    summary, number, other_metrics, "Summary"
                )
                if new_summary != summary:
                    current_data["SUMMARY_TEXT"] = new_summary
                    metric_modified = True
                continue
            # Bullet-to-bullet duplicate: edit only the LAST matching
            # bullet in EXPERIENCE order, leaving the first (the source of
            # truth per seen_in_bullets in _check_metric_uniqueness) intact.
            matches = [
                (j_idx, b_idx)
                for j_idx, job in enumerate(current_data.get("EXPERIENCE", []))
                for b_idx, bullet in enumerate(job.get("achievements", []))
                if number.lower() in bullet.lower()
            ]
            if len(matches) < 2:
                continue
            j_idx, b_idx = matches[-1]
            old_bullet = current_data["EXPERIENCE"][j_idx]["achievements"][b_idx]
            new_bullet = _micro_dedupe_metric(
                old_bullet, number, other_metrics, "Experience bullet"
            )
            if new_bullet != old_bullet:
                current_data["EXPERIENCE"][j_idx]["achievements"][b_idx] = new_bullet
                metric_modified = True

    # 7. Targeted ATS Keyword Density Repair
    # Same real-build stall as step 6, different violation: "Keyword
    # 'content' appears 16 times (3.8%)" survived all 4 fix attempts
    # unchanged. Computes exactly how many occurrences must go, then
    # hands _micro_trim_keyword_density a single targeted call instead of
    # relying on another full-resume regenerate.
    density_modified = False
    density_violations = [
        v for v in violations if v.startswith("ATS Keyword Density Ceiling:")
    ]
    if density_violations:
        for v in density_violations:
            match = re.match(
                r"^ATS Keyword Density Ceiling: Keyword '([^']+)' appears (\d+) times "
                r"\([\d.]+% of (\d+) words\), exceeding the ([\d.]+)% natural density limit\.",
                v,
            )
            if not match:
                continue
            word, count_str, total_words_str, max_density_pct_str = match.groups()
            count = int(count_str)
            total_words = int(total_words_str)
            max_density = float(max_density_pct_str) / 100.0
            allowed = int(max_density * total_words)
            reduce_by = count - allowed
            if reduce_by <= 0:
                continue
            current_data, changed = _micro_trim_keyword_density(
                current_data, word, reduce_by
            )
            density_modified = density_modified or changed

    # 8. Deterministic Bullet Count Repair
    # _check_bullet_counts()'s own docstring names this exact failure --
    # VML and Callahan Creek shipping 2 bullets against a declared
    # min_bullets of 3 -- as "observed live", but no repair for it was
    # ever built (unlike Role roster / step 5, which this mirrors): the
    # LLM full-resume retry loop restates the same instruction on every
    # attempt and it survives all 4, failing the whole build (fatal per
    # partition_violations). Pulls additional bullets for the same
    # company straight from bullet_tuples -- the same source of truth
    # step 5 uses -- skipping any bullet text already present anywhere
    # in that job's achievements. If the bank doesn't have enough spare
    # bullets for that company, this is a no-op and the violation is
    # left for the LLM loop, same as step 5's "nothing to build from"
    # case.
    bullet_count_modified = False
    bullet_count_violations = [
        v
        for v in violations
        if v.startswith("Bullet count:") and "below its required minimum of" in v
    ]
    if bullet_count_violations and bullet_tuples:
        for v in bullet_count_violations:
            match = re.match(
                r"^Bullet count: '(.+)' has \d+ achievement bullet\(s\), "
                r"below its required minimum of (\d+)",
                v,
            )
            if not match:
                continue
            company, minimum_str = match.groups()
            minimum = int(minimum_str)
            needle = validate_resume._normalize_company(company)
            for job in current_data.get("EXPERIENCE", []):
                entry = validate_resume._normalize_company(job.get("company", ""))
                if not (needle and (needle in entry or entry in needle)):
                    continue
                achievements = job.setdefault("achievements", [])
                existing = set(achievements)
                candidates = [
                    b
                    for b, c, _t in bullet_tuples
                    # Loose containment, same reasoning as the roster repair
                    # above -- an exact-match top-up is a no-op whenever the
                    # bank tags a stint rather than the rendered company.
                    if needle
                    and (
                        needle in validate_resume._normalize_company(c)
                        or validate_resume._normalize_company(c) in needle
                    )
                    and b not in existing
                ]
                max_b = (role_bullet_maximums or {}).get(company)
                for candidate in candidates:
                    if len(achievements) >= minimum:
                        break
                    if max_b and len(achievements) >= max_b:
                        break
                    achievements.append(candidate)
                    existing.add(candidate)
                    bullet_count_modified = True
                break

    # 9. Targeted Pronoun Removal Repair
    # Same gap as step 8: _check_pronouns_outside_why() had no repair path
    # at all until now, and a real 2026-09-04 build reduced every other
    # fatal violation to zero across 4 fix attempts while this one alone
    # survived unchanged. The violation message embeds the exact text via
    # repr(), which ast.literal_eval() reverses; the field is then located
    # by an exact content match rather than by re-parsing the field-name
    # label, so this works regardless of which field type flagged it
    # (Summary, a Skills line, or any EXPERIENCE/EDUCATION bullet).
    pronoun_modified = False
    pronoun_violations = [
        v for v in violations if v.startswith("Pronoun found outside the Why section")
    ]
    if pronoun_violations:
        for v in pronoun_violations:
            match = re.match(
                r"^Pronoun found outside the Why section, in \S+: (.+)$", v
            )
            if not match:
                continue
            try:
                original_text = ast.literal_eval(match.group(1))
            except (ValueError, SyntaxError):
                continue

            if current_data.get("SUMMARY_TEXT") == original_text:
                new_text = _micro_strip_pronoun(original_text)
                if new_text != original_text:
                    current_data["SUMMARY_TEXT"] = new_text
                    pronoun_modified = True
                continue

            found = False
            for idx, line in enumerate(current_data.get("SKILLS", [])):
                if line == original_text:
                    new_line = _micro_strip_pronoun(original_text)
                    if new_line != original_text:
                        current_data["SKILLS"][idx] = new_line
                        pronoun_modified = True
                    found = True
                    break
            if found:
                continue

            for job in current_data.get("EXPERIENCE", []):
                achievements = job.get("achievements", [])
                for idx, bullet in enumerate(achievements):
                    if bullet == original_text:
                        new_bullet = _micro_strip_pronoun(original_text)
                        if new_bullet != original_text:
                            achievements[idx] = new_bullet
                            pronoun_modified = True
                        found = True
                        break
                if found:
                    break
            if found:
                continue

            for entry in current_data.get("EDUCATION", []):
                bullets = entry.get("bullets", [])
                for idx, bullet in enumerate(bullets):
                    if bullet == original_text:
                        new_bullet = _micro_strip_pronoun(original_text)
                        if new_bullet != original_text:
                            bullets[idx] = new_bullet
                            pronoun_modified = True
                        found = True
                        break
                if found:
                    break

    # 10. Targeted Metric Provenance Repair
    # Same gap class as steps 8/9: validate_resume._check_metric_provenance()
    # had no repair path at all until now. Parses company + bullet text out
    # of the violation message (repr()'d, reversed via ast.literal_eval, same
    # idiom as the pronoun block above) and hands only that company's own
    # real bullet-bank text to the rewrite, so the model can't reach for
    # another company's number a second time.
    metric_provenance_modified = False
    if bullet_tuples:
        metric_provenance_violations = [
            v
            for v in violations
            if v.startswith("Metric '") and "does not appear in" in v
        ]
        for v in metric_provenance_violations:
            match = re.match(
                r"^Metric '.+?' in a (.+?) bullet does not appear in .+? bullet-bank source -- likely fabricated or borrowed from a different company's bullet: (.+)$",
                v,
            )
            if not match:
                continue
            company = match.group(1)
            try:
                original_text = ast.literal_eval(match.group(2))
            except (ValueError, SyntaxError):
                continue

            for job in current_data.get("EXPERIENCE", []):
                if job.get("company") != company:
                    continue
                achievements = job.get("achievements", [])
                for idx, bullet in enumerate(achievements):
                    if bullet == original_text:
                        new_bullet = _micro_fix_metric_provenance(
                            original_text, company, bullet_tuples
                        )
                        if new_bullet != original_text:
                            achievements[idx] = new_bullet
                            metric_provenance_modified = True
                        break
                break

    # Only re-evaluate if we actually modified something
    if (
        verb_modified
        or order_modified
        or opener_modified
        or punct_modified
        or fragment_modified
        or widow_modified
        or skills_modified
        or hallucination_modified
        or roster_modified
        or metric_modified
        or density_modified
        or bullet_count_modified
        or pronoun_modified
        or metric_provenance_modified
    ):
        final_violations = validate_resume.validate(
            current_data,
            style_rules,
            role_roster,
            role_bullet_minimums,
            role_bullet_maximums=role_bullet_maximums,
            bullet_tuples=bullet_tuples,
        )
        return current_data, final_violations

    return current_data, violations


def trim_surplus_bullet_deterministically(
    resume_data: dict,
    profile_data: dict,
    role_bullet_minimums: dict[str, int],
) -> tuple[dict, bool]:
    """Finds the lowest-flex_priority role with surplus bullets (> min_bullets)
    and drops 1 non-protected bullet."""
    roles = profile_data.get("roles") or []
    protected_set = set(profile_data.get("protected_bullets") or [])

    # Sort roles by flex_priority (lowest flex_priority / highest numeric value trimmed first)
    flex_order = sorted(roles, key=lambda r: r.get("flex_priority", 999), reverse=True)

    for role_cfg in flex_order:
        company_name = role_cfg.get("name")
        if not company_name:
            continue
        needle = validate_resume._normalize_company(company_name)
        min_floor = role_bullet_minimums.get(
            company_name, role_cfg.get("min_bullets", 2)
        )
        for job in resume_data.get("EXPERIENCE", []):
            entry = validate_resume._normalize_company(job.get("company", ""))
            if entry and (needle in entry or entry in needle):
                achievements = job.get("achievements", [])
                if len(achievements) > min_floor:
                    for idx in range(len(achievements) - 1, -1, -1):
                        bullet = achievements[idx]
                        if not any(prot in bullet for prot in protected_set):
                            dropped = achievements.pop(idx)
                            cli_art.detail(
                                f"  Trim: Deterministically dropped surplus bullet from {company_name}: '{dropped[:40]}...'"
                            )
                            return resume_data, True
    return resume_data, False


def extract_jd_keywords_via_gemini(jd_text: str) -> dict | None:
    """Runs extract_keywords.md against raw JD text, standalone from
    ResumeEngine (prompts_dir is fixed under PROJECT_ROOT/resume-engine, not
    profile-scoped, so no instance state is needed). This is the same
    extraction the tailoring pipeline's Step 1.5 already pays for -- pulled
    out so any other caller (the Skills Gap Matrix, a bulk pending-role skill
    scan) can request it without going through a resume build."""
    prompt_path = os.path.join(
        PROJECT_ROOT, "resume-engine", "prompts", "extract_keywords.md"
    )
    with open(prompt_path, "r", encoding="utf-8") as f:
        keyword_prompt = f.read()
    keyword_text, _ = GeminiClient.generate(
        model=BUILDER_MODEL,
        system_instruction=keyword_prompt,
        contents=f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===",
        response_schema=JDKeywordSchema,
        temperature=0.0,
    )
    return GeminiClient.parse_json(keyword_text or "") or None


def get_or_extract_jd_keywords(jd_path: str) -> dict | None:
    """Reads a JD's cached _extracted_keywords (jd_manager.save_extracted_keywords),
    or extracts and caches them on a miss. Callers outside the tailoring
    pipeline's own checkpoint (which extracts and stores jd_keywords
    per-build-attempt) should go through this rather than re-extracting on
    every call."""
    cached = jd_manager.read_extracted_keywords(jd_path)
    if cached is not None:
        return cached
    jd_text = jd_manager.read_jd_text(jd_path)
    keywords = extract_jd_keywords_via_gemini(jd_text)
    if keywords is not None:
        jd_manager.save_extracted_keywords(jd_path, keywords)
    return keywords


def warm_jd_keyword_cache(jd_path: str) -> None:
    """Extracts and caches a JD's _extracted_keywords during evaluation,
    paired so the Skills Gap Matrix is already warm by the time a role
    reaches the Jobs dashboard -- a role must be evaluated before "m" is
    even offered (dashboard_actions._matrix requires an existing
    evaluation), so pairing extraction with evaluate_fit() means the
    Matrix's own get_or_extract_jd_keywords() fallback almost always finds
    a cache hit instead of paying for extraction at view time.

    Deliberately does not feed extraction into the fit score itself --
    tools_process_overlap already reads the raw JD text directly, and
    build_verified_skills_context() covers the candidate side. This is
    purely a cache pre-warm and must never affect or block evaluation, so
    every failure mode -- missing file, JD already has scan-provided
    skills, already cached, extraction failure -- is a silent no-op.

    Requires the JD file to already exist on disk: save_extracted_keywords
    can't persist into a path that isn't there, and a real evaluate_fit()
    call only ever reaches here after jd_manager.read_jd_text(jd_path) has
    already succeeded from that same file.
    """
    if not jd_path or not os.path.exists(jd_path):
        return
    try:
        if jd_manager.read_extracted_keywords(jd_path) is not None:
            return
        with open(jd_path, "r", encoding="utf-8") as f:
            jd_data = json.load(f)
        if isinstance(jd_data, dict) and jd_data.get("skills"):
            return
        get_or_extract_jd_keywords(jd_path)
    except Exception:
        pass


def gather_jd_skill_names(jd_path: str) -> list[str]:
    """The same skill-name derivation dashboard_actions._matrix() uses:
    scan-provided jd_data["skills"] first (only ever populated by
    scan_linkedin.py/scan_jobright.py), falling back to extracted
    keywords via get_or_extract_jd_keywords() -- a cache hit for any JD
    that already went through warm_jd_keyword_cache(). Assumes jd_path is
    a real, already-resolved file."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            jd_data = json.load(f)
    except Exception:
        return []
    if not isinstance(jd_data, dict):
        return []

    skills = jd_data.get("skills") or []
    skill_names = [s.get("skill", "") for s in skills if s.get("skill")]
    if skill_names:
        return skill_names

    try:
        jd_keywords = get_or_extract_jd_keywords(jd_path)
    except Exception:
        return []
    if not jd_keywords:
        return []

    seen = set()
    names = []
    for name in (
        list(jd_keywords.get("tools") or [])
        + list(jd_keywords.get("hard_skills") or [])
        + list(jd_keywords.get("core_functions") or [])
    ):
        name = (name or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def compute_skill_coverage_matrix(skill_names: list) -> list:
    """Embeds skill_names against the bullet bank and ranks each by
    coverage percentile against the bank's own best-match distribution --
    the same computation dashboard_actions._matrix() runs for the Jobs
    dashboard's manual "m" action, shared here so evaluate_fit() can
    populate `skill_matrix` automatically. See dashboard_actions'
    _coverage_reference()/_coverage_percentile() docstrings for why this
    is a rank against the corpus, not a raw cosine score.

    Returns [] on any missing prerequisite (no skills, no bullet-bank
    embeddings file, an embedding API failure) rather than raising --
    callers treat this as optional enrichment, never a required step.
    """
    if not skill_names:
        return []
    try:
        import dashboard_actions
        import numpy as np
        from embed_bullet_bank import (
            BACKUP_EMBED_MODEL,
            BATCH_SIZE,
            EMBED_MODEL,
            embed_batch,
            index_paths,
        )
        from vector_store import cosine_similarity_matrix
    except ImportError:
        return []

    kb_dir = profile_paths.kb_dir()
    # The primary model first, then the backup, each against ITS OWN index
    # (the two models' vectors are not comparable). A short retry ladder,
    # since there is somewhere else to go: the full ~150s wait on every
    # rate-limited evaluation is what stalled a 374-role re-score for hours.
    candidates = [
        (model, index_paths(kb_dir, model)[0])
        for model in (EMBED_MODEL, BACKUP_EMBED_MODEL)
    ]
    candidates = [(model, npy) for model, npy in candidates if os.path.exists(npy)]
    if not candidates:
        return []

    for model, emb_npy in candidates:
        try:
            embs = np.load(emb_npy)
            skill_vecs = []
            for i in range(0, len(skill_names), BATCH_SIZE):
                batch = skill_names[i : i + BATCH_SIZE]
                skill_vecs.extend(embed_batch(batch, model=model, max_retries=2))
            if embs.ndim != 2 or any(v and len(v) != embs.shape[1] for v in skill_vecs):
                continue
        except Exception:
            continue
        return _rank_skill_coverage(skill_names, skill_vecs, embs)
    return []


def _rank_skill_coverage(skill_names: list, skill_vecs: list, embs) -> list:
    """Coverage percentile per skill against `embs` (one model's index)."""
    try:
        import dashboard_actions
        import numpy as np
        from vector_store import cosine_similarity_matrix

        reference = dashboard_actions._coverage_reference(embs)

        skill_matrix = []
        for name, vec in zip(skill_names, skill_vecs):
            if vec:
                scores = cosine_similarity_matrix(np.array(vec, dtype=np.float32), embs)
                max_score = float(np.max(scores)) if len(scores) > 0 else 0.0
                coverage_pct = dashboard_actions._coverage_percentile(
                    max_score, reference
                )
                skill_matrix.append({"skill": name, "coverage": coverage_pct})
        skill_matrix.sort(key=lambda x: x["coverage"])
        return skill_matrix
    except Exception:
        return []


def find_unverified_jd_skill_gaps(
    jd_keywords: dict, verified_tools_data: dict, profile_data: dict
) -> list[str]:
    """
    Identifies tools and hard skills requested in the JD that are not yet recorded
    in verified_tools.json or profile.yml.

    Candidates deliberately mirror validate_resume.check_keyword_coverage()'s
    own `all_keywords` (tools + hard_skills + core_functions), not just
    tools/hard_skills -- core_functions was missing here until 2026-09-06,
    so anything the JD listed only under core_functions could never surface
    at this early Step 1.5 prompt, only in check_keyword_coverage()'s
    post-build report, which triggered a second, separate confirm-and-
    rebuild prompt for a keyword Step 1.5 should have already asked about.
    """
    import validate_resume

    known = set()
    for t in (verified_tools_data or {}).get("tools", []):
        name = t.get("name", "").strip()
        if name:
            known.add(name.lower())
    for cat, skills in (profile_data or {}).get("skills", {}).items():
        if isinstance(skills, list):
            for s in skills:
                known.add(str(s).strip().lower())

    candidates = (
        list(jd_keywords.get("tools") or [])
        + list(jd_keywords.get("hard_skills") or [])
        + list(jd_keywords.get("core_functions") or [])
    )
    gaps = []
    seen = set()
    for c in candidates:
        if not c or not c.strip():
            continue
        c_str = c.strip()
        c_lower = c_str.lower()
        if c_lower in seen:
            continue
        seen.add(c_lower)

        # Check against known tools and skills
        is_known = False
        for k in known:
            if (
                k == c_lower
                or validate_resume._keyword_matches_haystack(c_str, k)
                or validate_resume._keyword_matches_haystack(k, c_str)
            ):
                is_known = True
                break
        if not is_known:
            gaps.append(c_str)
    return gaps


def confirm_jd_skill_gaps_interactively(
    jd_keywords: dict, checkpoint: dict | None = None, job_key: str | None = None
) -> list[str]:
    """
    Prompts the user interactively (JobRight-style) to verify candidate tools/skills
    from the target JD. Confirmed tools are atomically saved to verified_tools.json.
    Respects checkpointing under "confirmed_skill_gaps" so a resumed run doesn't re-prompt.
    """
    if checkpoint is not None:
        confirmed = checkpoint.get("confirmed_skill_gaps")
        if confirmed is not None:
            return confirmed

    import profile_paths
    import skills_menu
    import yaml

    # Explicit test/headless guard: never prompt or mutate in non-interactive/unittest mode
    if "unittest" in sys.modules or not sys.stdin.isatty():
        if checkpoint is not None and "confirmed_skill_gaps" not in checkpoint:
            checkpoint["confirmed_skill_gaps"] = []
            if job_key:
                jd_manager.save_checkpoint(job_key, checkpoint)
        return []

    try:
        verified_tools_data = skills_menu._load_verified_tools()
    except Exception:
        verified_tools_data = {"tools": []}

    try:
        profile_data = profile_paths.profile_yaml() or {}
    except Exception:
        profile_data = {}

    gaps = find_unverified_jd_skill_gaps(jd_keywords, verified_tools_data, profile_data)
    if not gaps:
        if checkpoint is not None:
            checkpoint["confirmed_skill_gaps"] = []
            if job_key:
                jd_manager.save_checkpoint(job_key, checkpoint)
        return []

    cli_art.console.rule(
        "Step 1.5: Skill Gap Discovery (JobRight Style)", style=theme.BRAND
    )
    cli_art.detail(
        "The target JD requests the following tools/skills not yet in your verified profile.\n"
        "Check any that you have legitimate experience with to add them to your verified tools ledger:",
        level=cli_art.NORMAL,
    )

    try:
        selected = questionary.checkbox(
            "Select verified skills/tools to add to your profile:",
            choices=gaps,
            style=cli_art.QUESTIONARY_STYLE,
        ).ask()
    except Exception:
        selected = []

    if not selected:
        cli_art.detail(
            "No additional skills added. Continuing build...", level=cli_art.NORMAL
        )
        if checkpoint is not None:
            checkpoint["confirmed_skill_gaps"] = []
            if job_key:
                jd_manager.save_checkpoint(job_key, checkpoint)
        return []

    # Atomically persist newly confirmed tools
    tools = verified_tools_data.setdefault("tools", [])
    for skill_name in selected:
        new_id = skills_menu._generate_next_id(tools)
        tools.append(
            {
                "id": new_id,
                "name": skill_name,
                "category": "Candidate Verified",
                "confidence": "Proficient",
                "employer": "Self / Profile",
                "use_notes": "Added via JD Skill Gap Discovery",
                "tr_references": ["profile.yml"],
            }
        )

    saved = skills_menu._save_verified_tools(verified_tools_data)
    if saved:
        cli_art.console.print(
            f"  {theme.colorize_icon('success')} Added [bold green]{len(selected)}[/bold green] tool(s) to verified_tools.json: {', '.join(selected)}"
        )

    if checkpoint is not None:
        checkpoint["confirmed_skill_gaps"] = selected
        if job_key:
            jd_manager.save_checkpoint(job_key, checkpoint)

    return selected


def confirm_missing_coverage_keywords_interactively(missing: list[str]) -> list[str]:
    """
    Runs after check_keyword_coverage() reports on the FINISHED resume (Step
    1.5's confirm_jd_skill_gaps_interactively() only sees pre-build JD
    keywords, so a gap that check_keyword_coverage() catches -- a keyword
    the model still didn't use, or one Step 1.5 never surfaced -- would
    otherwise need a manual trip to Settings & Upkeep to fix. Confirmed
    2026-09-04: a real build reported 'Missing: Claude, Asana, CMS
    platforms, Cybersecurity' with no way to say "I actually have that"
    short of hand-editing verified_tools.json and re-running from scratch.

    Per-keyword confirm/deny (not the Step 1.5 checkbox) since this list is
    already short and specific to one finished build. Returns the names
    confirmed, so the caller can offer to rebuild with them included.
    """
    if not missing:
        return []
    if "unittest" in sys.modules or not sys.stdin.isatty():
        return []

    import skills_menu

    try:
        verified_tools_data = skills_menu._load_verified_tools()
    except Exception:
        verified_tools_data = {"tools": []}
    tools = verified_tools_data.setdefault("tools", [])

    # "Missing" means the finished resume did not use a keyword, not that the
    # candidate lacks it. Asking about ledger skills re-prompted the same
    # dozen names every build and appended a duplicate on each "yes".
    known = {" ".join(str(t.get("name", "")).lower().split()) for t in tools}
    already = [kw for kw in missing if " ".join(kw.lower().split()) in known]
    missing = [kw for kw in missing if " ".join(kw.lower().split()) not in known]
    if already:
        cli_art.detail(
            "Already in your verified skills, just not used on this resume: "
            + ", ".join(already),
            level=cli_art.NORMAL,
        )
    if not missing:
        return []

    cli_art.detail(
        "The finished resume is missing some JD keywords. Confirm any you "
        "actually have -- they'll be added to your verified skills ledger:",
        level=cli_art.NORMAL,
    )

    confirmed = []
    for kw in missing:
        has_it = cli_art.confirm(f"Do you have experience with '{kw}'?", default=False)
        if not has_it:
            continue
        note = (
            cli_art.text(
                f"Optional one-line note on how you've used '{kw}' (Enter to skip):",
                default="",
            )
            or ""
        )
        tools.append(
            {
                "id": skills_menu._generate_next_id(tools),
                "name": kw,
                "category": "Candidate Verified",
                "confidence": "Proficient",
                "employer": "Self / Profile",
                "use_notes": note or "Added via post-build keyword-coverage prompt",
                "tr_references": ["profile.yml"],
            }
        )
        confirmed.append(kw)

    if confirmed:
        saved = skills_menu._save_verified_tools(verified_tools_data)
        if saved:
            cli_art.console.print(
                f"  {theme.colorize_icon('success')} Added [bold green]{len(confirmed)}[/bold green] "
                f"tool(s) to verified_tools.json: {', '.join(confirmed)}"
            )
    else:
        cli_art.detail("No additional skills added.", level=cli_art.NORMAL)

    return confirmed


def _review_recommendations_interactively(
    recs: list[str], checkpoint: dict, job_key: str
) -> list[str]:
    """
    Prompts a y/n approval for each Step 5 critique recommendation before Step
    5.5 is allowed to apply any of them -- so gap-filling content never lands
    in the resume without explicit approval. Approval choices are checkpointed
    under "approved_recommendations" so a resumed run doesn't re-prompt.
    """
    approved_recs = checkpoint.get("approved_recommendations")
    if approved_recs is not None:
        return approved_recs

    cli_art.console.rule("Step 5.5 review", style=theme.BRAND)
    cli_art.detail(
        "approve which recommendations to attempt (nothing below is applied until you say yes).",
        level=cli_art.NORMAL,
    )
    import sys

    # Headless guard, same shape as confirm_jd_skill_gaps_interactively's:
    # a non-TTY run (piped sample build, CI) has no way to answer, and the
    # old behavior was an EOFError traceback from prompt_toolkit instead of
    # a clean "no recommendations approved". Under unittest the loop still
    # runs so tests can drive it with patched prompts.
    if "unittest" not in sys.modules and not sys.stdin.isatty():
        cli_art.detail(
            "Non-interactive session -- declining all recommendations. Re-run from a "
            "terminal to review them.",
            level=cli_art.NORMAL,
        )
        checkpoint["approved_recommendations"] = []
        jd_manager.save_checkpoint(job_key, checkpoint)
        return []

    approved_recs = []
    for idx, rec in enumerate(recs, start=1):
        # Inlines cli_art.confirm()'s own test-mode/Charm-routing split
        # rather than calling it directly -- cli_art.confirm() coerces a
        # Ctrl-C to False, which would collapse it with an explicit
        # per-recommendation "no" below; this loop needs the real None to
        # tell "interrupted, stop asking" apart from "declined just this
        # one and keep going".
        if "unittest" in sys.modules:
            answer = questionary.confirm(
                f"[{idx}/{len(recs)}] {rec}\n    Apply this?",
                default=False,
                style=cli_art.QUESTIONARY_STYLE,
            ).ask()
        else:
            answer = charm_prompt.confirm(
                f"[{idx}/{len(recs)}] {rec}\n    Apply this?",
                default=False,
            )
        if answer is None:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} Review interrupted -- treating remaining "
                "recommendation(s) as declined.",
                soft_wrap=True,
            )
            break
        if answer:
            approved_recs.append(rec)

    checkpoint["approved_recommendations"] = approved_recs
    jd_manager.save_checkpoint(job_key, checkpoint)
    if not approved_recs:
        cli_art.detail("None approved -- skipping Step 5.5.", level=cli_art.NORMAL)
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
    except Exception as exc:
        cli_art.friendly_warning(
            exc,
            "reading the rendered PDF's page count",
            "the page count won't be shown for this build",
        )
        page_count = None
    size_match = re.search(r"Size:\s*([\d.]+\s*\w+)", stdout)
    size_str = size_match.group(1) if size_match else "unknown size"
    return page_count, size_str


def _page1_overflow_roles(pdf_path: str, profile_data: dict) -> list[str]:
    """Roles flagged must_fit_page_1 in profile.yml, but whose company name
    doesn't appear anywhere in the rendered PDF's page 1 text -- i.e. the
    whole .job block (break-inside: avoid in cv-template.html) got pushed
    to page 2 rather than split. A role can satisfy the overall <=2-page
    rule and still fail this: the trim loop only ever measured total page
    count, so a role that *almost* fit on page 1 spilled entirely onto
    page 2, leaving page 1 with leftover white space."""
    required = [
        str(role.get("name", "")).strip()
        for role in (profile_data.get("roles") or [])
        if role.get("must_fit_page_1") and str(role.get("name", "")).strip()
    ]
    if not required:
        return []
    try:
        page1_text = validate_resume._normalize_company(
            PdfReader(pdf_path).pages[0].extract_text() or ""
        )
    except Exception:
        return []
    return [
        name
        for name in required
        if validate_resume._normalize_company(name) not in page1_text
    ]


def _summarize_keywords(jd_keywords: dict) -> str:
    """One-line count summary of a JDKeywordSchema-shaped dict (tools,
    hard_skills, core_functions today, but iterates generically over
    whatever keys are present). Full values remain in the checkpoint JSON
    for anyone who needs them."""
    parts = [f"{len(v)} {k.replace('_', ' ')}" for k, v in jd_keywords.items() if v]
    return ", ".join(parts) if parts else "none found"


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS -- see scripts/schemas.py (F1, extracted out of this
# file so a consumer that only wants a schema type doesn't have to import
# orchestrator.py's full dependency chain).
# ---------------------------------------------------------------------------
from schemas import (  # noqa: E402
    BulletAuditSchema,
    CapabilityEvaluationSchema,
    CertItem,
    CompanyResearchSchema,
    CoverLetterSchema,
    CritiqueSchema,
    EducationItem,
    ExperienceEntry,
    FitEvaluationSchema,
    FitSubscores,
    InterviewOddsSubscores,
    JDKeywordSchema,
    PracticalPursueSubscores,
    RecommendationApplySchema,
    RecruiterEvaluationSchema,
    ResumeCritiqueSchema,
    ResumeSchema,
    RewriteMinimalSchema,
    RewriteSchema,
    TemplateSchema,
    VocabularySubstitution,
    WhyBackfillSchema,
    WorkExperience,
)

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
    "functional_alignment": 0.30,
    "north_star_alignment": 0.20,
    "level_plausibility": 0.20,
    "work_style_sustainability": 0.15,
    "tools_process_overlap": 0.15,
}

INTERVIEW_ODDS_WEIGHTS = {
    "title_continuity": 0.25,
    "evidence_match": 0.25,
    "domain_credibility": 0.15,
    "recruiter_legibility": 0.15,
    "narrative_burden": 0.05,
    "funnel_friction": 0.15,
}

PRACTICAL_PURSUE_WEIGHTS = {
    "remote_quality": 0.25,
    "compensation_viability": 0.15,
    "growth_value": 0.10,
    "time_to_offer": 0.15,
    "company_reputation": 0.10,
    "cultural_signals": 0.10,
    "posting_legitimacy_score": 0.15,
}

# Interview odds carries slightly more weight than fit -- being a good
# fit on paper doesn't matter if the funnel/title/evidence math means a
# recruiter never moves you forward. Practical constraints matter but
# shouldn't dominate the decision the way a hard blocker does (that's
# handled separately, via hard_blockers).
COMPOSITE_SCORE_WEIGHTS = {
    "fit_score": 0.35,
    "interview_odds_score": 0.45,
    "practical_pursue_score": 0.20,
}

# Applying early matters a lot, and the scanners now pull in enough
# volume that a posting sitting open for weeks shouldn't rank the same
# as one found today.
#
# These were previously 7 / 0.03 / 0.75, deliberately gentle so age acted
# as "a tiebreaker, not an override". In practice that was too weak to do
# its job, for a structural reason rather than a tuning one: because the
# cap was only 0.75 on a 1-5 scale, a strong-but-stale posting could
# NEVER fall below a mediocre fresh one at any age -- a 4.20 role bottomed
# out at 3.45 and stayed there forever, still outranking a fresh 3.40. And
# the penalty fully saturated at day 32, so a 90-day-old posting scored
# exactly the same as a month-old one. Nothing could ever age off the
# list, which is how a queue reaches 1,000+ postings.
#
# The new curve makes age able to overturn quality, which is the whole
# point when applying early is the single biggest lever a candidate has:
#   day 0-3   no penalty        (a genuinely fresh find is untouched)
#   day 7     -0.32
#   day 14    -0.88             (a strong 4.20 now sits below a fresh 3.40)
#   day 21    -1.44
#   day 30    -2.16
#   day 34+   -2.50 (capped)
# The cap still exists so the score stays interpretable on a 1-5 scale
# rather than collapsing everything old into an undifferentiated floor,
# but it now sits well below "still competitive".
#
# Ranking alone can't shrink an existing backlog, so this pairs with
# stale_sweep.py, which archives postings past its own (larger) age
# threshold. Devaluing decides ordering; sweeping decides membership.
STALE_POSTING_THRESHOLD_DAYS = 3
STALE_POSTING_PENALTY_PER_DAY = 0.08
STALE_POSTING_MAX_PENALTY = 2.5

# Stress signals (scripts/stress_signals.py) are deterministic phrase
# detections, not an LLM judgment, so they enter composite math directly
# here rather than through a subscore -- same reasoning as the proximity
# bonus above: grounded facts about the posting's own text, not something
# worth asking the model to re-derive. Weighted asymmetrically on purpose:
# a genuinely low-stress posting (zero categories detected) earns a BONUS
# larger than the penalty for any single detected category, because the
# stated goal here is finding comfortable, sustainable work, not merely
# avoiding red flags. A 2026-09-01 corpus measurement found real but
# modest hit rates (7.8% of postings had any signal), so most postings
# receive the bonus, not the penalty -- see
# docs/superpowers/specs/2026-09-01-stress-challenge-scoring-design.md.
STRESS_SIGNAL_PENALTY_PER_CATEGORY = 0.25
STRESS_SIGNAL_MAX_PENALTY = 0.75
LOW_STRESS_BONUS = 0.40

# capability_gaps (CapabilityEvaluationSchema) is a deterministic COUNT of
# explicit narrative/functional mismatches the model already lists --
# distinct from fit_subscores['level_plausibility'], which is the model's
# own subjective screen-risk judgment. A per-gap penalty belongs here,
# in Python, rather than folding it into that subscore a second time.
STRETCH_GAP_PENALTY_PER_ITEM = 0.20
STRETCH_GAP_MAX_PENALTY = 0.80

# posting_legitimacy ("High Confidence" / "Proceed with Caution" /
# "Suspicious") used to be a label only: its numeric sibling,
# posting_legitimacy_score, is 15% of Practical Pursue, which is itself 20%
# of composite -- about 3% of the ranking. On 2026-09-13 a profile's #1 role
# was an "Applied AI Engineer" at a home-renovation LLC whose postings the
# evaluator itself had flagged (a different company named in the body, a
# Tally.so application form), and 5 of its top 12 were from two such LLCs.
# The label now costs composite points, like the other deterministic
# adjustments here.
LEGITIMACY_CAUTION_PENALTY = 0.50
LEGITIMACY_SUSPICIOUS_PENALTY = 1.50


def legitimacy_penalty(
    posting_legitimacy: str | None = None,
    caution_penalty: float | None = None,
    suspicious_penalty: float | None = None,
) -> float:
    """Composite points a posting_legitimacy verdict costs. None or "High
    Confidence" costs nothing."""
    if posting_legitimacy == "Suspicious":
        return (
            LEGITIMACY_SUSPICIOUS_PENALTY
            if suspicious_penalty is None
            else suspicious_penalty
        )
    if posting_legitimacy == "Proceed with Caution":
        return (
            LEGITIMACY_CAUTION_PENALTY if caution_penalty is None else caution_penalty
        )
    return 0.0


def _weighted_score(subscores: dict, weights: dict) -> float:
    """1-5 weighted average of a subscore dict against its matching
    weight dict (FIT_SUBSCORE_WEIGHTS / INTERVIEW_ODDS_WEIGHTS /
    PRACTICAL_PURSUE_WEIGHTS)."""
    return round(
        sum(subscores.get(dim, 0) * weight for dim, weight in weights.items()), 2
    )


def compute_fit_score(fit_subscores: dict) -> float:
    return _weighted_score(fit_subscores, FIT_SUBSCORE_WEIGHTS)


def compute_interview_odds_score(interview_odds_subscores: dict) -> float:
    return _weighted_score(interview_odds_subscores, INTERVIEW_ODDS_WEIGHTS)


def compute_practical_pursue_score(practical_pursue_subscores: dict) -> float:
    return _weighted_score(practical_pursue_subscores, PRACTICAL_PURSUE_WEIGHTS)


def calibrate_commute_quality(
    distance_miles: float | None = None, radius_miles: float = 5.0
) -> float:
    """Scores commute convenience on a 1-5 scale for local jobs within radius:
    0.0 - 1.0 mi -> 5.0 (walking/ultra-local)
    Down to 3.0 at exactly radius_miles limit."""
    if distance_miles is None or radius_miles is None or radius_miles <= 0:
        return 5.0
    ratio = min(max(float(distance_miles) / float(radius_miles), 0.0), 1.0)
    return round(max(3.0, 5.0 - 2.0 * ratio), 2)


def fit_composite_score(
    fit_score: float,
    interview_odds_score: float,
    practical_pursue_score: float,
    posting_age_days: int | None = None,
    distance_miles: float | None = None,
    radius_miles: float | None = None,
    stress_signal_count: int | None = None,
    capability_gap_count: int | None = None,
    stress_signal_penalty_per_category: float | None = None,
    stress_signal_max_penalty: float | None = None,
    low_stress_bonus: float | None = None,
    stretch_gap_penalty_per_item: float | None = None,
    stretch_gap_max_penalty: float | None = None,
    posting_legitimacy: str | None = None,
    legitimacy_caution_penalty: float | None = None,
    legitimacy_suspicious_penalty: float | None = None,
    constraint_penalty: float = 0.0,
) -> float:
    """Weighted 1-5 blend of the three independent layer scores, per
    COMPOSITE_SCORE_WEIGHTS, plus a proximity boost for local commutable jobs
    (closer = higher, up to +0.50 score boost at 0 mi), minus an age penalty for
    postings older than STALE_POSTING_THRESHOLD_DAYS (see jd_manager.compute_posting_age_days()
    for how posting_age_days is derived -- None means no age signal at
    all, so no penalty is applied rather than assuming staleness).

    stress_signal_count (scripts/stress_signals.py's deterministic phrase
    detector) is None when never computed -- no adjustment, not an assumed
    clean posting. Zero categories detected earns low_stress_bonus; each
    detected category costs stress_signal_penalty_per_category, capped at
    stress_signal_max_penalty.

    capability_gap_count is len(capability_gaps) -- a deterministic count
    of stated mismatches, not the model's subjective level_plausibility
    judgment which is already in fit_score. None/0 means no penalty.

    The five stress_signal_*/stretch_gap_* keyword params default to None,
    which falls back to the module-level STRESS_SIGNAL_*/LOW_STRESS_BONUS/
    STRETCH_GAP_* constants below -- keeping this function pure and
    deterministic for direct unit testing (test_orchestrator_fit_composite_score.py
    calls it with no overrides and asserts against those same module
    constants). The one real caller, rescore_evaluation_with_location(),
    is where a profile's content_settings.read_scoring_weights() override
    actually reaches this function -- see that function's own
    scoring_weights param."""
    stress_signal_penalty_per_category = (
        STRESS_SIGNAL_PENALTY_PER_CATEGORY
        if stress_signal_penalty_per_category is None
        else stress_signal_penalty_per_category
    )
    stress_signal_max_penalty = (
        STRESS_SIGNAL_MAX_PENALTY
        if stress_signal_max_penalty is None
        else stress_signal_max_penalty
    )
    low_stress_bonus = (
        LOW_STRESS_BONUS if low_stress_bonus is None else low_stress_bonus
    )
    stretch_gap_penalty_per_item = (
        STRETCH_GAP_PENALTY_PER_ITEM
        if stretch_gap_penalty_per_item is None
        else stretch_gap_penalty_per_item
    )
    stretch_gap_max_penalty = (
        STRETCH_GAP_MAX_PENALTY
        if stretch_gap_max_penalty is None
        else stretch_gap_max_penalty
    )

    base = (
        fit_score * COMPOSITE_SCORE_WEIGHTS["fit_score"]
        + interview_odds_score * COMPOSITE_SCORE_WEIGHTS["interview_odds_score"]
        + practical_pursue_score * COMPOSITE_SCORE_WEIGHTS["practical_pursue_score"]
    )
    proximity_bonus = 0.0
    if distance_miles is not None and radius_miles and radius_miles > 0:
        if distance_miles <= radius_miles:
            # Closer jobs get up to +0.50 score boost (e.g. 0 mi -> +0.50, 2.5 mi in 5 mi radius -> +0.25)
            proximity_bonus = max(
                0.0, 0.50 * (1.0 - (float(distance_miles) / float(radius_miles)))
            )

    penalty = 0.0
    if posting_age_days is not None and posting_age_days > STALE_POSTING_THRESHOLD_DAYS:
        penalty = min(
            (posting_age_days - STALE_POSTING_THRESHOLD_DAYS)
            * STALE_POSTING_PENALTY_PER_DAY,
            STALE_POSTING_MAX_PENALTY,
        )

    stress_adjustment = 0.0
    if stress_signal_count is not None:
        if stress_signal_count == 0:
            stress_adjustment = low_stress_bonus
        else:
            stress_adjustment = -min(
                stress_signal_count * stress_signal_penalty_per_category,
                stress_signal_max_penalty,
            )

    stretch_penalty = 0.0
    if capability_gap_count:
        stretch_penalty = min(
            capability_gap_count * stretch_gap_penalty_per_item,
            stretch_gap_max_penalty,
        )

    legit_penalty = legitimacy_penalty(
        posting_legitimacy, legitimacy_caution_penalty, legitimacy_suspicious_penalty
    )

    return round(
        max(
            min(
                base
                + proximity_bonus
                + stress_adjustment
                - penalty
                - stretch_penalty
                - legit_penalty
                - (constraint_penalty or 0.0),
                5.0,
            ),
            0.0,
        ),
        2,
    )


# Categories carved out of the unconditional hard_blockers zero-out below,
# since neither has ever been holdout-measured for precision -- unlike
# role_track, which cleared a >=90% bar before it was allowed to gate
# anything (see docs/hard_blockers.md). These surface only as an opt-in
# view filter (model.JobRow.IsExperienceBlocked) instead.
#
# field_domain (required industry/functional background) is deliberately
# NOT in this tuple yet -- it's a new category (see evaluate_recruiter.md)
# carved out of the catch-all `other` bucket specifically so it can be
# measured (scripts/eval_hard_blocker.py) before it gets the same
# stop-auto-zeroing treatment. Until it clears its own holdout bar it
# stays in the unconditional zero-out path below, same as `other`.
EXPERIENCE_BLOCKER_CATEGORIES = ("years_experience", "degree")


def _blocker_text(blocker) -> str:
    """blocker may be a dict ({"text": ..., "category": ...}) or, for older
    persisted evaluations predating the categorized schema, a plain string."""
    if isinstance(blocker, dict):
        return (blocker.get("text") or "").strip()
    return (blocker or "").strip()


def _with_normalized_direction(blocker):
    """Fills a missing/None `direction` on a hard blocker.

    HardBlockerSchema declares `direction` with default="n/a", but that
    default NEVER executes: evaluate_fit() parses the model's reply with
    GeminiClient.parse_json() and passes the raw dicts straight through --
    `response_schema` is only a generation hint to Gemini, not validation.
    Measured 2026-09-16: 47 of Dom's 311 years_experience blockers and 128
    of Morgan's 159 carried direction=None, Dom's all on the CURRENT
    scoring version, so this is live rather than legacy.

    years_experience normalizes to "under_qualified" and every other
    category to "n/a". That choice is deliberately behavior-preserving:
    the only consumer, the over_qualified filter below, drops nothing for
    a None today, so mapping None to under_qualified changes no score --
    it just makes the stored record say what the pipeline already assumed.
    Every undirected entry sampled was of that shape ("5+ years", "7+
    years"). Defaulting the other way would silently delete real blockers.
    """
    if not isinstance(blocker, dict):
        return blocker
    if blocker.get("direction") in ("under_qualified", "over_qualified", "n/a"):
        return blocker
    normalized = dict(blocker)
    normalized["direction"] = (
        "under_qualified" if normalized.get("category") == "years_experience" else "n/a"
    )
    return normalized


def is_spurious_commute_blocker(blocker) -> bool:
    """Returns True if a hard blocker is merely a routine onsite/hybrid requirement
    or local commute prompt that is resolved because the job is within the candidate's
    local commute radius, while strictly preserving genuine non-local travel or vehicle duties.
    """
    b = _blocker_text(blocker)
    category = blocker.get("category") if isinstance(blocker, dict) else None
    b_lower = b.lower()

    # If it specifies external travel, field visits, client visits, or non-local destinations, preserve it!
    non_commute_markers = [
        "client",
        "customer site",
        "field",
        "territory",
        "travel",
        "traveling",
        "overnight",
        "multi-site",
        "driver's license",
        "drivers license",
        "personal vehicle for",
        "vehicle for client",
        "fleet",
        "airline",
    ]
    if any(m in b_lower for m in non_commute_markers):
        return False

    if category == "onsite_commute":
        return True

    # Legacy/auto-generated string forms (evaluations predating the
    # categorized schema, and the Python-injected remote-required message
    # below, which is appended as a plain dict but starts identically).
    if b.startswith("Onsite/hybrid signal detected"):
        return True

    # ATS / Indeed commute prompt (e.g. "Ability to Commute: Buffalo, NY 14228 (Required)")
    if re.match(r"^ability to commute\b", b_lower):
        return True

    # Routine onsite/hybrid presence requirements
    if re.match(r"^(on-?site|hybrid|in-office)\b", b_lower):
        return True

    return False


def build_situational_track_context(
    jd_text: str, roles_data: dict | None = None
) -> str:
    """Tells the evaluator a posting belongs to one of the candidate's
    situational tracks (situational_roles.yaml) -- matched on the TITLE,
    since those triggers ("administrative support", "data entry") appear in
    plenty of marketing bodies too.

    Without it, a local clerical or retail role was scored against the
    candidate's primary career: "a significant step down", north_star 1,
    growth 1 -- composites of 0.4-1.4 for roles the candidate had asked the
    scanner to find (2026-09-14). The situational entry is what goes on the
    resume for such a role, so it is what the fit should be judged on."""
    try:
        title = str((_parse_jd_data(jd_text) or {}).get("job_title") or "").strip()
        names = (
            situational_roles.detect_situational_candidates(title, roles_data)
            if title
            else []
        )
    except Exception:
        return ""
    if not names:
        return ""
    return (
        "=== SITUATIONAL TRACK ===\n"
        f"This posting's title matches the candidate's situational experience: "
        f"{', '.join(names)}. The candidate deliberately considers roles like this "
        "as a calm, local alternative to their primary career -- applying is a "
        "choice, not a misstep, and that experience goes on the resume they send.\n"
        "- Judge functional_alignment, tools_process_overlap, evidence_match, "
        "title_continuity and domain_credibility against that situational "
        "experience, not against target_roles.\n"
        "- Do not score north_star_alignment, growth_value or level_plausibility "
        "low merely because the role is junior to or outside the primary career; "
        "score whether it is a stable, sustainable, reasonable fit for them.\n"
        "- Being over-qualified is never a hard_blocker."
    )


def build_tagline_descriptor_block(role_dna: dict | None) -> str:
    """The tagline's Part 2 options, from the active profile's own archetype
    library (role_dna.yaml `tagline_descriptor`s). tailor_resume.md used to
    hardcode one marketing profile's five descriptors, so a data-science
    profile's sample tagline came out "DATA SCIENTIST | CAMPAIGN CRM SYSTEMS
    SPECIALIST" (2026-09-14). Empty when no archetype carries one -- the
    prompt then has the model write a descriptor from the candidate's own
    background."""
    archetypes = (role_dna or {}).get("archetypes") or {}
    lines = [
        f"- {cfg.get('label') or key} -> \"{cfg['tagline_descriptor']}\""
        for key, cfg in archetypes.items()
        if isinstance(cfg, dict) and cfg.get("tagline_descriptor")
    ]
    if not lines:
        return ""
    return "=== TAGLINE DESCRIPTORS ===\n" + "\n".join(lines)


def build_commute_context(
    distance_miles, radius_miles, workplace, location=None
) -> str:
    """One computed fact for the evaluator: how far a non-remote posting's
    office is from home, against the configured radius. Without it the model
    judged the candidate's commute deal-breaker blind and called offices
    3 miles away "incompatible" (2026-09-14). Empty when remote, or when the
    distance or radius is unknown -- unknown is never stated as near or far."""
    if (
        workplace == location_filter.REMOTE
        or distance_miles is None
        or not radius_miles
    ):
        return ""
    where = f" ({location})" if location else ""
    if distance_miles <= radius_miles:
        verdict = (
            f"WITHIN the candidate's {radius_miles:g}-mile commute radius. Onsite or "
            "hybrid work at this office is exactly what their location deal-breaker "
            "allows -- do not treat the in-office requirement as a deal-breaker or "
            "score it as incompatible."
        )
    else:
        verdict = f"OUTSIDE the candidate's {radius_miles:g}-mile commute radius."
    return (
        "=== COMMUTE (computed from the posting's location, not stated in it) ===\n"
        f"This posting's office{where} is about {float(distance_miles):.1f} miles from "
        f"the candidate's home -- {verdict}"
    )


def city_level_distance(location, loc_settings: dict) -> float | None:
    """Miles from the profile's home city to the posting's nearest listed
    hub, from city centroids -- the same resolution the scan-time location
    gate already trusts (location_filter.nearest_hub_distance). None when
    either side can't be resolved; never 0.

    location_enricher resolves to an ADDRESS (a ZIP in the text, or Maps)
    and reports a bare "Buffalo, NY, US" as unresolved, so on 2026-09-13
    every one of a profile's first 33 local roles reached
    rescore_evaluation_with_location() with no distance: routine
    onsite/commute lines ("Fully onsite in Buffalo, NY", "Ability to
    commute: Depew, NY") were never recognized as commutable and zeroed
    roles 4-11 miles from home."""
    if not location or not loc_settings:
        return None
    origin = ", ".join(
        str(x) for x in (loc_settings.get("city"), loc_settings.get("state")) if x
    )
    if not origin:
        return None
    try:
        import location_filter

        miles, _hub = location_filter.nearest_hub_distance(str(location), origin)
    except Exception:
        return None
    return round(miles, 1) if miles is not None else None


def rescore_evaluation_with_location(
    evaluation: dict,
    distance_miles: float | None = None,
    radius_miles: float = 5.0,
    workplace_mode: str = "any",
    remote_required: bool = False,
    posting_age_days: int | None = None,
    description: str | None = None,
    scoring_weights: dict | None = None,
    role_track_settings: dict | None = None,
    work_constraints_settings: dict | None = None,
    posting_workplace: str | None = None,
    job_title: str | None = None,
) -> dict:
    """Recalculates an evaluation dict incorporating local commute distance:
    1. Calibrates practical_pursue_subscores['remote_quality'] (closer = higher).
    2. Clears spurious onsite/commute blockers if commutable local.
    3. Recomputes composite_score with proximity boost, plus the deterministic
       stress-signal and capability-gap adjustments in fit_composite_score.
    4. Recalculates recommendation and estimated interview odds.

    description is the posting's own body text, used to run
    stress_signals.categories() -- optional and separate from evaluation
    itself because the description isn't persisted on the evaluation dict.
    None means the count is never computed, so fit_composite_score applies
    no stress adjustment rather than assuming a clean posting.

    scoring_weights is None by default so this function stays pure and
    deterministic for direct unit testing -- see fit_composite_score()'s
    own docstring. The real pipeline (evaluate_fit()) passes in
    content_settings.read_scoring_weights(), a profile's override merged
    with defaults.

    role_track_settings is the same pattern: None by default, and the
    real pipeline passes content_settings.read_role_track_settings(). When
    its exclude_manager key is set, a HIGH-confidence manager/player_coach
    verdict forces the same Skip/zero outcome as a disqualifying hard
    blocker (see docs/role_track.md for why "high confidence" -- the
    holdout that measures this classifier's precision only covers that
    slice)."""
    if not evaluation:
        return evaluation

    ev = dict(evaluation)
    subs = dict(ev.get("practical_pursue_subscores", {}))
    blockers = list(ev.get("hard_blockers", []))

    # Blocker hygiene, every category. Over-qualification is a recruiting
    # concern, never a reason not to apply (the years_experience carve-out
    # below predates this and covered only that category -- an `other`
    # entry tagged over_qualified still zeroed a retail role on
    # 2026-09-14). And a "blocker" whose text is just the job title is the
    # model disqualifying the role for being what it is.
    # Fill `direction` before anything reads it -- the filter immediately
    # below keys on it, and the model omits the field often enough that
    # trusting the prompt alone would leave the same gap (see
    # _with_normalized_direction for why the schema default never fires).
    blockers = [_with_normalized_direction(b) for b in blockers]

    title_key = " ".join(str(job_title or "").lower().split())
    blockers = [
        b
        for b in blockers
        if not (isinstance(b, dict) and b.get("direction") == "over_qualified")
        and not (title_key and " ".join(_blocker_text(b).lower().split()) == title_key)
    ]

    is_commutable_local = (
        radius_miles
        and distance_miles is not None
        and distance_miles <= radius_miles
        and (workplace_mode in ("any", "onsite", "hybrid") or not remote_required)
    )

    if is_commutable_local:
        # Clear only spurious routine onsite/commute blockers; preserve travel/vehicle duties
        blockers = [b for b in blockers if not is_spurious_commute_blocker(b)]

        # Calibrate commute quality (closer = higher score, 3.0 to 5.0)
        commute_val = calibrate_commute_quality(distance_miles, radius_miles)
        subs["remote_quality"] = commute_val
        ev["practical_pursue_subscores"] = subs
        ev["hard_blockers"] = blockers
    else:
        # Remote required check for non-commutable jobs
        remote_val = subs.get("remote_quality", 5)
        if remote_required and remote_val < 5:
            msg = (
                f"Onsite/hybrid signal detected (Remote Quality scored {remote_val}/5)"
            )
            existing_texts = {_blocker_text(b) for b in blockers}
            if msg not in existing_texts:
                blockers.append({"text": msg, "category": "onsite_commute"})
            ev["hard_blockers"] = blockers

    # A profile's own physical/phone limits (scan_filters.yml
    # work_constraints:, scripts/work_constraints.py). Deterministic, so
    # the verdict does not depend on how the model reads a posting today;
    # physical_demands is not an EXPERIENCE category, so it forces Skip.
    constraint_penalty = 0.0
    if work_constraints_settings and description:
        import work_constraints

        seen = {
            (b.get("category"), _blocker_text(b))
            for b in blockers
            if isinstance(b, dict)
        }
        for finding in work_constraints.detect(description, work_constraints_settings):
            if finding["severity"] == work_constraints.BLOCKER:
                key = ("physical_demands", finding["text"])
                if key not in seen:
                    seen.add(key)
                    blockers.append(
                        {
                            "text": finding["text"],
                            "category": "physical_demands",
                            "direction": "n/a",
                        }
                    )
            else:
                constraint_penalty += finding["penalty"]
    ev["hard_blockers"] = blockers

    fit_score = compute_fit_score(ev.get("fit_subscores", {}))
    interview_odds_score = compute_interview_odds_score(
        ev.get("interview_odds_subscores", {})
    )
    practical_pursue_score = compute_practical_pursue_score(subs)

    ev["fit_score"] = fit_score
    ev["interview_odds_score"] = interview_odds_score
    ev["practical_pursue_score"] = practical_pursue_score

    # years_experience/degree blockers are split out and never force a
    # Skip/zero -- see EXPERIENCE_BLOCKER_CATEGORIES above. Every other
    # category keeps the original unconditional behavior.
    #
    # A years_experience entry tagged direction="over_qualified" is a real
    # recruiting concern (see docs/hard_blockers.md's
    # overqualification-conflation finding) but not what this list is
    # meant to represent -- only a candidate falling BELOW a stated floor
    # is a blocker. Excluded here rather than in the prompt: telling the
    # model not to notice overqualification collided with an instinct it
    # clearly has, so the signal is allowed to surface and is filtered out
    # downstream instead. degree/other categories carry no direction
    # concept and are never affected by this filter.
    experience_blockers = [
        b
        for b in blockers
        if isinstance(b, dict)
        and b.get("category") in EXPERIENCE_BLOCKER_CATEGORIES
        and not (
            b.get("category") == "years_experience"
            and b.get("direction") == "over_qualified"
        )
    ]
    disqualifying_blockers = [
        b
        for b in blockers
        if not (
            isinstance(b, dict) and b.get("category") in EXPERIENCE_BLOCKER_CATEGORIES
        )
    ]
    ev["experience_blockers"] = experience_blockers
    # The persisted display list is exactly the disqualifying set. The Jobs
    # detail pane renders hard_blockers and experience_blockers as two
    # separate labeled blocks, so any category living in BOTH lists printed
    # twice -- a degree requirement showed up once as a hard blocker and
    # again as an experience blocker on the same role. Only over_qualified
    # entries were being filtered here, which left every years_experience
    # and degree blocker duplicated.
    #
    # Reusing disqualifying_blockers rather than repeating its predicate
    # keeps the two from drifting, and subsumes the over_qualified case:
    # those are years_experience, so the category filter already drops them.
    # Scoring is unaffected -- it reads disqualifying_blockers, which is
    # unchanged.
    ev["hard_blockers"] = disqualifying_blockers

    # Opt-in IC-only preference (content_settings.py's role_track editor).
    # Confidence-gated the same way as the Jobs/Pipeline view filters
    # (model.JobRow.IsManagerTrack) -- only a HIGH-confidence manager or
    # player_coach verdict excludes, since that's the only slice
    # docs/role_track.md's holdout actually measured precision on.
    role_track_excluded = bool(
        (role_track_settings or {}).get("exclude_manager")
        and ev.get("role_track") in ("manager", "player_coach")
        and ev.get("role_track_confidence") == "high"
    )

    if disqualifying_blockers or role_track_excluded:
        ev["recommendation"] = "Skip"
        reasons = [_blocker_text(b) for b in disqualifying_blockers]
        if role_track_excluded:
            reasons.append(
                f"role_track preference: excludes {ev.get('role_track')} roles"
            )
        ev["why"] = "Application skipped due to triggered deal-breakers: " + ", ".join(
            reasons
        )
        ev["composite_score"] = 0.00
        ev["estimated_interview_probability"] = 0.0
    else:
        stress_signal_count = None
        if description:
            import stress_signals

            stress_signal_count = len(stress_signals.categories(description))

        weights = dict(scoring_weights or {})
        # An in-person job has to be calm to be worth the commute: a
        # profile can scale the stress penalty for onsite/hybrid postings.
        multiplier = float(
            (work_constraints_settings or {}).get("onsite_stress_multiplier") or 1.0
        )
        if multiplier != 1.0 and posting_workplace in (
            location_filter.ONSITE,
            location_filter.HYBRID,
        ):
            for key, default in (  # type: ignore[assignment]
                (
                    "stress_signal_penalty_per_category",
                    STRESS_SIGNAL_PENALTY_PER_CATEGORY,
                ),
                ("stress_signal_max_penalty", STRESS_SIGNAL_MAX_PENALTY),
            ):
                base_value = weights.get(key)
                weights[key] = (
                    default if base_value is None else base_value
                ) * multiplier
        comp = fit_composite_score(
            fit_score,
            interview_odds_score,
            practical_pursue_score,
            posting_age_days=(
                posting_age_days
                if posting_age_days is not None
                else ev.get("posting_age_days")
            ),
            distance_miles=distance_miles if is_commutable_local else None,
            radius_miles=radius_miles if is_commutable_local else None,
            stress_signal_count=stress_signal_count,
            capability_gap_count=len(ev.get("capability_gaps") or []),
            stress_signal_penalty_per_category=weights.get(
                "stress_signal_penalty_per_category"
            ),
            stress_signal_max_penalty=weights.get("stress_signal_max_penalty"),
            low_stress_bonus=weights.get("low_stress_bonus"),
            stretch_gap_penalty_per_item=weights.get("stretch_gap_penalty_per_item"),
            stretch_gap_max_penalty=weights.get("stretch_gap_max_penalty"),
            posting_legitimacy=ev.get("posting_legitimacy"),
            legitimacy_caution_penalty=weights.get("legitimacy_caution_penalty"),
            legitimacy_suspicious_penalty=weights.get("legitimacy_suspicious_penalty"),
            constraint_penalty=constraint_penalty,
        )
        ev["composite_score"] = comp

        # Derived recommendation if was Skip due to cleared onsite blocker
        rec = ev.get("recommendation")
        if is_commutable_local and (rec == "Skip" or not rec):
            if comp >= 3.8:
                ev["recommendation"] = "Strong pursue"
            elif comp >= 2.5:
                # Was two branches, with the >= 3.2 one emitting "Pursue" --
                # not a member of FitEvaluationSchema's Literal, absent from
                # theme.RECOMMENDATION_COLORS/STYLES (so it rendered unstyled),
                # and live in 2 stored evaluations. Collapsed into the valid
                # neighbouring tier rather than inventing a fifth label.
                ev["recommendation"] = "Selective pursue"
            else:
                ev["recommendation"] = "Low-priority pursue" if comp > 1.5 else "Skip"

        # Estimated interview odds
        x = interview_odds_score
        points = [(1.0, 0.2), (2.0, 2.0), (3.0, 5.0), (4.0, 12.0), (5.0, 25.0)]
        if x <= 1.0:
            estimated_prob = 0.2
        elif x >= 5.0:
            estimated_prob = 25.0
        else:
            estimated_prob = 0.0
            for i in range(len(points) - 1):
                x0, y0 = points[i]
                x1, y1 = points[i + 1]
                if x0 <= x <= x1:
                    estimated_prob = round(y0 + (x - x0) * (y1 - y0) / (x1 - x0), 1)
                    break
        ev["estimated_interview_probability"] = estimated_prob

    return ev


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

    for entry in jd_data.get("social_connections") or []:
        name = entry.get("fullName") or entry.get("firstName") or ""
        if not name:
            continue
        contacts.append(
            {
                "name": name,
                "title": entry.get("jobTitle") or "",
                "company": entry.get("companyName") or "",
                "linkedin_url": entry.get("linkedinUrl") or "",
                "connection_type": "JobRight match",
            }
        )

    personal = jd_data.get("personal_social_connections") or {}
    for tie_type in ("company", "school"):
        for entry in personal.get(tie_type) or []:
            name = entry.get("fullName") or entry.get("firstName") or ""
            if not name:
                continue
            contacts.append(
                {
                    "name": name,
                    "title": entry.get("jobTitle") or "",
                    "company": entry.get("companyName") or "",
                    "linkedin_url": entry.get("linkedinUrl") or "",
                    "connection_type": f"Personal {tie_type} connection",
                }
            )

    return contacts


_CONTACT_TITLE_KEYWORDS = ("hr", "recruit", "talent", "people")


def _resolve_contact_fallback(letter_data: dict, jd_data: dict) -> None:
    """Fills contact_name/contact_title from already-scraped, real JD
    contacts (find_jd_contacts()) when the model found no named contact
    in the JD text itself. Mutates letter_data in place. Never invents a
    person -- prefers a contact whose title reads as HR/recruiting/talent,
    else the first scraped contact; no-op if none exist."""
    if letter_data.get("contact_name"):
        return
    contacts = find_jd_contacts(jd_data)
    if not contacts:
        return
    chosen = next(
        (
            c
            for c in contacts
            if any(k in (c.get("title") or "").lower() for k in _CONTACT_TITLE_KEYWORDS)
        ),
        contacts[0],
    )
    letter_data["contact_name"] = chosen.get("name", "")
    letter_data["contact_title"] = chosen.get("title", "")


def _resolve_company_location(research: dict | None, jd_data: dict) -> str:
    """Prefers company_hq_location from company research (traceable to
    real source text); falls back to the JD's own posted location.
    Shown regardless of remote/on-site status -- the candidate wants the
    address line for professionalism even on remote roles."""
    if research and research.get("company_hq_location"):
        return research["company_hq_location"]
    return jd_data.get("location") or ""


_SMALL_TITLE_WORDS = {"and", "of", "for", "the", "to", "in", "on", "at", "a", "an"}


_WORD_COUNT_VIOLATION = re.compile(
    r"Expected (\d+)-(\d+) words across body paragraphs, got (\d+)"
)


def _word_count_fix_guidance(violations) -> str:
    """Turns a word-count violation into an explicit instruction.

    Listed under "change nothing else", a bare "got 184" produced small
    edits that never closed the gap: one sample took 184 -> 200 -> 234 ->
    235 across every retry and still shipped short."""
    for v in violations:
        m = _WORD_COUNT_VIOLATION.search(str(v))
        if not m:
            continue
        low, high, got = (int(x) for x in m.groups())
        target = (low + high) // 2
        if got < low:
            return (
                f"\n\nLENGTH IS THE MAIN FIX: the body paragraphs total {got} words; "
                f"rewrite them to about {target} words (add roughly {target - got}). "
                "Give each body paragraph one or two more sentences of concrete, "
                "verified detail from the background context -- never filler."
            )
        if got > high:
            return (
                f"\n\nLENGTH IS THE MAIN FIX: the body paragraphs total {got} words; "
                f"cut them to about {target} (remove roughly {got - target})."
            )
    return ""


def _coverletter_role_title(jd_data: dict, stem: str) -> str:
    """The role title a cover letter names in its first paragraph: the
    posting's own job_title, else Part 1 of the matching resume's tagline
    (a plain-text JD has no structured title). Trimmed of a trailing
    " — subtitle" or "(Remote)", and title-cased if it arrived in caps."""
    title = str((jd_data or {}).get("job_title") or "").strip()
    if not title:
        title = _read_matching_resume_tagline(stem).split("|")[0].strip()
    title = re.split(r"\s+[—–-]\s+|\s*\(", title)[0].strip()
    if title.isupper():
        words = []
        for index, word in enumerate(title.split()):
            lower = word.lower()
            if index and lower in _SMALL_TITLE_WORDS:
                words.append(lower)
            elif len(word) <= 3 and word.isalpha() and lower not in _SMALL_TITLE_WORDS:
                words.append(word)  # likely an acronym: ML, AI, BI
            else:
                words.append(word.capitalize())
        title = " ".join(words)
    return title


def _read_matching_resume_tagline(stem: str) -> str:
    """Best-effort read of a resume TAGLINE already built for the same
    JD -- '{stem}_Resume.json' in this profile's output/json dir, the
    exact filename build_tailored_resume() writes (see _build_output_stem,
    the shared stem builder). Returns "" if no resume has been built yet
    for this JD, or if its JSON can't be parsed -- a cover letter can
    always be generated standalone."""
    resume_path = os.path.join(
        profile_paths.output_dir(), "json", f"{stem}_Resume.json"
    )
    if not os.path.exists(resume_path):
        return ""
    try:
        with open(resume_path, "r", encoding="utf-8") as f:
            resume_data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return ""
    return resume_data.get("TAGLINE", "") if isinstance(resume_data, dict) else ""


def _build_output_stem(jd_path: str) -> str:
    """Returns '<CandidateName>[_Title][_Company]' for resume/cover-letter
    output filenames, with the candidate name prefix derived from the
    active profile's profile.yml (candidate.full_name, spaces stripped --
    e.g. "Alex Mercer" -> "AlexMercer"). Role title and company
    segments are each included only when known -- omitted entirely (not a
    placeholder like "Unknown") when missing, since a filename with a
    placeholder in it would always need fixing before sending, whereas
    e.g. "AlexMercer_CampaignManager_Resume" is still sendable as-is.

    When NEITHER is known the stem falls back to the JD file's own
    basename rather than the bare candidate name. A bare stem is not a
    harmless shorter name -- it is the SAME name for every meta-less JD,
    so each such build silently overwrote the last one's PDF (and the
    recruiter resume's, which is deliberately the bare name). The JD
    filename is already distinctive in practice
    ("2026-09-15_Customerio_SeniorDataScientist"), so it separates those
    builds without inventing a placeholder."""
    job_title, company_name = jd_manager.extract_job_meta(jd_path)
    parts = [profile_paths.full_name().replace(" ", "")]
    if job_title:
        parts.append(jd_manager.sanitize_for_filename(job_title))
    if company_name:
        parts.append(jd_manager.sanitize_for_filename(company_name))
    if not job_title and not company_name:
        basename = os.path.splitext(os.path.basename(jd_path))[0]
        sanitized = jd_manager.sanitize_for_filename(basename)
        if sanitized:
            parts.append(sanitized)
    return "_".join(parts)


def _sort_audited_bullets(bullets: list, critiques: list) -> tuple[list, list]:
    """Stable-sorts audited bullets by their critique (None sorts last) and
    returns (sorted_bullets, order), where order[k] is the ORIGINAL index of
    sorted_bullets[k]. The order matters: callers recover each bullet's
    company by pairing with bullet_tuples by index, so they must apply the
    same permutation to bullet_tuples."""
    order = sorted(
        range(len(bullets)), key=lambda i: _bullet_sort_key(critiques[i] or {})
    )
    return [bullets[i] for i in order], order


def format_company_research_block(research: dict) -> str:
    """Formats a CompanyResearchSchema-shaped dict into the
    '=== COMPANY RESEARCH ===' context block both build_tailored_coverletter
    and build_tailored_resume fold into their system-instruction context."""
    block = (
        "\n\n=== COMPANY RESEARCH ===\n"
        f"Overall tone: {research.get('overall_tone_adjective', '')}\n"
        f"Register: {research.get('tone_register', '')} | Framing: {research.get('pronoun_framing', '')} | "
        f"Sentence style: {research.get('sentence_style', '')} | Jargon: {research.get('jargon_density', '')}\n"
        f"Recurring brand words: {', '.join(research.get('recurring_keywords', []))}\n"
        "Company facts (use at most 1-2, never fabricate beyond these):\n"
        + "\n".join(f"- {fact}" for fact in research.get("company_facts", []))
    )

    highlights = research.get("notable_highlights") or []
    if highlights:
        block += (
            "\n\nNotable highlights (use at most 1-2, ideal for an opening hook, never fabricate beyond these):\n"
            + "\n".join(f"- {h}" for h in highlights)
        )

    pairs = [
        f"{p.get('generic_term')} -> {p.get('company_term')}"
        for p in (research.get("vocabulary_substitutions") or [])
        if isinstance(p, dict) and p.get("generic_term") and p.get("company_term")
    ]
    if pairs:
        block += (
            "\nPreferred vocabulary (use the company's term in place of the generic one "
            f"wherever it reads naturally): {', '.join(pairs)}"
        )

    return block


# Front-loading emphasis wording per ATS weight_tier (see
# scan_ats.classify_ats()) -- enterprise/AI-prescreened platforms scan for
# exact literal terms, so keyword front-loading matters there; startup/
# evidence-based platforms are read by a human first, so the same terms
# should read naturally rather than mechanically. "unknown" (no
# classification, or a source_url the classifier didn't recognize) gets
# the same light-touch wording as the human-read tiers.
_ATS_TIER_EMPHASIS = {
    "enterprise_high": "critical -- this posting runs through an enterprise ATS that scans for exact literal term matches",
    "ai_prescreened": "critical -- this posting is AI-prescreened, which weighs exact keyword matches heavily",
    "startup_zero": "a light touch -- a human reads this first, so work these in naturally rather than front-loading mechanically",
    "evidence_based": "a light touch -- weave these in naturally alongside real evidence rather than front-loading mechanically",
    "unknown": "helpful context -- include naturally where they fit",
}


def build_recommendations_block(recommendations) -> str:
    """profile.yml's key_recommendations, formatted for the cover-letter
    builder, or "" when there are none.

    Until 2026-09-13 nothing read key_recommendations at all -- bootstrap
    wrote it, and both the evaluator and rewriter trims exclude it on
    purpose (a third party's praise is not evidence of fit or a source of
    bullet facts). A cover letter is where a short, attributed line from a
    real reference helps, so this is its one consumer. The quotes are sent
    verbatim and the model may use at most one, unaltered; validate_coverletter
    exempts quoted text from its third-person check, since a recommendation
    naming the candidate is not the letter slipping into third person."""
    lines = []
    for rec in recommendations or []:
        if not isinstance(rec, dict):
            continue
        quote = " ".join(str(rec.get("quote") or "").split())
        name = str(rec.get("name") or "").strip()
        if not quote or not name:
            continue
        attribution = name + (f", {rec['title']}" if rec.get("title") else "")
        detail = ", ".join(
            str(x)
            for x in (rec.get("relationship"), str(rec.get("date") or "")[:4])
            if x
        )
        lines.append(
            f'- "{quote}" -- {attribution}' + (f" ({detail})" if detail else "")
        )
    if not lines:
        return ""
    return (
        "\n\n=== RECOMMENDATIONS (verbatim, from people who worked with the candidate) ===\n"
        "Optional. You MAY quote at most ONE short line from below, and only if it directly "
        "supports something this role asks for: verbatim, inside quotation marks, attributed "
        "by name and title, woven into a first-person sentence (the letter stays in the "
        "candidate's voice). Keep it under 30 words; you may shorten it with an ellipsis, but "
        "never change, combine or paraphrase the words, and never attribute anything not "
        "listed here. If none fits naturally, use none.\n" + "\n".join(lines) + "\n"
    )


def _build_keyword_block(
    jd_keywords: dict | None, ats_classification: dict | None
) -> str:
    """Formats up to 8 top JD keywords (Feature #12) into a
    '=== KEYWORDS ===' context block build_tailored_coverletter() folds
    into its system-instruction context, with front-loading emphasis
    scaled by the JD's ATS weight_tier (Feature #1). Returns '' when no
    keywords are available -- most callers before this feature existed."""
    if not jd_keywords:
        return ""
    terms = (
        list(jd_keywords.get("tools") or [])
        + list(jd_keywords.get("hard_skills") or [])
        + list(jd_keywords.get("core_functions") or [])
    )[:8]
    if not terms:
        return ""

    weight_tier = (ats_classification or {}).get("weight_tier", "unknown")
    emphasis = _ATS_TIER_EMPHASIS.get(weight_tier, _ATS_TIER_EMPHASIS["unknown"])
    return (
        "\n\n=== KEYWORDS ===\n"
        f"Top terms from this job description: {', '.join(terms)}\n"
        f"Front-loading these into the first 100 words of paragraph 1 is {emphasis}.\n"
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
        self.engine_dir = os.path.join(PROJECT_ROOT, "resume-engine")
        self.prompts_dir = os.path.join(self.engine_dir, "prompts")
        self.rules_dir = os.path.join(self.engine_dir, "rules")
        self.scoring_dir = os.path.join(self.engine_dir, "scoring")
        self.kb_dir = profile_paths.kb_dir()
        self.templates_dir = os.path.join(self.engine_dir, "templates")
        self.output_json_dir = os.path.join(profile_paths.output_dir(), "json")
        self.output_html_dir = os.path.join(profile_paths.output_dir(), "html")
        self.output_pdf_dir = os.path.join(profile_paths.output_dir(), "pdf")
        self.output_docx_dir = os.path.join(profile_paths.output_dir(), "docx")
        self.jds_dir = profile_paths.jds_dir()
        os.makedirs(self.output_json_dir, exist_ok=True)
        self._segment_cache: dict = {}
        self._gemma_segment_cache: dict = {}
        try:
            self.deep_evidence_keywords = (
                self.load_yaml(self.kb_dir, "profile.yml") or {}
            ).get("deep_evidence_keywords") or []
        except Exception:
            self.deep_evidence_keywords = (
                profile_paths.profile_yaml().get("deep_evidence_keywords") or []
            )
        self.voice_rules = self.load_yaml(self.scoring_dir, "voice_rules.yaml") or {}

    def load_yaml(self, dir_path, filename):
        path = os.path.join(dir_path, filename)
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_prompt(self, filename):
        path = os.path.join(self.prompts_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def load_knowledge_base(self):
        """
        Stitches allowlisted and dynamically discovered KB files into a single
        static context string. Output is sorted so it is byte-for-byte
        identical across runs for optimal prompt-prefix caching.
        """
        master_context = "=== SYSTEM KNOWLEDGE BASE ===\n\n"
        if os.path.exists(self.kb_dir):
            for filename in get_active_kb_files(self.kb_dir):
                filepath = os.path.join(self.kb_dir, filename)
                if not os.path.exists(filepath):
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} KB allowlist entry not found, skipping: {filename}",
                        soft_wrap=True,
                    )
                    continue
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    if filename.endswith(".json"):
                        # Pretty-printed JSON is mostly whitespace, and the
                        # full tools ledger alone pushed this prompt past the
                        # free tier's 250k tokens/minute, so every retry 429'd.
                        loaded = json.loads(content)
                        content = (
                            compact_tools_text(loaded.get("tools", []))
                            if filename == "verified_tools.json"
                            else json.dumps(
                                loaded, ensure_ascii=False, separators=(",", ":")
                            )
                        )
                    master_context += f"--- START OF {filename} ---\n{content}\n--- END OF {filename} ---\n\n"
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} Could not load KB file {filename}: {e}",
                        soft_wrap=True,
                    )
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
        voice_preferences = profile_data.get("voice_preferences") or {}

        if (
            not roles
            and not protected
            and not certs
            and not education
            and not voice_example
            and not voice_preferences.get("summary_first_person")
        ):
            return ""

        lines = ["\n\n=== ROLE RULES ==="]

        if roles:
            lines.append("Per-Role Bullet Count Targets:")
            lines.append("| Company | Min | Target | Max | Page |")
            lines.append("| --- | --- | --- | --- | --- |")
            for role in roles:
                name = role.get("name") or role.get("company", "")
                min_b = role.get("min_bullets", 1)
                tgt_b = role.get("target_bullets", min_b)
                max_b = role.get("max_bullets")
                max_display = max_b if max_b is not None else "-"
                pg = role.get("page", 1)
                lines.append(f"| {name} | {min_b} | {tgt_b} | {max_display} | {pg} |")

            must_fit_page_1 = [
                (r.get("name") or r.get("company", ""))
                for r in roles
                if r.get("must_fit_page_1")
            ]
            must_fit_page_1 = [name for name in must_fit_page_1 if name]
            if must_fit_page_1:
                lines.append(
                    f"\nThe following roles must fit entirely on page 1: {', '.join(must_fit_page_1)}."
                )

            flex_order = sorted(roles, key=lambda r: r.get("flex_priority", 999))
            flex_names = [(r.get("name") or r.get("company", "")) for r in flex_order]
            flex_names = [name for name in flex_names if name]
            if flex_names:
                lines.append(
                    "\nTrim priority (lowest-priority roles trimmed toward their Min first, before any "
                    f"higher-priority role loses a bullet): {', '.join(flex_names)}."
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
                # bullet_count missing (not just falsy) used to raise
                # KeyError here and abort EVERY resume build for the whole
                # profile -- a hand-written profile.yml with education
                # entries that only set institution/credential is an easy,
                # unenforced-until-now mistake to make (see
                # test_profile_yml_schema.py's own
                # test_education_entries_declare_an_institution_and_bullet_count,
                # which now actually asserts presence rather than
                # type-checking a defaulted 0). 1 is a safe minimum, not a
                # guess at the "right" number -- profile.yml is still the
                # place to set the real intended count.
                bullet_count = ed.get("bullet_count", 1)
                # Same defense for institution/credential: a partial entry
                # renders what it has rather than aborting the build.
                label = (
                    " -- ".join(
                        p for p in (ed.get("institution"), ed.get("credential")) if p
                    )
                    or "Unnamed education entry"
                )
                lines.append(f"{i}. {label}: exactly {bullet_count} bullet(s)")

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

        design_only_names = [
            entry.get("name")
            or entry.get("credential")
            or entry.get("institution")
            or "Unnamed credential"
            for entry in (certs + education)
            if entry.get("design_only")
        ]
        if design_only_names:
            lines.append(
                "\nDesign-Only Credentials -- "
                + ", ".join(design_only_names)
                + " only belong on this resume when INCLUDE_DESIGN_CREDENTIALS is true. "
                "Set it true ONLY if the JD has explicit graphic/visual design responsibilities "
                "as an actual job requirement (producing layouts, brand assets, or UI/UX work; "
                "naming tools like Illustrator, Photoshop, InDesign, or Figma) -- not merely "
                "'creative' or 'visual communication' as a soft nice-to-have. False for every "
                "other archetype, including content/copy/marketing roles. normalize_resume.py "
                "drops these credentials when the field is false, so leave them out of your own "
                "drafted Certifications/Education content regardless of what you set that field to."
            )

        if roles:
            page_1_roles = [r["name"] for r in roles if r.get("page") == 1]
            page_2_roles = [r["name"] for r in roles if r.get("page") == 2]
            if page_1_roles or page_2_roles:
                lines.append(
                    f"\nSection Order (Page 1 -> Page 2): Page 1 Work Experience: {', '.join(page_1_roles)}. "
                    f"Page 2 Work Experience: {', '.join(page_2_roles)}."
                )

        if voice_example:
            lines.append(
                f'\nVoice Calibration Example (this candidate\'s authentic voice): "{voice_example}"'
            )

        # Per-profile Summary voice policy (profile.yml's
        # voice_preferences.summary_first_person). Deliberately phrased as a
        # property of THIS candidate's documented register, and only emitted
        # when the profile opts in -- a profile without the key gets no line
        # and tailor_resume.md's default (pronoun-free Summary) applies.
        if (profile_data.get("voice_preferences") or {}).get("summary_first_person"):
            lines.append(
                "\nSummary Voice: first person (\"I've owned...\") is this candidate's real "
                'register -- their own favorite summaries all speak as "I" (see the '
                "=== VOICE FAVORITES === context block when present). Write the Summary in "
                'first person; never third person ("She leads...", "[Name] is a..."). '
                "Bullets, Skills, and Education stay pronoun-free regardless."
            )

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
        for i, (institution, options) in enumerate(
            profile_paths.education_achievement_slots(), 1
        ):
            field_name = f"EDU_ACHIEVEMENT_KEY_{i}"
            properties[field_name] = {
                "type": "string",
                "enum": list(options.keys()),
                "description": (
                    f"Pre-approved achievement-bullet choice for {institution} -- "
                    + "; ".join(
                        f"{key} = {framing}" for key, framing in options.items()
                    )
                ),
            }
            required.append(field_name)

        # Same dynamic-field mechanism as above, for a different profile-
        # specific gate: certifications/education entries marked
        # design_only in fixed_credentials (see profile_paths.
        # has_design_only_credentials()) are only worth showing when the
        # JD itself has real graphic-design responsibilities -- normalize_
        # resume.py reads this field to decide whether to include them.
        # Omitted entirely for a profile with no such entries.
        if profile_paths.has_design_only_credentials():
            properties["INCLUDE_DESIGN_CREDENTIALS"] = {
                "type": "boolean",
                "description": (
                    "True only if the JD has explicit graphic/visual design "
                    "responsibilities as an actual job requirement (producing "
                    "layouts, brand assets, or UI/UX work; naming tools like "
                    "Illustrator, Photoshop, InDesign, or Figma) -- not merely "
                    "'creative' or 'visual communication' as a soft nice-to-have. "
                    "False for every other archetype."
                ),
            }
            required.append("INCLUDE_DESIGN_CREDENTIALS")

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
        cli_art.console.print(
            f"\n{theme.colorize_icon('hint')} Loading knowledge base context (Tier 1)...",
            soft_wrap=True,
        )
        sections = []

        profile_path = os.path.join(self.kb_dir, "profile.yml")
        if os.path.exists(profile_path):
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                cli_art.detail(
                    f"   {theme.colorize_icon('success')} Loaded profile.yml ({len(raw):,} chars)"
                )
                trimmed = _trim_profile_yaml(raw)
                if trimmed:
                    cli_art.detail(
                        f"   {theme.colorize_icon('hint')} profile.yml trimmed to {len(trimmed):,} chars"
                    )
                    sections.append(
                        "=== TARGET ROLES & PROFILE (from profile.yml) ===\n"
                        "Use these to understand what roles this bullet needs to appeal to and what to avoid.\n"
                        + trimmed
                    )
            except Exception as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load profile.yml: {e}",
                    soft_wrap=True,
                )

        for fname, header, note in [
            (
                "verified_facts.json",
                "=== VERIFIED FACTS (high-confidence claims -- use freely) ===",
                "These are the only facts about this candidate's career that are evidence-backed.\nDo NOT invent facts outside this list.",
            ),
            (
                "verified_tools.json",
                "=== VERIFIED TOOLS (HF002 guard -- only claim tools listed here) ===",
                "Never claim proficiency with any tool not present in this list.",
            ),
            (
                "verified_projects.json",
                "=== VERIFIED PROJECTS ===",
                "Use these to add accurate project detail and scope.",
            ),
        ]:
            fpath = os.path.join(self.kb_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    # Names only -- the whole entries cost ~77k tokens a
                    # call on a large ledger; see compact_tools_text().
                    data = (
                        compact_tools_text(loaded.get("tools", []))
                        if fname == "verified_tools.json"
                        else json.dumps(
                            loaded, ensure_ascii=False, separators=(",", ":")
                        )
                    )
                    cli_art.detail(
                        f"   {theme.colorize_icon('success')} Loaded {fname} ({len(data):,} chars)"
                    )
                    sections.append(f"{header}\n{note}\n{data}")
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load {fname}: {e}",
                        soft_wrap=True,
                    )

        voice_anchors_path = os.path.join(self.kb_dir, "voice-anchors.md")
        if os.path.exists(voice_anchors_path):
            try:
                with open(voice_anchors_path, "r", encoding="utf-8") as f:
                    data = f.read()
                cli_art.detail(
                    f"   {theme.colorize_icon('success')} Loaded voice-anchors.md ({len(data):,} chars)"
                )
                sections.append(
                    f"=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n{data}"
                )
            except Exception as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load voice-anchors.md: {e}",
                    soft_wrap=True,
                )
        else:
            sections.append(
                "=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n"
            )

        voice_favorites_path = os.path.join(self.kb_dir, "voice-favorites.md")
        if os.path.exists(voice_favorites_path):
            try:
                with open(voice_favorites_path, "r", encoding="utf-8") as f:
                    data = f.read()
                cli_art.detail(
                    f"   {theme.colorize_icon('success')} Loaded voice-favorites.md ({len(data):,} chars)"
                )
                sections.append(
                    "=== VOICE FAVORITES (summaries the candidate wrote and liked -- match this register) ===\n"
                    f"{data}"
                )
            except Exception as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load voice-favorites.md: {e}",
                    soft_wrap=True,
                )

        if include_evidence_guide:
            evidence_guide_path = os.path.join(self.kb_dir, "evidence-guide.csv")
            if os.path.exists(evidence_guide_path):
                try:
                    with open(evidence_guide_path, "r", encoding="utf-8") as f:
                        data = f.read()
                    cli_art.detail(
                        f"   {theme.colorize_icon('success')} Loaded evidence-guide.csv ({len(data):,} chars)"
                    )
                    sections.append(
                        f"=== EVIDENCE GUIDE (thematic career-proof clusters) ===\n{data}"
                    )
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} build_audit_static_prefix: could not load evidence-guide.csv: {e}",
                        soft_wrap=True,
                    )
            else:
                sections.append(
                    "=== EVIDENCE GUIDE (thematic career-proof clusters) ===\n"
                )

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
            (
                "verified_facts.json",
                "=== VERIFIED FACTS (high-confidence claims -- use freely) ===",
                "These are the only facts about this candidate's career that are evidence-backed.\nDo NOT invent facts outside this list.",
            ),
            (
                "verified_tools.json",
                "=== VERIFIED TOOLS (HF002 guard -- only claim tools listed here) ===",
                "Never claim proficiency with any tool not present in this list.",
            ),
        ]:
            fpath = os.path.join(self.kb_dir, fname)
            if os.path.exists(fpath):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    # Names only -- the whole entries cost ~77k tokens a
                    # call on a large ledger; see compact_tools_text().
                    data = (
                        compact_tools_text(loaded.get("tools", []))
                        if fname == "verified_tools.json"
                        else json.dumps(
                            loaded, ensure_ascii=False, separators=(",", ":")
                        )
                    )
                    sections.append(f"{header}\n{note}\n{data}")
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} build_audit_static_prefix_gemma: could not load {fname}: {e}",
                        soft_wrap=True,
                    )

        voice_anchors_path = os.path.join(self.kb_dir, "voice-anchors.md")
        if os.path.exists(voice_anchors_path):
            try:
                with open(voice_anchors_path, "r", encoding="utf-8") as f:
                    data = f.read()
                sections.append(
                    f"=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n{data}"
                )
            except Exception as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} build_audit_static_prefix_gemma: could not load voice-anchors.md: {e}",
                    soft_wrap=True,
                )
        else:
            sections.append(
                "=== VOICE ANCHORS (real past answers, themes and quotes worth echoing) ===\n"
            )

        # Deliberately NOT here: voice-favorites.md. This slim tier exists
        # because gemma-4-31b-it's 16k TPM cap leaves little headroom once
        # the KB segment bundle is added (2026-07-16), and the favorites add
        # ~1.1k tokens per rewrite call across every bullet in the run. The
        # register they teach matters for the BUILDER (flash-lite, full
        # tier) and cover letters, both of which load it via
        # build_audit_static_prefix()/load_knowledge_base(); Gemma's rewrite
        # register is covered by the two rewrite-goal lines in
        # REWRITE_SYSTEM_BASE instead.

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
                data = json.dumps(
                    json.load(f), ensure_ascii=False, separators=(",", ":")
                )
        except Exception as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} recruiter_context_block: could not load recruiter_memory_patterns.json: {e}",
                soft_wrap=True,
            )
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
        critique_prompt = self.load_prompt("critique_bullet.md")
        manager_test_rules = json.dumps(
            self.load_yaml(self.scoring_dir, "manager_test.yaml")
        )
        believability_rules = json.dumps(
            self.load_yaml(self.scoring_dir, "believability.yaml")
        )
        style_rules = json.dumps(self.load_yaml(self.rules_dir, "style_rules.yaml"))
        language_quality = json.dumps(
            self.load_yaml(self.rules_dir, "language_quality.yaml")
        )
        verb_taxonomy = json.dumps(self.load_yaml(self.rules_dir, "verb_taxonomy.yaml"))
        verb_intent_mapping = json.dumps(
            self.load_yaml(self.rules_dir, "verb_intent_mapping.yaml")
        )
        hard_failures = json.dumps(self.load_yaml(self.rules_dir, "hard_failures.yaml"))
        truthfulness_rules = json.dumps(
            self.load_yaml(self.rules_dir, "truthfulness_rules.yaml")
        )

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
        # Lazy pandas/numpy -- see _LAZY_HEAVY_DEPS at the top of this module.
        import pandas as pd

        sections = []

        cv_path = os.path.join(self.kb_dir, "cv.md")
        cv_full = ""
        if os.path.exists(cv_path):
            try:
                with open(cv_path, "r", encoding="utf-8") as f:
                    cv_full = f.read()
            except Exception as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle: could not load cv.md: {e}",
                    soft_wrap=True,
                )

        cv_section = extract_cv_section(cv_full, company)
        if cv_section:
            label = (
                "ROLE CONTEXT (cv.md excerpt)"
                if cv_section != cv_full
                else "CAREER OVERVIEW (cv.md)"
            )
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
                            df_claims["Use in Resume?"]
                            .str.strip()
                            .str.lower()
                            .str.startswith("yes")
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
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle: could not load verified-claims.csv: {e}",
                        soft_wrap=True,
                    )

            screenshot_path = os.path.join(
                self.kb_dir, "extracted-screenshot-metrics.csv"
            )
            if os.path.exists(screenshot_path):
                try:
                    df_screens = pd.read_csv(screenshot_path)
                    screenshot_text = df_screens.to_csv(index=False)
                    if screenshot_text:
                        sections.append(
                            f"=== SCREENSHOT-SOURCED METRICS ===\n{screenshot_text}"
                        )
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle: could not load screenshot metrics: {e}",
                        soft_wrap=True,
                    )

            metrics_path = os.path.join(self.kb_dir, "verified_metrics.json")
            if os.path.exists(metrics_path):
                try:
                    with open(metrics_path, "r", encoding="utf-8") as f:
                        verified_metrics = json.dumps(
                            json.load(f), ensure_ascii=False, separators=(",", ":")
                        )
                    if verified_metrics:
                        sections.append(
                            "=== VERIFIED METRICS (authoritative — use these numbers, not guesses) ===\n"
                            f"These are the ONLY numeric metrics that may be cited as hard facts in {company} bullets.\n"
                            + verified_metrics
                        )
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle: could not load verified_metrics.json: {e}",
                        soft_wrap=True,
                    )

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
        # Lazy pandas/numpy -- see _LAZY_HEAVY_DEPS at the top of this module.
        import pandas as pd

        sections = []

        cv_path = os.path.join(self.kb_dir, "cv.md")
        cv_full = ""
        if os.path.exists(cv_path):
            try:
                with open(cv_path, "r", encoding="utf-8") as f:
                    cv_full = f.read()
            except Exception as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load cv.md: {e}",
                    soft_wrap=True,
                )

        cv_section = extract_cv_section(cv_full, company)
        if cv_section:
            label = (
                "ROLE CONTEXT (cv.md excerpt)"
                if cv_section != cv_full
                else "CAREER OVERVIEW (cv.md)"
            )
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
                    filtered_projects = filter_json_entries_by_tags(
                        projects_entries, tags, MAX_GEMMA_FILTER_ROWS
                    )
                    if filtered_projects:
                        sections.append(
                            "=== VERIFIED PROJECTS (tag-filtered) ===\n"
                            "Use these to add accurate project detail and scope.\n"
                            + json.dumps(
                                filtered_projects,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load verified_projects.json: {e}",
                        soft_wrap=True,
                    )

            claims_path = os.path.join(self.kb_dir, "verified-claims.csv")
            if os.path.exists(claims_path):
                try:
                    df_claims = pd.read_csv(claims_path)
                    if "Use in Resume?" in df_claims.columns:
                        df_claims = df_claims[
                            df_claims["Use in Resume?"]
                            .str.strip()
                            .str.lower()
                            .str.startswith("yes")
                        ]
                    filtered_claims = filter_claims_by_tags(
                        df_claims, tags, max_rows=MAX_GEMMA_FILTER_ROWS
                    )
                    claims_text = get_verified_claims_text(filtered_claims)
                    if claims_text:
                        sections.append(
                            f"=== VERIFIED CLAIMS & METRICS ({company} — resume-usable, tag-filtered) ===\n"
                            "Use these to inject real, verified metrics where appropriate. "
                            "Do NOT use metrics marked Medium or Low confidence as hard facts.\n"
                            + claims_text
                        )
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load verified-claims.csv: {e}",
                        soft_wrap=True,
                    )

            screenshot_path = os.path.join(
                self.kb_dir, "extracted-screenshot-metrics.csv"
            )
            if os.path.exists(screenshot_path):
                try:
                    df_screens = pd.read_csv(screenshot_path)
                    filtered_screens = filter_claims_by_tags(
                        df_screens, tags, max_rows=MAX_GEMMA_FILTER_ROWS
                    )
                    screenshot_text = filtered_screens.to_csv(index=False)
                    if screenshot_text:
                        sections.append(
                            f"=== SCREENSHOT-SOURCED METRICS (tag-filtered) ===\n{screenshot_text}"
                        )
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load screenshot metrics: {e}",
                        soft_wrap=True,
                    )

            metrics_path = os.path.join(self.kb_dir, "verified_metrics.json")
            if os.path.exists(metrics_path):
                try:
                    with open(metrics_path, "r", encoding="utf-8") as f:
                        metrics_entries = json.load(f).get("metrics", [])
                    filtered_metrics = filter_json_entries_by_tags(
                        metrics_entries, tags, MAX_GEMMA_FILTER_ROWS
                    )
                    if filtered_metrics:
                        sections.append(
                            "=== VERIFIED METRICS (authoritative — tag-filtered) ===\n"
                            f"These are the ONLY numeric metrics that may be cited as hard facts in {company} bullets.\n"
                            + json.dumps(
                                filtered_metrics,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                        )
                except Exception as e:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} _build_audit_segment_bundle_gemma: could not load verified_metrics.json: {e}",
                        soft_wrap=True,
                    )

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
            cli_art.detail(
                f"   {theme.colorize_icon('warning')} Cache miss for {key} — building segment on demand."
            )
            self._segment_cache[key] = self._build_audit_segment_bundle(
                company, normalized_tags
            )
        return self._segment_cache[key]

    def audit_segment_bundle_for_gemma(self, company: str, tags: str) -> str:
        """Memoized accessor for _build_audit_segment_bundle_gemma (Tier 2,
        Gemma-slim) -- mirrors rewrite_bullets.py's
        context_block_for_bullet_gemma()."""
        normalized_tags = self._normalize_tags(tags)
        key = (company, normalized_tags)
        if key not in self._gemma_segment_cache:
            cli_art.detail(
                f"   {theme.colorize_icon('warning')} Gemma cache miss for {key} — building segment on demand."
            )
            self._gemma_segment_cache[key] = self._build_audit_segment_bundle_gemma(
                company, normalized_tags
            )
        return self._gemma_segment_cache[key]

    @staticmethod
    def _normalize_tags(tags_str: str) -> str:
        """Normalize tag string by sorting individual tags alphabetically.
        '[email][content]' and '[content][email]' both normalize to '[content][email]'.
        """
        tag_list = re.findall(r"\[([^\]]+)\]", tags_str)
        return "".join(f"[{tag}]" for tag in sorted(tag_list))

    def warm_segment_cache(self, bullet_tuples: List[Tuple[str, str, str]]) -> None:
        """
        Mirrors rewrite_bullets.py's KnowledgeBase.warm_segment_cache(): pre-builds
        every unique (company, tags) segment bundle before the audit loop starts,
        so audit_segment_bundle_for() is a pure dict lookup with no on-demand file
        I/O mid-loop, and the terminal report shows what's cached upfront.
        """
        self._segment_cache = {}
        self._gemma_segment_cache = {}
        pairs = sorted(
            {
                (company, self._normalize_tags(tags))
                for _, company, tags in bullet_tuples
            }
        )
        cli_art.detail(
            f"\n{theme.colorize_icon('hint')} Warming segment cache for {len(pairs)} unique (company, tags) combos..."
        )
        cli_art.detail("")
        for company, tags in pairs:
            bundle = self._build_audit_segment_bundle(company, tags)
            self._segment_cache[(company, tags)] = bundle
            gemma_bundle = self._build_audit_segment_bundle_gemma(company, tags)
            self._gemma_segment_cache[(company, tags)] = gemma_bundle
            deep_evidence_flag = (
                " [+claims]"
                if is_deep_evidence_bullet(company, self.deep_evidence_keywords)
                else ""
            )
            cli_art.detail(
                f"   {theme.colorize_icon('hint')} ({company[:30]!r}, {tags[:40]!r}) → {len(bundle):,} chars{deep_evidence_flag} (Gemma: {len(gemma_bundle):,} chars)"
            )
        cli_art.detail(
            f"   {theme.colorize_icon('success')} {len(self._segment_cache)} segment bundles ready.\n"
        )

    @staticmethod
    def critique_composite(scores: dict) -> float:
        # Lazy pandas/numpy -- see _LAZY_HEAVY_DEPS at the top of this module.
        import pandas as pd

        numeric = sum(
            pd.to_numeric(scores.get(c, 0), errors="coerce") or 0
            for c in (
                "accuracy_score",
                "believability_score",
                "clarity_score",
                "ats_value",
            )
        )
        mgr_bonus = 10 if str(scores.get("manager_test", "")).upper() == "PASS" else 0
        return numeric + mgr_bonus

    def audit_and_refine_bullets(
        self,
        bullet_tuples: List[Tuple[str, str, str]],
        static_prefix: str,
        resume_from: List[str] | None = None,
        on_bullet_complete=None,
        vocabulary_substitutions: list | None = None,
        order_out: list | None = None,
    ) -> List[str]:
        """
        Skeptical Editor audit loop.
        Accepts List[Tuple[str, str, str]] -- (bullet_text, company, tags).
        Critiques on slim static_prefix (Tier 1+2 cache architecture).
        Rewrites get segment bundle prepended (Gap 3) but critiques do not.
        """
        cli_art.detail(
            f"{theme.colorize_icon('hint')} Loading rules bundle...",
            level=cli_art.NORMAL,
        )
        cli_art.detail(
            f"{theme.colorize_icon('hint')} Static prefix (Tier 1): {len(static_prefix):,} chars — shared across ALL bullets",
            level=cli_art.NORMAL,
        )
        cli_art.detail("", level=cli_art.NORMAL)

        if not isinstance(bullet_tuples, list) or len(bullet_tuples) == 0:
            cli_art.detail(
                "  No bullets to audit -- empty or invalid input. Skipping audit loop.",
                level=cli_art.NORMAL,
            )
            return []

        refined_bullets = list(resume_from) if resume_from else []
        if len(refined_bullets) >= len(bullet_tuples):
            cli_art.detail(
                f"  Resuming: all {len(bullet_tuples)} bullets already refined in a prior run. Skipping audit loop.",
                level=cli_art.NORMAL,
            )
            return refined_bullets

        critique_system = self.build_bullet_critique_system()
        cli_art.detail(
            f"   {theme.colorize_icon('success')} Rules loaded: manager_test, believability, style_rules, language_quality, verb_taxonomy, verb_intent_mapping, hard_failures, truthfulness_rules",
            level=cli_art.NORMAL,
        )
        cli_art.detail("", level=cli_art.NORMAL)

        # Gemma-slim Tier 1 -- see build_audit_static_prefix_gemma(). Cheap
        # to build (2 small JSON files + voice-anchors.md), so it's built
        # here rather than threaded through as another caller-supplied
        # parameter the way static_prefix is.
        static_prefix_gemma = self.build_audit_static_prefix_gemma()
        cli_art.detail(
            f"{theme.colorize_icon('hint')} Gemma static prefix (slim): {len(static_prefix_gemma):,} chars — Gemma-only, flash-lite keeps the full tier",
            level=cli_art.NORMAL,
        )

        # Load rules needed for rewrite prompt
        verb_intent_mapping = self.load_yaml(self.rules_dir, "verb_intent_mapping.yaml")
        verb_taxonomy = self.load_yaml(self.rules_dir, "verb_taxonomy.yaml")
        language_quality = self.load_yaml(self.rules_dir, "language_quality.yaml")
        hard_failures = self.load_yaml(self.rules_dir, "hard_failures.yaml")
        truthfulness_rules = self.load_yaml(self.rules_dir, "truthfulness_rules.yaml")
        style_rules = self.load_yaml(self.rules_dir, "style_rules.yaml")

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
            "avoid": verb_taxonomy.get("avoid", []),
            "archetype_allows": verb_taxonomy.get("archetype_allows", {}),
        }
        language_quality_curated = {
            "weak_verbs": language_quality.get("weak_verbs", {}),
            "buzzwords": language_quality.get("buzzwords", {}),
            "ai_language_patterns": language_quality.get("ai_language_patterns", {}),
            "specificity_checks": language_quality.get("specificity_checks", {}),
            "final_principle": language_quality.get("final_principle", ""),
        }

        def _rewrite_block(
            verb_intent_data: dict, style_data: dict, style_heading: str
        ) -> str:
            return "\n".join(
                [
                    "=== VERB INTENT MAP ===",
                    "Before choosing a verb, identify the accomplishment intent and select from the matching preferred_verbs list below.",
                    json.dumps(verb_intent_data),
                    "",
                    "=== VERB TAXONOMY (priority tiers) ===",
                    "Use elite > strong > acceptable. NEVER use verbs in the avoid list.",
                    "Per-bullet exception: when the bullet's own tags (shown in the prompt below) "
                    "match any tag name in archetype_allows.match_tags, the verbs in "
                    "archetype_allows.allowed_from_avoid are acceptable openers for that bullet -- "
                    "for craft/creative work the honest verb IS the plain creation verb. For every "
                    "other bullet the avoid list applies in full.",
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
                ]
            )

        rewrite_rules_block = _rewrite_block(
            verb_intent_mapping, style_rules, "=== STYLE RULES ==="
        )

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
                    "signals": data.get("signals", []),
                    "preferred_verbs": data.get("preferred_verbs", {}),
                }
                for intent, data in verb_intent_mapping.get(
                    "intent_categories", {}
                ).items()
            },
            "selection_rules": verb_intent_mapping.get("selection_rules", {}),
            "verb_replacements": verb_intent_mapping.get("verb_replacements", {}),
            "final_principle": verb_intent_mapping.get("final_principle", ""),
        }
        gemma_style_rules = {
            "philosophy": [
                p
                for p in style_rules.get("philosophy", [])
                if any(
                    kw in _rule_text(p).lower()
                    for kw in (
                        "bullet",
                        "metric",
                        "verb",
                        "cares test",
                        "systems not tasks",
                    )
                )
            ],
            "writing_style": style_rules.get("writing_style", {}),
            "bullet_structure": style_rules.get("bullet_structure", {}),
            "verb_rules": [
                r
                for r in style_rules.get("verb_rules", [])
                if not _rule_text(r).startswith("Recommended verbs")
            ],
            "vague_verbs": style_rules.get("vague_verbs", []),
            "forbidden_openers": style_rules.get("forbidden_openers", []),
            "forbidden_phrases": style_rules.get("forbidden_phrases", []),
            "punctuation_rules": style_rules.get("punctuation_rules", []),
            "metrics_rules": style_rules.get("metrics_rules", {}),
            "tool_mention_rules": style_rules.get("tool_mention_rules", {}),
            "redundancy_rules": style_rules.get("redundancy_rules", {}),
        }
        rewrite_rules_block_gemma = _rewrite_block(
            gemma_verb_intent,
            gemma_style_rules,
            "=== STYLE RULES (bullet-level subset) ===",
        )

        # FIX: use .replace() instead of .format() to avoid ValueError when
        # rules YAML content contains literal curly braces { } (e.g. JSON examples).
        rewrite_system = REWRITE_SYSTEM_BASE.replace(
            "{rules_block}", rewrite_rules_block
        )
        rewrite_system_gemma = REWRITE_SYSTEM_BASE.replace(
            "{rules_block}", rewrite_rules_block_gemma
        )

        cli_art.detail(
            f"{theme.colorize_icon('hint')} Rewrite rules block:   {len(rewrite_rules_block):,} chars",
            level=cli_art.NORMAL,
        )
        cli_art.detail(
            f"{theme.colorize_icon('hint')} Gemma rules block (slim): {len(rewrite_rules_block_gemma):,} chars",
            level=cli_art.NORMAL,
        )
        cli_art.detail("", level=cli_art.NORMAL)
        cli_art.detail(
            f"{theme.colorize_icon('hint')}  Rewrite system prompt: {len(rewrite_system):,} chars (stable across ALL calls)",
            level=cli_art.NORMAL,
        )
        cli_art.detail(
            f"{theme.colorize_icon('hint')}  Gemma rewrite system prompt (slim): {len(rewrite_system_gemma):,} chars",
            level=cli_art.NORMAL,
        )
        cli_art.detail("", level=cli_art.NORMAL)
        cli_art.detail(
            f"{theme.colorize_icon('hint')} Score system prompt:   {len(critique_system):,} chars",
            level=cli_art.NORMAL,
        )

        self.warm_segment_cache(bullet_tuples)

        # Track critique data parallel to refined_bullets (same length, same
        # order, always appended -- including None entries) so no bullet can
        # be silently dropped when sorting below. A None entry sorts last via
        # _bullet_sort_key({}) (worst manager_test tier, 0 believability).
        bullet_critique_list = []  # List[Optional[dict]], parallel to refined_bullets

        start_index = len(refined_bullets)
        if start_index:
            cli_art.detail(
                f"  Resuming audit loop at bullet {start_index + 1}/{len(bullet_tuples)} (already refined: {start_index}).",
                level=cli_art.NORMAL,
            )

        def _record(refined_bullet: str, critique_data: dict | None = None) -> None:
            refined_bullets.append(refined_bullet)
            bullet_critique_list.append(critique_data)
            if on_bullet_complete:
                on_bullet_complete(list(refined_bullets))

        for i, (bullet, company, tags) in enumerate(bullet_tuples):
            if i < start_index:
                continue

            bullet_preview = bullet[:60]
            cli_art.console.rule(
                f"[{i+1}/{len(bullet_tuples)}] {bullet_preview}...",
                style="dim",
                align="left",
            )
            cli_art.detail(
                f"   Tags: {cli_art._escape_markup(tags)}  |  Company: {cli_art._escape_markup(company)}",
                level=cli_art.NORMAL,
            )

            if i > 0:
                time.sleep(CRITIQUE_SLEEP)

            critique_contents = (
                f"{static_prefix}\n\n--- BULLET TO CRITIQUE ---\n{bullet}"
            )

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

                gem_score = critique_data.get("hidden_gem_score", 0)
                gem_flag = critique_data.get("hidden_gem_flag", False)
                gem_reason = critique_data.get("hidden_gem_reason", "")
                if gem_flag:
                    cli_art.detail(
                        f"   {theme.colorize_icon('success')} GEM: Hidden Gem! score={gem_score} — {gem_reason}"
                    )
                elif gem_score >= 75:
                    cli_art.detail(
                        f"   {theme.colorize_icon('success')} STRONG: gem_score={gem_score} — {gem_reason}"
                    )

                if (
                    critique_data.get("manager_test") == "FAIL"
                    or critique_data.get("believability_score", 100) < 80
                ):
                    cli_art.detail(
                        f"   {theme.colorize_icon('hint')}  Rewriting with {REWRITE_MODEL}..."
                    )
                    time.sleep(REWRITE_SLEEP)

                    segment_bundle = self.audit_segment_bundle_for(company, tags)
                    segment_bundle_gemma = self.audit_segment_bundle_for_gemma(
                        company, tags
                    )
                    if segment_bundle:
                        cli_art.detail(
                            f"   {theme.colorize_icon('hint')} segment bundle (Tier 2): {len(segment_bundle):,} chars (Gemma: {len(segment_bundle_gemma):,} chars)"
                        )

                    active_rewrite_model = _starting_rewrite_model()
                    rewrite_parse_failures = 0
                    rewritten_bullet = bullet

                    for rw_attempt in range(MAX_REWRITE_PARSE_FAILURES + 1):
                        rewrite_text = None
                        is_gemma_attempt = "gemma" in active_rewrite_model.lower()
                        use_minimal = GEMMA_MINIMAL_JSON and is_gemma_attempt
                        runner_schema = (
                            RewriteMinimalSchema if use_minimal else RewriteSchema
                        )
                        active_rewrite_system = (
                            rewrite_system_gemma if is_gemma_attempt else rewrite_system
                        )

                        # Tier 1 + Tier 2 -> kb_context. build_rewrite_prompt() appends
                        # the Tier 3 tail (persona + weaknesses + bullet + JSON reminder),
                        # exactly like rewrite_bullets.py's process_bullet() does. Gemma
                        # gets the slim static prefix + slim segment bundle (2026-07-16
                        # fix for its 16k TPM cap); flash-lite keeps the full tier.
                        active_static_prefix = (
                            static_prefix_gemma if is_gemma_attempt else static_prefix
                        )
                        active_segment_bundle = (
                            segment_bundle_gemma if is_gemma_attempt else segment_bundle
                        )
                        context_block = (
                            f"{active_static_prefix}\n{active_segment_bundle}"
                            if active_segment_bundle
                            else active_static_prefix
                        )

                        already_written = [
                            refined_bullets[idx]
                            for idx, (_, c, _) in enumerate(
                                bullet_tuples[: len(refined_bullets)]
                            )
                            if c == company
                        ]
                        other_cv_bullets = [
                            refined_bullets[idx]
                            for idx, (_, c, _) in enumerate(
                                bullet_tuples[: len(refined_bullets)]
                            )
                            if c != company
                        ]

                        rewrite_contents = build_rewrite_prompt(
                            bullet=bullet,
                            tags=tags,
                            weaknesses=critique_data.get("weaknesses", ""),
                            kb_context=context_block,
                            minimal_schema=use_minimal,
                            vocabulary_substitutions=vocabulary_substitutions,
                            already_written_bullets=already_written,
                            other_cv_bullets=other_cv_bullets,
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
                                **(
                                    {"max_retries": GEMMA_REWRITE_MAX_RETRIES}
                                    if is_gemma_attempt
                                    else {}
                                ),
                            )

                            if not rewrite_text:
                                raise ValueError("Empty rewrite response")

                            _log_cache_stats(
                                rw_usage, len(context_block), rw_attempt + 1
                            )

                            rw_data = GeminiClient.parse_json(rewrite_text)
                            candidate_bullet = rw_data.get(
                                "rewritten_bullet", ""
                            ).strip()

                            if not candidate_bullet:
                                raise ValueError("Empty rewritten_bullet in response")

                            time.sleep(RESCORE_SLEEP)
                            rescore_contents = f"{static_prefix}\n\n--- BULLET TO CRITIQUE ---\n{candidate_bullet}"
                            rescore_text, _ = GeminiClient.generate(
                                model=CRITIQUE_MODEL,
                                system_instruction=critique_system,
                                contents=rescore_contents,
                                response_schema=CritiqueSchema,
                                temperature=0.0,
                                max_output_tokens=280,
                            )
                            rescore_data = GeminiClient.parse_json(rescore_text or "")
                            original_composite = ResumeEngine.critique_composite(
                                critique_data
                            )
                            rewrite_composite = ResumeEngine.critique_composite(
                                rescore_data
                            )

                            # Date-anchor rule, decided BEFORE the composite
                            # comparison (mirrors rewrite_bullets.best_version's
                            # margin bypass and process_bullet's rejection): a
                            # rewrite that KEEPS a school-year/calendar anchor
                            # loses outright, and a rewrite that DROPS one wins
                            # outright -- the composite can't see this failure
                            # mode, and the margin/criteria would otherwise let
                            # the anchored original survive a marginal rewrite
                            # (observed live 2026-09-17, "in the 2020-21 season").
                            original_anchors = date_anchors(bullet)
                            rewrite_anchors = date_anchors(candidate_bullet)

                            if rewrite_anchors:
                                rewritten_bullet = bullet
                                critique_to_record = critique_data
                                cli_art.detail(
                                    f"   {theme.colorize_icon('hint')} KEPT original (rewrite kept a calendar anchor: {', '.join(rewrite_anchors)})"
                                )
                            elif original_anchors:
                                rewritten_bullet = candidate_bullet
                                critique_to_record = rescore_data
                                cli_art.detail(
                                    f"   {theme.colorize_icon('success')} ACCEPTED rewrite (dropped calendar anchor {', '.join(original_anchors)})"
                                )
                            elif rewrite_composite >= original_composite:
                                rewritten_bullet = candidate_bullet
                                cli_art.detail(
                                    f"   {theme.colorize_icon('success')} ACCEPTED rewrite (composite {rewrite_composite:.0f} >= {original_composite:.0f})"
                                )
                                # Use the rescore data for the rewritten bullet
                                critique_to_record = rescore_data
                                try:
                                    if bullet_feedback.queue_accepted_rewrite(
                                        bullet,
                                        rewritten_bullet,
                                        company,
                                        tags,
                                        critique_to_record,
                                    ):
                                        cli_art.detail(
                                            f"   {theme.colorize_icon('hint')} Queued for bank review (needs-review.csv)"
                                        )
                                except Exception as feedback_err:
                                    cli_art.console.print(
                                        f"   {theme.colorize_icon('warning')}  Could not queue bullet for bank review: {feedback_err}",
                                        soft_wrap=True,
                                    )
                            else:
                                rewritten_bullet = bullet
                                cli_art.detail(
                                    f"   {theme.colorize_icon('hint')} KEPT original (composite {original_composite:.0f} > {rewrite_composite:.0f})"
                                )
                                # Use the original critique data
                                critique_to_record = critique_data
                            break

                        except Exception as rw_err:
                            rewrite_parse_failures += 1
                            cli_art.console.print(
                                f"   {theme.colorize_icon('warning')}  Rewrite parse error (attempt {rw_attempt+1}): {rw_err}",
                                soft_wrap=True,
                            )
                            # No text back means Gemma itself failed (a parse
                            # error on real text keeps its second try).
                            gemma_unavailable = is_gemma_attempt and not rewrite_text
                            if gemma_unavailable:
                                gemini_client.bench_model(active_rewrite_model)
                            if (
                                rewrite_parse_failures >= MAX_REWRITE_PARSE_FAILURES
                                or gemma_unavailable
                            ) and active_rewrite_model != REWRITE_FALLBACK_MODEL:
                                cli_art.console.print(
                                    f"   {theme.colorize_icon('warning')} FALLBACK: Switching rewrite to {REWRITE_FALLBACK_MODEL}",
                                    soft_wrap=True,
                                )
                                active_rewrite_model = REWRITE_FALLBACK_MODEL
                            time.sleep(REWRITE_SLEEP)

                    _record(rewritten_bullet, critique_to_record)
                else:
                    _record(bullet, critique_data)

            except Exception as e:
                cli_art.console.print(
                    f"   {theme.colorize_icon('warning')}  Critique error on bullet {i+1}: {e}",
                    soft_wrap=True,
                )
                _record(bullet, None)

        cli_art.print_literal(f"\n{'='*60}")
        cli_art.console.print(
            f"{theme.colorize_icon('success')} Audit complete: {len(refined_bullets)} bullets refined",
            soft_wrap=True,
        )

        # Sort bullets deterministically by manager_test and believability_score.
        # Only apply sorting to bullets processed in this run (not resumed bullets).
        # Every bullet in refined_bullets is paired with its critique (or None,
        # which sorts last) so no bullet is ever dropped by this step.
        if start_index == 0 and refined_bullets:
            refined_bullets, order = _sort_audited_bullets(
                refined_bullets, bullet_critique_list
            )
            # The caller pairs this output with bullet_tuples BY INDEX to
            # recover each bullet's company, so hand back the permutation.
            # Without it, every bullet after the first reordering was
            # attributed to the wrong employer in the builder prompt.
            if order_out is not None:
                order_out[:] = order

        return refined_bullets

    def mine_bullet_bank(
        self,
        jd_text: str,
        master_resume: dict,
        extra_company_minimums: dict | None = None,
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
        # Lazy pandas/numpy -- see _LAZY_HEAVY_DEPS at the top of this module.
        import numpy as np
        import pandas as pd

        cli_art.detail("\nMining bullet bank...", level=cli_art.NORMAL)
        bank_csv = os.path.join(self.kb_dir, "bullet-bank-keepers-audited.csv")
        emb_npy = os.path.join(self.kb_dir, "bullet_vectors_ge2_d768.npy")
        emb_meta = os.path.join(self.kb_dir, "bullet_vectors_ge2_d768.meta")

        if not os.path.exists(bank_csv):
            cli_art.console.print(
                f"  {cli_art.WARNING} bullet-bank-keepers-audited.csv not found. Skipping mine.",
                soft_wrap=True,
            )
            return []
        if not os.path.exists(emb_npy):
            cli_art.console.print(
                f"  {cli_art.WARNING} bullet_vectors_ge2_d768.npy not found. Run embed_bullet_bank.py first. Skipping mine.",
                soft_wrap=True,
            )
            return []

        try:
            df = pd.read_csv(bank_csv)
            embs = np.load(emb_npy)
        except Exception as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} Could not load bullet bank: {e}",
                soft_wrap=True,
            )
            return []

        if "Bullet Point" not in df.columns:
            cli_art.console.print(
                f"  {cli_art.WARNING} 'Bullet Point' column not found in bullet bank CSV.",
                soft_wrap=True,
            )
            return []

        if len(df) != len(embs):
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} Row count mismatch -- CSV {len(df)} rows vs embeddings {len(embs)} rows. Skipping mine.",
                soft_wrap=True,
            )
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
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} Could not read {emb_meta}: {e}. Skipping mine.",
                soft_wrap=True,
            )
            return []
        current_sha = bullets_sha(df["Bullet Point"].fillna("").tolist())
        if meta.get("bullets_sha") != current_sha:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} bullet_vectors_ge2_d768.npy is stale (bullet bank content "
                "changed since it was built) -- run embed_bullet_bank.py again. Skipping mine.",
                soft_wrap=True,
            )
            return []

        jd_emb = GeminiClient.embed(jd_text[:8000])
        # A dimension mismatch (embedding model changed since the bank was
        # embedded) would otherwise raise ValueError at the matmul below and
        # abort the build; the bullets_sha check can't see it. Same fallback.
        if jd_emb is not None and embs.ndim == 2 and len(jd_emb) != embs.shape[1]:
            cli_art.console.print(
                f"  {cli_art.WARNING} JD embedding has {len(jd_emb)} dims but the bank has "
                f"{embs.shape[1]} -- re-run embed_bullet_bank.py.",
                soft_wrap=True,
            )
            jd_emb = None
        if jd_emb is None:
            # The primary model failed (usually a 429). The backup model has
            # its own quota but its own vector space, so it is usable only
            # against its OWN index, and only when that index was built from
            # this exact bank (same content hash) -- otherwise fall through to
            # the unranked fallback below, as before.
            try:
                from embed_bullet_bank import (
                    BACKUP_EMBED_MODEL,
                    embed_batch,
                    index_paths,
                )

                b_npy, b_meta, _ = index_paths(self.kb_dir, BACKUP_EMBED_MODEL)
                if os.path.exists(b_npy) and os.path.exists(b_meta):
                    with open(b_meta, "r", encoding="utf-8") as f:
                        b_sha = json.load(f).get("bullets_sha")
                    b_embs = np.load(b_npy)
                    if b_sha == current_sha and len(b_embs) == len(df):
                        vec = embed_batch(
                            [jd_text[:8000]], model=BACKUP_EMBED_MODEL, max_retries=2
                        )[0]
                        if b_embs.ndim == 2 and len(vec) == b_embs.shape[1]:
                            jd_emb, embs = vec, b_embs
                            cli_art.console.print(
                                f"  {theme.colorize_icon('hint')} Primary embedding unavailable -- "
                                f"matched against the {BACKUP_EMBED_MODEL} backup index.",
                                soft_wrap=True,
                            )
            except Exception:
                pass
        if jd_emb is None:
            cli_art.console.print(
                f"  {cli_art.WARNING} JD embedding failed. Falling back to first TOP_K_BULLETS rows.",
                soft_wrap=True,
            )
            bullets_col = df["Bullet Point"].fillna("").tolist()
            company_col = (
                df["Role / Company"].fillna("").tolist()
                if "Role / Company" in df.columns
                else [""] * len(df)
            )
            tags_col = (
                df["Tags"].fillna("").tolist()
                if "Tags" in df.columns
                else [""] * len(df)
            )
            return list(
                zip(
                    bullets_col[:TOP_K_BULLETS],
                    company_col[:TOP_K_BULLETS],
                    tags_col[:TOP_K_BULLETS],
                )
            )

        jd_vec = np.array(jd_emb, dtype=np.float32)
        jd_norm = np.linalg.norm(jd_vec)
        if jd_norm > 0:
            jd_vec = jd_vec / jd_norm

        embs_norm = embs / (np.linalg.norm(embs, axis=1, keepdims=True) + 1e-9)
        sims = embs_norm @ jd_vec

        if "hidden_gem_score" in df.columns:
            gem_scores = (
                pd.to_numeric(df["hidden_gem_score"], errors="coerce").fillna(0).values
            )
            boosted = sims + GEM_BOOST_WEIGHT * gem_scores
        else:
            boosted = sims

        if "strength_category" in df.columns:
            tier_rank = df["strength_category"].map(STRENGTH_ORDER).fillna(99).values
        else:
            tier_rank = np.zeros(len(df))

        # Full-bank ranking, best first: lower tier_rank wins, then higher boosted score.
        ranked_idx = np.lexsort((-boosted, tier_rank))

        selected_idx: list = []
        selected_set: set = set()
        guaranteed_count = 0
        bullet_values = df["Bullet Point"].fillna("").values

        # Whole-CV uniqueness (duplicate metrics, duplicate opening verbs) is
        # enforced HERE, at selection, rather than left to the builder's
        # validator-retry loop. Those rules are global but the retry loop can
        # only fix one violation at a time, blind: a pool mined down to
        # exactly each role's minimum has zero slack, so the model's only
        # remaining move is rewording pre-audited bullets, which sets off
        # whack-a-mole and burns all 4 attempts. Filtering at selection is
        # free (deterministic, pre-audit) and the bank is big enough to have
        # the slack -- 84 Element 8 keepers to fill 3 slots.
        claimed_signatures: set = set()
        claimed_verbs: set = set()

        def _is_near_duplicate(idx: int) -> bool:
            if not selected_idx:
                return False
            return bool(
                (embs_norm[selected_idx] @ embs_norm[idx]).max()
                >= DEDUP_SIMILARITY_THRESHOLD
            )

        def _collides(idx: int) -> bool:
            sigs, verb = validate_resume.uniqueness_keys(str(bullet_values[idx]))
            return bool(sigs & claimed_signatures) or (
                verb is not None and verb in claimed_verbs
            )

        def _take(idx: int) -> None:
            sigs, verb = validate_resume.uniqueness_keys(str(bullet_values[idx]))
            selected_idx.append(idx)
            selected_set.add(idx)
            claimed_signatures.update(sigs)
            if verb is not None:
                claimed_verbs.add(verb)

        # A situational role (situational_roles.yaml) belongs on the resume
        # only when the JD cleared its keyword gate -- the caller passes those
        # candidates' bank_tags in as extra_company_minimums. Every OTHER
        # situational role is kept out of the general fill: the roster drops
        # that company later anyway, so each slot spent on it was a slot lost
        # (a 2026-09-13 build spent 3 of 21 on Men's Wearhouse this way).
        try:
            situational_tags = {
                str(cfg.get("bank_tag", "")).strip()
                for cfg in situational_roles.load_situational_roles()["roles"].values()
            } - {""}
        except Exception:
            situational_tags = set()
        excluded_companies = situational_tags - set(extra_company_minimums or {})
        # Same waste, wider net: once a profile has a roster, any bank company
        # on neither the roster nor this JD's situational candidates -- an
        # education institution, a retired job, a section label like
        # "Additional Experience" -- can never land in EXPERIENCE either.
        try:
            roster_roles = (self.load_yaml(self.kb_dir, "profile.yml") or {}).get(
                "roles"
            ) or []
        except Exception:
            roster_roles = []
        roster_names = {
            str(r.get(key) or "").strip()
            for r in roster_roles
            if isinstance(r, dict)
            for key in ("company", "name")
        } - {""}
        if roster_names and "Role / Company" in df.columns:
            allowed = roster_names | set(extra_company_minimums or {})
            excluded_companies |= {
                c
                for c in set(df["Role / Company"].fillna(""))
                if c and c not in allowed
            }
        excluded_values = (
            df["Role / Company"].fillna("").values
            if excluded_companies and "Role / Company" in df.columns
            else None
        )

        def _excluded(idx: int) -> bool:
            return (
                excluded_values is not None
                and excluded_values[idx] in excluded_companies
            )

        if "Role / Company" in df.columns:
            company_values = df["Role / Company"].values
            try:
                profile_roles = (self.load_yaml(self.kb_dir, "profile.yml") or {}).get(
                    "roles"
                ) or []
            except Exception:
                profile_roles = profile_paths.profile_yaml().get("roles") or []
            company_min_bullets = {
                r["company"]: r["min_bullets"]
                for r in profile_roles
                if "min_bullets" in r and "company" in r
            }
            if not company_min_bullets:
                company_min_bullets = {
                    r["name"]: r["min_bullets"]
                    for r in profile_roles
                    if "min_bullets" in r and "name" in r
                }
            combined_minimums = {
                **company_min_bullets,
                **(extra_company_minimums or {}),
            }

            def _scarcity(item):
                # Scarcest role first: whoever has the least room to be picky
                # claims its metrics and verbs before an abundant role does.
                # Kansas Colloquies (3 keepers, minimum 2) has to win against
                # Treering (561 keepers, minimum 6), not lose the coin toss.
                company, min_count = item
                available = int((company_values == company).sum())
                return (available - min_count, available)

            for company, min_count in sorted(combined_minimums.items(), key=_scarcity):
                company_ranked = [
                    int(i) for i in ranked_idx if company_values[i] == company
                ]
                taken = 0
                for i in company_ranked:
                    if taken >= min_count:
                        break
                    if i in selected_set or _is_near_duplicate(i) or _collides(i):
                        continue
                    _take(i)
                    guaranteed_count += 1
                    taken += 1
                # The per-role minimum is a hard floor and uniqueness is only
                # best-effort: a starved role fails validation outright
                # ("below its required minimum"), which is strictly worse than
                # a duplicate metric the retry loop still gets a shot at. So
                # top up ignoring collisions rather than come up short.
                for i in company_ranked:
                    if taken >= min_count:
                        break
                    if i in selected_set or _is_near_duplicate(i):
                        continue
                    _take(i)
                    guaranteed_count += 1
                    taken += 1

        for i in ranked_idx:
            if len(selected_idx) >= TOP_K_BULLETS:
                break
            i = int(i)
            if (
                i in selected_set
                or _excluded(i)
                or _is_near_duplicate(i)
                or _collides(i)
            ):
                continue
            _take(i)

        # Same fallback for the general fill: a short pool starves the builder
        # of material, so prefer a collision over an undersized pool.
        for i in ranked_idx:
            if len(selected_idx) >= TOP_K_BULLETS:
                break
            i = int(i)
            if i in selected_set or _excluded(i) or _is_near_duplicate(i):
                continue
            _take(i)

        top_df = df.iloc[selected_idx]
        bullets_out = top_df["Bullet Point"].fillna("").tolist()
        company_out = (
            top_df["Role / Company"].fillna("").tolist()
            if "Role / Company" in top_df.columns
            else [""] * len(top_df)
        )
        tags_out = (
            top_df["Tags"].fillna("").tolist()
            if "Tags" in top_df.columns
            else [""] * len(top_df)
        )

        cli_art.detail(
            f"  Mined {len(bullets_out)} bullets from bank ({guaranteed_count} from guaranteed per-company minimums, top_k={TOP_K_BULLETS}).",
            level=cli_art.NORMAL,
        )
        return list(zip(bullets_out, company_out, tags_out))

    def _role_dna_dir(self) -> str:
        """Where role_dna.yaml comes from: the profile's own knowledge base
        when it has one, else the shared resume-engine/scoring library.

        The shared library is a marketing one (email_lifecycle,
        sales_enablement, marketing_ops_crm, generalist_coordinator), and
        until 2026-09-13 it was the only one: a data-science profile's
        evaluations were told to "choose the archetype from these keys", and
        339 of 344 came back generalist_coordinator or marketing_ops_crm. The
        resume critique's ROLE DNA rubric read the same file."""
        own = os.path.join(self.kb_dir, "role_dna.yaml")
        return self.kb_dir if os.path.exists(own) else self.scoring_dir

    def build_fit_evaluation_context(
        self, jd_text: str, jd_skill_names: list | None = None, commute_block: str = ""
    ) -> str:
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

        Three blocks, all cheap:
          - profile.yml, trimmed to the identity sections, so "does this
            candidate fit" has a candidate.
          - verified_tools.json + profile.yml's skills dict, so
            tools_process_overlap/capability_gaps are grounded in the
            candidate's actual confirmed tool list, not just narrative
            prose (see build_verified_skills_context()).
          - role_dna.yaml, so the returned `archetype` is drawn from the
            project's own controlled vocabulary rather than freeformed. It is
            the archetype library and, per the review, is loaded by nothing
            else today.

        All are optional: a freshly-bootstrapped profile with none still
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
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} evaluate_fit: could not load profile.yml: {e}",
                    soft_wrap=True,
                )

        skills_block = build_verified_skills_context(jd_text, jd_skill_names)
        if skills_block:
            sections.append(skills_block)

        try:
            role_dna = self.load_yaml(self._role_dna_dir(), "role_dna.yaml")
            if role_dna:
                sections.append(
                    "=== ROLE ARCHETYPE LIBRARY (from role_dna.yaml) ===\n"
                    "Choose the returned `archetype` from these keys. Do not invent one.\n"
                    + json.dumps(role_dna)
                )
        except Exception as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} evaluate_fit: could not load role_dna.yaml: {e}",
                soft_wrap=True,
            )

        if not sections:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} evaluate_fit: no candidate profile "
                "or archetype library found -- scoring the JD in isolation.",
                soft_wrap=True,
            )

        track_block = build_situational_track_context(jd_text)
        if track_block:
            sections.append(track_block)

        if commute_block:
            sections.append(commute_block)

        pay_block = build_compensation_context(jd_text)
        if pay_block:
            sections.append(pay_block)

        sections.append(
            f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ==="
        )
        return "\n\n".join(sections)

    def evaluate_fit(self, jd_path: str) -> dict:
        """
        Ultra-Premium grounded two-stage fit evaluation check for a JD.
        Loads profile.yml dynamically to apply custom deal-breaker skips and
        empirical score calibration (piecewise linear interpolation) in Python.
        """
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} JD file not found: {jd_path}",
                soft_wrap=True,
            )
            return {}

        try:
            profile = self.load_yaml(self.kb_dir, "profile.yml") or {}
        except Exception:
            profile = profile_paths.profile_yaml() or {}

        remote_required = profile.get("location", {}).get("remote_required", False)

        # Pre-warm the Skills Gap Matrix's extraction cache -- see
        # warm_jd_keyword_cache()'s own docstring for why this is paired
        # here rather than left for the Matrix to pay for on first view.
        warm_jd_keyword_cache(jd_path)

        # The posting's own extracted skills (cached by the warm-up above):
        # the skills block's semantic matching and the step-9 matrix both
        # use them, so they are gathered once.
        try:
            jd_skill_names = gather_jd_skill_names(jd_path)
        except Exception:
            jd_skill_names = []

        # 0. Resolve workplace mode and commute distance BEFORE the model
        # calls, so the evaluator is told how far the office is. It used to
        # run afterwards: the model read the candidate's commute deal-breaker
        # with no distance and called a 3-mile office "incompatible", and
        # rescoring corrected remote_quality but not the other subscores.
        jd_data = _parse_jd_data(jd_text)
        workplace = location_filter.classify_workplace(
            jd_data.get("location", ""),
            jd_data.get("is_remote"),
            jd_data.get("work_model", ""),
        )
        loc_dist = None
        try:
            import location_settings

            loc_settings = location_settings.read_settings()
        except Exception:
            loc_settings = {}

        radius_miles = loc_settings.get("radius_miles")
        workplace_mode = loc_settings.get("workplace_mode", "any")

        enrichment = jd_data.get("_location_enrichment")
        if (
            isinstance(enrichment, dict)
            and enrichment.get("distance_miles") is not None
        ):
            loc_dist = enrichment.get("distance_miles")
        elif radius_miles and (jd_data.get("location") or jd_text):
            try:
                import location_enricher

                job_data = {
                    "id": os.path.basename(jd_path),
                    "title": jd_data.get("job_title", ""),
                    "company": jd_data.get("company_name", ""),
                    "location": jd_data.get("location", ""),
                    "raw_text": jd_text,
                    "company_website": jd_data.get("company_website", ""),
                    "is_remote": jd_data.get("is_remote"),
                    "work_model": jd_data.get("work_model"),
                }
                cache = location_enricher.load_locations_cache()
                enr = location_enricher.enrich_job_location(
                    job_data,
                    settings=loc_settings,
                    allow_search_backup=False,
                    cache=cache,
                )
                if enr.get("distance_miles") is not None:
                    loc_dist = enr.get("distance_miles")
            except Exception:
                pass
        if loc_dist is None and radius_miles:
            loc_dist = city_level_distance(jd_data.get("location"), loc_settings)

        # 1. Prepare evaluation context
        fit_context = self.build_fit_evaluation_context(
            jd_text,
            jd_skill_names,
            commute_block=build_commute_context(
                loc_dist, radius_miles, workplace, jd_data.get("location")
            ),
        )

        # 2. Stage 1 LLM Call: Capability Fit
        capability_prompt = self.load_prompt("evaluate_capability.md")
        cap_text, _ = GeminiClient.generate(
            model=EVAL_MODEL,
            system_instruction=capability_prompt,
            contents=fit_context,
            response_schema=CapabilityEvaluationSchema,
            temperature=0.0,
            fallbacks=SCORING_FALLBACKS,
        )
        capability_data = GeminiClient.parse_json(cap_text or "") or {}

        # 3. Stage 2 LLM Call: Recruiter & Legitimacy Fit
        recruiter_prompt = self.load_prompt("evaluate_recruiter.md")
        rec_text, _ = GeminiClient.generate(
            model=EVAL_MODEL,
            system_instruction=recruiter_prompt,
            contents=fit_context,
            response_schema=RecruiterEvaluationSchema,
            temperature=0.0,
            fallbacks=SCORING_FALLBACKS,
        )
        recruiter_data = GeminiClient.parse_json(rec_text or "") or {}

        # 4. Synthesize Split Results into the unified FitEvaluationSchema format
        evaluation = {
            "archetype": capability_data.get("archetype", "Unknown"),
            "hard_blockers": recruiter_data.get("hard_blockers", []),
            "fit_subscores": capability_data.get("fit_subscores", {}),
            "interview_odds_subscores": recruiter_data.get(
                "interview_odds_subscores", {}
            ),
            "practical_pursue_subscores": recruiter_data.get(
                "practical_pursue_subscores", {}
            ),
            "recommendation": recruiter_data.get("recommendation", "Selective pursue"),
            "why": recruiter_data.get("why", ""),
            "recruiter_read": recruiter_data.get("recruiter_read", ""),
            "posting_legitimacy": recruiter_data.get(
                "posting_legitimacy", "Proceed with Caution"
            ),
            "posting_legitimacy_notes": recruiter_data.get(
                "posting_legitimacy_notes", ""
            ),
            # Advanced Metadata injection
            "capability_gaps": capability_data.get("capability_gaps", []),
            "role_track": capability_data.get("role_track", "unknown"),
            "role_track_confidence": capability_data.get(
                "role_track_confidence", "low"
            ),
            "role_track_evidence": capability_data.get("role_track_evidence", ""),
            "stretch_evidence": capability_data.get("stretch_evidence", ""),
            "ghost_job_red_flags": recruiter_data.get("ghost_job_red_flags", []),
            "prestige_tier": recruiter_data.get("prestige_tier", "Tier-2"),
        }

        # 5. Prestige-Tier Funnel Friction Calibration
        prestige_tier = evaluation["prestige_tier"]
        funnel_friction_score = evaluation["interview_odds_subscores"].get(
            "funnel_friction", 3
        )
        if prestige_tier == "Tier-1":
            funnel_friction_score = min(funnel_friction_score, 2)
        elif prestige_tier == "Tier-3":
            funnel_friction_score = min(funnel_friction_score + 1, 5)

        # Read once, used by both the 5b nudge below and the composite-
        # score rescoring at the end of this function -- same
        # try/except-with-fallback pattern the location_settings read
        # just below already uses, so a missing/broken scan_filters.yml
        # degrades to today's hardcoded defaults rather than raising.
        try:
            import content_settings

            scoring_weights = content_settings.read_scoring_weights()
            role_track_settings = content_settings.read_role_track_settings()
            work_constraints_settings = content_settings.read_work_constraints()
        except Exception:
            scoring_weights = {}
            role_track_settings = {}
            work_constraints_settings = {}

        # 5b. Remote-vs-Local Candidate Pool Calibration. A remote posting
        # competes against a national/global applicant pool; an onsite
        # posting is filtered down to whoever can commute to it. Same
        # magnitude and pattern as the prestige-tier nudge above, and
        # applied after it so both adjustments compound rather than race.
        # Nudge magnitude is Settings-configurable (funnel_friction_nudge,
        # default 1) via scripts/content_settings.py.
        funnel_friction_nudge = scoring_weights.get("funnel_friction_nudge", 1)
        if workplace == location_filter.REMOTE:
            funnel_friction_score = max(
                funnel_friction_score - funnel_friction_nudge, 1
            )
        elif workplace == location_filter.ONSITE:
            funnel_friction_score = min(
                funnel_friction_score + funnel_friction_nudge, 5
            )
        evaluation["interview_odds_subscores"][
            "funnel_friction"
        ] = funnel_friction_score

        # 6. (Commute distance was resolved in step 0, before the model calls.)
        posting_age_days = jd_manager.compute_posting_age_days(jd_path)
        evaluation["posting_age_days"] = posting_age_days

        # 7. Apply Location-Aware Rescoring & Profile Deal-Breaker Overrides
        evaluation = rescore_evaluation_with_location(
            evaluation=evaluation,
            distance_miles=loc_dist,
            radius_miles=radius_miles,
            workplace_mode=workplace_mode,
            remote_required=remote_required,
            posting_age_days=posting_age_days,
            description=jd_data.get("description") or jd_text,
            scoring_weights=scoring_weights,
            role_track_settings=role_track_settings,
            work_constraints_settings=work_constraints_settings,
            posting_workplace=workplace,
            job_title=jd_data.get("job_title"),
        )

        # 8. Heuristic Ghost Job Probability Calculator
        red_flags_count = len(evaluation.get("ghost_job_red_flags", []))
        ghost_score = 0.0
        if posting_age_days is not None:
            if posting_age_days > 30:
                ghost_score += 0.40
            elif posting_age_days > 14:
                ghost_score += 0.20
        ghost_score += min(red_flags_count * 0.20, 0.50)
        evaluation["ghost_job_probability"] = round(min(ghost_score * 100.0, 95.0), 1)

        # 9. Skills Gap Matrix -- computed automatically now that
        # warm_jd_keyword_cache() above guarantees the JD's tools/skills
        # are already extracted, so this and the Jobs dashboard's "m"
        # action (dashboard_actions._matrix) never race to be first to
        # pay for extraction. Never blocks or fails evaluation: a missing
        # bullet-bank embeddings file or an embedding API hiccup just
        # means no matrix this round, same as before this existed.
        try:
            skill_names = jd_skill_names or gather_jd_skill_names(jd_path)
            skill_matrix = compute_skill_coverage_matrix(skill_names)
            if skill_matrix:
                evaluation["skill_matrix"] = skill_matrix
        except Exception as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} evaluate_fit: could not compute skill matrix: {e}",
                soft_wrap=True,
            )

        return evaluation

    def _extract_company_research(
        self, source_text: str, source_label: str
    ) -> dict | None:
        """
        The single structured-extraction call behind all three of
        research_company()'s tiers -- each tier's job is only to produce
        source text, so there's exactly one place that produces a
        CompanyResearchSchema-shaped dict.

        source_label is internal bookkeeping (which tier won) and is
        returned under the underscore-prefixed _research_source key so it
        can never be mistaken for prompt content; format_company_research_block
        ignores it. Returns None if the model response can't be parsed.
        """
        research_prompt = self.load_prompt("research_company.md")
        research_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=research_prompt,
            contents=f"=== COMPANY SOURCE TEXT ===\n{source_text}\n=== END COMPANY SOURCE TEXT ===",
            response_schema=CompanyResearchSchema,
            temperature=0.0,
        )
        research_data = GeminiClient.parse_json(research_text or "")
        if not research_data:
            cli_art.console.print(
                f"  {theme.colorize_icon('hint')} Company research skipped: model response couldn't be parsed.",
                soft_wrap=True,
            )
            return None

        research_data["_research_source"] = source_label
        return research_data

    def research_company(self, jd_data: dict, jd_text: str = "") -> dict | None:
        """
        Extracts a company's tone signals, traceable facts, and preferred
        vocabulary, trying three sources in descending order of quality:

          1. The company's own About/Mission/Careers pages, if a
             company_website is known in jd_data or findable via a Google
             Search grounding lookup keyed on company_name.
          2. A grounded search writeup of the company, used only when the
             model self-reports "high" confidence that it found the right
             company (many companies share a name -- see
             company_research.research_company_via_search).
          3. The JD's own text, which always exists.

        Tier 3 means this effectively never returns None any more, which is
        the point: every role should have something real to tailor against.
        The remaining None paths are an empty jd_text (operationally a
        non-occurrence) and an unparseable model response. Callers must
        still treat None as "proceed exactly as if this feature didn't
        exist." See
        docs/superpowers/specs/2026-08-11-company-research-tiered-fallback-design.md.
        """
        # --- Cache: research describes the company, not the role ---
        cached = company_research.load_cached_research(
            jd_data.get("company_name"), jd_data.get("company_website") or ""
        )
        if cached:
            cli_art.console.print(
                f"  {theme.colorize_icon('success')} Reused saved research for "
                f"{jd_data.get('company_name')} (from the last "
                f"{company_research.CACHE_TTL_DAYS} days).",
                soft_wrap=True,
            )
            return cached

        # --- Tier 1: the company's own site ---
        company_website = jd_data.get("company_website")
        # A JD's own company_website field is sometimes a LinkedIn/ATS page
        # rather than the company's site -- the same rejection
        # find_company_website() applies to search hits.
        if company_website and not company_research.is_usable_company_site(
            company_website
        ):
            company_website = None
        if not company_website:
            company_website = company_research.find_company_website(
                jd_data.get("company_name")
            )
            if company_website:
                cli_art.console.print(
                    f"  {theme.colorize_icon('hint')} No company website on file -- found one via search: {company_website}",
                    soft_wrap=True,
                )

        if company_website:
            scraped_text = company_research.fetch_company_pages(company_website)
            if len(scraped_text) >= company_research.MIN_USEFUL_CHARS:
                research_data = self._extract_company_research(scraped_text, "website")
                if research_data:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('success')} Company research complete for {company_website}.",
                        soft_wrap=True,
                    )
                    company_research.save_cached_research(
                        jd_data.get("company_name"), research_data, company_website
                    )
                    return research_data
                # An extraction failure used to `return None` right here,
                # skipping the search and JD-text tiers that exist so every
                # role gets something. Fall through to them instead.
                cli_art.console.print(
                    f"  {theme.colorize_icon('hint')} Couldn't extract research from {company_website} -- trying a web search instead.",
                    soft_wrap=True,
                )
            else:
                cli_art.console.print(
                    f"  {theme.colorize_icon('hint')} Couldn't find enough usable content on {company_website} -- trying a web search instead.",
                    soft_wrap=True,
                )
        else:
            cli_art.console.print(
                f"  {theme.colorize_icon('hint')} No company website known for this JD -- trying a web search instead.",
                soft_wrap=True,
            )

        # --- Tier 2: grounded search, trusted only at high confidence ---
        company_name = jd_data.get("company_name")
        context_hint = ", ".join(
            str(v) for v in (jd_data.get("job_title"), jd_data.get("industry")) if v
        )
        search_text = company_research.research_company_via_search(
            company_name, context_hint
        )
        if search_text:
            research_data = self._extract_company_research(search_text, "search")
            if research_data:
                cli_art.console.print(
                    f"  {theme.colorize_icon('success')} Company research complete for {company_name} (from a web search).",
                    soft_wrap=True,
                )
                company_research.save_cached_research(company_name, research_data)
                return research_data
            # Same as Tier 1: an extraction failure falls through to the
            # JD's own text rather than ending research with nothing.

        # --- Tier 3: the JD's own text ---
        if not jd_text.strip():
            cli_art.console.print(
                f"  {theme.colorize_icon('hint')} Company research skipped: nothing usable found for this JD.",
                soft_wrap=True,
            )
            return None

        research_data = self._extract_company_research(jd_text, "jd_text")
        if research_data:
            cli_art.console.print(
                f"  {theme.colorize_icon('success')} Company research complete for {company_name} (from the job posting's own text).",
                soft_wrap=True,
            )
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

    def draft_followup_message(
        self, jd_path: str, follow_up_count: int, contact: dict | None = None
    ) -> str | None:
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
        # Lazy pandas/numpy -- see _LAZY_HEAVY_DEPS at the top of this module.
        import numpy as np
        import pandas as pd

        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} JD file not found: {jd_path}",
                soft_wrap=True,
            )
            return {}

        jd_data = _parse_jd_data(jd_text)
        job_key = jd_manager.compute_job_key(jd_path)
        checkpoint = jd_manager.load_checkpoint(job_key)
        jd_keywords = checkpoint.get("jd_keywords") if checkpoint else None
        # The role being applied for: named (and bolded at render) in the
        # first paragraph -- a 2026-09-14 letter never said which job it was for.
        role_title = _coverletter_role_title(jd_data, _build_output_stem(jd_path))

        # Feature #12 needs keywords even for a standalone cover-letter-only
        # run (no prior resume build, so no checkpoint to reuse). Extracted
        # in-memory only -- deliberately not written to a checkpoint, since
        # this function is checkpoint-free by design (see docstring above).
        if not jd_keywords:
            keyword_prompt = self.load_prompt("extract_keywords.md")
            keyword_text, _ = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=keyword_prompt,
                contents=f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===",
                response_schema=JDKeywordSchema,
                temperature=0.0,
            )
            jd_keywords = GeminiClient.parse_json(keyword_text or "") or None

        # Saved research first, same as build_tailored_resume: in a package
        # build the resume step has just saved it, and re-running
        # research_company() here paid for the same scrape + search twice.
        research = jd_manager.read_research(jd_path)
        if not research:
            research = self.research_company(jd_data, jd_text)
            if research:
                jd_manager.save_research(jd_path, research)
        research_block = format_company_research_block(research) if research else ""

        # Feature #5: a referral is per-application (this specific job came
        # via a specific contact), saved via jd_manager.save_referral() --
        # by the --referral CLI flag or the interactive menu prompt -- and
        # read back here rather than living in profile.yml. Absent for most
        # JDs, so the block is empty and the prompt's existing Hook-First
        # Opening behavior is unchanged.
        referral = jd_manager.read_referral(jd_path)
        referral_block = (
            f"\n\n=== REFERRAL ===\nThe candidate has a referral for this specific "
            f"role: {referral['text']}\nName this referral by name in the first "
            f"1-2 sentences of the opening paragraph (15x hire-rate boost) -- "
            f"weave it into the Hook-First Opening rather than treating it as a "
            f"separate sentence.\n"
            if referral and referral.get("text")
            else ""
        )

        # Feature #1: classify which ATS this posting runs on, cached per-JD
        # (see jd_manager.save/read_ats_classification()) so a rebuild
        # doesn't reclassify. Feature #12's keyword block uses the result's
        # weight_tier to decide how hard to push front-loading.
        ats_classification = jd_manager.read_ats_classification(jd_path)
        if ats_classification is None:
            source_url = jd_manager.extract_source_url(jd_path)
            ats_classification = scan_ats.classify_ats(source_url)
            if ats_classification:
                jd_manager.save_ats_classification(jd_path, ats_classification)

        keyword_block = _build_keyword_block(jd_keywords, ats_classification)

        try:
            recommendations_block = build_recommendations_block(
                (profile_paths.profile_yaml() or {}).get("key_recommendations")
            )
        except Exception:
            recommendations_block = ""

        coverletter_prompt = self.load_prompt("tailor_coverletter.md")
        background_context = self.build_audit_static_prefix(include_evidence_guide=True)
        role_block = f"\n\n=== ROLE TITLE ===\n{role_title}\n" if role_title else ""
        system_instruction = f"{coverletter_prompt}\n\n{background_context}{research_block}{referral_block}{keyword_block}{recommendations_block}{role_block}"

        letter_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=system_instruction,
            contents=f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===",
            response_schema=CoverLetterSchema,
            temperature=0.0,
        )
        letter_data = GeminiClient.parse_json(letter_text or "")
        if not letter_data:
            cli_art.console.print(
                f"  {cli_art.ERROR} Cover letter generation returned no parseable result.",
                soft_wrap=True,
            )
            return {}

        style_rules = self.load_yaml(self.rules_dir, "style_rules.yaml")
        # Load keeper bullets and embeddings for advanced semantic grounding check
        keeper_bullets = []
        keeper_embs = None
        keeper_embs_backup = None
        bank_csv = os.path.join(self.kb_dir, "bullet-bank-keepers-audited.csv")
        emb_npy = os.path.join(self.kb_dir, "bullet_vectors_ge2_d768.npy")
        if os.path.exists(bank_csv) and os.path.exists(emb_npy):
            try:
                import numpy as np
                import pandas as pd

                df = pd.read_csv(bank_csv)
                keeper_bullets = df["Bullet Point"].fillna("").tolist()
                keeper_embs = np.load(emb_npy)
                import embed_bullet_bank

                # Used only when the primary model can't embed a sentence;
                # None unless it matches this exact bank.
                keeper_embs_backup = embed_bullet_bank.backup_index_for(
                    self.kb_dir, bullets_sha(keeper_bullets), len(keeper_bullets)
                )
            except Exception:
                pass

        # kb_corpus=background_context: the same grounding corpus the model
        # was given in system_instruction, re-used here so validate() can
        # check that specific factual claims (metrics, years-of-experience,
        # date ranges) in the letter actually trace back to it -- see B14.
        violations = validate_coverletter.validate(
            letter_data,
            style_rules,
            kb_corpus=background_context,
            keeper_bullets=keeper_bullets,
            keeper_embs=keeper_embs,
            keeper_embs_backup=keeper_embs_backup,
            voice_rules=self.voice_rules,
            role_title=role_title,
        )

        max_coverletter_attempts = 3
        attempt = 1
        while violations and attempt <= max_coverletter_attempts:
            cli_art.detail(
                f"  Validator found {len(violations)} issue(s), attempt {attempt}/{max_coverletter_attempts}:",
                level=cli_art.NORMAL,
            )
            for v in violations:
                cli_art.detail(
                    f"    - {cli_art._escape_markup(_condensed_violation(str(v)))}",
                    level=cli_art.NORMAL,
                )
            fix_contents = f"=== ORIGINAL COVER LETTER JSON ===\n{json.dumps(letter_data, indent=2)}\n\n" f"=== ISSUES TO FIX (change nothing else) ===\n" + "\n".join(
                f"- {v}" for v in violations
            ) + _word_count_fix_guidance(
                violations
            )
            fix_temperature = round(0.2 * (attempt - 1), 2)
            fix_text, _ = GeminiClient.generate(
                model=BUILDER_MODEL,
                system_instruction=system_instruction,
                contents=fix_contents,
                response_schema=CoverLetterSchema,
                temperature=fix_temperature,
            )
            fixed_data = GeminiClient.parse_json(fix_text or "")
            if fixed_data:
                letter_data = fixed_data
                violations = validate_coverletter.validate(
                    letter_data,
                    style_rules,
                    kb_corpus=background_context,
                    keeper_bullets=keeper_bullets,
                    keeper_embs=keeper_embs,
                    keeper_embs_backup=keeper_embs_backup,
                    voice_rules=self.voice_rules,
                    role_title=role_title,
                )
            attempt += 1

        if violations:
            cli_art.detail(
                f"  {theme.colorize_icon('warning')} {len(violations)} issue(s) remain after retries, proceeding anyway:",
                level=cli_art.NORMAL,
            )
            for v in violations:
                cli_art.detail(
                    f"    - {cli_art._escape_markup(str(v))}", level=cli_art.NORMAL
                )

        _resolve_contact_fallback(letter_data, jd_data)
        letter_data["company_location"] = _resolve_company_location(research, jd_data)

        stem = _build_output_stem(jd_path)
        letter_data["tagline"] = _read_matching_resume_tagline(stem)
        letter_data["role_title"] = role_title
        json_out = os.path.join(self.output_json_dir, f"{stem}_CoverLetter.json")
        html_out = os.path.join(self.output_html_dir, f"{stem}_CoverLetter.html")
        pdf_out = os.path.join(self.output_pdf_dir, f"{stem}_CoverLetter.pdf")

        os.makedirs(os.path.dirname(json_out), exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(letter_data, f, indent=2, ensure_ascii=False)
        cli_art.detail(
            f"  Cover letter saved to: {cli_art._escape_markup(json_out)}",
            level=cli_art.NORMAL,
        )

        render_coverletter(letter_data, html_out)

        pdf_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")
        try:
            pdf_result = subprocess.run(
                ["node", pdf_script, html_out, pdf_out, "--format=letter"],
                capture_output=True,
                text=True,
                timeout=PDF_GENERATION_TIMEOUT_SECONDS,
                env={**os.environ, "RESUME_BUILDER_ICONS": theme.icon_set_name()},
            )
        except subprocess.TimeoutExpired:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')}  PDF generation timed out after "
                f"{PDF_GENERATION_TIMEOUT_SECONDS}s.",
                soft_wrap=True,
            )
            return {}
        if pdf_result.returncode != 0:
            cli_art.friendly_subprocess_error(
                pdf_result.stderr, "creating the PDF for this cover letter"
            )
            return {}
        cli_art.print_subprocess_output(pdf_result.stdout)

        docx_out = os.path.join(self.output_docx_dir, f"{stem}_CoverLetter.docx")
        try:
            render_coverletter_docx(letter_data, docx_out)
        except Exception as e:
            cli_art.friendly_error(e, "creating the DOCX for this cover letter")
            return {}

        cl_text_warnings = validate_pdf_text.validate_coverletter_pdf_text(
            pdf_out, letter_data, jd_keywords=jd_keywords
        )
        if cl_text_warnings:
            cli_art.detail(
                f"  {theme.colorize_icon('warning')} Cover-letter PDF text-layer check found {len(cl_text_warnings)} potential issue(s) (what an ATS would actually parse from the file, not just the pre-render JSON):",
                level=cli_art.NORMAL,
            )
            for w in cl_text_warnings:
                cli_art.detail(
                    f"    - {cli_art._escape_markup(str(w))}", level=cli_art.NORMAL
                )

        letter_data["_output_paths"] = {
            "json": json_out,
            "html": html_out,
            "pdf": pdf_out,
            "docx": docx_out,
        }
        cli_art.detail(
            f"  {theme.colorize_icon('success')} Cover letter complete! PDF → {cli_art._escape_markup(pdf_out)}",
            level=cli_art.NORMAL,
        )
        os.environ["RESUME_BUILDER_LAST_PDF"] = pdf_out
        return letter_data

    def build_tailored_resume(
        self,
        jd_path: str,
        master_resume: dict,
        output_filename: str | None = None,
        job_key: str | None = None,
        interactive: bool = False,
        *,
        skip_company_research: bool = False,
    ) -> dict | None:
        """
        Full pipeline: JD -> keywords -> mine bullets -> audit -> build -> critique.

        interactive=True (single-file `resume run <path>` only -- never batch mode,
        `resume sample`, or tests) gates Step 5.5's critique-driven recommendations
        behind an explicit per-recommendation y/n before any of them are applied,
        so gap-filling content never lands in the resume without approval. Approval
        choices are checkpointed so a resumed run doesn't re-prompt.

        skip_company_research=True is for a build with no employer on the other
        end of it -- currently only the recruiter resume (build_recruiter_resume.py),
        whose "JD" is synthesized from the candidate's own profile. It must be
        explicit rather than left to degrade on its own: research_company()'s
        Tier 3 falls back to the JD's own text, so a candidate-derived brief
        would come back as confident "company research" about the candidate,
        and the Why section would then be addressed to a company that does not
        exist. With research empty, research_block is "" and SECTION_WHY /
        WHY_TEXT are optional in TemplateSchema, so the Why section is simply
        omitted and validate_resume's Why checks stay dormant.

        Gap 1 fix: kb_context is placed in builder_system (system_instruction)
        rather than combined_contents. The full ~457k-token KB now forms a
        stable, cacheable system prefix. Only variable content (JD keywords,
        JD text, master resume JSON, refined bullets) sits in combined_contents,
        so Google can cache-hit the KB prefix on every builder call regardless
        of JD changes.
        """
        logger = logging.getLogger("resume_pipeline")
        cli_art.print_literal(
            f"\nBuilding tailored resume for: {cli_art._escape_markup(jd_path)}"
        )
        logger.info(f"build_tailored_resume starting: {jd_path}")

        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} JD file not found: {jd_path}",
                soft_wrap=True,
            )
            return {}

        situational_candidates = situational_roles.detect_situational_candidates(
            _situational_gate_text(jd_text)
        )
        if situational_candidates:
            cli_art.print_literal(
                f"  Situational role candidate(s) cleared the keyword gate: {cli_art._escape_markup(', '.join(situational_candidates))}"
            )

        if job_key is None:
            job_key = jd_manager.compute_job_key(jd_path)
        checkpoint = jd_manager.load_checkpoint(job_key)

        if output_filename is None:
            output_filename = f"{_build_output_stem(jd_path)}_Resume.json"

        # --- Step 1: Extract JD keywords ---
        cli_art.console.rule(
            "Step 1: Extracting JD keywords...", style="dim", align="left"
        )
        jd_keywords = checkpoint.get("jd_keywords")
        if jd_keywords is not None:
            cli_art.print_literal("  Resuming: using JD keywords from checkpoint.")
        else:
            extract_prompt = self.load_prompt("extract_keywords.md")
            with cli_art.thinking_status("Extracting keywords with Gemini..."):
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
                cli_art.console.print(
                    f"  {theme.colorize_icon('error')} JD keyword extraction returned nothing.",
                    soft_wrap=True,
                )
                cli_art.print_literal(
                    "    This usually means the file isn't a job description "
                    "(wrong path, an empty export, or a login/error page saved as text)."
                )
                if not (interactive and _confirm_continue_without_keywords()):
                    cli_art.print_literal(
                        "    Stopping before the bullet audit. Nothing was spent on this file beyond Step 1."
                    )
                    return None
                cli_art.print_literal(
                    "    Continuing at your request, with empty keywords."
                )
            checkpoint["jd_keywords"] = jd_keywords
            jd_manager.save_checkpoint(job_key, checkpoint)
        jd_keywords = _drop_target_role_titles(
            jd_keywords, profile_paths.profile_yaml() or {}
        )
        cli_art.print_literal(
            f"  Keywords extracted: {_summarize_keywords(jd_keywords)}"
        )
        cli_art.print_literal()

        if interactive and jd_keywords:
            confirm_jd_skill_gaps_interactively(jd_keywords, checkpoint, job_key)

        # --- Step 2: Mine bullet bank ---
        cli_art.console.rule("Step 2: Mining bullet bank...", style="dim", align="left")
        bullet_tuples = checkpoint.get("bullet_tuples")
        if bullet_tuples is not None:
            cli_art.print_literal(
                f"  Resuming: using {len(bullet_tuples)} bullet tuples from checkpoint."
            )
        else:
            bullet_tuples = self.mine_bullet_bank(
                jd_text,
                master_resume,
                extra_company_minimums=situational_roles.bank_minimums_for(
                    situational_candidates
                ),
            )
            checkpoint["bullet_tuples"] = bullet_tuples
            jd_manager.save_checkpoint(job_key, checkpoint)
        cli_art.print_literal(f"  {len(bullet_tuples)} bullet tuples retrieved.")
        # --- Step 2b: Load company research and vocabulary substitutions early ---
        research = None if skip_company_research else jd_manager.read_research(jd_path)
        if skip_company_research:
            cli_art.print_literal(
                "  No employer on this build -- skipping company research and the Why section."
            )
        elif research:
            cli_art.console.print(
                f"  {theme.colorize_icon('success')} Loaded saved company research from JD.",
                soft_wrap=True,
            )
        else:
            jd_data = _parse_jd_data(jd_text)
            research = self.research_company(jd_data, jd_text)
            if research:
                jd_manager.save_research(jd_path, research)

        vocabulary_substitutions = (research or {}).get("vocabulary_substitutions", [])
        checkpoint["vocabulary_substitutions"] = vocabulary_substitutions
        jd_manager.save_checkpoint(job_key, checkpoint)
        # Built here, not in Step 4's fresh-build branch: Step 7's Why
        # backfill reads it too, and a checkpoint-resumed run skips that
        # branch -- a NameError on exactly the runs closest to finishing.
        research_block = format_company_research_block(research) if research else ""

        # --- Step 3: Audit and refine bullets ---
        cli_art.console.rule("Step 3: Auditing bullets...", style="dim", align="left")
        static_prefix = self.build_audit_static_prefix()

        def _save_bullets_checkpoint(partial_bullets):
            checkpoint["refined_bullets"] = partial_bullets
            jd_manager.save_checkpoint(job_key, checkpoint)

        audit_order: list[int] = []
        refined_tuples = self.audit_and_refine_bullets(
            bullet_tuples,
            static_prefix,
            resume_from=checkpoint.get("refined_bullets", []),
            on_bullet_complete=_save_bullets_checkpoint,
            vocabulary_substitutions=vocabulary_substitutions,
            order_out=audit_order,
        )
        if audit_order:
            # The audit sorted its output; keep bullet_tuples index-aligned
            # with it, and persist both so a resumed run stays aligned too.
            bullet_tuples = [bullet_tuples[i] for i in audit_order]
            checkpoint["bullet_tuples"] = bullet_tuples
        refined_bullets = [b for b in refined_tuples if b]  # plain strings for builder
        checkpoint["refined_bullets"] = refined_tuples
        jd_manager.save_checkpoint(job_key, checkpoint)
        cli_art.print_literal(f"  {len(refined_bullets)} bullets after audit.")
        cli_art.print_literal()

        # audit_and_refine_bullets emits exactly one output bullet per input
        # tuple, in order, so re-pairing by index recovers each bullet's
        # source company without changing that function's return contract or
        # the checkpoint format. Without this, the builder saw a flat list of
        # bullet text with no company attribution at all and had to guess
        # which company each bullet belonged to -- a likely contributor to it
        # giving up and emitting empty Experience entries.
        # Paired with zip BEFORE dropping empties -- slicing bullet_tuples to
        # len(refined_bullets) after the filter shifted every company after
        # the first empty entry onto the wrong bullet.
        paired = [
            (b, company)
            for b, (_, company, _) in zip(refined_tuples, bullet_tuples)
            if b
        ]
        refined_bullets = [b for b, _ in paired]
        bullet_companies = [company for _, company in paired]

        # --- Step 4: Build resume ---
        cli_art.console.rule("Step 4: Building resume...", style="dim", align="left")
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
        try:
            descriptor_block = build_tagline_descriptor_block(
                self.load_yaml(self._role_dna_dir(), "role_dna.yaml")
            )
        except Exception:
            descriptor_block = ""
        if descriptor_block:
            build_prompt = f"{build_prompt}\n\n{descriptor_block}"

        # Computed once and reused at every response_schema=TemplateSchema
        # call below (build, fix, trim) -- see
        # build_education_achievement_schema_fields()'s docstring for why
        # these can't just be static fields on TemplateSchema itself.
        edu_schema_properties, edu_schema_required = (
            self.build_education_achievement_schema_fields()
        )

        try:
            _p_yaml = self.load_yaml(self.kb_dir, "profile.yml") or {}
        except Exception:
            _p_yaml = profile_paths.profile_yaml() or {}
        # Loaded unconditionally (not just in the fresh-build branch below)
        # for the same reason build_prompt is: Step 7's trim loop re-validates
        # every trim attempt regardless of whether this run resumed resume_data
        # from a checkpoint, so style_rules_for_validation must be in scope
        # even when the fresh-build branch below never executes.
        style_rules_for_validation = self.load_yaml(self.rules_dir, "style_rules.yaml")
        # Per-profile Summary voice policy: profile.yml's
        # voice_preferences.summary_first_person opts this profile into
        # first-person Summaries (validated the same way -- validate_resume
        # reads the flag off this style_rules dict, the same pattern as its
        # enforce_star flag). Deliberately NOT a shared-rules change:
        # first-person summaries are one candidate's documented register
        # (their voice-favorites.md), not a universal style; a profile
        # without the key keeps the pronoun-free Summary.
        style_rules_for_validation["summary_first_person"] = bool(
            (_p_yaml or {}).get("voice_preferences", {}).get("summary_first_person")
        )
        # Same per-profile pattern: voice_preferences.prose_advisory_words
        # downgrades the named single words to soft advisories in Summary/
        # Why only (see validate_resume._check_forbidden_phrases). Empty by
        # default -- the hard ban applies everywhere unless the profile
        # opts in, exactly like summary_first_person.
        style_rules_for_validation["prose_advisory_words"] = list(
            (_p_yaml or {}).get("voice_preferences", {}).get("prose_advisory_words")
            or []
        )
        # Same reason, same place: the post-trim gate runs on the resumed path
        # too, so the roster can't be computed inside the fresh-build branch.
        role_roster = _required_role_roster(_p_yaml)
        role_bullet_minimums = _required_role_bullet_minimums(_p_yaml)
        role_bullet_maximums = _required_role_bullet_maximums(_p_yaml)
        # For repair_violations_surgically's deterministic Role Roster repair
        # -- title/period/location for a company the LLM fix loop couldn't
        # restore. Best-effort: an unreadable/missing cv.md just means that
        # repair step falls through to the existing LLM retry path instead.
        try:
            with open(os.path.join(self.kb_dir, "cv.md"), "r", encoding="utf-8") as f:
                role_metadata = _parse_cv_role_metadata(f.read())
        except Exception:
            role_metadata = {}

        resume_data = checkpoint.get("resume_data")
        if resume_data is not None:
            cli_art.print_literal("  Resuming: using resume JSON from checkpoint.")
        else:
            kb_context = self.load_knowledge_base()

            # `research` and `research_block` come from Step 2b. Re-running
            # research_company() here when it came back empty just paid for
            # the same scrape + grounded-search tiers a second time.

            situational_block = ""
            if situational_candidates:
                situational_block = (
                    "\n\n=== SITUATIONAL ROLE CANDIDATES ===\n"
                    f"The JD's language matched a deterministic keyword gate for: "
                    f"{', '.join(situational_candidates)}. These are NOT automatically "
                    "included -- use your own judgment on whether including one of them, or "
                    "at most two (each a small, 2-bullet supporting entry), would genuinely "
                    "help this specific JD, per the Situational/Optional Work History Entries rules. "
                    "If none would genuinely help, don't include any of them -- this "
                    "should be rare by construction, not a default."
                )

            role_rules_block = self.build_role_rules_block(_p_yaml)

            # style_rules.yaml/ai_risk.yaml used to be attached only to the
            # post-build critique call (Step 5) and polish.py's cover-letter
            # edit call -- the builder itself relied on tailor_resume.md's own
            # hard-coded banned-word list, which had already drifted out of
            # sync with the real ones (see that file's own note). Attaching
            # the real rubrics here lets the builder avoid these terms at
            # generation time instead of only getting flagged for them after
            # the fact. style_rules_for_validation is already loaded above
            # (unconditionally, for the post-trim gate) -- reused here rather
            # than loading style_rules.yaml a second time.
            banned_language_block = (
                "\n\n=== STYLE RULES (avoid every term in forbidden_phrases below "
                "-- this is the tested master banned-phrase list) ===\n"
                f"{json.dumps(style_rules_for_validation)}"
                "\n\n=== AI RISK SCORING RUBRIC (avoid every term in buzzwords, "
                "adjective_padding, banned_openers, and banned_phrases below) ===\n"
                f"{json.dumps(self.load_yaml(self.scoring_dir, 'ai_risk.yaml'))}"
            )

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
            builder_system = (
                f"{build_prompt}\n\n{kb_context}{research_block}{situational_block}"
                f"{role_rules_block}{banned_language_block}\n\n"
                "=== ATS KEYWORD DENSITY INSTRUCTION ===\n"
                "When crafting SUMMARY_TEXT and selecting verified SKILLS, prioritize verbatim phrases "
                "from JD KEYWORDS (e.g. use exact domain titles like 'Cybersecurity' or verbatim tool names) "
                "whenever truthful, maximizing exact ATS keyword density."
            )

            bullets_block = "\n".join(
                f"- [{company or 'unknown company'}] {b}"
                for b, company in zip(refined_bullets, bullet_companies)
            )
            try:
                import skills_menu

                _priority_skills = verified_jd_skills(
                    jd_keywords,
                    [
                        (t.get("name") or "").strip()
                        for t in (skills_menu._load_verified_tools() or {}).get(
                            "tools", []
                        )
                    ],
                )
            except Exception:
                _priority_skills = []
            _priority_block = (
                (
                    "=== VERIFIED SKILLS THIS JD ASKS FOR ===\n"
                    "The candidate is verified for every skill below AND the job asks for it. "
                    "Give each a place in SKILLS before any generic item the JD never names "
                    '(e.g. drop "Dashboards" to make room for "Report & Dashboard Building"). '
                    "Keep line-length rules; shorten or cut non-JD items rather than skipping these.\n"
                    + "\n".join(f"- {k}" for k in _priority_skills)
                    + "\n\n"
                )
                if _priority_skills
                else ""
            )
            combined_contents = (
                _priority_block + f"=== JD KEYWORDS ===\n{json.dumps(jd_keywords)}\n\n"
                f"=== JOB DESCRIPTION ===\n{jd_text}\n=== END JOB DESCRIPTION ===\n\n"
                f"=== MASTER RESUME ===\n{json.dumps(master_resume, indent=2)}\n\n"
                f"=== REFINED BULLETS ===\n{bullets_block}"
            )

            cli_art.detail(
                f"  builder_system size: {len(builder_system)} chars / ~{len(builder_system)//4} tokens"
            )
            cli_art.detail(
                f"  combined_contents size: {len(combined_contents)} chars / ~{len(combined_contents)//4} tokens"
            )

            # Step 3's audit loop just made up to 30 calls; give the free
            # tier's rolling per-minute token window a moment to recover
            # before this ~105k-token call (see PRE_BUILDER_SLEEP above).
            cli_art.detail(
                f"  Pausing {PRE_BUILDER_SLEEP}s before the builder call to avoid tripping the per-minute token cap...",
                level=cli_art.NORMAL,
            )
            time.sleep(PRE_BUILDER_SLEEP)

            with cli_art.thinking_status("Building custom resume with Gemini..."):
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
                cli_art.console.print(
                    f"  {cli_art.ERROR} Builder returned empty response.",
                    soft_wrap=True,
                )
                return {}

            resume_data = GeminiClient.parse_json(resume_text)
            if not resume_data:
                cli_art.console.print(
                    f"  {cli_art.ERROR} Could not parse builder JSON.", soft_wrap=True
                )
                cli_art.console.rule(
                    "Raw builder response (truncated)", style="dim", align="left"
                )
                # Preserve exact text for debugging assertions/tests.
                cli_art.print_literal(resume_text[:500])
                return {}

            resume_data = normalize_resume.normalize(resume_data)

            violations = validate_resume.validate(
                resume_data,
                style_rules_for_validation,
                role_roster,
                role_bullet_minimums,
                role_bullet_maximums=role_bullet_maximums,
                bullet_tuples=bullet_tuples,
            )
            if violations:
                cli_art.print_literal(
                    f"  Validator found {len(violations)} issue(s), attempting surgical zero-token & micro-repairs..."
                )
                resume_data, violations = repair_violations_surgically(
                    resume_data,
                    violations,
                    style_rules_for_validation,
                    role_roster,
                    role_bullet_minimums,
                    bullet_tuples,
                    role_bullet_maximums=role_bullet_maximums,
                    role_metadata=role_metadata,
                )

            max_fix_attempts = 4
            fix_attempt = 0
            # Hill-climb rather than random-walk. Each retry re-generates the
            # WHOLE resume (response_schema=TemplateSchema below), so despite
            # "change nothing else" an attempt is free to regress anything:
            # observed live 2026-08-12, attempt 2 got within 2 violations of
            # clean and attempt 3 came back with 5 new bullet widows and 4
            # roles pushed below their bullet minimums, because it had
            # silently deleted bullets. Anchoring each attempt (and the final
            # result) on the best state reached so far makes a bad attempt
            # cost one turn instead of destroying all prior progress.
            best_resume_data = resume_data
            best_violations = violations
            # Tracks consecutive fix attempts that failed to beat best_violations.
            # When best never advances, the next attempt re-sends the identical
            # fix_contents (same resume_data, same violations) -- so at
            # temperature=0.0 it is GUARANTEED to reproduce the exact same
            # failed output, burning the remaining attempts on repeats of one
            # failure rather than distinct tries. Escalating temperature on a
            # stall breaks the determinism trap without touching the first,
            # most-likely-to-succeed attempt.
            #
            # A modest linear bump (0.2/0.4/0.6) was tried first and observed
            # live 2026-08-22 NOT to be enough on its own: for a bullet/skills
            # line the model has decided is "already fine" (usually because it
            # can't reliably count characters the way the validator does), the
            # next-token probabilities for reproducing that exact text are so
            # close to 1.0 that a small temperature increase barely perturbs
            # them -- 4 attempts came back byte-identical even as temperature
            # rose from 0.0 to 0.4. Real fix has two parts: escalate harder
            # once a stall is confirmed (not gradually), and explicitly tell
            # the model its last output was unchanged -- the arithmetic hint
            # alone wasn't enough to make it realize it hadn't acted on it.
            stall_streak = 0
            prev_round_violations = None
            while violations and fix_attempt < max_fix_attempts:
                fix_attempt += 1
                resume_data, violations = best_resume_data, best_violations
                exact_repeat = (
                    prev_round_violations is not None
                    and violations == prev_round_violations
                )
                fix_temperature = (
                    0.0
                    if stall_streak == 0
                    else min(0.4 + 0.2 * (stall_streak - 1), 0.9)
                )
                if exact_repeat:
                    # Full detail was already printed once for this exact
                    # set of violations -- reprinting it verbatim on every
                    # stalled retry is exactly the noise that made this
                    # section unreadable live. One compact line instead.
                    cli_art.print_literal(
                        f"  Validator: same {len(violations)} issue(s) as last attempt "
                        f"(unresolved), attempt {fix_attempt}/{max_fix_attempts}, "
                        f"retrying at temperature {fix_temperature:.1f}."
                    )
                else:
                    cli_art.print_literal(
                        f"  Validator found {len(violations)} issue(s), attempt {fix_attempt}/{max_fix_attempts}:"
                    )
                    for v in violations:
                        cli_art.print_literal(f"    - {_condensed_violation(v)}")
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
                        v.split("'")[1]
                        for v in violations
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
                        + "\n".join(roster_lines)
                        + "\n\n"
                    )
                if any(_is_skills_line_violation(v) for v in violations):
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
                if any(_is_bullet_widow_violation(v) for v in violations):
                    # Mirrors the Skills-widow block above: repeated bullet-widow
                    # violations across retry attempts mean the model can't
                    # reliably count characters from prose alone, so restate the
                    # exact arithmetic here instead of a vague "tighten it".
                    limits = style_rules_for_validation.get("bullet_structure", {})
                    one_liner_max = limits.get("one_liner_max_chars", 108)
                    widow_min_words = limits.get("widow_min_words", 5)
                    exp_bullets = [
                        b
                        for job in resume_data.get("EXPERIENCE", [])
                        for b in job.get("achievements", [])
                    ]
                    widow_details = [
                        f"- {len(b)} chars, {wc}-word widow: {b!r}"
                        for b, wc in validate_resume.bullets_with_short_widow(
                            exp_bullets, style_rules_for_validation
                        )
                    ]
                    fix_contents += (
                        f"=== FIXING A BULLET WIDOW ===\n"
                        f"Each bullet below wraps to a 2nd line at the {one_liner_max}-char mark but "
                        f"leaves fewer than {widow_min_words} words there. Either (1) trim it to "
                        f"{one_liner_max} chars or fewer so it fits on one line, or (2) lengthen it "
                        f"well past {one_liner_max} chars so the 2nd line carries at least "
                        f"{widow_min_words} words -- don't leave it in the narrow band between those "
                        f"two targets.\n" + "\n".join(widow_details) + "\n\n"
                    )
                if _needs_metric_inventory(violations):
                    # Same whack-a-mole risk as the Opening Verb block above,
                    # and the reason it's needed here too: observed live --
                    # lengthening a bullet to fix the widow violation above
                    # pulled in "100+" as filler, colliding with a "100+"
                    # already used in an unrelated bullet.
                    current_metrics = validate_resume.get_all_metrics(resume_data)
                    fix_contents += (
                        f"=== ALL METRICS CURRENTLY USED ACROSS THE CV ===\n"
                        f"{', '.join(current_metrics)}\n"
                        f"When fixing a duplicate-metric issue, or adding filler content to "
                        f"lengthen a bullet for the widow fix above, the number used must not "
                        f"already appear anywhere in this list.\n\n"
                    )
                if any("Hallucinated skill or tool" in v for v in violations):
                    fix_contents += (
                        f"=== FIXING A HALLUCINATED TOOL OR SKILL ===\n"
                        f"Every tool and skill in the SKILLS section and EXPERIENCE bullets MUST come strictly "
                        f"from verified_tools.json or profile.yml. Remove any unverified, invented, or generic "
                        f"phrases not explicitly grounded in the candidate's verified profile.\n\n"
                    )
                if exact_repeat:
                    # The arithmetic hints above (exact char counts, the
                    # illegal dead-band) were already present last round and
                    # weren't enough on their own -- the model's most common
                    # failure mode here isn't ignoring the rule, it's judging
                    # the existing text as already compliant and passing it
                    # through unedited. Name that explicitly, since "here's
                    # the same math again" doesn't fix a problem that was
                    # never a math problem in the first place.
                    fix_contents += (
                        f"=== YOUR LAST ATTEMPT DID NOT CHANGE THIS TEXT ===\n"
                        f"The issue(s) below are byte-for-byte identical to what you returned "
                        f"last attempt -- the text was not edited at all. Whatever you believe "
                        f"about its current length, it still measures as a violation. You must "
                        f"produce genuinely different wording for every line listed below, not "
                        f"re-affirm the same text.\n\n"
                    )
                fix_contents += (
                    f"=== ISSUES TO FIX (change nothing else) ===\n"
                    + "\n".join(f"- {v}" for v in violations)
                )
                fix_text, fix_usage = GeminiClient.generate(
                    model=BUILDER_MODEL,
                    system_instruction=build_prompt,
                    contents=fix_contents,
                    response_schema=TemplateSchema,
                    extra_schema_properties=edu_schema_properties,
                    extra_required=edu_schema_required,
                    temperature=fix_temperature,
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
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} Fix attempt {fix_attempt}/{max_fix_attempts} returned unparseable JSON; keeping prior resume_data and retrying if attempts remain.",
                        soft_wrap=True,
                    )
                    # Counts as a stall: otherwise the next attempt re-sends
                    # the identical call at the same temperature, and a
                    # deterministic parse failure repeats until attempts run out.
                    stall_streak += 1
                    continue
                resume_data = normalize_resume.normalize(fixed)
                violations = validate_resume.validate(
                    resume_data,
                    style_rules_for_validation,
                    role_roster,
                    role_bullet_minimums,
                    role_bullet_maximums=role_bullet_maximums,
                    bullet_tuples=bullet_tuples,
                )
                if violations:
                    resume_data, violations = repair_violations_surgically(
                        resume_data,
                        violations,
                        style_rules_for_validation,
                        role_roster,
                        role_bullet_minimums,
                        bullet_tuples,
                        role_bullet_maximums=role_bullet_maximums,
                        role_metadata=role_metadata,
                    )
                if len(violations) < len(best_violations):
                    best_resume_data, best_violations = resume_data, violations
                    stall_streak = 0
                else:
                    stall_streak += 1
                prev_round_violations = violations

            resume_data, violations = best_resume_data, best_violations

            # Last deterministic pass before giving up. An unverified tool in
            # SKILLS is removable without a model call, yet a data-science
            # sample failed twice on 2026-09-14 with only such violations left
            # (Snowflake/Redshift/Docker, then Spark/Snowflake/Prototyping) --
            # the retry loop kept re-adding them and the build returned {}.
            if violations and any(
                "Hallucinated skill or tool" in v for v in violations
            ):
                resume_data, violations = repair_violations_surgically(
                    resume_data,
                    violations,
                    style_rules_for_validation,
                    role_roster,
                    role_bullet_minimums,
                    bullet_tuples,
                    role_bullet_maximums=role_bullet_maximums,
                    role_metadata=role_metadata,
                )

            if violations:
                fatal_violations, soft_warnings = partition_violations(violations)
                if fatal_violations:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('error')} Validator still found {len(fatal_violations)} fatal issue(s) after {max_fix_attempts} attempts:",
                        soft_wrap=True,
                    )
                    for v in fatal_violations:
                        cli_art.print_literal(f"    - {v}")
                    return {}
                else:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} {len(soft_warnings)} non-fatal warning(s) remain after {max_fix_attempts} attempts; proceeding with build:",
                        soft_wrap=True,
                    )
                    for v in soft_warnings:
                        cli_art.print_literal(f"    - {v}")

            checkpoint["resume_data"] = resume_data
            # Persisted (rather than read off `research` at the Step 6 call
            # site) because `research` only exists in this fresh-build
            # branch -- a resumed run enters at the `resume_data is not
            # None` branch above and would otherwise both NameError and
            # silently lose the substitution.
            checkpoint["vocabulary_substitutions"] = (research or {}).get(
                "vocabulary_substitutions", []
            )
            jd_manager.save_checkpoint(job_key, checkpoint)

        # --- Step 5: Post-build holistic critique ---
        cli_art.console.rule(
            "Step 5: Running holistic resume critique...", style="dim", align="left"
        )
        critique_data = checkpoint.get("critique_data")
        if critique_data is not None:
            cli_art.print_literal(
                "  Resuming: using holistic critique from checkpoint."
            )
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
                (self.rules_dir, "style_rules.yaml", "STYLE RULES"),
                (
                    self.scoring_dir,
                    "professional_identity_score.yaml",
                    "PROFESSIONAL IDENTITY SCORING RUBRIC",
                ),
                (
                    self.scoring_dir,
                    "resume_cohesion_score.yaml",
                    "RESUME COHESION SCORING RUBRIC",
                ),
                (
                    self.scoring_dir,
                    "believability.yaml",
                    "BELIEVABILITY SCORING RUBRIC",
                ),
                (
                    self.scoring_dir,
                    "experience_structure_score.yaml",
                    "EXPERIENCE STRUCTURE SCORING RUBRIC",
                ),
                (self.scoring_dir, "manager_test.yaml", "MANAGER TEST SCORING RUBRIC"),
                (self.scoring_dir, "skills_scoring.yaml", "SKILLS SCORING RUBRIC"),
                (self._role_dna_dir(), "role_dna.yaml", "ROLE DNA SCORING RUBRIC"),
                (self.scoring_dir, "ats_match.yaml", "ATS MATCH SCORING RUBRIC"),
                (self.scoring_dir, "ai_risk.yaml", "AI RISK SCORING RUBRIC"),
                (
                    self.scoring_dir,
                    "evidence_alignment.yaml",
                    "EVIDENCE ALIGNMENT SCORING RUBRIC",
                ),
                (
                    self.scoring_dir,
                    "summary_patterns.yaml",
                    "SUMMARY PATTERNS SCORING RUBRIC",
                ),
                (
                    self.scoring_dir,
                    "certifications_score.yaml",
                    "CERTIFICATIONS SCORING RUBRIC",
                ),
                (
                    self.scoring_dir,
                    "recruiter_score.yaml",
                    "RECRUITER SCORE SCORING RUBRIC",
                ),
                (self.scoring_dir, "specificity.yaml", "SPECIFICITY SCORING RUBRIC"),
                (self.scoring_dir, "summary_score.yaml", "SUMMARY SCORING RUBRIC"),
                (
                    self.scoring_dir,
                    "top_third_score.yaml",
                    "TOP-THIRD-OF-PAGE-ONE SCORING RUBRIC",
                ),
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
            with cli_art.thinking_status("Auditing CV fit and quality with Gemini..."):
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
                    critique_data["recommendations"] = list(
                        critique_data.get("recommendations", []) or []
                    ) + [f"Fix rubric hard failure -- {hf}" for hf in hard_failures]

                cli_art.console.rule(
                    "Holistic critique scores", style="dim", align="left"
                )
                cli_art.print_literal(
                    f"summary_alignment : {critique_data.get('summary_alignment_score', '?')}"
                )
                cli_art.print_literal(
                    f"skills_relevance  : {critique_data.get('skills_relevance_score',  '?')}"
                )
                cli_art.print_literal(
                    f"top_third         : {critique_data.get('top_third_score',         '?')}"
                )
                cli_art.print_literal(
                    f"overall_fit       : {critique_data.get('overall_fit_score',        '?')}"
                )
                identity_line = critique_data.get("primary_identity", "?")
                if critique_data.get("secondary_identity"):
                    identity_line += f" / {critique_data['secondary_identity']}"
                cli_art.print_literal(f"identity          : {identity_line}")
                cli_art.print_literal(
                    f"weakest ATS       : {critique_data.get('weakest_ats_platform', '?')}"
                )
                cli_art.print_literal()
                if hard_failures:
                    cli_art.console.print(
                        f"{theme.colorize_icon('error')} Hard rubric failures (added to recommendations):",
                        soft_wrap=True,
                    )
                    for hf in hard_failures:
                        cli_art.print_literal(f"- {hf}")
                    cli_art.print_literal()
                flags = critique_data.get("flags", [])
                if flags:
                    cli_art.print_literal("Flags:")
                    for flag in flags:
                        cli_art.print_literal(f"- {flag}")
                    cli_art.print_literal()
                recs = critique_data.get("recommendations", [])
                if recs:
                    cli_art.print_literal("Recommendations:")
                    for rec in recs:
                        cli_art.print_literal(f"- {rec}")
                    cli_art.print_literal()
                moments = critique_data.get("distinctive_moments", [])
                if moments:
                    cli_art.print_literal("Distinctive moments (protected):")
                    for m in moments:
                        cli_art.print_literal(f"- {m}")
                    cli_art.print_literal()
                flat = critique_data.get("flat_sections", [])
                if flat:
                    cli_art.print_literal("Flat sections:")
                    for f in flat:
                        cli_art.print_literal(f"- {f}")
                    cli_art.print_literal()
                platform_risks = critique_data.get("platform_parsing_risks", [])
                if platform_risks:
                    cli_art.print_literal("Platform parsing risks:")
                    for risk in platform_risks:
                        cli_art.print_literal(f"- {risk}")
                    cli_art.print_literal()
                resume_data["_critique"] = critique_data
                checkpoint["critique_data"] = critique_data
                jd_manager.save_checkpoint(job_key, checkpoint)
            else:
                cli_art.console.print(
                    f"  {cli_art.WARNING} Holistic critique returned empty.",
                    soft_wrap=True,
                )

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
            cli_art.console.print(
                f"\n  {theme.colorize_icon('hint')} {len(question_recs)} recommendation(s) "
                "are questions for you, not edits -- saved for `resume polish`, not applied.",
                soft_wrap=True,
            )
        distinctive_moments = (resume_data.get("_critique") or {}).get(
            "distinctive_moments", []
        )
        protected_block = (
            (
                "=== PROTECTED DISTINCTIVE MOMENTS (preserve verbatim unless THIS "
                "recommendation specifically targets them) ===\n"
                + "\n".join(f"- {m}" for m in distinctive_moments)
                + "\n\n"
            )
            if distinctive_moments
            else ""
        )

        if recs and interactive:
            recs = _review_recommendations_interactively(recs, checkpoint, job_key)

        if recs or question_recs:
            state = checkpoint.get("recommendation_actions") or {
                # Seeded, not appended later: question_recs must survive even
                # when they were the *only* recommendations, in which case the
                # apply loop below never runs.
                "resume_data": resume_data,
                "applied": [],
                "skipped": [],
                "needs_polish": list(question_recs),
                "next_index": 0,
            }
            start_index = state["next_index"]
            if not recs:
                pass
            elif start_index >= len(recs):
                cli_art.console.rule(
                    "Step 5.5: Resuming: recommendation pass already complete from checkpoint.",
                    style="dim",
                    align="left",
                )
            else:
                cli_art.console.rule(
                    f"Step 5.5: Applying actionable recommendations one at a time ({start_index}/{len(recs)} already done)...",
                    style="dim",
                    align="left",
                )
            resume_data = state["resume_data"]
            applied, skipped = state["applied"], state["skipped"]
            needs_polish = state.get("needs_polish", [])

            # A recommendation is judged on what IT introduced, never on what
            # the resume already carried. Step 4 legitimately leaves soft
            # violations standing -- partition_violations makes vague
            # magnitudes and filler lines non-fatal, so the build ships with
            # them -- and comparing each candidate against zero meant a single
            # leftover discarded EVERY later recommendation as if it had caused
            # it. Measured on a real build: one stray "significantly" in the
            # Summary threw away both actionable recommendations, neither of
            # which touched that sentence. Same baseline subtraction the
            # Why-section backfill below already does.
            baseline_violations = validate_resume.validate(
                resume_data,
                style_rules_for_validation,
                role_roster,
                role_bullet_minimums,
                role_bullet_maximums=role_bullet_maximums,
                bullet_tuples=bullet_tuples,
            )

            for i in range(start_index, len(recs)):
                rec = recs[i]
                if i > 0:
                    time.sleep(RECOMMENDATION_SLEEP)
                cli_art.print_literal(
                    f"\n  [{i + 1}/{len(recs)}] {cli_art._escape_markup(rec[:70])}..."
                )
                rec_contents = (
                    f"=== CURRENT RESUME JSON ===\n{json.dumps(_sanitize_none_for_prompt(resume_data), indent=2)}\n\n"
                    f"{protected_block}"
                    f"=== RECOMMENDATION TO CONSIDER ===\n{rec}\n\n"
                    f"=== INSTRUCTIONS ===\n"
                    f"Decide whether the recommendation above is a concrete, actionable edit to "
                    f"THIS resume's own content (e.g. naming a specific tool, rewording a title/"
                    f"summary/skills phrase to mirror the JD). If so, apply ONLY this one "
                    f"recommendation and put its exact original text in applied_recommendations. "
                    f"When applying edits to summary/skills/bullets, prioritize using verbatim terminology "
                    f"from the JD keywords and recommendation (e.g. use 'Cybersecurity' instead of generic "
                    f"'Technical SaaS') when truthful to maximize ATS exact-match density. "
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
                    cli_art.console.print(
                        f"    {cli_art.WARNING} unparseable JSON; leaving resume as-is for this recommendation.",
                        soft_wrap=True,
                    )
                else:
                    this_applied = rec_result.pop("applied_recommendations", [])
                    this_skipped = rec_result.pop("skipped_recommendations", [])
                    this_needs_input = rec_result.pop("needs_personal_input", [])
                    candidate_resume_data = normalize_resume.normalize(rec_result)
                    rec_violations_all = validate_resume.validate(
                        candidate_resume_data,
                        style_rules_for_validation,
                        role_roster,
                        role_bullet_minimums,
                        role_bullet_maximums=role_bullet_maximums,
                        bullet_tuples=bullet_tuples,
                    )
                    rec_violations = [
                        v for v in rec_violations_all if v not in baseline_violations
                    ]
                    if rec_violations:
                        cli_art.console.print(
                            f"    {cli_art.WARNING} introduced {len(rec_violations)} validator violation(s); "
                            f"discarding just this recommendation:",
                            soft_wrap=True,
                        )
                        for v in rec_violations:
                            cli_art.print_literal(
                                f"      - {cli_art._escape_markup(v)}"
                            )
                        skipped.append(
                            f"{rec} (attempted, discarded: introduced a validator violation)"
                        )
                    elif this_applied:
                        resume_data = candidate_resume_data
                        # The accepted edit becomes the new baseline: it may
                        # have cleared a pre-existing violation (good) or left
                        # one standing, and the NEXT recommendation must be
                        # judged against what the resume actually looks like
                        # now, not against what Step 4 produced.
                        baseline_violations = rec_violations_all
                        applied.append(rec)
                        cli_art.print_literal("    Applied.")
                    elif this_needs_input:
                        needs_polish.append(rec)
                        cli_art.print_literal(
                            "    Needs your input -- left unchanged (try `resume polish`)."
                        )
                    else:
                        skipped.append(rec)
                        cli_art.print_literal(
                            "    Skipped (not a resume-content edit)."
                        )

                checkpoint["recommendation_actions"] = {
                    "resume_data": resume_data,
                    "applied": applied,
                    "skipped": skipped,
                    "needs_polish": needs_polish,
                    "next_index": i + 1,
                }
                jd_manager.save_checkpoint(job_key, checkpoint)

            checkpoint["recommendation_actions"] = {
                "resume_data": resume_data,
                "applied": applied,
                "skipped": skipped,
                "needs_polish": needs_polish,
                "next_index": len(recs),
            }
            jd_manager.save_checkpoint(job_key, checkpoint)

            resume_data["_recommendation_actions"] = {
                "applied": applied,
                "skipped": skipped,
                "needs_polish": needs_polish,
            }
            if applied:
                cli_art.print_literal("\n  Applied:")
                for a in applied:
                    cli_art.print_literal(f"    - {cli_art._escape_markup(a)}")
            if skipped:
                cli_art.print_literal("  Skipped:")
                for s in skipped:
                    cli_art.print_literal(f"    - {cli_art._escape_markup(s)}")
            if needs_polish:
                cli_art.print_literal(
                    "  Needs your input -- good candidates for `resume polish`:"
                )
                for n in needs_polish:
                    cli_art.print_literal(f"    - {cli_art._escape_markup(n)}")

        # Mirror the company's own vocabulary into bullet text (e.g.
        # "customers" -> "guests"). Deliberately last, after Step 5.5's
        # recommendation pass: running it here means no later step can
        # reword a bullet back out of the company's language, and it's a
        # deterministic regex swap rather than an LLM edit, so it cannot
        # touch a metric, verb, or claim.
        resume_data = company_research.apply_vocabulary_substitutions_to_resume(
            resume_data, checkpoint.get("vocabulary_substitutions", [])
        )

        # A JD keyword the candidate is ALREADY verified for, that the
        # finished resume simply doesn't happen to say, is lost credit
        # rather than an honest gap -- and neither existing safety net
        # catches it. Step 1.5 flags keywords absent from the verified set
        # (an already-verified skill is correctly not a gap), and the
        # post-build prompt only offers to ADD one to the ledger. Nothing
        # asked whether a verified, JD-matching skill reached the page.
        # Deliberately before Step 6's save, so the JSON, HTML and PDF all
        # agree; see _top_up_verified_skills for why it skips rather than
        # guesses at placement.
        try:
            import skills_menu

            _verified_names = [
                (t.get("name") or "").strip()
                for t in (skills_menu._load_verified_tools() or {}).get("tools", [])
            ]
            with open(os.path.join(self.kb_dir, "cv.md"), "r", encoding="utf-8") as f:
                _cv_text = f.read()
        except Exception:
            _verified_names, _cv_text = [], ""
        if _verified_names and _cv_text:
            resume_data, _topped_up = _top_up_verified_skills(
                resume_data,
                jd_keywords,
                style_rules_for_validation,
                _cv_text,
                _verified_names,
                assign_groups=_assign_skill_groups_with_model,
            )
            if _topped_up:
                cli_art.print_literal(
                    "  Restored verified skill(s) the JD asks for: "
                    + cli_art._escape_markup(", ".join(_topped_up))
                )

        # --- Step 6: Save output ---
        output_path = os.path.join(self.output_json_dir, output_filename)
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(resume_data, f, indent=2, ensure_ascii=False)
            cli_art.print_literal(
                f"\n  Resume saved to: {cli_art._escape_markup(output_path)}"
            )
        except Exception as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} Could not save resume JSON: {e}",
                soft_wrap=True,
            )

        # --- Step 7: Render HTML + Generate PDF ---
        cli_art.console.rule(
            "Step 7: Rendering HTML and generating PDF...", style="dim", align="left"
        )
        # The JSON honors an explicit output_filename but the HTML/PDF/DOCX
        # used to re-derive their own stem from jd_path, so a caller that
        # named its JSON got differently-named siblings -- the recruiter
        # build wrote Recruiter_Resume.json beside a DominickColosimo_Resume.pdf
        # that overwrote an unrelated build. Deriving the stem from the
        # filename actually used keeps all four in step. No-op for normal
        # runs: output_filename defaults to this same stem above.
        if output_filename and output_filename.endswith("_Resume.json"):
            stem = output_filename[: -len("_Resume.json")]
        else:
            stem = _build_output_stem(jd_path)
        html_out = os.path.join(self.output_html_dir, f"{stem}_Resume.html")
        pdf_out = os.path.join(self.output_pdf_dir, f"{stem}_Resume.pdf")
        pdf_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")

        os.makedirs(os.path.dirname(html_out), exist_ok=True)
        os.makedirs(os.path.dirname(pdf_out), exist_ok=True)

        render_html(resume_data, html_out)

        trim_instructions = [
            lambda rd: "Trim the Summary to its 5-line limit.",
            lambda rd: _widow_trim_instruction(rd, style_rules_for_validation),
            lambda rd: _bullet_removal_trim_instruction(_p_yaml),
        ]
        max_trim_attempts = len(trim_instructions)
        trim_attempt = 0
        page_count = None
        dropped_optional_clients = False
        dropped_why = False
        page1_condense_attempt = 0
        page1_condense_last_violations: list[str] = []
        MAX_PAGE1_CONDENSE_ATTEMPTS = 5
        why_backfill_attempt = 0
        why_backfill_last_violations: list[str] = []
        MAX_WHY_BACKFILL_ATTEMPTS = 3

        while True:
            try:
                pdf_result = subprocess.run(
                    [
                        "node",
                        pdf_script,
                        html_out,
                        pdf_out,
                        "--format=letter",
                        "--max-pages=2",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=PDF_GENERATION_TIMEOUT_SECONDS,
                    env={**os.environ, "RESUME_BUILDER_ICONS": theme.icon_set_name()},
                )
            except subprocess.TimeoutExpired:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')}  PDF generation timed out after "
                    f"{PDF_GENERATION_TIMEOUT_SECONDS}s.",
                    soft_wrap=True,
                )
                return {}
            if pdf_result.returncode != 0:
                cli_art.friendly_subprocess_error(
                    pdf_result.stderr, "creating the PDF for this resume"
                )
                return {}

            page_count, size_str = _parse_pdf_result(pdf_result.stdout, pdf_out)
            if page_count is None:
                cli_art.console.print(
                    f"  {theme.colorize_icon('error')} Could not verify PDF page count via pypdf -- "
                    "treating as a failure rather than silently passing the 2-page rule.",
                    soft_wrap=True,
                )
                return {}
            overflow_roles = (
                _page1_overflow_roles(pdf_out, _p_yaml) if page_count <= 2 else []
            )
            page1_condense_exhausted = (
                page1_condense_attempt >= MAX_PAGE1_CONDENSE_ATTEMPTS
            )
            why_backfill_exhausted = why_backfill_attempt >= MAX_WHY_BACKFILL_ATTEMPTS
            needs_why_backfill = (
                page_count <= 2
                and not overflow_roles
                and bool(research)
                and bool(research_block)
                and not (resume_data.get("WHY_TEXT") or "").strip()
                and not why_backfill_exhausted
            )
            is_final = (
                page_count <= 2
                and (not overflow_roles or page1_condense_exhausted)
                and not needs_why_backfill
            ) or trim_attempt >= max_trim_attempts
            if is_final:
                if overflow_roles:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('warning')} {', '.join(overflow_roles)} still "
                        f"spilled onto page 2 after {MAX_PAGE1_CONDENSE_ATTEMPTS} condense "
                        "attempt(s); keeping this build rather than looping indefinitely.",
                        soft_wrap=True,
                    )
                cli_art.print_subprocess_output(pdf_result.stdout)
                break

            if page_count <= 2 and overflow_roles and page1_condense_attempt >= 1:
                page1_trim = _page1_overflow_trim(resume_data, _p_yaml)
                if page1_trim:
                    resume_data, removed_bullet = page1_trim
                    cli_art.print_literal(
                        f"  Condensing wording was not enough; dropped a "
                        f"{_p_yaml.get('page1_overflow_trim_role')} bullet so "
                        f"{', '.join(overflow_roles)} can fit on page 1: {removed_bullet}"
                    )
                    render_html(resume_data, html_out)
                    continue

            if page_count <= 2 and overflow_roles:
                page1_condense_attempt += 1
                cli_art.print_literal(
                    f"  {', '.join(overflow_roles)} spilled onto page 2 with room to spare on "
                    f"page 1 (job entries never split across pages); condensing wording to "
                    f"reclaim space (attempt {page1_condense_attempt}/{MAX_PAGE1_CONDENSE_ATTEMPTS})..."
                )
                condense_instruction = _page1_condense_instruction(
                    resume_data, _p_yaml, overflow_roles
                )
                if page1_condense_last_violations:
                    condense_instruction += (
                        "\n\nThe previous attempt at this same instruction was discarded for "
                        "introducing these validator violation(s) -- do not repeat them, and "
                        "do not touch SKILLS or any section not named above:\n"
                        + "\n".join(f"- {v}" for v in page1_condense_last_violations)
                    )
                condense_contents = (
                    f"=== ORIGINAL RESUME JSON ===\n{json.dumps(_sanitize_none_for_prompt(resume_data), indent=2)}\n\n"
                    f"=== TRIM INSTRUCTION (apply only this step) ===\n{condense_instruction}"
                )
                # Escalate off temperature=0.0 on a repeat attempt -- a
                # deterministic call given the identical prompt otherwise
                # returns the identical (already-discarded) response.
                condense_temperature = (
                    0.0
                    if page1_condense_attempt == 1
                    else min(0.2 + 0.15 * (page1_condense_attempt - 2), 0.8)
                )
                condense_text, condense_usage = GeminiClient.generate(
                    model=BUILDER_MODEL,
                    system_instruction=build_prompt,
                    contents=condense_contents,
                    response_schema=TemplateSchema,
                    extra_schema_properties=edu_schema_properties,
                    extra_required=edu_schema_required,
                    temperature=condense_temperature,
                )
                _log_cache_stats(condense_usage, 0, 0)
                condensed = GeminiClient.parse_json(condense_text or "")
                if condensed:
                    # The condense instruction only asks for wording changes to
                    # specific EXPERIENCE bullets, but SKILLS kept drifting
                    # anyway (e.g. adding "AI-Driven Ideation"), repeatedly
                    # tripping the same dead-band/hallucinated-skill violation
                    # across attempts despite being told not to touch it.
                    # Enforce the scope instead of relying on instruction-
                    # following alone.
                    condensed["SKILLS"] = resume_data.get("SKILLS")
                    condense_targets = {
                        b for _, _, b in _page1_condense_targets(resume_data, _p_yaml)
                    }
                    condensed_resume_data = _merge_condensed_bullets(
                        resume_data,
                        normalize_resume.normalize(condensed),
                        condense_targets,
                    )
                    _validate_kwargs = dict(
                        role_bullet_maximums=role_bullet_maximums,
                        bullet_tuples=bullet_tuples,
                    )
                    baseline_violations = validate_resume.validate(
                        resume_data,
                        style_rules_for_validation,
                        role_roster,
                        role_bullet_minimums,
                        **_validate_kwargs,
                    )
                    condense_violations = _newly_introduced(
                        validate_resume.validate(
                            condensed_resume_data,
                            style_rules_for_validation,
                            role_roster,
                            role_bullet_minimums,
                            **_validate_kwargs,
                        ),
                        baseline_violations,
                    )
                    if condensed_resume_data == resume_data:
                        condense_violations = condense_violations or [
                            "No targeted bullet was shortened -- rewrite at least one listed bullet to 108 characters or fewer."
                        ]
                    if condense_violations and condensed_resume_data != resume_data:
                        # One widow among four shortened bullets used to throw
                        # away all four, so every attempt of a 2026-09-16
                        # build was discarded. Keep each edit that is clean
                        # on its own.
                        partial = _keep_clean_bullet_edits(
                            resume_data,
                            condensed_resume_data,
                            lambda data: _newly_introduced(
                                validate_resume.validate(
                                    data,
                                    style_rules_for_validation,
                                    role_roster,
                                    role_bullet_minimums,
                                    **_validate_kwargs,
                                ),
                                baseline_violations,
                            ),
                        )
                        if partial != resume_data:
                            cli_art.print_literal(
                                f"  Kept the condensed bullets that passed validation; "
                                f"{len(condense_violations)} violating edit(s) reverted."
                            )
                            condensed_resume_data, condense_violations = partial, []
                    if not condense_violations:
                        resume_data = condensed_resume_data
                        render_html(resume_data, html_out)
                        page1_condense_last_violations = []
                        continue
                    cli_art.console.print(
                        f"  {cli_art.WARNING} Condense attempt introduced "
                        f"{len(condense_violations)} validator violation(s); discarding and "
                        "retrying if attempts remain:",
                        soft_wrap=True,
                    )
                    for v in condense_violations:
                        cli_art.print_literal(f"    - {cli_art._escape_markup(v)}")
                    page1_condense_last_violations = condense_violations
                continue

            if needs_why_backfill:
                why_backfill_attempt += 1
                cli_art.print_literal(
                    f"  PDF is {page_count} page(s) with room to spare and company research "
                    f"is available; backfilling the omitted Why section "
                    f"(attempt {why_backfill_attempt}/{MAX_WHY_BACKFILL_ATTEMPTS})..."
                )
                why_instruction = _why_backfill_instruction(resume_data, research_block)
                if why_backfill_last_violations:
                    why_instruction += (
                        "\n\nThe previous attempt at this same instruction was discarded for "
                        "introducing these validator violation(s) -- do not repeat them, and "
                        "do not touch any field other than SECTION_WHY/WHY_TEXT:\n"
                        + "\n".join(f"- {v}" for v in why_backfill_last_violations)
                    )
                why_contents = (
                    f"=== ORIGINAL RESUME JSON ===\n{json.dumps(_sanitize_none_for_prompt(resume_data), indent=2)}\n\n"
                    f"=== TASK ===\n{why_instruction}"
                )
                # Escalate off temperature=0.0 on a repeat attempt -- a
                # deterministic call given the identical prompt otherwise
                # returns the identical (already-discarded) response.
                why_temperature = (
                    0.0
                    if why_backfill_attempt == 1
                    else min(0.2 + 0.15 * (why_backfill_attempt - 2), 0.8)
                )
                why_text_resp, why_usage = GeminiClient.generate(
                    model=BUILDER_MODEL,
                    system_instruction=build_prompt,
                    contents=why_contents,
                    response_schema=WhyBackfillSchema,
                    temperature=why_temperature,
                )
                _log_cache_stats(why_usage, 0, 0)
                why_fields = GeminiClient.parse_json(why_text_resp or "")
                if why_fields and why_fields.get("WHY_TEXT"):
                    # Compare against the resume's own pre-backfill violations,
                    # not an absolute zero -- resume_data can already carry
                    # latent violations unrelated to Why (e.g. a bullet widow
                    # that slipped through an earlier step), and treating
                    # those as "introduced by this backfill" would wrongly
                    # discard a perfectly good Why section forever.
                    baseline_violations = set(
                        validate_resume.validate(
                            resume_data,
                            style_rules_for_validation,
                            role_roster,
                            role_bullet_minimums,
                            role_bullet_maximums=role_bullet_maximums,
                            bullet_tuples=bullet_tuples,
                        )
                    )
                    candidate_resume_data = dict(resume_data)
                    candidate_resume_data["SECTION_WHY"] = why_fields.get(
                        "SECTION_WHY", ""
                    )
                    candidate_resume_data["WHY_TEXT"] = why_fields.get("WHY_TEXT", "")
                    all_violations = validate_resume.validate(
                        candidate_resume_data,
                        style_rules_for_validation,
                        role_roster,
                        role_bullet_minimums,
                        role_bullet_maximums=role_bullet_maximums,
                        bullet_tuples=bullet_tuples,
                    )
                    why_violations = [
                        v for v in all_violations if v not in baseline_violations
                    ]
                    if not why_violations:
                        # If this pushes the page count past 2, the existing
                        # dropped_why trim step below removes it again on a
                        # later iteration -- no separate revert path needed.
                        resume_data = candidate_resume_data
                        render_html(resume_data, html_out)
                        why_backfill_last_violations = []
                        continue
                    cli_art.console.print(
                        f"  {cli_art.WARNING} Why-section backfill introduced "
                        f"{len(why_violations)} validator violation(s); discarding and "
                        "retrying if attempts remain:",
                        soft_wrap=True,
                    )
                    for v in why_violations:
                        cli_art.print_literal(f"    - {cli_art._escape_markup(v)}")
                    why_backfill_last_violations = why_violations
                continue

            if not dropped_optional_clients:
                dropped_optional_clients = True
                fixed_content = profile_paths.fixed_content_module()
                has_optional_clients = any(
                    fixed_content.CLIENTS.get(job.get("company"), {}).get("essential")
                    is False
                    and job.get("clients")
                    for job in resume_data.get("EXPERIENCE", [])
                )
                if has_optional_clients:
                    # Free, non-LLM trim step: drop the Inside Sales Team
                    # client roster (fixed_content.CLIENTS marks it
                    # non-essential) before spending an LLM-driven
                    # trim_instructions attempt.
                    cli_art.print_literal(
                        f"  PDF is {page_count} pages ({cli_art._escape_markup(size_str)}), dropping optional client rosters..."
                    )
                    resume_data = normalize_resume.normalize(
                        resume_data, include_optional_clients=False
                    )
                    render_html(resume_data, html_out)
                    continue

            if not dropped_why:
                dropped_why = True
                if resume_data.get("SECTION_WHY") or resume_data.get("WHY_TEXT"):
                    # Free, non-LLM trim step, same reasoning as the client-
                    # roster drop above: Why only belongs on the resume if it
                    # fits without pushing the page count past 2, and dropping
                    # it is just blanking two fields -- routing it through the
                    # LLM used to let the model bundle unrelated edits into
                    # the same response, so a validator violation *anywhere*
                    # in that response discarded the one edit that actually
                    # freed a page, and Why silently stuck around for every
                    # remaining trim attempt.
                    cli_art.print_literal(
                        f"  PDF is {page_count} pages ({cli_art._escape_markup(size_str)}), dropping the Why section (first thing to go when space is tight)..."
                    )
                    resume_data = dict(resume_data)
                    resume_data["SECTION_WHY"] = ""
                    resume_data["WHY_TEXT"] = ""
                    render_html(resume_data, html_out)
                    continue

            # Deterministic, non-LLM trim step: drop a surplus bullet from the
            # lowest-flex_priority role (respecting min_bullets floors and
            # protected_bullets) before spending an LLM-driven trim_instructions attempt.
            resume_data_trimmed, trimmed_bullet = trim_surplus_bullet_deterministically(
                resume_data, _p_yaml, role_bullet_minimums
            )
            if trimmed_bullet:
                resume_data = resume_data_trimmed
                render_html(resume_data, html_out)
                continue

            cli_art.print_literal(
                f"  PDF is {page_count} pages ({cli_art._escape_markup(size_str)}), applying trim step {trim_attempt + 1}/{max_trim_attempts}..."
            )
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
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} Trim attempt {trim_attempt + 1}/{max_trim_attempts} returned unparseable JSON; "
                    f"keeping prior resume_data and retrying if attempts remain.",
                    soft_wrap=True,
                )
                trim_attempt += 1
                continue

            trimmed_resume_data = normalize_resume.normalize(trimmed)
            trim_violations = validate_resume.validate(
                trimmed_resume_data,
                style_rules_for_validation,
                role_roster,
                role_bullet_minimums,
                role_bullet_maximums=role_bullet_maximums,
                bullet_tuples=bullet_tuples,
            )
            if trim_violations:
                cli_art.console.print(
                    f"  {cli_art.WARNING} Trim attempt {trim_attempt + 1} introduced {len(trim_violations)} "
                    f"validator violation(s); discarding this trim and keeping the prior resume_data:",
                    soft_wrap=True,
                )
                for v in trim_violations:
                    cli_art.print_literal(f"    - {cli_art._escape_markup(v)}")
                trim_attempt += 1
                continue

            resume_data = trimmed_resume_data
            render_html(resume_data, html_out)
            trim_attempt += 1

        if page_count > 2:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} PDF still {page_count} pages after {max_trim_attempts} trim attempts.",
                soft_wrap=True,
            )
            return {}

        # Re-save after Step 7: page fitting can still change resume_data --
        # the Why backfill adds WHY_TEXT when the PDF has room, and trims drop
        # bullets -- after Step 6 already wrote the JSON. A 2026-09-14 sample's
        # saved JSON had an empty WHY_TEXT while its PDF carried a full Why
        # section, so a re-render from the JSON silently lost it.
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(resume_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} Could not re-save final resume JSON: {e}",
                soft_wrap=True,
            )

        final_companies = {
            job.get("company") for job in resume_data.get("EXPERIENCE", [])
        }
        fired_situational_roles = final_companies & set(
            situational_roles.load_situational_roles()["roles"].keys()
        )
        if fired_situational_roles:
            cli_art.console.print(
                f"  {theme.colorize_icon('hint')} Situational role fired: {', '.join(sorted(fired_situational_roles))}",
                soft_wrap=True,
            )

        pdf_fatal, pdf_text_warnings = validate_pdf_text.validate_pdf_text(
            pdf_out, resume_data, jd_keywords=jd_keywords
        )
        if pdf_fatal:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} PDF text-layer check could not verify the rendered file "
                f"-- treating this as a failed build, not a warning:",
                soft_wrap=True,
            )
            from rich.text import Text

            for f in pdf_fatal:
                # Print raw to stdout so the exact exception text appears
                # unwrapped and unstyled for tests that assert on the
                # literal substring.
                print(f"    - {f}")
            return {}
        if pdf_text_warnings:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} PDF text-layer check found {len(pdf_text_warnings)} potential issue(s) "
                f"(what an ATS would actually parse from the file, not just the pre-render JSON):",
                soft_wrap=True,
            )
            from rich.text import Text

            for w in pdf_text_warnings:
                msg = Text("    - ")
                msg.append(str(w))
                cli_art.console.print(msg)
        else:
            cli_art.console.print(
                f"  {theme.colorize_icon('success')} PDF text-layer check: 0 issues.",
                soft_wrap=True,
            )

        docx_out = os.path.join(self.output_docx_dir, f"{stem}_Resume.docx")
        try:
            render_resume_docx(resume_data, docx_out)
        except Exception as e:
            cli_art.friendly_error(e, "creating the DOCX for this resume")
            return {}

        # B18 (phase-9-backlog.md): reported before the pipeline claims
        # success, per the backlog item's own wording -- not gated. See
        # validate_resume.check_keyword_coverage()'s docstring for why a
        # missing keyword doesn't block the build.
        ats_match_rules = self.load_yaml(self.scoring_dir, "ats_match.yaml")
        coverage = validate_resume.check_keyword_coverage(
            resume_data, jd_keywords, ats_match_rules
        )
        jd_manager.save_coverage(jd_path, coverage)
        coverage_icon = (
            "success"
            if coverage["band"] in ("excellent_match", "good_match")
            else "warning"
        )
        cli_art.console.print(
            f"  {theme.colorize_icon(coverage_icon)} JD-keyword coverage: {coverage['score']}% "
            f"({coverage['band']}, {len(coverage['matched'])}/{len(coverage['matched']) + len(coverage['missing'])})",
            soft_wrap=True,
        )
        if coverage["missing"]:
            cli_art.print_literal(
                f"    Missing: {cli_art._escape_markup(', '.join(coverage['missing']))}"
            )

        # B29 (phase-9-backlog.md): same non-blocking, report-not-gate
        # treatment as the coverage check above, and for the same class of
        # reason -- see validate_resume.check_summary_specificity()'s
        # docstring for the real build failure that made this non-blocking.
        specificity_notes = validate_resume.check_summary_specificity(resume_data)
        for note in specificity_notes:
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} {note}", soft_wrap=True
            )

        # Belt-and-suspenders on top of the fatal check above: don't claim
        # success or record output paths unless the PDF is actually on disk
        # (ResumeDesignSystem.md's guarantee -- the system must never claim a
        # resume exists when generation failed).
        if not os.path.exists(pdf_out):
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} Pipeline did not complete -- expected PDF not found on disk: {pdf_out}",
                soft_wrap=True,
            )
            return {}

        cli_art.console.print(
            f"  {theme.colorize_icon('success')} Pipeline complete! PDF → {pdf_out}",
            soft_wrap=True,
        )
        jd_manager.delete_checkpoint(job_key)
        resume_data["_output_paths"] = {
            "json": output_path,
            "html": html_out,
            "pdf": pdf_out,
            "docx": docx_out,
        }
        resume_data["_page_count"] = page_count
        os.environ["RESUME_BUILDER_LAST_PDF"] = pdf_out

        logger.info(f"build_tailored_resume completed successfully: {job_key}")

        # Record any still-missing keywords to the verified skills ledger for
        # NEXT time, without offering to rebuild THIS run. Previously this
        # auto-offered (and defaulted to yes on) a full from-scratch rebuild
        # -- re-mining the bank and re-running the builder, a second real
        # API cost -- every time the finished-resume coverage check found
        # something Step 1.5's confirm_jd_skill_gaps_interactively() (the
        # pre-build prompt) hadn't already asked about. Since
        # find_unverified_jd_skill_gaps() now checks the same
        # tools/hard_skills/core_functions universe check_keyword_coverage()
        # does (2026-09-06 fix), this list should usually already be empty
        # by the time we get here; confirming here is a safety net for the
        # cases it doesn't catch (e.g. ATS text-matching quirks), not a
        # second full prompt-and-rebuild cycle.
        if interactive and coverage["missing"]:
            confirmed_skills = confirm_missing_coverage_keywords_interactively(
                coverage["missing"]
            )
            if confirmed_skills:
                cli_art.console.print(
                    f"  {theme.colorize_icon('hint')} Saved for next build -- "
                    f"run `resume run {jd_path}` again if you want this resume "
                    f"to reflect {'them' if len(confirmed_skills) > 1 else 'it'}.",
                    soft_wrap=True,
                )

        return resume_data

    def build_application_package(
        self,
        jd_path: str,
        master_resume: dict | None = None,
        output_filename: str | None = None,
        referral: str | None = None,
        force: bool = False,
        skip_liveness: bool = False,
        skip_fit: bool = False,
        interactive: bool = False,
    ) -> dict:
        """
        Builds a complete, 4-artifact application package (Resume PDF/DOCX +
        Cover Letter PDF/DOCX) for a single JD with fail-fast liveness and fit gates.

        1. Liveness Gate: If source_url exists and not skip_liveness, verifies URL.
           If expired, moves JD to jds/expired/ and returns {"status": "expired", "reason": ...}.
        2. Fit & Capability Gate: Unless skip_fit, checks evaluation. If "Skip" and not force,
           moves JD to jds/archived/ and returns {"status": "skipped", "evaluation": ...}.
        3. Referral & ATS Classification: Saves referral if given, extracts metadata & ATS tier.
        4. Resume Generation: Builds tailored resume (PDF, DOCX, HTML, JSON).
        5. Cover Letter Generation: Builds tailored cover letter (PDF, DOCX, HTML, JSON).
        6. Persistence & Tracking: Moves JD to jds/completed/, records in tracker & DB.
        7. Returns comprehensive package dict with status 'completed' and output_paths.
        """
        if not os.path.exists(jd_path):
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} JD file not found: {jd_path}",
                soft_wrap=True,
            )
            return {"status": "error", "message": f"JD file not found: {jd_path}"}

        try:
            job_key = jd_manager.compute_job_key(jd_path)
        except Exception as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} Could not compute job key for {jd_path}: {e}",
                soft_wrap=True,
            )
            return {"status": "error", "message": str(e)}

        job_title, company_name = jd_manager.extract_job_meta(jd_path)
        source_url = jd_manager.extract_source_url(jd_path)

        # Stage 1: Liveness Gate
        if source_url and not skip_liveness:
            cli_art.detail(
                f"  Checking posting liveness for {company_name}...",
                level=cli_art.NORMAL,
            )
            try:
                liveness_res = liveness.verify_jd_paths([jd_path])
                if liveness_res.get("expired", 0) > 0:
                    cli_art.console.print(
                        f"  {theme.colorize_icon('error')} Posting expired or taken down. Moved to jds/expired/.",
                        soft_wrap=True,
                    )
                    return {
                        "status": "expired",
                        "job_key": job_key,
                        "company_name": company_name,
                        "job_title": job_title,
                        "source_url": source_url,
                        "reason": "Posting URL returned 404 or expired status.",
                    }
            except Exception as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} Liveness check encountered an issue: {e}. Proceeding...",
                    soft_wrap=True,
                )

        # Stage 2: Fit & Capability Gate
        evaluation = jd_manager.read_evaluation(jd_path)
        if not evaluation and not skip_fit:
            cli_art.detail(
                f"  Evaluating candidate-role fit for {company_name}...",
                level=cli_art.NORMAL,
            )
            try:
                evaluation = self.evaluate_fit(jd_path)
                if evaluation:
                    jd_manager.save_evaluation(jd_path, evaluation)
            except Exception as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} Fit evaluation skipped due to error: {e}",
                    soft_wrap=True,
                )

        if evaluation and evaluation.get("recommendation") == "Skip" and not force:
            archived_path = jd_manager.archive_jd(jd_path)
            cli_art.console.print(
                f"  {theme.colorize_icon('warning')} Fit score recommended 'Skip' ({evaluation.get('composite_score', '-')}/5). Moved to {archived_path}.",
                soft_wrap=True,
            )
            return {
                "status": "skipped",
                "job_key": job_key,
                "company_name": company_name,
                "job_title": job_title,
                "source_url": source_url,
                "evaluation": evaluation,
            }

        # Stage 3: Referral & ATS Classification
        if referral:
            jd_manager.save_referral(jd_path, referral)

        ats_classification = jd_manager.read_ats_classification(jd_path)
        if not ats_classification and source_url:
            ats_classification = scan_ats.classify_ats(source_url)
            if ats_classification:
                jd_manager.save_ats_classification(jd_path, ats_classification)

        # Stage 4: Tailored Resume
        cli_art.console.rule(
            f"[bold {theme.BRAND}]Generating Tailored Resume[/bold {theme.BRAND}]",
            style="dim",
        )
        resume_result = self.build_tailored_resume(
            jd_path=jd_path,
            master_resume=master_resume if master_resume is not None else {},
            output_filename=output_filename,
            job_key=job_key,
            interactive=interactive,
        )
        if not resume_result:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} Resume generation failed for {jd_path}.",
                soft_wrap=True,
            )
            return {"status": "error", "message": "Resume generation failed"}

        # Stage 5: Tailored Cover Letter
        cli_art.console.rule(
            f"[bold {theme.BRAND}]Generating Tailored Cover Letter[/bold {theme.BRAND}]",
            style="dim",
        )
        cl_result = self.build_tailored_coverletter(jd_path)
        if not cl_result:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} Cover letter generation failed for {jd_path}.",
                soft_wrap=True,
            )
            return {
                "status": "error",
                "message": "Cover letter generation failed",
                "resume": resume_result,
            }

        # Stage 6: Move to completed and record tracking
        output_paths = {
            "resume_pdf": resume_result.get("_output_paths", {}).get("pdf", ""),
            "resume_docx": resume_result.get("_output_paths", {}).get("docx", ""),
            "resume_json": resume_result.get("_output_paths", {}).get("json", ""),
            "resume_html": resume_result.get("_output_paths", {}).get("html", ""),
            "coverletter_pdf": cl_result.get("_output_paths", {}).get("pdf", ""),
            "coverletter_docx": cl_result.get("_output_paths", {}).get("docx", ""),
            "coverletter_json": cl_result.get("_output_paths", {}).get("json", ""),
            "coverletter_html": cl_result.get("_output_paths", {}).get("html", ""),
        }

        # Handle file movement to jds/completed/
        # Same as run_pipeline: move_jd_to never clobbers an existing file in
        # completed/ and re-syncs data.db's status. A failed move is reported
        # rather than swallowed -- the JD would otherwise stay pending silently.
        if os.path.exists(jd_path):
            try:
                jd_manager.move_jd_to(jd_path, jd_manager.COMPLETED_DIR)
            except OSError as e:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} Could not move JD to completed/: {e}",
                    soft_wrap=True,
                )

        tracker = jd_manager.JDTracker()
        tracker.mark_completed(
            job_key=job_key,
            job_title=job_title,
            company_name=company_name,
            source_file=os.path.basename(jd_path),
            output_json=output_paths.get("resume_json", ""),
            output_pdf=output_paths.get("resume_pdf", ""),
        )
        jd_manager.append_application_row(
            company_name=company_name,
            job_title=job_title,
            has_pdf=bool(os.path.exists(output_paths.get("resume_pdf", ""))),
            source_url=source_url,
            evaluation=evaluation,
        )
        try:
            import db

            db.checkpoint()
        except Exception:
            pass

        return {
            "status": "completed",
            "job_key": job_key,
            "company_name": company_name,
            "job_title": job_title,
            "source_url": source_url,
            "evaluation": evaluation,
            "ats_classification": ats_classification,
            "resume": resume_result,
            "coverletter": cl_result,
            "output_paths": output_paths,
        }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def append_console_transcript(log_path: str) -> None:
    """Appends the full recorded on-screen console output (everything
    cli_art printed, not just this module's curated checkpoint lines) to
    log_path, then clears the recording buffer for the next run.

    Best-effort -- a failure here shouldn't take down a build that
    otherwise completed successfully.
    """
    try:
        transcript = cli_art.console.export_text(clear=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 80 + "\n")
            f.write("FULL CONSOLE TRANSCRIPT\n")
            f.write("=" * 80 + "\n")
            f.write(transcript)
    except Exception:
        pass


def run_pipeline(jd_path=None, master_resume_path=None, output_filename=None):
    """Runs the tailor+render pipeline.

    jd_path=None means batch mode (every pending JD in jds/). Returns
    (completed_count, failed_count) rather than exiting, so callers other
    than the CLI (e.g. scripts/cli.py) can decide how to report failure.
    """
    kb_snapshot.snapshot_kb()

    logger = None
    log_path = None
    import db as _db  # local import: avoids a module-level cycle, matches

    # the existing lazy `import db` pattern used later in this function
    if not _db._is_unisolated_test_write():
        try:
            log_root = profile_paths.logs_dir()
            os.makedirs(log_root, exist_ok=True)
            timestamp = datetime.datetime.now().isoformat().replace(":", "-")
            log_path = os.path.join(log_root, f"pipeline_run_{timestamp}.log")
            logger = logging.getLogger("resume_pipeline")
            if logger.handlers:
                logger.handlers.clear()
            handler = logging.FileHandler(log_path, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.info("Pipeline run started")
            cli_art.console.export_text(clear=True)  # discard stale transcript
        except Exception as e:
            cli_art.detail(f"Could not initialize logging: {e}", level=cli_art.NORMAL)
            logger = None
            log_path = None

    master_resume = {}
    if master_resume_path:
        try:
            with open(master_resume_path, "r", encoding="utf-8") as f:
                master_resume = json.load(f)
            cli_art.print_literal(
                f"Loaded master resume from: {cli_art._escape_markup(master_resume_path)}"
            )
        except Exception as e:
            cli_art.console.print(
                f"{cli_art.WARNING} Could not load master resume: {e}. Proceeding with empty dict.",
                soft_wrap=True,
            )

    engine = ResumeEngine()
    tracker = jd_manager.JDTracker()

    if jd_path:
        jd_paths = [jd_path]
    else:
        jd_paths = jd_manager.get_pending_jds()
        if not jd_paths:
            cli_art.print_literal("\nNo pending JDs found in jds/. Nothing to do.")
            if logger:
                logger.info("No pending JDs found, exiting")
            return 0, 0

    if logger:
        logger.info(
            f"Processing {len(jd_paths)} JD(s): {', '.join(os.path.basename(p) for p in jd_paths[:5])}{'...' if len(jd_paths) > 5 else ''}"
        )

    completed_count = 0
    failed_count = 0
    aborted_remaining = 0

    for index, path in enumerate(jd_paths):
        try:
            job_key = jd_manager.compute_job_key(path)
        except OSError as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} Could not read JD file {path}: {e}",
                soft_wrap=True,
            )
            if logger:
                logger.warning(
                    f"[{index + 1}/{len(jd_paths)}] Could not read JD file {path}: {e}"
                )
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

        if logger:
            logger.info(
                f"[{index + 1}/{len(jd_paths)}] Starting: {job_title} at {company_name}"
            )

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
            if logger:
                logger.error(f"Sustained API failure for {job_key}: {e}")
            tracker.mark_failed(
                job_key=job_key,
                job_title=job_title,
                company_name=company_name,
                source_file=os.path.basename(path),
                error_message=str(e),
            )
            failed_count += 1
            aborted_remaining = len(jd_paths) - (index + 1)
            cli_art.console.print(
                f"\n  {theme.colorize_icon('error')} Sustained API failure -- stopping the batch.",
                soft_wrap=True,
            )
            cli_art.print_literal(f"    {cli_art._escape_markup(str(e))}")
            if aborted_remaining:
                cli_art.print_literal(
                    f"    {aborted_remaining} JD(s) left untouched; re-run to pick up where this stopped."
                )
            if logger:
                logger.info(
                    f"Pipeline stopped early: {aborted_remaining} JD(s) not attempted"
                )
            break
        except Exception as e:
            if logger:
                logger.error(f"Unhandled exception for {job_key}: {e}")
            result = None
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} Unhandled exception building resume for {path}: {e}",
                soft_wrap=True,
            )

        if result:
            output_paths = result.get("_output_paths", {})
            # move_jd_to, not shutil.move: it never clobbers a same-named
            # file already in completed/ and re-syncs data.db's status from
            # the new path, which a bare move left stale.
            jd_manager.move_jd_to(path, jd_manager.COMPLETED_DIR)
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
            if logger:
                logger.info(f"Successfully completed: {job_key}")
            cli_art.print_literal(
                f"\nDone! Resume built successfully for {cli_art._escape_markup(path)}"
            )
        else:
            if logger:
                logger.warning(f"Failed to build: {job_key}")
            tracker.mark_failed(
                job_key=job_key,
                job_title=job_title,
                company_name=company_name,
                source_file=os.path.basename(path),
                error_message="Resume build failed. Check output above for details.",
            )
            failed_count += 1
            cli_art.console.print(
                f"\n{cli_art.ERROR} Resume build failed for {path}. It stays pending and will be retried next run.",
                soft_wrap=True,
            )

    from rich.text import Text

    summary = Text("\nBatch summary: ")
    summary.append(str(completed_count))
    summary.append(" completed, ")
    summary.append(str(failed_count))
    summary.append(" failed.")
    if aborted_remaining:
        summary.append(
            f" Aborted early on sustained API failure -- {aborted_remaining} JD(s) not attempted."
        )
    cli_art.console.print(summary, soft_wrap=True)

    if logger:
        logger.info(
            f"Pipeline run complete: {completed_count} completed, {failed_count} failed"
        )
        if aborted_remaining:
            logger.info(
                f"Pipeline stopped early: {aborted_remaining} JD(s) not attempted"
            )

    if log_path:
        append_console_transcript(log_path)

    try:
        import db

        db.checkpoint()
    except Exception:
        pass  # best-effort (F6) -- a checkpoint failure shouldn't fail a
        # batch run that otherwise completed successfully

    return completed_count, failed_count


def run_application_package(
    jd_path=None,
    master_resume_path=None,
    output_filename=None,
    referral=None,
    force=False,
    skip_liveness=False,
    skip_fit=False,
):
    """
    Runs the full 4-artifact application package pipeline for a single JD or all pending JDs.
    Returns (completed_count, failed_count).
    """
    kb_snapshot.snapshot_kb()

    master_resume = {}
    if master_resume_path:
        try:
            with open(master_resume_path, "r", encoding="utf-8") as f:
                master_resume = json.load(f)
            cli_art.print_literal(
                f"Loaded master resume from: {cli_art._escape_markup(master_resume_path)}"
            )
        except Exception as e:
            cli_art.console.print(
                f"{cli_art.WARNING} Could not load master resume: {e}. Proceeding with empty dict.",
                soft_wrap=True,
            )

    engine = ResumeEngine()

    if jd_path:
        jd_paths = [jd_path]
    else:
        jd_paths = jd_manager.get_pending_jds()
        if not jd_paths:
            cli_art.print_literal("\nNo pending JDs found in jds/. Nothing to do.")
            return 0, 0

    completed_count = 0
    failed_count = 0

    for path in jd_paths:
        try:
            result = engine.build_application_package(
                jd_path=path,
                master_resume=master_resume,
                output_filename=output_filename if jd_path else None,
                referral=referral if jd_path else None,
                force=force,
                skip_liveness=skip_liveness,
                skip_fit=skip_fit,
                interactive=jd_path is not None,
            )
            if result and result.get("status") == "completed":
                completed_count += 1
                if hasattr(cli_art, "render_application_package_hud"):
                    cli_art.render_application_package_hud(result)
            elif result and result.get("status") in ("expired", "skipped"):
                pass
            else:
                failed_count += 1
        except SustainedFailureError:
            cli_art.console.print(
                f"\n  {theme.colorize_icon('error')} Sustained API failure -- stopping package batch.",
                soft_wrap=True,
            )
            failed_count += 1
            break
        except Exception as e:
            cli_art.console.print(
                f"  {theme.colorize_icon('error')} Unhandled exception packaging {path}: {e}",
                soft_wrap=True,
            )
            failed_count += 1

    return completed_count, failed_count


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Resume Builder Orchestrator")
    parser.add_argument(
        "jd",
        nargs="?",
        default=None,
        help="Path to a specific JD file. Omit to batch-process everything pending in jds/.",
    )
    parser.add_argument(
        "--master", default=None, help="Path to master resume JSON (optional)"
    )
    parser.add_argument(
        "--output", default=None, help="Output JSON filename (single-JD mode only)"
    )
    verbosity_group = parser.add_mutually_exclusive_group()
    verbosity_group.add_argument(
        "--verbose",
        action="store_true",
        help="Show implementation detail (cache/tier internals, token counts, model "
        "IDs, rule filenames) alongside normal step output. Same effect as "
        "RESUME_BUILDER_VERBOSITY=verbose, but overrides that env var.",
    )
    verbosity_group.add_argument(
        "--quiet",
        action="store_true",
        help="Show only errors, warnings and final results -- no step labels or "
        "cache hit/miss. Same effect as RESUME_BUILDER_VERBOSITY=quiet, but "
        "overrides that env var.",
    )
    args = parser.parse_args()

    if args.verbose:
        cli_art.set_verbosity(cli_art.VERBOSE)
    elif args.quiet:
        cli_art.set_verbosity(cli_art.QUIET)
    else:
        cli_art.set_verbosity(None)  # let RESUME_BUILDER_VERBOSITY decide

    completed_count, failed_count = run_pipeline(
        jd_path=args.jd,
        master_resume_path=args.master,
        output_filename=args.output,
    )

    if args.jd and failed_count and not completed_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
