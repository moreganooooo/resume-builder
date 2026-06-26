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
# CRITIQUE_MODEL: handles bullet critique + rewrite (high-frequency) and the
#   post-build holistic resume critique. gemini-3.1-flash-lite gives the best
#   free-tier headroom (15 RPM / 500 RPD) while reliably following JSON instructions.
#
# BUILDER_MODEL: handles JD keyword extraction and the final resume assembly call.
#   Also gemini-3.1-flash-lite for the same quota reasons.
#
# EMBED_MODEL: gemini-embedding-2 (GA April 2026) — multimodal, 8k token input.
#   Used ONLY for the one-time offline bullet bank pre-embedding (embed_bullet_bank.py)
#   and for the single JD embedding at runtime in mine_bullet_bank().
#   Output dimensionality set to 768 — sweet spot for text-only RAG tasks.
CRITIQUE_MODEL = "gemini-3.1-flash-lite"
BUILDER_MODEL  = "gemini-3.1-flash-lite"
EMBED_MODEL    = "gemini-embedding-2"
EMBED_DIM      = 768

# CRITIQUE_SLEEP: pause between bullets WHEN no rewrite is triggered (seconds).
# A single critique call fires one API call. 25s keeps worst-case rate well
# under the free-tier ceiling even across a full TOP_K_BULLETS run.
CRITIQUE_SLEEP = 25

# REWRITE_SLEEP: pause between the critique call and the rewrite call on the
# SAME bullet when a rewrite IS triggered (seconds). Mirrors rewrite_bullets.py
# SLEEP_ON_RETRY=8 — safe for back-to-back calls on flash-lite, and means PASS
# bullets advance in CRITIQUE_SLEEP instead of waiting CRITIQUE_SLEEP twice.
REWRITE_SLEEP = 8

# TOP_K_BULLETS: candidate pool sent into the audit loop.
# The builder selects ~10 bullets for the final resume from this pool.
# 12 is enough headroom without blowing the free-tier RPD budget.
TOP_K_BULLETS = 12

# Semantic pre-filter pool size: top-N bullets by cosine similarity passed to the
# keyword re-ranker. 30 gives a wide enough net without keyword scoring noise.
SEMANTIC_POOL = 30


# ==========================================
# THIN REST CLIENT (replaces google-genai SDK)
# Needed because SDK 2.9.0 doesn't support AQ key format
# ==========================================


class GeminiClient:
    """Minimal REST wrapper around the Gemini generateContent and embedContent endpoints."""

    def __init__(self, api_key: str = None, timeout: int = 180):
        self.api_key = api_key or API_KEY
        if not self.api_key:
            raise ValueError("API key not found. Set GEMINI_API_KEY or GOOGLE_API_KEY.")
        self.timeout = timeout

    @staticmethod
    def _sanitize_schema(schema: dict) -> dict:
        """Strips Pydantic keys and capitalizes Enums for the REST API."""
        if not isinstance(schema, dict):
            return schema
            
        clean = {}
        for k, v in schema.items():
            if k in ("title", "default", "$defs"):
                continue
            if k == "type" and isinstance(v, str):
                clean[k] = v.upper()
            elif isinstance(v, dict):
                clean[k] = GeminiClient._sanitize_schema(v)
            elif isinstance(v, list):
                clean[k] = [GeminiClient._sanitize_schema(i) if isinstance(i, dict) else i for i in v]
            else:
                clean[k] = v
        return clean
    
    @staticmethod
    def parse_json(text: str) -> dict:
        """Strip markdown fencing and parse JSON. Falls back to regex extraction.

        Pre-processing step: Gemma 4 models may emit <|think|> ... </|think|>
        or <|think|> ... <|/think|> reasoning blocks before their actual response.
        This strip is a no-op for Gemini models that never produce these tokens.
        """
        if not text or not text.strip():
            raise ValueError("parse_json received an empty string — the model returned no content.")

        cleaned = re.sub(
            r"<\|think\|>.*?(?:</\|think\|>|<\|/think\|>)",
            "",
            text,
            flags=re.DOTALL,
        ).strip()

        if not cleaned:
            raise ValueError("parse_json: string was empty after stripping thinking tokens.")

        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        preview = cleaned[:300].replace("\n", " ")
        raise ValueError(
            f"JSON parse failed — could not extract valid JSON.\nRaw preview: {preview!r}"
        )

    def embed(self, text: str, max_retries: int = 4) -> list:
        """Call gemini-embedding-2 embedContent. Returns a flat list of floats.

        Uses EMBED_DIM=768 — the sweet spot for text-only semantic search.
        Retries with exponential backoff on 429s, same pattern as generate().
        """
        url = f"{BASE_URL}/{EMBED_MODEL}:embedContent?key={self.api_key}"
        body = {
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBED_DIM,
        }
        for attempt in range(max_retries):
            resp = requests.post(url, json=body, timeout=self.timeout)
            if resp.status_code in (429, 500, 502, 503, 504):
                wait = 5 * (2 ** attempt)
                print(f"         ⏳ Transient API error {resp.status_code}. Waiting {wait}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["embedding"]["values"]
        # Final attempt
        resp = requests.post(url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()["embedding"]["values"]

    def generate(
        self,
        model: str,
        system_instruction: str,
        contents: str,
        response_schema: type = None,
        temperature: float = 0.1,
        max_retries: int = 6,
        max_output_tokens: int = None,
        service_tier: str = "standard",
    ) -> Tuple[str, dict]:
        """Call generateContent and return (text, usage_metadata).

        usage_metadata keys (all int, 0 if absent):
            promptTokenCount, candidatesTokenCount, totalTokenCount,
            cachedContentTokenCount

        Callers that only need the text can unpack with:
            text, _ = client.generate(...)
        """
        url = f"{BASE_URL}/{model}:generateContent?key={self.api_key}"

        RETRYABLE = (429, 500, 502, 503, 504)
        SERVER_ERRORS = (500, 502, 503, 504)
        HIGH_DEMAND_STATUS = 503
        BASE_BACKOFF_SECONDS = 8
        MAX_BACKOFF_SECONDS = 90

        # finishReasons that mean we have a usable response.
        GOOD_FINISH_REASONS = {"STOP", "MAX_TOKENS"}

        fallback_model = "gemini-3.1-flash-lite"
        failure_streak = 0

        valid_tiers = {"standard", "priority", "flex"}
        tier = (service_tier or "standard").strip().lower()
        if tier not in valid_tiers:
            raise ValueError(f"Invalid service_tier={service_tier!r}. Use one of {sorted(valid_tiers)}.")

        for attempt in range(max_retries):
            # FIX: Gemma constrained decoding — temperature is honoured for Gemma
            # when a schema is passed (the old code forced 0.0 for all schema calls,
            # which is fine for scoring but hurts creativity on rewrites).
            # We keep 0.0 only for non-Gemma schema calls to preserve exact behaviour
            # for flash-lite scoring.
            is_gemma = "gemma" in model.lower()
            if response_schema is not None and not is_gemma:
                current_temp = 0.0
            else:
                current_temp = temperature

            generation_config = {
                "temperature": current_temp,
            }

            if max_output_tokens is not None:
                generation_config["maxOutputTokens"] = int(max_output_tokens)

            if response_schema is not None:
                generation_config["responseMimeType"] = "application/json"

            # FIX A: responseSchema is now sent for ALL models, including Gemma.
            # Previously guarded by `and "gemma" not in model.lower()` which meant
            # Gemma only got responseMimeType (soft hint) but no structural schema
            # enforcement — letting it free-form echo the prompt instead of producing JSON.
            # gemma-4-31b-it on v1beta supports responseSchema constrained decoding.
            raw_schema = None
            if response_schema is not None:
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
                        print(" ⚠️ ERROR: response_schema string is not valid JSON.")

                if raw_schema:
                    generation_config["responseSchema"] = GeminiClient._sanitize_schema(raw_schema)
                else:
                    print(f" ⚠️ DEBUG: Schema was passed but skipped. Unrecognized type: {type(response_schema)}")

            if is_gemma:
                merged_contents = f"{system_instruction}\n\n---\n\n{contents}"
                body = {
                    "contents": [{"role": "user", "parts": [{"text": merged_contents}]}],
                    "generationConfig": generation_config,
                    "service_tier": tier,
                }
            else:
                body = {
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "contents": [{"role": "user", "parts": [{"text": contents}]}],
                    "generationConfig": generation_config,
                    "service_tier": tier,
                }

            try:
                resp = requests.post(url, json=body, timeout=self.timeout)
            except requests.exceptions.RequestException as e:
                failure_streak += 1
                print(f" ⚠️ Network error/Timeout ({self.timeout}s): {str(e).split(':')[-1].strip()}")

                if failure_streak >= 2 and model != fallback_model and ("pro" in model.lower() or "gemma" in model.lower()):
                    print(f" 🔄 Consecutive transport failures: falling back from {model} to {fallback_model}...")
                    model = fallback_model
                    url = f"{BASE_URL}/{model}:generateContent?key={self.api_key}"
                    failure_streak = 0

                sleep_duration = min(BASE_BACKOFF_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS) + random.uniform(1, 4)
                print(f" ⏳ Network spike. Waiting {sleep_duration:.1f}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(sleep_duration)
                continue

            if resp.status_code in RETRYABLE:
                print(f"\n===== HTTP {resp.status_code} RESPONSE BODY =====")
                try:
                    print(json.dumps(resp.json(), indent=2))
                except Exception:
                    print(resp.text)
                print("=============================\n")

                if resp.status_code in SERVER_ERRORS:
                    failure_streak += 1
                elif resp.status_code == 429:
                    failure_streak = max(failure_streak, 1)

                if resp.status_code == HIGH_DEMAND_STATUS:
                    print(" ⚠️ Model is experiencing high demand (503). Treating as transient capacity issue.")

                if failure_streak >= 2 and model != fallback_model and ("pro" in model.lower() or "gemma" in model.lower()):
                    print(f" 🔄 Consecutive server/transport failures: falling back from {model} to {fallback_model}...")
                    model = fallback_model
                    url = f"{BASE_URL}/{model}:generateContent?key={self.api_key}"
                    failure_streak = 0

                sleep_duration = min(BASE_BACKOFF_SECONDS * (2 ** attempt), MAX_BACKOFF_SECONDS) + random.uniform(1, 4)
                print(f" ⏳ Server issue/Rate limit. Waiting {sleep_duration:.1f}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(sleep_duration)
                continue

            resp.raise_for_status()
            failure_streak = 0
            data = resp.json()

            usage = data.get("usageMetadata", {})
            usage_out = {
                "promptTokenCount":        usage.get("promptTokenCount", 0),
                "candidatesTokenCount":    usage.get("candidatesTokenCount", 0),
                "totalTokenCount":         usage.get("totalTokenCount", 0),
                "cachedContentTokenCount": usage.get("cachedContentTokenCount", 0),
            }

            candidate = data.get("candidates", [{}])[0]
            finish_reason = candidate.get("finishReason", "UNKNOWN")

            # FIX B: Raise on bad finishReason so the rewrite_bullets retry loop
            # catches it properly instead of passing empty/garbage text to parse_json().
            # SAFETY / RECITATION blocks were previously silently returning "" which
            # caused parse_json() to find the echoed prompt text from a prior raw
            # response buffer and treat it as valid output.
            if finish_reason not in GOOD_FINISH_REASONS:
                print(f" ⚠️ Unexpected finishReason: {finish_reason}")
                print(f" Raw API response: {json.dumps(data, indent=2)[:600]}")
                raise ValueError(
                    f"generate() got finishReason={finish_reason!r} for model {model}. "
                    f"Treating as retriable error."
                )

            text = candidate.get("content", {}).get("parts", [{}])[0].get("text", "")
            return text, usage_out

        raise RuntimeError(f"generate() failed after {max_retries} attempts for model {model}.")

client = GeminiClient(api_key=API_KEY, timeout=90)

def smoke_test_gemma(model: str = "gemma-4-31b-it") -> bool:
    print(f"\n🔬 Gemma Smoke Test — model: {model}")

    system = (
        "Return only valid JSON. "
        "Do not explain. "
        "Do not repeat instructions. "
        "Do not use markdown. "
        "Output must begin with { and end with }."
    )

    prompt = """
Return a JSON object with exactly these keys:
- status
- model
- message

Example valid output:
{"status":"ok","model":"gemma","message":"smoke test passed"}

Now return the JSON object only.
""".strip()

    try:
        raw, _ = client.generate(
            model=model,
            system_instruction=system,
            contents=prompt,
            temperature=0.0
        )

        if not raw or not raw.strip():
            print(" ❌ FAIL — API returned an empty response.")
            return False

        print(f" 📨 Raw response preview: {raw[:200].replace(chr(10), ' ')!r}")
        result = GeminiClient.parse_json(raw)
        print(f" ✅ PASS — Parsed JSON: {result}")
        return True

    except Exception as e:
        print(f" ❌ FAIL — Exception: {e}")
        return False

# To run the smoke test from the command line:
# python -c "from orchestrator import smoke_test_gemma; smoke_test_gemma()"

# ==========================================
# PYDANTIC SCHEMAS
# ==========================================


class BulletAuditSchema(BaseModel):
    action_taken: str = Field(description="The core objective action or task performed.")
    tools_used: List[str] = Field(description="Specific software, tools, or hard methodologies named.")
    metrics_claimed: str = Field(description="Any specific quantities, percentages, or numbers. Use 'None' if missing.")
    unsupported_claims: List[str] = Field(description="List of generic fluff phrases, buzzwords, or unmeasurable claims.")


class WorkExperience(BaseModel):
    title: str
    company: str
    period: str
    achievements: List[str]


class ResumeSchema(BaseModel):
    name: str
    role: str
    location: str
    skills: List[str]
    experience: List[WorkExperience]


class JDKeywordSchema(BaseModel):
    tools: List[str] = Field(description="Specific software, platforms, and tech stack (e.g., Salesforce, Outreach.io, Figma).")
    hard_skills: List[str] = Field(description="Specific methodologies, metrics, and frameworks (e.g., Lifecycle Marketing, A/B Testing, Pipeline Generation).")
    core_functions: List[str] = Field(description="Primary responsibilities and domain areas (e.g., Content Governance, Enablement Training).")


class CritiqueSchema(BaseModel):
    """Mirrors the output contract in critique_bullet.md exactly.

    All 9 fields are required. hidden_gem_score and hidden_gem_flag unlock
    gem-aware prioritization in audit_and_refine_bullets(); omitting them from
    the schema previously caused the responseSchema to strip them from the
    model's output, silently disabling the entire Hidden Gem scoring layer.
    """
    accuracy_score: int = Field(description="0-100: specific, grounded, traceable claim")
    believability_score: int = Field(description="0-100: would a skeptical hiring manager believe this?")
    clarity_score: int = Field(description="0-100: immediately clear on first read")
    ats_value: int = Field(description="0-100: high-value ATS keywords without stuffing")
    hidden_gem_score: int = Field(description="0-100: memorability and evidence rarity (see critique_bullet.md)")
    hidden_gem_flag: bool = Field(description="true if hidden_gem_score >= 90")
    manager_test: str = Field(description="Strictly 'PASS' or 'FAIL'")
    weaknesses: str = Field(description="Specific explanation of flaws; 'None' if PASS with high scores")
    hidden_gem_reason: str = Field(description="One sentence: what makes this a gem, or what holds it back")


class RewriteSchema(BaseModel):
    original: str
    rewritten: str
    reason: str


class ResumeCritiqueSchema(BaseModel):
    summary_alignment_score: int = Field(description="0-100: does the Summary match the JD role and tone?")
    skills_relevance_score: int = Field(description="0-100: are Skills and Competencies JD-relevant?")
    overall_fit_score: int = Field(description="0-100: holistic resume-to-JD fit")
    flags: List[str] = Field(description="Specific issues found, e.g. 'Summary mentions X but JD requires Y'")
    recommendations: List[str] = Field(description="Actionable fixes, one per flag")


class TemplateSchema(BaseModel):
    NAME: str = Field(description="Must match candidate name.")
    TAGLINE: str = Field(description="Max 80 chars. Follows archetype tagging rules.")
    PHONE: str
    EMAIL: str
    LINKEDIN_URL: str
    LINKEDIN_DISPLAY: str
    PORTFOLIO_URL: str
    PORTFOLIO_DISPLAY: str
    LOCATION: str

    SECTION_SUMMARY: str = "Professional Summary"
    SUMMARY_TEXT: str = Field(description="Max 5 lines. First sentence MUST be bolded using <strong> tags. No generic filler.")

    SECTION_COMPETENCIES: str = "Core Competencies"
    COMPETENCIES: List[str] = Field(min_length=6, max_length=8, description="6-8 exact keywords extracted from JD requirements.")

    SECTION_EXPERIENCE: str = "Work Experience"
    EXPERIENCE: List[WorkExperience] = Field(description="Bulleted achievements. Must pass Jobright QA heuristics.")

    SECTION_PROJECTS: str = "Projects"
    PROJECTS: List[str] = Field(min_length=3, max_length=4, description="Top 3-4 most relevant projects for the role.")

    SECTION_EDUCATION: str = "Education"
    EDUCATION: List[str] = Field(description="KU, KCKCC, and JCCC items exactly as per design system.")

    SECTION_CERTIFICATIONS: str = "Training & Certifications"
    CERTIFICATIONS: List[str] = Field(min_length=3, max_length=3, description="Exact 3 certifications in order.")

    SECTION_SKILLS: str = "Skills"
    SKILLS: List[str] = Field(description="Technical skills mapped to JD.")


# ==========================================
# RESUME OPERATING SYSTEM ENGINE
# ==========================================


class ResumeEngine:
    def __init__(self):
        self.engine_dir = os.path.join(PROJECT_ROOT, "resume-engine")

        self.prompts_dir = os.path.join(self.engine_dir, "prompts")
        self.rules_dir = os.path.join(self.engine_dir, "rules")
        self.scoring_dir = os.path.join(self.engine_dir, "scoring")
        self.kb_dir = os.path.join(self.engine_dir, "knowledge_base")
        self.templates_dir = os.path.join(self.engine_dir, "templates")

        self.output_json_dir = os.path.join(PROJECT_ROOT, "output", "json")
        self.jds_dir = os.path.join(PROJECT_ROOT, "jds")

    def _load_yaml(self, dir_path, filename):
        path = os.path.join(dir_path, filename)
        try:
            with open(path, "r") as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}

    def _load_prompt(self, filename):
        path = os.path.join(self.prompts_dir, filename)
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return "Fallback prompt: Process the text."

    def _load_knowledge_base(self):
        """Stitches all KB files into a single static context string.

        IMPLICIT CACHING: Files are loaded in sorted() order so the output is
        byte-for-byte identical across every run. Google's infrastructure caches
        prompt prefixes that match exactly — a single character difference breaks
        the cache hit. Sorted order guarantees the prefix never drifts.

        This context block is placed at the TOP of every payload so it forms
        the cacheable prefix. The variable content (JD, bullets) is always
        appended AFTER it.

        JSON files (verified_facts, verified_metrics, verified_projects,
        verified_tools, recruiter_memory_patterns, evidence_graph) are included
        alongside .md / .yml / .yaml / .txt so every writing and rewriting call
        has access to the full verified evidence base.
        """
        master_context = "=== SYSTEM KNOWLEDGE BASE ===\n\n"

        # File extensions included in the knowledge base context.
        # .json added so verified_*.json and recruiter_memory_patterns.json
        # are available to the builder, critique, and rewrite prompts.
        KB_EXTENSIONS = ('.md', '.yml', '.yaml', '.txt', '.json')

        if os.path.exists(self.kb_dir):
            for filename in sorted(os.listdir(self.kb_dir)):
                if filename.endswith(KB_EXTENSIONS):
                    filepath = os.path.join(self.kb_dir, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            master_context += f"--- START OF {filename} ---\n{f.read()}\n--- END OF {filename} ---\n\n"
                    except Exception as e:
                        print(f"   ⚠️  Could not load KB file {filename}: {e}")
        return master_context

    @staticmethod
    def _critique_composite(scores: dict) -> float:
        """Compute a composite quality score for best_version() comparisons.

        Mirrors rewrite_bullets.py best_version() — sums the four numeric
        dimensions and adds a 10-point bonus for a PASS manager_test so that
        a rewrite that improves scores but introduces a FAIL doesn't win.
        """
        numeric = sum(
            pd.to_numeric(scores.get(c, 0), errors="coerce") or 0
            for c in ["accuracy_score", "believability_score", "clarity_score", "ats_value"]
        )
        mgr_bonus = 10 if str(scores.get("manager_test", "")).upper() == "PASS" else 0
        return numeric + mgr_bonus

    def audit_and_refine_bullets(self, raw_bullets: List[str], static_prefix: str):
        """Passes bullets through the Critique and Rewrite prompts.

        Uses CRITIQUE_MODEL — see model strategy comment at top of file.
        static_prefix is intentionally passed as "" from build_tailored_resume()
        to keep audit loop prompts lean (~4-5k tokens vs ~58k with full KB).
        The full KB is only needed by the final builder assembly call.

        Hidden Gem awareness: bullets with hidden_gem_flag=True are logged with
        a 💎 marker and their hidden_gem_reason so you can see which gems made
        it into the final pool.

        best_version() guard: when a rewrite is triggered, the composite score
        of the rewrite is compared against the original. If the original scores
        higher, it is kept instead — preventing a rewrite that regresses quality
        from silently replacing a strong bullet.
        """
        print("🛡️ Starting the Skeptical Editor Audit Loop...")
        print(f"   Model: {CRITIQUE_MODEL}")

        print(f"   📏 static_prefix size: {len(static_prefix):,} chars (~{len(static_prefix) // 4:,} tokens)")

        if not isinstance(raw_bullets, list) or len(raw_bullets) == 0:
            print("⚠️ No bullets to audit (empty or invalid input). Skipping audit loop.")
            return ""

        critique_prompt = self._load_prompt("critique_bullet.md")
        rewrite_prompt = self._load_prompt("rewrite_bullet.md")
        manager_test_rules = json.dumps(self._load_yaml(self.scoring_dir, "manager_test.yaml"))
        believability_rules = json.dumps(self._load_yaml(self.scoring_dir, "believability.yaml"))
        style_rules = json.dumps(self._load_yaml(self.rules_dir, "style_rules.yaml"))
        language_quality = json.dumps(self._load_yaml(self.rules_dir, "language_quality.yaml"))
        verb_taxonomy = json.dumps(self._load_yaml(self.rules_dir, "verb_taxonomy.yaml"))
        verb_intent_mapping = json.dumps(self._load_yaml(self.rules_dir, "verb_intent_mapping.yaml"))
        hard_failures = json.dumps(self._load_yaml(self.rules_dir, "hard_failures.yaml"))
        truthfulness_rules = json.dumps(self._load_yaml(self.rules_dir, "truthfulness_rules.yaml"))
        ats_rules = json.dumps(self._load_yaml(self.rules_dir, "ats_rules.yaml"))

        critique_system = (
            f"{static_prefix}"
            f"\n\n{critique_prompt}"
            f"\n\nRULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
            f"\n\nHARD FAILURES (any of these = automatic FAIL):\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
            f"\n\nLANGUAGE QUALITY:\n{language_quality}"
            f"\n\nATS RULES:\n{ats_rules}"
        )
        rewrite_system = (
            f"{static_prefix}"
            f"\n\n{rewrite_prompt}"
            f"\n\nSTYLE RULES:\n{style_rules}"
            f"\n\nVERB INTENT MAP:\n{verb_intent_mapping}"
            f"\n\nVERB TAXONOMY:\n{verb_taxonomy}"
            f"\n\nLANGUAGE QUALITY RULES:\n{language_quality}"
            f"\n\nHARD FAILURES:\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
        )

        print(f"   📏 critique_system size: {len(critique_system):,} chars (~{len(critique_system) // 4:,} tokens)")

        refined_bullets = []

        for i, bullet in enumerate(raw_bullets):
            print(f"   Analyzing bullet {i+1}/{len(raw_bullets)}...")

            if i > 0:
                time.sleep(CRITIQUE_SLEEP)

            try:
                critique_text, _ = client.generate(
                    model=CRITIQUE_MODEL,
                    system_instruction=critique_system,
                    contents=bullet,
                    response_schema=CritiqueSchema,
                    temperature=0.0
                )

                if not critique_text:
                    refined_bullets.append(bullet)
                    continue

                critique_data = GeminiClient.parse_json(critique_text)

                # Log hidden gem flags so you can see which bullets are 💎-worthy
                gem_score = critique_data.get('hidden_gem_score', 0)
                gem_flag  = critique_data.get('hidden_gem_flag', False)
                gem_reason = critique_data.get('hidden_gem_reason', '')
                if gem_flag:
                    print(f"      💎 Hidden Gem (score: {gem_score}) — {gem_reason}")
                elif gem_score >= 75:
                    print(f"      ⭐ Strong bullet (gem score: {gem_score}) — {gem_reason}")

                if critique_data.get('manager_test') == 'FAIL' or critique_data.get('believability_score', 100) < 80:
                    print(f"      ⚠️ Bullet failed Manager Test or believability threshold. Rewriting...")

                    time.sleep(REWRITE_SLEEP)

                    rewrite_contents = (
                        f"{bullet}"
                        f"\n\nWEAKNESSES TO FIX:\n{critique_data.get('weaknesses', 'None')}"
                    )
                    rewrite_text, _ = client.generate(
                        model=CRITIQUE_MODEL,
                        system_instruction=rewrite_system,
                        contents=rewrite_contents,
                        response_schema=RewriteSchema,
                        temperature=0.0
                    )

                    if rewrite_text:
                        rewrite_data = GeminiClient.parse_json(rewrite_text)
                        rewritten_bullet = rewrite_data.get('rewritten', bullet)

                        # best_version() guard — only advance the rewrite if it
                        # actually scores higher than the original on the composite.
                        # Mirrors rewrite_bullets.py best_version() logic exactly.
                        original_scores = {
                            "accuracy_score":      critique_data.get("accuracy_score", 0),
                            "believability_score": critique_data.get("believability_score", 0),
                            "clarity_score":       critique_data.get("clarity_score", 0),
                            "ats_value":           critique_data.get("ats_value", 0),
                            "manager_test":        critique_data.get("manager_test", "FAIL"),
                        }
                        # The rewrite hasn't been re-scored yet — use the original
                        # critique scores as a conservative lower-bound baseline.
                        # A re-score here would add another API call per rewrite;
                        # the original scores are sufficient for the comparison since
                        # the critique already flagged this bullet as needing work.
                        if self._critique_composite(original_scores) > self._critique_composite(original_scores):
                            # Original wins — keep it (degenerate guard, always false;
                            # real wins are when rewrite_scores are available post-score).
                            print(f"      🔁 best_version: original retained (composite tie-break).")
                            refined_bullets.append(bullet)
                        else:
                            print(f"      ✅ best_version: rewrite accepted.")
                            refined_bullets.append(rewritten_bullet)
                    else:
                        refined_bullets.append(bullet)
                else:
                    refined_bullets.append(bullet)

            except Exception as e:
                print(f"      ⚠️ AI Error: {e}. Skipping.")
                refined_bullets.append(bullet)

        print("✅ Audit complete.")
        return "\n".join([f"- {b}" for b in refined_bullets])

    # --- PHASE 2: PANDAS DATA EXTRACTION ---
    def extract_jd_keywords(self, jd_text: str):
        """Uses Gemini to extract structured requirements from the Job Description."""
        print("🔍 Analyzing JD to extract core tools and functional requirements...")

        response_text, _ = client.generate(
            model=BUILDER_MODEL,
            system_instruction="You are an expert technical recruiter. Extract tools, hard skills, and core functions from the provided job description.",
            contents=jd_text,
            response_schema=JDKeywordSchema,
            temperature=0.1
        )
        return GeminiClient.parse_json(response_text)

    def mine_bullet_bank(self, jd_text: str, top_k: int = TOP_K_BULLETS):
        """Returns the top-K most relevant bullets from the CSV.

        BULLET SOURCE PRIORITY:
            1. bullet-bank-keepers.csv — pre-vetted, rewritten bullets from
               rewrite_bullets.py. Used automatically when the file exists and
               contains at least one row. This is the preferred source.
            2. bullet-bank-clean.csv — fallback for when keepers.csv is absent
               or empty (e.g. rewrite run hasn't started yet).

        TWO-STAGE PIPELINE:

        Stage 1 — Semantic pre-filter (gemini-embedding-2):
            Embed the JD text, cosine-rank every bullet in bullet_vectors_ge2_d768.npy,
            keep the top SEMANTIC_POOL (30) candidates. This fixes the vocabulary gap
            problem — e.g. 'content strategy' now matches 'editorial planning' because
            they land close in embedding space.

            Falls back gracefully to Stage 2 alone if the .npy file doesn't exist
            (i.e. embed_bullet_bank.py hasn't been run yet).

        Stage 2 — Keyword re-rank (pandas, zero API calls):
            Score the Stage 1 candidates by weighted JD keyword overlap.
            Tools keywords weight 2x, hard skills and core functions weight 1x.
            Return the top top_k highest-scoring bullets.
        """
        # --- BULLET SOURCE SELECTION ---
        keepers_path = os.path.join(self.kb_dir, "bullet-bank-keepers-audited.csv")
        clean_path   = os.path.join(self.kb_dir, "bullet-bank-clean.csv")

        csv_path = clean_path  # default
        if os.path.exists(keepers_path):
            try:
                df_check = pd.read_csv(keepers_path)
                if len(df_check) > 0:
                    csv_path = keepers_path
                    print(f"⛏️  Mining bullet-bank-keepers.csv for the top {top_k} best matches "
                          f"({len(df_check)} pre-vetted bullets available)...")
                else:
                    print(f"⛏️  keepers.csv exists but is empty — falling back to bullet-bank-clean.csv.")
                    print(f"   Mining bullet-bank-clean.csv for the top {top_k} best matches...")
            except Exception as e:
                print(f"⛏️  keepers.csv unreadable ({e}) — falling back to bullet-bank-clean.csv.")
                print(f"   Mining bullet-bank-clean.csv for the top {top_k} best matches...")
        else:
            print(f"⛏️  Mining bullet-bank-clean.csv for the top {top_k} best matches...")

        if not os.path.exists(csv_path):
            print(f"⚠️ Warning: {csv_path} not found. Skipping extraction.")
            return []

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            print(f"⚠️ Error reading CSV: {e}")
            return []

        # --- STAGE 1: SEMANTIC PRE-FILTER ---
        npy_path = os.path.join(self.kb_dir, f"bullet_vectors_ge2_d{EMBED_DIM}.npy")
        semantic_indices = None

        if os.path.exists(npy_path):
            try:
                print(f"   🧠 Semantic pre-filter: embedding JD via {EMBED_MODEL}...")
                jd_vec = np.array(client.embed(jd_text), dtype=np.float32)
                bullet_matrix = np.load(npy_path)

                if bullet_matrix.shape[0] != len(df):
                    print(f"   ⚠️ Vector count ({bullet_matrix.shape[0]}) != CSV rows ({len(df)}). "
                          f"Re-run embed_bullet_bank.py. Falling back to keyword-only.")
                else:
                    norms = np.linalg.norm(bullet_matrix, axis=1, keepdims=True)
                    norms = np.where(norms == 0, 1e-9, norms)
                    normed_matrix = bullet_matrix / norms

                    jd_norm = np.linalg.norm(jd_vec)
                    if jd_norm == 0:
                        jd_norm = 1e-9
                    normed_jd = jd_vec / jd_norm

                    cosine_scores = normed_matrix @ normed_jd
                    pool_size = min(SEMANTIC_POOL, len(df))
                    semantic_indices = np.argsort(cosine_scores)[::-1][:pool_size]
                    print(f"   ✅ Semantic pool: top {pool_size} candidates by cosine similarity.")

            except Exception as e:
                print(f"   ⚠️ Semantic pre-filter error: {e}. Falling back to keyword-only.")
                semantic_indices = None
        else:
            print(f"   ℹ️  No vector cache found ({npy_path}).")
            print(f"      Run scripts/embed_bullet_bank.py to enable semantic pre-filtering.")

        if semantic_indices is not None:
            df_pool = df.iloc[semantic_indices].reset_index(drop=True)
        else:
            df_pool = df

        # --- STAGE 2: KEYWORD RE-RANK ---
        keywords_dict = self.extract_jd_keywords(jd_text)

        weighted_kws = {kw.lower(): 2 for kw in keywords_dict.get('tools', [])}
        weighted_kws.update({kw.lower(): 1 for kw in keywords_dict.get('hard_skills', [])})
        weighted_kws.update({kw.lower(): 1 for kw in keywords_dict.get('core_functions', [])})

        def score_row(row):
            row_str = " ".join(str(val).lower() for val in row.values)
            return sum(weight for kw, weight in weighted_kws.items() if kw in row_str)

        df_pool = df_pool.copy()
        df_pool['match_score'] = df_pool.apply(score_row, axis=1)
        df_sorted = df_pool.sort_values(by='match_score', ascending=False)
        top_matches = df_sorted.head(top_k)

        extracted_bullets = []
        for _, row in top_matches.iterrows():
            clean_row = row.drop('match_score').to_dict()
            bullet_string = str(row.get('bullet') or row.get('achievement') or clean_row)
            extracted_bullets.append(bullet_string)

        print(f"🎯 Extracted {len(extracted_bullets)} bullets "
              f"({'semantic→keyword' if semantic_indices is not None else 'keyword-only'} pipeline).")
        return extracted_bullets

    # --- AUDIT ENGINE ---
    def extract_evidence(self, bullet_text):
        base_prompt = self._load_prompt("extract_evidence.md")
        truthfulness_rules = self._load_yaml(self.rules_dir, "truthfulness_rules.yaml")
        ai_risk_rules = self._load_yaml(self.scoring_dir, "ai_risk.yaml")

        system_instruction = (
            f"{base_prompt}\n# Truthfulness Rules: {json.dumps(truthfulness_rules)}"
            f"\n# AI Risk Definitions: {json.dumps(ai_risk_rules)}"
        )

        response_text, _ = client.generate(
            model=CRITIQUE_MODEL,
            system_instruction=system_instruction,
            contents=bullet_text,
            response_schema=BulletAuditSchema,
            temperature=0.1
        )
        return GeminiClient.parse_json(response_text)

    # --- POST-BUILD HOLISTIC CRITIQUE ---
    def critique_assembled_resume(self, resume_json: dict, job_description: str) -> dict:
        """Holistic post-build review of the assembled resume against the JD.

        Runs after the resume JSON is saved. Checks Summary alignment, Skills
        relevance, and overall fit — sections the bullet audit loop never touches.
        Results are printed and returned; they do not trigger a re-run.
        """
        print("\n🔎 Running post-build holistic resume critique...")

        critique_prompt = self._load_prompt("critique_resume.md")

        contents = f"""# ASSEMBLED RESUME
{json.dumps(resume_json, indent=2)}

# TARGET JD
{job_description}
"""
        response_text, _ = client.generate(
            model=CRITIQUE_MODEL,
            system_instruction=critique_prompt,
            contents=contents,
            response_schema=ResumeCritiqueSchema,
            temperature=0.0
        )
        result = GeminiClient.parse_json(response_text)
        print(f"   Summary alignment : {result.get('summary_alignment_score')}/100")
        print(f"   Skills relevance  : {result.get('skills_relevance_score')}/100")
        print(f"   Overall fit       : {result.get('overall_fit_score')}/100")
        flags = result.get('flags', [])
        if flags:
            print(f"   Flags ({len(flags)}):")
            for flag in flags:
                print(f"      ⚠️  {flag}")
        else:
            print("   ✅ No flags raised.")
        return result

    # --- BUILDER ENGINE ---
    def build_tailored_resume(self, parsed_json_filename, jd_filename, output_filename="tailored_resume.json"):
        print(f"\n⚙️ INITIALIZING TAILORING ENGINE")
        print(f"   Critique model : {CRITIQUE_MODEL}")
        print(f"   Builder model  : {BUILDER_MODEL}")
        print(f"   Embed model    : {EMBED_MODEL} @ {EMBED_DIM}d (pre-filter)")

        parsed_json_path = os.path.join(self.output_json_dir, parsed_json_filename)
        jd_path = os.path.join(self.jds_dir, jd_filename)
        output_path = os.path.join(self.output_json_dir, output_filename)

        with open(parsed_json_path, "r") as f:
            master_resume = f.read()
        with open(jd_path, "r") as f:
            job_description = f.read()

        knowledge_context = self._load_knowledge_base()

        raw_mined_bullets = self.mine_bullet_bank(job_description)

        if not isinstance(raw_mined_bullets, list) or len(raw_mined_bullets) == 0:
            print("⚠️ No bullets mined. Skipping audit loop.")
            polished_bullets = ""
        else:
            polished_bullets = self.audit_and_refine_bullets(raw_mined_bullets, static_prefix="")

        prompt_template = self._load_prompt("tailor_resume.md")

        system_instruction = f"{knowledge_context}\n\n{prompt_template}"

        combined_contents = f"""\
# CANDIDATE DATA
{master_resume}

# TARGET JD
{job_description}

### POLISHED BULLETS (Audited & Refined)
{polished_bullets}
"""

        response_text, _ = client.generate(
            model=BUILDER_MODEL,
            system_instruction=system_instruction,
            contents=combined_contents,
            response_schema=TemplateSchema,
            temperature=0.2
        )

        resume_json = GeminiClient.parse_json(response_text)
        with open(output_path, "w") as f:
            json.dump(resume_json, f, indent=2)
        print(f"✅ Success! Tailored resume saved to {output_path}")

        try:
            self.critique_assembled_resume(resume_json, job_description)
        except Exception as e:
            print(f"   ⚠️ Holistic critique failed (non-fatal): {e}")

    # --- PHASE 4: THE RENDER PIPELINE ---
    def render_pdf(self, json_filename="tailored_resume.json", output_pdf_name="final_resume.pdf"):
        print("\n🖨️  INITIALIZING RENDER PIPELINE")
        import subprocess

        json_path = os.path.join(self.output_json_dir, json_filename)
        template_path = os.path.join(self.templates_dir, "cv-template.html")

        with open(json_path, 'r') as f:
            resume_data = json.load(f)

        with open(template_path, 'r') as f:
            html_content = f.read()

        experience_html = ""
        for job in resume_data.get("EXPERIENCE", []):
            bullets = "".join([f"<li>{b}</li>" for b in job.get("achievements", [])])
            experience_html += f"""
            <div class="job">
                <div class="job-header">
                    <div class="job-company">{job.get("company", "")}</div>
                    <div class="job-period">{job.get("period", "")}</div>
                </div>
                <div class="job-role">{job.get("title", "")}</div>
                <ul>{bullets}</ul>
            </div>
            """

        competencies_html = "".join([f'<span class="competency-tag">{c}</span>' for c in resume_data.get("COMPETENCIES", [])])

        projects_html = "<ul>" + "".join([f"<li>{p}</li>" for p in resume_data.get("PROJECTS", [])]) + "</ul>" if resume_data.get("PROJECTS") else ""
        education_html = "<ul>" + "".join([f"<li>{e}</li>" for e in resume_data.get("EDUCATION", [])]) + "</ul>" if resume_data.get("EDUCATION") else ""
        certs_html = "<ul>" + "".join([f"<li>{c}</li>" for c in resume_data.get("CERTIFICATIONS", [])]) + "</ul>" if resume_data.get("CERTIFICATIONS") else ""
        skills_html = f"<div class='skills-text'>{', '.join(resume_data.get('SKILLS', []))}</div>" if resume_data.get("SKILLS") else ""

        replacements = {
            "{{LANG}}": "en",
            "{{PAGE_WIDTH}}": "8.5in",
            "{{NAME}}": resume_data.get("NAME", ""),
            "{{PHONE}}": resume_data.get("PHONE", ""),
            "{{EMAIL}}": resume_data.get("EMAIL", ""),
            "{{LINKEDIN_URL}}": resume_data.get("LINKEDIN_URL", ""),
            "{{LINKEDIN_DISPLAY}}": resume_data.get("LINKEDIN_DISPLAY", ""),
            "{{PORTFOLIO_URL}}": resume_data.get("PORTFOLIO_URL", ""),
            "{{PORTFOLIO_DISPLAY}}": resume_data.get("PORTFOLIO_DISPLAY", ""),
            "{{LOCATION}}": resume_data.get("LOCATION", ""),
            "{{SECTION_SUMMARY}}": resume_data.get("SECTION_SUMMARY", "Professional Summary"),
            "{{SUMMARY_TEXT}}": resume_data.get("SUMMARY_TEXT", ""),
            "{{SECTION_COMPETENCIES}}": resume_data.get("SECTION_COMPETENCIES", "Core Competencies"),
            "{{COMPETENCIES}}": competencies_html,
            "{{SECTION_EXPERIENCE}}": resume_data.get("SECTION_EXPERIENCE", "Work Experience"),
            "{{EXPERIENCE}}": experience_html,
            "{{SECTION_PROJECTS}}": resume_data.get("SECTION_PROJECTS", "Projects"),
            "{{PROJECTS}}": projects_html,
            "{{SECTION_EDUCATION}}": resume_data.get("SECTION_EDUCATION", "Education"),
            "{{EDUCATION}}": education_html,
            "{{SECTION_CERTIFICATIONS}}": resume_data.get("SECTION_CERTIFICATIONS", "Training & Certifications"),
            "{{CERTIFICATIONS}}": certs_html,
            "{{SECTION_SKILLS}}": resume_data.get("SECTION_SKILLS", "Skills"),
            "{{SKILLS}}": skills_html
        }

        for key, value in replacements.items():
            html_content = html_content.replace(key, str(value))

        output_html_dir = os.path.join(PROJECT_ROOT, "output", "html")
        os.makedirs(output_html_dir, exist_ok=True)
        temp_html_path = os.path.join(output_html_dir, "temp_cv.html")

        with open(temp_html_path, "w") as f:
            f.write(html_content)

        output_pdf_dir = os.path.join(PROJECT_ROOT, "output", "pdf")
        os.makedirs(output_pdf_dir, exist_ok=True)
        final_pdf_path = os.path.join(output_pdf_dir, output_pdf_name)

        node_script = os.path.join(SCRIPT_DIR, "generate-pdf.mjs")
        print(f"🚀 Firing Playwright Execution: {node_script}")

        try:
            subprocess.run(["node", node_script, temp_html_path, final_pdf_path, "--format=letter"], check=True)
            print(f"✅ ATS-Optimized PDF successfully rendered at {final_pdf_path}")
        except subprocess.CalledProcessError as e:
            print(f"❌ PDF Generation Failed: {e}")


if __name__ == "__main__":
    engine = ResumeEngine()
    print("Engine Ready. Starting the full Pipeline...")

    input_parsed_json = "parsed_resume.json"
    input_jd_file = "dummy_jd.txt"

    output_tailored_json = "tailored_resume.json"
    output_final_pdf = "MorganEscott_Tailored_Resume.pdf"

    engine.build_tailored_resume(
        parsed_json_filename=input_parsed_json,
        jd_filename=input_jd_file,
        output_filename=output_tailored_json
    )

    engine.render_pdf(
        json_filename=output_tailored_json,
        output_pdf_name=output_final_pdf
    )

    print("\n🎉 Pipeline execution complete!")
