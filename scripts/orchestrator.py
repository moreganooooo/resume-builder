import os
import time
import yaml
import json
import re
import random
import requests
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Tuple


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
# REWRITE_MODEL: gemma-4-31b-it — primary rewrite model for the audit loop.
#   Mirrors rewrite_bullets.py exactly. Has the largest free-tier daily quota
#   by a wide margin. The audit loop rewrites benefit from Gemma's richer
#   generation quality while critiques/scoring stay on Flash-Lite for strict
#   JSON compliance. GEMMA_MINIMAL_JSON=True means Gemma only has to produce
#   {"rewritten": "..."} — one key, much less drift.
#
# REWRITE_FALLBACK_MODEL: gemini-3.1-flash-lite — activated automatically
#   after MAX_REWRITE_PARSE_FAILURES consecutive parse failures on a single
#   bullet. Reliable JSON compliance as a safety net.
#
# BUILDER_MODEL: handles JD keyword extraction and the final resume assembly.
#   gemini-3.1-flash-lite for quota reasons. TemplateSchema is now flattened
#   (List[dict] instead of List[NestedModel]) to avoid the deeply-nested
#   $defs in responseSchema that caused the builder 400.
#
# EMBED_MODEL: gemini-embedding-2 (GA April 2026) — multimodal, 8k token input.
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

# When True, Gemma rewrites use a single-key schema {"rewritten": "..."}
# instead of the full 3-key schema. Mirrors rewrite_bullets.py's
# GEMMA_MINIMAL_JSON flag. Dramatically improves Gemma JSON compliance.
GEMMA_MINIMAL_JSON         = True
MAX_REWRITE_PARSE_FAILURES = 2


# --- TIMING CONSTANTS ---
CRITIQUE_SLEEP = 4    # seconds between critique calls (free-tier: 15 RPM)
REWRITE_SLEEP  = 4    # seconds before the rewrite call after a FAIL
RESCORE_SLEEP  = 8    # seconds before the re-score call after a rewrite
                      # (longer because rescore fires immediately after rewrite)


# --- PIPELINE CONSTANTS ---
TOP_K_BULLETS  = 20   # bullets mined from the bank per run
SEMANTIC_POOL  = 30   # semantic pre-filter pool size (Stage 1)
GEM_BOOST_WEIGHT = 0.15  # additive bonus per hidden_gem_score point above 0


# --- STRENGTH TIER SORT ORDER (Bug 4 fix) ---
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
# every run → maximises Google's implicit prompt-prefix caching hit rate.
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
# These files are the ONLY context the Skeptical Editor needs to ground
# truthfulness checks: who is this person, what facts are verified, what
# tools did they actually use, what projects are real.
# recruiter_memory_patterns.json is included to give the critique model the
# same recruiter-lens context that rewrite_bullets.py's score calls use,
# bringing believability scoring into full parity with the standalone script.
# Built once per run, shared across all bullet critique/rewrite calls.
# ~5-10k tokens vs ~457k for the full KB — eliminates the 429 on bullet 1.
AUDIT_KB_FILES = [
    "profile.yml",
    "verified_facts.json",
    "verified_tools.json",
    "verified_projects.json",
    "recruiter_memory_patterns.json",  # Gap 2: parity with rewrite_bullets.py scoring context
]

# --- AUDIT SEGMENT FILES ---
# Per-bullet context files loaded by _build_audit_segment_bundle().
# Mirrors rewrite_bullets.py's _build_segment_bundle() file list exactly.
# Loaded on-demand per (company, tags) pair — NOT pre-loaded into the static
# prefix — so token cost is zero for bullets that don't need enrichment.
# Only appended to rewrite_contents when a bullet fails critique; critique
# calls stay on the slim static_prefix to preserve cache efficiency.
AUDIT_SEGMENT_FILES = [
    "cv.md",
    "morgan-background-guide.md",
    "verified-claims.csv",
    "extracted-screenshot-metrics.csv",
    "verified_metrics.json",
]

# profile.yml sections to KEEP in the audit prefix (trimmed for token efficiency).
# Mirrors rewrite_bullets.py's trim_profile_yml() keep/stop lists.
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
# RETRY / BACKOFF CONSTANTS  (mirrors rewrite_bullets.py)
# ---------------------------------------------------------------------------
RETRYABLE          = {429, 500, 502, 503, 504}
SERVER_ERRORS      = {500, 502, 503, 504}
HIGH_DEMAND_STATUS = 503
BASE_BACKOFF_SECS  = 8
MAX_BACKOFF_SECS   = 90


# ---------------------------------------------------------------------------
# GEMINI CLIENT  (raw REST — avoids SDK versioning headaches on free tier)
# ---------------------------------------------------------------------------

class GeminiClient:
    """Thin wrapper around the Gemini v1beta REST API.

    Uses requests (not urllib) for cleaner error handling and resp.raise_for_status().
    Mirrors the battle-tested client from rewrite_bullets.py with:
      - jittered exponential backoff for 429 / 5xx
      - high-demand 503 special handling + logging
      - progressive fallback to gemini-3.1-flash-lite after 2 consecutive
        server failures on pro/Gemma models
      - finishReason guard (raises RuntimeError on SAFETY/RECITATION/UNKNOWN)
      - maxOutputTokens and serviceTier support
      - schema-bound calls frozen at temp=0.0 (no ramp-up on retries)
      - Gemma-aware: merges system_instruction into contents for Gemma models
        (Gemma models on the REST API don't support a top-level systemInstruction
        field — the contents payload handles it instead)
      - cached token count logging
    """

    _timeout = 90  # seconds

    @staticmethod
    def sanitize_schema(schema: dict) -> dict:
        """Remove JSON Schema keywords unsupported by Gemini's responseSchema."""
        UNSUPPORTED = {"title", "description", "$defs", "$schema", "default", "examples"}
        if not isinstance(schema, dict):
            return schema
        cleaned = {}
        for k, v in schema.items():
            if k in UNSUPPORTED:
                continue
            if isinstance(v, dict):
                cleaned[k] = GeminiClient.sanitize_schema(v)
            elif isinstance(v, list):
                cleaned[k] = [
                    GeminiClient.sanitize_schema(i) if isinstance(i, dict) else i
                    for i in v
                ]
            else:
                cleaned[k] = v
        return cleaned

    @staticmethod
    def parse_json(text: str) -> dict:
        """Strip <think> tokens, markdown fences, and parse JSON. Returns {} on failure."""
        if not text:
            return {}
        # Strip Gemma 4 thinking tokens before any other processing.
        # Safe no-op if the pattern is absent (i.e. all non-Gemma models).
        # Handles both </think> and <\/think> closing tag variants.
        cleaned = re.sub(r"<think>.*?(?:</think>|<\/think>)", "", text, flags=re.DOTALL).strip()
        if not cleaned:
            raise ValueError("parse_json: string was empty after stripping thinking tokens.")
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def generate(
        model: str,
        system_instruction: str,
        contents: str,
        response_schema=None,
        temperature: float = 0.0,
        max_retries: int = 6,
        max_output_tokens: int = None,
        service_tier: str = "standard",
    ) -> tuple[str | None, dict]:
        """
        Call generateContent and return (response_text, usage_metadata).
        Returns (None, {}) on any unrecoverable error after max_retries attempts.

        Key behaviors (mirrors rewrite_bullets.py's GeminiClient):
          - Schema-bound calls are frozen at temp=0.0 regardless of the
            temperature arg (prevents drifting toward non-JSON on retries).
          - Gemma models: system_instruction is merged into the contents
            payload (Gemma on the REST API doesn't support systemInstruction).
          - finishReason guard: raises RuntimeError on SAFETY/RECITATION/UNKNOWN.
          - 503 high-demand: logged distinctly, treated as transient.
          - Progressive fallback: after 2 consecutive server errors on a
            pro/Gemma model, auto-switches to REWRITE_FALLBACK_MODEL.
          - maxOutputTokens: caps generation length (great for tiny JSON tasks).
          - serviceTier: 'standard' | 'priority' | 'flex' (default: 'standard').
        """
        url = f"{BASE_URL}/{model}:generateContent?key={API_KEY}"

        valid_tiers = {"standard", "priority", "flex"}
        tier = (service_tier or "standard").strip().lower()
        if tier not in valid_tiers:
            raise ValueError(
                f"Invalid service_tier {service_tier!r}. Use one of {sorted(valid_tiers)}."
            )

        failure_streak = 0

        for attempt in range(max_retries):
            # Schema-bound calls: always temp=0.0 (never ramp up on retries).
            current_temp = 0.0 if response_schema is not None else temperature

            generation_config: dict = {"temperature": current_temp}
            if max_output_tokens is not None:
                generation_config["maxOutputTokens"] = int(max_output_tokens)

            raw_schema = None
            if response_schema is not None:
                generation_config["responseMimeType"] = "application/json"
                # Gemma models: skip responseSchema (rely on prompt discipline +
                # GEMMA_MINIMAL_JSON single-key contract instead).
                if "gemma" not in model.lower():
                    if hasattr(response_schema, "model_json_schema"):
                        raw_schema = response_schema.model_json_schema()
                    elif hasattr(response_schema, "schema") and callable(response_schema.schema):
                        raw_schema = response_schema.schema()
                    elif isinstance(response_schema, dict):
                        raw_schema = response_schema
                    elif isinstance(response_schema, str):
                        try:
                            raw_schema = json.loads(response_schema)
                        except json.JSONDecodeError:
                            print("ERROR: response_schema string is not valid JSON.")
                    else:
                        print(f"DEBUG: Schema passed but skipped. Unrecognized type {type(response_schema)}")

                if raw_schema:
                    generation_config["responseSchema"] = GeminiClient.sanitize_schema(raw_schema)

            # Gemma: merge system_instruction into contents (REST API requirement).
            if "gemma" in model.lower():
                merged_contents = f"{system_instruction}\n\n---\n{contents}"
                body = {
                    "contents": [{"role": "user", "parts": [{"text": merged_contents}]}],
                    "generationConfig": generation_config,
                    "serviceTier": tier,
                }
            else:
                body = {
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "contents": [{"role": "user", "parts": [{"text": contents}]}],
                    "generationConfig": generation_config,
                    "serviceTier": tier,
                }

            try:
                resp = requests.post(url, json=body, timeout=GeminiClient._timeout)
            except requests.exceptions.RequestException as e:
                failure_streak += 1
                # Progressive fallback after 2 consecutive transport failures
                # on pro/Gemma models (mirrors rewrite_bullets.py behavior).
                if (failure_streak >= 2
                        and model != REWRITE_FALLBACK_MODEL
                        and ("pro" in model.lower() or "gemma" in model.lower())):
                    print(f"    ⚠️  Consecutive transport failures — falling back from {model} to {REWRITE_FALLBACK_MODEL}...")
                    model = REWRITE_FALLBACK_MODEL
                    url = f"{BASE_URL}/{model}:generateContent?key={API_KEY}"
                    failure_streak = 0
                sleep_dur = min(BASE_BACKOFF_SECS * (2 ** attempt), MAX_BACKOFF_SECS) + random.uniform(1, 4)
                print(f"    ⚠️  Network error/timeout ({GeminiClient._timeout}s): {str(e).split()[-1].strip()}. "
                      f"Waiting {sleep_dur:.1f}s before retry {attempt+1}/{max_retries}...")
                time.sleep(sleep_dur)
                continue

            if resp.status_code in SERVER_ERRORS:
                failure_streak += 1
            elif resp.status_code == 429:
                failure_streak = max(failure_streak, 1)

            if resp.status_code == HIGH_DEMAND_STATUS:
                print("    ⚠️  Model is experiencing high demand (503). Treating as transient capacity issue.")

            if resp.status_code in RETRYABLE:
                # Progressive fallback after 2 consecutive server errors
                if (failure_streak >= 2
                        and model != REWRITE_FALLBACK_MODEL
                        and ("pro" in model.lower() or "gemma" in model.lower())):
                    print(f"    ⚠️  Consecutive server/transport failures — falling back from {model} to {REWRITE_FALLBACK_MODEL}...")
                    model = REWRITE_FALLBACK_MODEL
                    url = f"{BASE_URL}/{model}:generateContent?key={API_KEY}"
                    failure_streak = 0
                sleep_dur = min(BASE_BACKOFF_SECS * (2 ** attempt), MAX_BACKOFF_SECS) + random.uniform(1, 4)
                print(f"    ⚠️  HTTP {resp.status_code}. Waiting {sleep_dur:.1f}s before retry {attempt+1}/{max_retries}...")
                time.sleep(sleep_dur)
                continue

            # Don't retry permanent client errors (400, 404).
            if resp.status_code in (400, 404):
                print(f"    ⚠️  Gemini API permanent error {resp.status_code}: HTTP Error {resp.status_code}: {resp.reason}. Not retrying.")
                try:
                    err_detail = resp.json()
                    print(json.dumps(err_detail, indent=2)[:800])
                except Exception:
                    print(resp.text[:800])
                return None, {}

            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"    ⚠️  HTTP error {resp.status_code}: {e}. Not retrying.")
                return None, {}

            failure_streak = 0
            data = resp.json()
            usage = data.get("usageMetadata", {})

            cached = (usage.get("cachedContentTokenCount", 0) or 0) if usage else 0
            cache_str = f" cached {cached:,}" if cached > 0 else ""
            print(f"    tokens prompt {usage.get('promptTokenCount', '?')} "
                  f"output {usage.get('candidatesTokenCount', '?')} "
                  f"total {usage.get('totalTokenCount', '?')}{cache_str}")

            candidates = data.get("candidates", [])
            if not candidates:
                print("    ⚠️  No candidates in response.")
                return None, usage

            candidate = candidates[0]
            finish_reason = candidate.get("finishReason", "UNKNOWN")
            if finish_reason not in ("STOP", "MAX_TOKENS"):
                print(f"    ⚠️  Unexpected finishReason: {finish_reason}")
                print(json.dumps(data, indent=2)[:600])
                raise RuntimeError(
                    f"generate failed: unexpected finishReason={finish_reason} "
                    f"for model {model}."
                )

            text = (
                candidate.get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            return text, usage

        raise RuntimeError(f"generate failed after {max_retries} attempts for model {model}.")

    @staticmethod
    def embed(text: str) -> list[float] | None:
        """Embed a single text string. Returns a float list or None on error."""
        url = f"{BASE_URL}/{EMBED_MODEL}:embedContent?key={API_KEY}"
        payload = {
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBED_DIM,
        }
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json().get("embedding", {}).get("values")
        except Exception as e:
            print(f"    ⚠️  Embed error: {e}")
            return None


# ---------------------------------------------------------------------------
# PYDANTIC SCHEMAS
# ---------------------------------------------------------------------------

class BulletAuditSchema(BaseModel):
    action_taken:       str        = Field(description="The core objective action or task performed.")
    tools_used:         List[str]  = Field(description="Specific software, tools, or hard methodologies named.")
    metrics_claimed:    str        = Field(description="Any specific quantities, percentages, or numbers. Use 'None' if missing.")
    unsupported_claims: List[str]  = Field(description="List of generic fluff phrases, buzzwords, or unmeasurable claims.")

class WorkExperience(BaseModel):
    title:        str
    company:      str
    period:       str
    location:     str = Field(default="", description="City, State or 'Remote'. Leave blank if unknown.")
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
    """
    Mirrors the output contract in critique_bullet.md exactly.
    All 9 fields are required. hidden_gem_score and hidden_gem_flag unlock
    gem-aware prioritization in audit_and_refine_bullets — omitting them from
    the schema previously caused the responseSchema to strip them from the
    model's output, silently disabling the entire Hidden Gem scoring layer.
    """
    accuracy_score:     int  = Field(description="0-100: specific, grounded, traceable claim")
    believability_score:int  = Field(description="0-100: would a skeptical hiring manager believe this?")
    clarity_score:      int  = Field(description="0-100: immediately clear on first read")
    ats_value:          int  = Field(description="0-100: high-value ATS keywords without stuffing")
    hidden_gem_score:   int  = Field(description="0-100: memorability and evidence rarity — see critique_bullet.md")
    hidden_gem_flag:    bool = Field(description="true if hidden_gem_score >= 90")
    manager_test:       str  = Field(description="Strictly 'PASS' or 'FAIL'")
    weaknesses:         str  = Field(description="Specific explanation of flaws. 'None' if PASS with high scores.")
    hidden_gem_reason:  str  = Field(description="One sentence: what makes this a gem, or what holds it back")

class RewriteSchema(BaseModel):
    """Full 3-key schema — used by non-Gemma models (CRITIQUE_MODEL, REWRITE_FALLBACK_MODEL)."""
    original:  str
    rewritten: str
    reason:    str

class RewriteMinimalSchema(BaseModel):
    """Minimal 1-key schema — used by REWRITE_MODEL (Gemma). Mirrors rewrite_bullets.py's
    RewriteOutputMinimalSchema. One key = far less structural drift for instruct models."""
    rewritten: str

class ResumeCritiqueSchema(BaseModel):
    summary_alignment_score: int        = Field(description="0-100: does the Summary match the JD role and tone?")
    skills_relevance_score:  int        = Field(description="0-100: are Skills and Competencies JD-relevant?")
    overall_fit_score:       int        = Field(description="0-100: holistic resume-to-JD fit")
    flags:                   List[str]  = Field(description="Specific issues found, e.g. 'Summary mentions X but JD requires Y'")
    recommendations:         List[str]  = Field(description="Actionable fixes, one per flag")

class ProjectItem(BaseModel):
    title:       str  = Field(description="Project name.")
    badge:       str  = Field(default="", description="Short type label, e.g. 'Open Source', 'Featured', 'AI'. Leave blank if none.")
    description: str  = Field(description="1-2 sentence impact summary.")
    tech:        str  = Field(default="", description="Comma-separated tech stack. Leave blank if not applicable.")

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

    EXPERIENCE / PROJECTS / EDUCATION / CERTIFICATIONS are List[dict] instead
    of List[NestedModel]. This eliminates the deeply-nested $defs structure that
    Gemini's responseSchema validation rejects with a 400 on gemini-3.1-flash-lite.
    The standalone Pydantic classes (WorkExperience, ProjectItem, CertItem,
    EducationItem) are kept intact above for use by render_pdf and other consumers.

    Contract details are enforced via description strings rather than nested
    schemas — the model receives the same field-level guidance without the
    schema complexity.
    """
    NAME:                str        = Field(description="Must match candidate name.")
    TAGLINE:             str        = Field(description="Max 80 chars. Follows archetype tagging rules.")
    PHONE:               str
    EMAIL:               str
    LINKEDIN_URL:        str
    LINKEDIN_DISPLAY:    str
    PORTFOLIO_URL:       str
    PORTFOLIO_DISPLAY:   str
    LOCATION:            str
    SECTION_SUMMARY:     str        = Field(default="Professional Summary")
    SUMMARY_TEXT:        str        = Field(description="Max 5 lines. First sentence MUST be bolded using <strong> tags. No generic filler.")
    SECTION_COMPETENCIES:str        = Field(default="Core Competencies")
    COMPETENCIES:        List[str]  = Field(min_length=6, max_length=8, description="6-8 exact keywords extracted from JD requirements.")
    SECTION_EXPERIENCE:  str        = Field(default="Work Experience")
    EXPERIENCE:          List[dict] = Field(
        description=(
            "List of work experience objects. Each dict must contain: "
            "title (str), company (str), period (str), location (str, city/state or Remote), "
            "achievements (list of str — bulleted accomplishments that pass Jobright QA heuristics). "
            "Bullet counts per role must match tailor.md targets exactly: "
            "Mercor 2-3, Treering 6-8, Inside Sales Team 4-5, "
            "Element 8/Strategy LLC 3-4, VML 3-4, Callahan Creek 3-4."
        )
    )
    SECTION_PROJECTS:    str        = Field(default="Projects")
    PROJECTS:            List[dict] = Field(
        min_length=3, max_length=4,
        description=(
            "Top 3-4 most relevant projects. Each dict must contain: "
            "title (str), badge (str, short label e.g. 'Open Source' — leave blank if none), "
            "description (str, 1-2 sentence impact summary), "
            "tech (str, comma-separated tech stack — leave blank if not applicable)."
        )
    )
    SECTION_EDUCATION:   str        = Field(default="Education")
    EDUCATION:           List[dict] = Field(
        description=(
            "KU, KCKCC, and JCCC items exactly as per design system. Each dict must contain: "
            "degree (str), institution (str), year (str), description (str — honors, GPA, coursework). "
            "KU: exactly 2 bullets. KCKCC: exactly 2 bullets. JCCC: exactly 1 bullet."
        )
    )
    SECTION_CERTIFICATIONS: str     = Field(default="Training & Certifications")
    CERTIFICATIONS:      List[dict] = Field(
        min_length=3, max_length=3,
        description=(
            "Exactly 3 certifications in fixed order. Each dict must contain: "
            "title (str, bold name only), org (str), year (str). "
            "Order: 1) Email Marketing Software Certification | HubSpot | 2026, "
            "2) Video for Sales Certification | Vidyard | 2021, "
            "3) Camp Portfolio | Bernstein Rein, Kansas City | 2008."
        )
    )
    SECTION_SKILLS:      str        = Field(default="Skills")
    SKILLS:              List[str]  = Field(description="Technical skills mapped to JD.")


# ---------------------------------------------------------------------------
# RESUME ENGINE
# ---------------------------------------------------------------------------

class ResumeEngine:

    def __init__(self):
        self.engine_dir   = os.path.join(PROJECT_ROOT, "resume-engine")
        self.prompts_dir  = os.path.join(self.engine_dir, "prompts")
        self.rules_dir    = os.path.join(self.engine_dir, "rules")
        self.scoring_dir  = os.path.join(self.engine_dir, "scoring")
        self.kb_dir       = os.path.join(self.engine_dir, "knowledge_base")
        self.templates_dir= os.path.join(self.engine_dir, "templates")
        self.output_json_dir = os.path.join(PROJECT_ROOT, "output", "json")
        self.jds_dir      = os.path.join(PROJECT_ROOT, "jds")

        # FIX #6: Ensure output/json/ exists at engine init time.
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
            return "Process the text."  # Fallback prompt

    def load_knowledge_base(self):
        """
        Stitches allowlisted KB files into a single static context string.

        ALLOWLIST: Only files in KB_ALLOWLIST (defined at module level) are loaded.
        IMPLICIT CACHING: KB_ALLOWLIST is pre-sorted so the output is
        byte-for-byte identical across every run. Google's infrastructure caches
        prompt prefixes that match exactly — a single character difference breaks
        the cache hit. Sorted order guarantees the prefix never drifts.

        This context block is placed at the TOP of every payload so it forms the
        cacheable prefix. The variable content (JD, bullets) is always appended
        AFTER it. To add a new file to the builder's context, add it to
        KB_ALLOWLIST in sorted order at the top of this module.
        """
        master_context = "=== SYSTEM KNOWLEDGE BASE ===\n\n"
        if os.path.exists(self.kb_dir):
            for filename in KB_ALLOWLIST:
                filepath = os.path.join(self.kb_dir, filename)
                if not os.path.exists(filepath):
                    print(f"  ⚠️  KB allowlist entry not found, skipping: {filename}")
                    continue
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        master_context += f"--- START OF {filename} ---\n{f.read()}\n--- END OF {filename} ---\n\n"
                except Exception as e:
                    print(f"  ⚠️  Could not load KB file {filename}: {e}")
        return master_context

    def build_audit_static_prefix(self) -> str:
        """
        Builds the slim Tier-1 context prefix for the audit loop.

        Mirrors rewrite_bullets.py's _build_static_prefix() exactly:
          - profile.yml (trimmed to target_roles / narrative / superpowers /
            background_context / deal_breakers — same keep/stop lists as
            rewrite_bullets.py's trim_profile_yml())
          - verified_facts.json
          - verified_tools.json
          - verified_projects.json
          - recruiter_memory_patterns.json (Gap 2: parity with rewrite_bullets.py)

        This is the ONLY context the Skeptical Editor needs to ground
        truthfulness checks. ~5-10k tokens vs ~457k for the full KB.
        Built once per run, shared across all bullet critique/rewrite calls.

        THREE-TIER ARCHITECTURE (matches rewrite_bullets.py):
          Tier 0 — system_instruction: rules only (critique/rewrite prompts
                   + scoring yamls). Compact, stable. No KB here.
          Tier 1 — contents prefix: this method's output. Stable across all
                   bullet calls → Google can cache-hit the prefix.
          Tier 2 — contents tail: bullet text + weaknesses. Only part that
                   varies per call.
        """
        sections = []

        # --- profile.yml (trimmed) ---
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
                print(f"  ⚠️  build_audit_static_prefix: could not load profile.yml: {e}")

        # --- verified_facts.json ---
        facts_path = os.path.join(self.kb_dir, "verified_facts.json")
        if os.path.exists(facts_path):
            try:
                with open(facts_path, "r", encoding="utf-8") as f:
                    facts = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                sections.append(
                    "=== VERIFIED FACTS (high-confidence claims — use freely) ===\n"
                    "These are the only facts about Morgan's career that are evidence-backed.\n"
                    "Do NOT invent facts outside this list.\n"
                    + facts
                )
            except Exception as e:
                print(f"  ⚠️  build_audit_static_prefix: could not load verified_facts.json: {e}")

        # --- verified_tools.json ---
        tools_path = os.path.join(self.kb_dir, "verified_tools.json")
        if os.path.exists(tools_path):
            try:
                with open(tools_path, "r", encoding="utf-8") as f:
                    tools = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                sections.append(
                    "=== VERIFIED TOOLS (HF002 guard — only claim tools listed here) ===\n"
                    "Never claim proficiency with any tool not present in this list.\n"
                    + tools
                )
            except Exception as e:
                print(f"  ⚠️  build_audit_static_prefix: could not load verified_tools.json: {e}")

        # --- verified_projects.json ---
        projects_path = os.path.join(self.kb_dir, "verified_projects.json")
        if os.path.exists(projects_path):
            try:
                with open(projects_path, "r", encoding="utf-8") as f:
                    projects = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                sections.append(
                    "=== VERIFIED PROJECTS ===\n"
                    "Use these to add accurate project detail and scope.\n"
                    + projects
                )
            except Exception as e:
                print(f"  ⚠️  build_audit_static_prefix: could not load verified_projects.json: {e}")

        # --- recruiter_memory_patterns.json (Gap 2) ---
        recruiter_path = os.path.join(self.kb_dir, "recruiter_memory_patterns.json")
        if os.path.exists(recruiter_path):
            try:
                with open(recruiter_path, "r", encoding="utf-8") as f:
                    recruiter = json.dumps(json.load(f), ensure_ascii=False, separators=(",", ":"))
                sections.append(
                    "=== RECRUITER MEMORY PATTERNS (believability lens) ===\n"
                    "Use these patterns to judge whether claims will land with skeptical hiring managers.\n"
                    + recruiter
                )
            except Exception as e:
                print(f"  ⚠️  build_audit_static_prefix: could not load recruiter_memory_patterns.json: {e}")

        return "\n\n".join(sections)

    def _build_audit_segment_bundle(self, company: str, tags: str) -> str:
        """
        Builds a per-bullet context bundle for the rewrite call.

        Mirrors rewrite_bullets.py's _build_segment_bundle() exactly. Loads
        the AUDIT_SEGMENT_FILES and filters them to content relevant to the
        bullet's company and tags. This gives Gemma the same CV section
        excerpts, background summaries, and Treering claim evidence that the
        standalone script has always had — closing Gap 3.

        Called only when a bullet fails critique (i.e. only for rewrites).
        Critiques stay on the slim static_prefix to preserve cache efficiency.

        Args:
            company: The 'Role / Company' value from the bullet bank CSV row,
                     e.g. 'Senior Marketing Manager / Treering'.
            tags:    The 'Tags' value from the bullet bank CSV row,
                     e.g. 'treering, data, automation'.

        Returns:
            A formatted string prepended to rewrite_contents, or "" if all
            segment files are missing (safe no-op).
        """
        company_lower = company.lower() if company else ""
        tags_lower    = tags.lower()    if tags    else ""
        combined_key  = f"{company_lower} {tags_lower}"

        sections = []

        for filename in AUDIT_SEGMENT_FILES:
            filepath = os.path.join(self.kb_dir, filename)
            if not os.path.exists(filepath):
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    raw = f.read()

                # For cv.md and morgan-background-guide.md: extract sections
                # that mention the company name or any of the tags. This avoids
                # dumping the entire file and keeps the bundle lean.
                if filename in ("cv.md", "morgan-background-guide.md"):
                    lines = raw.splitlines()
                    relevant = []
                    in_relevant_section = False
                    for line in lines:
                        line_lower = line.lower()
                        # Section headers that mention the company or tags start
                        # a relevant block; blank lines end it.
                        if line.startswith("#") or line.startswith("##"):
                            in_relevant_section = any(
                                kw in line_lower for kw in combined_key.split()
                                if len(kw) > 3
                            )
                        if in_relevant_section:
                            relevant.append(line)
                    content = "\n".join(relevant).strip() if relevant else ""
                    # If no targeted section found, include the full file —
                    # better to over-supply than leave Gemma without context.
                    if not content:
                        content = raw.strip()
                else:
                    # For CSVs and JSON: include as-is (already compact).
                    content = raw.strip()

                if content:
                    sections.append(
                        f"--- {filename} ---\n{content}"
                    )
            except Exception as e:
                print(f"  ⚠️  _build_audit_segment_bundle: could not load {filename}: {e}")

        if not sections:
            return ""

        header = (
            f"=== SEGMENT CONTEXT (company: {company or 'unknown'} | tags: {tags or 'none'}) ===\n"
            "Use the evidence below to strengthen the rewrite with accurate, specific claims.\n"
        )
        return header + "\n\n".join(sections)

    @staticmethod
    def critique_composite(scores: dict) -> float:
        """
        Compute a composite quality score for best_version comparisons.
        Mirrors rewrite_bullets.py best_version: sums the four numeric dimensions
        and adds a 10-point bonus for a PASS manager_test so that a rewrite that
        improves scores but introduces a FAIL doesn't win.
        """
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
        Passes bullets through the Critique and Rewrite prompts.

        Accepts List[Tuple[str, str, str]] — (bullet_text, company, tags) —
        as returned by mine_bullet_bank(). The company and tags fields are used
        to build a per-bullet segment bundle (Gap 3) that is prepended to
        rewrite_contents only. Critique calls stay on the slim static_prefix
        to preserve cache efficiency across all bullet calls.

        MODEL STRATEGY (mirrors rewrite_bullets.py):
          - Critiques: CRITIQUE_MODEL (gemini-3.1-flash-lite) — strict JSON,
            9-field schema, consistent scoring behavior.
          - Rewrites: REWRITE_MODEL (gemma-4-31b-it) — richer generation quality,
            minimal 1-key schema (GEMMA_MINIMAL_JSON=True), temp=0.0.
          - Rewrite fallback: REWRITE_FALLBACK_MODEL (gemini-3.1-flash-lite) —
            auto-activates after MAX_REWRITE_PARSE_FAILURES consecutive parse
            failures on a single bullet.

        THREE-TIER CACHE ARCHITECTURE (mirrors rewrite_bullets.py):
          Tier 0 — system_instruction: rules ONLY (critique/rewrite prompts +
            scoring yamls). Compact and stable. No KB context here.
          Tier 1 — contents prefix (static_prefix arg): slim verified-facts
            bundle built by build_audit_static_prefix(). ~5-10k tokens,
            identical across all bullet calls → Google can cache-hit the prefix.
          Tier 2 — contents tail: bullet text (+ weaknesses + segment bundle
            for rewrites). The ONLY part that varies per call.

        Hidden Gem awareness: bullets with hidden_gem_flag=True are logged with a
        marker and their hidden_gem_reason so you can see which gems made it into
        the final pool.

        best_version guard: when a rewrite is triggered, the rewrite is re-scored
        via a second critique call so we can compare its composite against the
        original. If the original scores higher, it is kept.
        """
        print("Starting the Skeptical Editor Audit Loop...")
        print(f"  Critique model: {CRITIQUE_MODEL}")
        print(f"  Rewrite model:  {REWRITE_MODEL}  (fallback: {REWRITE_FALLBACK_MODEL})")
        print(f"  static_prefix size: {len(static_prefix)} chars / ~{len(static_prefix)//4} tokens")

        if not isinstance(bullet_tuples, list) or len(bullet_tuples) == 0:
            print("  No bullets to audit — empty or invalid input. Skipping audit loop.")
            return []

        critique_prompt = self.load_prompt("critique_bullet.md")
        rewrite_prompt  = self.load_prompt("rewrite_bullet.md")
        manager_test_rules  = json.dumps(self.load_yaml(self.scoring_dir, "manager_test.yaml"))
        believability_rules = json.dumps(self.load_yaml(self.scoring_dir, "believability.yaml"))
        style_rules         = json.dumps(self.load_yaml(self.rules_dir,   "style_rules.yaml"))
        language_quality    = json.dumps(self.load_yaml(self.rules_dir,   "language_quality.yaml"))
        verb_taxonomy       = json.dumps(self.load_yaml(self.rules_dir,   "verb_taxonomy.yaml"))
        verb_intent_mapping = json.dumps(self.load_yaml(self.rules_dir,   "verb_intent_mapping.yaml"))
        hard_failures       = json.dumps(self.load_yaml(self.rules_dir,   "hard_failures.yaml"))
        truthfulness_rules  = json.dumps(self.load_yaml(self.rules_dir,   "truthfulness_rules.yaml"))
        ats_rules           = json.dumps(self.load_yaml(self.rules_dir,   "ats_rules.yaml"))

        # Tier 0: system_instruction = rules ONLY. No KB context here.
        critique_system = (
            f"{critique_prompt}"
            f"\n\nMANAGER TEST RULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
            f"\n\nHARD FAILURES (any of these = automatic FAIL):\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nATS RULES:\n{ats_rules}"
        )

        rewrite_system = (
            f"{rewrite_prompt}"
            f"\n\nSTYLE RULES:\n{style_rules}"
            f"\n\nINTENT MAP:\n{verb_intent_mapping}"
            f"\n\nTAXONOMY:\n{verb_taxonomy}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nHARD FAILURES:\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
        )

        print(f"  critique_system size: {len(critique_system)} chars / ~{len(critique_system)//4} tokens")
        print(f"  rewrite_system size:  {len(rewrite_system)} chars / ~{len(rewrite_system)//4} tokens")

        refined_bullets = []
        for i, (bullet, company, tags) in enumerate(bullet_tuples):
            print(f"\n  Analyzing bullet {i+1}/{len(bullet_tuples)}...")
            if i > 0:
                time.sleep(CRITIQUE_SLEEP)

            # Tier 1 + Tier 2: stable prefix first, bullet tail appended after.
            # static_prefix is identical for every bullet → cache-hit on calls 2-20.
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
                # Log cache hits if present
                cached_tokens = usage.get("cachedContentTokenCount", 0) if usage else 0
                if cached_tokens:
                    print(f"    💫 cached tokens: {cached_tokens:,}")

                if not critique_text:
                    refined_bullets.append(bullet)
                    continue

                critique_data = GeminiClient.parse_json(critique_text)

                # Log hidden gem flags
                gem_score  = critique_data.get("hidden_gem_score", 0)
                gem_flag   = critique_data.get("hidden_gem_flag", False)
                gem_reason = critique_data.get("hidden_gem_reason", "")
                if gem_flag:
                    print(f"    💎 Hidden Gem! score={gem_score} — {gem_reason}")
                elif gem_score >= 75:
                    print(f"    ✨ Strong bullet gem_score={gem_score} — {gem_reason}")

                if (critique_data.get("manager_test") == "FAIL" or
                        critique_data.get("believability_score", 100) < 80):
                    print(f"    Bullet failed Manager Test or believability threshold. Rewriting with {REWRITE_MODEL}...")
                    time.sleep(REWRITE_SLEEP)

                    # Gap 3: build segment bundle for this bullet's company/tags.
                    # Only loaded here (rewrite path) — critiques stay lean.
                    segment_bundle = self._build_audit_segment_bundle(company, tags)
                    if segment_bundle:
                        print(f"    📦 segment bundle: {len(segment_bundle)} chars / ~{len(segment_bundle)//4} tokens")

                    # Schema + prompt selection: Gemma uses minimal 1-key schema.
                    # Mirrors rewrite_bullets.py's per-attempt schema switching.
                    active_rewrite_model = REWRITE_MODEL
                    rewrite_parse_failures = 0
                    rewritten_bullet = bullet  # safe fallback

                    for rw_attempt in range(MAX_REWRITE_PARSE_FAILURES + 1):
                        use_minimal = GEMMA_MINIMAL_JSON and "gemma" in active_rewrite_model.lower()
                        runner_schema = RewriteMinimalSchema if use_minimal else RewriteSchema

                        weaknesses = critique_data.get("weaknesses", "")
                        # Tier 2 for rewrites: static_prefix + segment bundle
                        # + bullet + weaknesses. Segment bundle is the Gap 3 addition.
                        rewrite_contents = (
                            f"{static_prefix}\n\n"
                            + (f"{segment_bundle}\n\n" if segment_bundle else "")
                            + f"--- BULLET TO REWRITE ---\n{bullet}\n\n"
                            f"--- WEAKNESSES TO FIX ---\n{weaknesses}"
                        )

                        try:
                            rewrite_text, rw_usage = GeminiClient.generate(
                                model=active_rewrite_model,
                                system_instruction=rewrite_system,
                                contents=rewrite_contents,
                                response_schema=runner_schema,
                                temperature=0.0,
                                max_output_tokens=160,
                            )
                            rw_cached = rw_usage.get("cachedContentTokenCount", 0) if rw_usage else 0
                            if rw_cached:
                                print(f"    💫 rewrite cached tokens: {rw_cached:,}")

                            if not rewrite_text:
                                raise ValueError("Empty rewrite response")

                            rw_data = GeminiClient.parse_json(rewrite_text)
                            candidate_bullet = rw_data.get("rewritten", "").strip()

                            if not candidate_bullet:
                                raise ValueError("Empty rewritten field in response")

                            # best_version guard: rescore the rewrite and keep
                            # whichever version has the higher composite.
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
                            original_composite = ResumeEngine.critique_composite(critique_data)
                            rewrite_composite  = ResumeEngine.critique_composite(rescore_data)

                            if rewrite_composite >= original_composite:
                                rewritten_bullet = candidate_bullet
                                print(f"    ✅ Rewrite accepted (composite {rewrite_composite:.0f} >= {original_composite:.0f})")
                            else:
                                rewritten_bullet = bullet
                                print(f"    ↩️  Original kept (composite {original_composite:.0f} > {rewrite_composite:.0f})")
                            break

                        except Exception as rw_err:
                            rewrite_parse_failures += 1
                            print(f"    ⚠️  Rewrite parse error (attempt {rw_attempt+1}): {rw_err}")
                            if (rewrite_parse_failures >= MAX_REWRITE_PARSE_FAILURES
                                    and active_rewrite_model != REWRITE_FALLBACK_MODEL):
                                print(f"    🔄 Switching rewrite to fallback: {REWRITE_FALLBACK_MODEL}")
                                active_rewrite_model = REWRITE_FALLBACK_MODEL
                            time.sleep(REWRITE_SLEEP)

                    refined_bullets.append(rewritten_bullet)
                else:
                    refined_bullets.append(bullet)

            except Exception as e:
                print(f"    ⚠️  Critique error on bullet {i+1}: {e}")
                refined_bullets.append(bullet)

        print(f"\nAudit complete.")
        return refined_bullets

    def mine_bullet_bank(self, jd_text: str, master_resume: dict) -> List[Tuple[str, str, str]]:
        """
        Semantic + gem-aware retrieval from bullet-bank-keepers-audited.c