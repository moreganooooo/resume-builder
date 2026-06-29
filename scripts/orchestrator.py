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
   