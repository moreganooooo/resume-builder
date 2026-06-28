import os
import time
import yaml
import json
import re
import random
import requests
import urllib.request
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
#   Native output dimension: 768.
#
# GEMMA via Vertex: Gemma 4 31B (gemma-4-31b-it) is available on the free tier
#   with a much larger daily quota than Gemini Flash. Used in rewrite_bullets.py
#   (the rewrite-queue runner) where token volume is highest. Not used here because
#   orchestrator.py runs the live tailoring pipeline and needs strict JSON schema
#   enforcement, which Gemma handles less reliably than Gemini Flash.
#
# NOTE: orchestrator.py intentionally uses raw REST (urllib) rather than the
#   google-genai SDK. This avoids SDK versioning headaches on the free tier and
#   gives full explicit control over the payload shape and response parsing.
#   ingest.py uses the SDK because it relies on the Files API (file upload),
#   which is much cleaner via SDK. The two are deliberately divergent for
#   good architectural reasons — not an oversight.
CRITIQUE_MODEL = "gemini-3.1-flash-lite"
BUILDER_MODEL  = "gemini-3.1-flash-lite"
EMBED_MODEL    = "gemini-embedding-2"
EMBED_DIM      = 768   # gemini-embedding-2 native dimension


# --- TIMING CONSTANTS ---
CRITIQUE_SLEEP = 4    # seconds between critique calls (free-tier: 15 RPM)
REWRITE_SLEEP  = 4    # seconds before the rewrite call after a FAIL
RESCORE_SLEEP  = 8    # seconds before the re-score call after a rewrite
                      # (longer because rescore fires immediately after rewrite)


# --- PIPELINE CONSTANTS ---
TOP_K_BULLETS  = 12   # bullets mined from the bank per run
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


# ---------------------------------------------------------------------------
# GEMINI CLIENT  (raw REST — avoids SDK versioning headaches on free tier)
# ---------------------------------------------------------------------------

class GeminiClient:
    """Thin wrapper around the Gemini v1beta REST API."""

    @staticmethod
    def _build_url(model: str, stream: bool = False) -> str:
        action = "streamGenerateContent" if stream else "generateContent"
        return f"{BASE_URL}/{model}:{action}?key={API_KEY}"

    @staticmethod
    def parse_json(text: str) -> dict:
        """Strip markdown fences and parse JSON. Returns {} on failure."""
        if not text:
            return {}
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
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
        response_schema,
        temperature: float = 0.0,
        max_retries: int = 3,
        base_delay: float = 10.0,
    ) -> tuple[str | None, dict]:
        """
        Call generateContent and return (response_text, usage_metadata).
        Returns (None, {}) on any error after max_retries attempts.

        Retries on transient failures (network errors, 429 rate-limits, 5xx
        server errors) using exponential backoff. Permanent errors (400 bad
        request, 404 model not found) are not retried.
        """
        schema_dict = response_schema.model_json_schema()

        payload = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"parts": [{"text": contents}]}],
            "generationConfig": {
                "temperature": temperature,
                "responseMimeType": "application/json",
                "responseSchema": schema_dict,
            },
        }

        url = GeminiClient._build_url(model)
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        for attempt in range(1, max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    text = (
                        body.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                    )
                    usage = body.get("usageMetadata", {})
                    return text, usage
            except urllib.error.HTTPError as e:
                # Don't retry permanent client errors (400, 404)
                if e.code in (400, 404):
                    print(f"    ⚠️  Gemini API permanent error {e.code}: {e}. Not retrying.")
                    return None, {}
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    print(f"    ⚠️  Gemini API error {e.code} (attempt {attempt}/{max_retries}). Retrying in {delay:.0f}s...")
                    time.sleep(delay)
                else:
                    print(f"    ⚠️  Gemini API error {e.code}: {e}. All {max_retries} attempts exhausted.")
                    return None, {}
            except Exception as e:
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))
                    print(f"    ⚠️  Gemini API error (attempt {attempt}/{max_retries}): {e}. Retrying in {delay:.0f}s...")
                    time.sleep(delay)
                else:
                    print(f"    ⚠️  Gemini API error: {e}. All {max_retries} attempts exhausted.")
                    return None, {}

        return None, {}

    @staticmethod
    def embed(text: str) -> list[float] | None:
        """Embed a single text string. Returns a float list or None on error."""
        url = f"{BASE_URL}/{EMBED_MODEL}:embedContent?key={API_KEY}"
        payload = {
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBED_DIM,
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return body.get("embedding", {}).get("values")
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
    original:  str
    rewritten: str
    reason:    str

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
    EXPERIENCE:          List[WorkExperience] = Field(description="Bulleted achievements. Must pass Jobright QA heuristics.")
    SECTION_PROJECTS:    str        = Field(default="Projects")
    PROJECTS:            List[ProjectItem]    = Field(min_length=3, max_length=4, description="Top 3-4 most relevant projects for the role.")
    SECTION_EDUCATION:   str        = Field(default="Education")
    EDUCATION:           List[EducationItem]  = Field(description="KU, KCKCC, and JCCC items exactly as per design system.")
    SECTION_CERTIFICATIONS: str     = Field(default="Training & Certifications")
    CERTIFICATIONS:      List[CertItem]       = Field(min_length=3, max_length=3, description="Exact 3 certifications in order.")
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
        # output/html/ and output/pdf/ are created in render_pdf before use,
        # but output/json/ is written to in build_tailored_resume which runs
        # first. On a fresh clone (output/ is gitignored), this would crash
        # with FileNotFoundError without this line.
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
        Pipeline artifacts — cluster maps, audit CSVs, raw bullet banks,
        dedupe intermediates — are excluded. This reduces the builder payload
        from ~5.3 MB to ~380 KB (~93% reduction) with no loss of writing context.

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

    def audit_and_refine_bullets(self, raw_bullets: List[str], static_prefix: str):
        """
        Passes bullets through the Critique and Rewrite prompts.

        Uses CRITIQUE_MODEL (see model strategy comment at top of file).
        static_prefix is the loaded knowledge_base context string, passed in
        from build_tailored_resume. This gives the Skeptical Editor full
        grounding in the candidate's background, verified claims, and what
        tools/metrics are actually true — without re-loading the KB files here.

        Hidden Gem awareness: bullets with hidden_gem_flag=True are logged with a
        marker and their hidden_gem_reason so you can see which gems made it into
        the final pool.

        best_version guard: when a rewrite is triggered, the rewrite is re-scored
        via a second critique call so we can compare its composite against the
        original. If the original scores higher, it is kept — preventing a rewrite
        that regresses quality from silently replacing a strong bullet.
        """
        print("Starting the Skeptical Editor Audit Loop...")
        print(f"  Model: {CRITIQUE_MODEL}")
        print(f"  static_prefix size: {len(static_prefix)} chars / ~{len(static_prefix)//4} tokens")

        if not isinstance(raw_bullets, list) or len(raw_bullets) == 0:
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

        critique_system = (
            f"{static_prefix}"
            f"{critique_prompt}"
            f"\n\nMANAGER TEST RULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
            f"\n\nHARD FAILURES (any of these = automatic FAIL):\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nATS RULES:\n{ats_rules}"
        )

        rewrite_system = (
            f"{static_prefix}"
            f"{rewrite_prompt}"
            f"\n\nSTYLE RULES:\n{style_rules}"
            f"\n\nINTENT MAP:\n{verb_intent_mapping}"
            f"\n\nTAXONOMY:\n{verb_taxonomy}"
            f"\n\nQUALITY RULES:\n{language_quality}"
            f"\n\nHARD FAILURES:\n{hard_failures}"
            f"\n\nTRUTHFULNESS RULES:\n{truthfulness_rules}"
        )

        print(f"  critique_system size: {len(critique_system)} chars / ~{len(critique_system)//4} tokens")

        refined_bullets = []
        for i, bullet in enumerate(raw_bullets):
            print(f"\n  Analyzing bullet {i+1}/{len(raw_bullets)}...")
            if i > 0:
                time.sleep(CRITIQUE_SLEEP)

            try:
                critique_text, _ = GeminiClient.generate(
                    model=CRITIQUE_MODEL,
                    system_instruction=critique_system,
                    contents=bullet,
                    response_schema=CritiqueSchema,
                    temperature=0.0,
                )

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
                    print("    Bullet failed Manager Test or believability threshold. Rewriting...")
                    time.sleep(REWRITE_SLEEP)

                    rewrite_contents = (
                        f"{bullet}"
                        f"\n\nTO FIX:\n{critique_data.get('weaknesses', 'None')}"
                    )
                    rewrite_text, _ = GeminiClient.generate(
                        model=CRITIQUE_MODEL,
                        system_instruction=rewrite_system,
                        contents=rewrite_contents,
                        response_schema=RewriteSchema,
                        temperature=0.0,
                    )

                    if rewrite_text:
                        rewrite_data    = GeminiClient.parse_json(rewrite_text)
                        rewritten_bullet = rewrite_data.get("rewritten", bullet)

                        # Capture original scores for best_version comparison
                        original_scores = {
                            "accuracy_score":     critique_data.get("accuracy_score", 0),
                            "believability_score":critique_data.get("believability_score", 0),
                            "clarity_score":      critique_data.get("clarity_score", 0),
                            "ats_value":          critique_data.get("ats_value", 0),
                            "manager_test":       critique_data.get("manager_test", "FAIL"),
                        }
                        rewrite_scores = original_scores.copy()  # safe fallback

                        # Re-score the rewrite to enable a real comparison
                        try:
                            time.sleep(RESCORE_SLEEP)
                            rescore_text, _ = GeminiClient.generate(
                                model=CRITIQUE_MODEL,
                                system_instruction=critique_system,
                                contents=rewritten_bullet,
                                response_schema=CritiqueSchema,
                                temperature=0.0,
                            )
                            if rescore_text:
                                rescore_data = GeminiClient.parse_json(rescore_text)
                                rewrite_scores = {
                                    "accuracy_score":     rescore_data.get("accuracy_score", 0),
                                    "believability_score":rescore_data.get("believability_score", 0),
                                    "clarity_score":      rescore_data.get("clarity_score", 0),
                                    "ats_value":          rescore_data.get("ats_value", 0),
                                    "manager_test":       rescore_data.get("manager_test", "FAIL"),
                                }
                        except Exception as rescore_err:
                            print(f"    ⚠️  Re-score failed: {rescore_err}. Using original scores as fallback (rewrite accepted).")

                        # Best-version guard
                        orig_composite    = ResumeEngine.critique_composite(original_scores)
                        rewrite_composite = ResumeEngine.critique_composite(rewrite_scores)
                        if orig_composite > rewrite_composite:
                            print(f"    🔒 best_version: original retained (orig={orig_composite:.0f} > rewrite={rewrite_composite:.0f}).")
                            refined_bullets.append(bullet)
                        else:
                            print(f"    ✅ best_version: rewrite accepted (rewrite={rewrite_composite:.0f} >= orig={orig_composite:.0f}).")
                            refined_bullets.append(rewritten_bullet)
                    else:
                        refined_bullets.append(bullet)
                else:
                    refined_bullets.append(bullet)

            except Exception as e:
                print(f"    ⚠️  AI Error: {e}. Skipping.")
                refined_bullets.append(bullet)

        print("\nAudit complete.")
        return "\n".join(f"- {b}" for b in refined_bullets)

    def extract_jd_keywords(self, jd_text: str) -> dict:
        """Uses Gemini to extract structured requirements from the Job Description.

        Returns a dict with keys: tools, hard_skills, core_functions.
        Called once in mine_bullet_bank and the result is cached + passed
        through to build_tailored_resume to avoid processing the JD a second
        time via API (FIX #7: JD was previously sent to the API 3x per run).
        """
        print("Analyzing JD to extract core tools and functional requirements...")
        response_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction="You are an expert technical recruiter. Extract tools, hard skills, and core functions from the provided job description.",
            contents=jd_text,
            response_schema=JDKeywordSchema,
            temperature=0.1,
        )
        return GeminiClient.parse_json(response_text)

    def mine_bullet_bank(self, jd_text: str, top_k: int = TOP_K_BULLETS,
                         keywords_dict: dict = None):
        """
        Returns the top-K most relevant bullets from the CSV.

        keywords_dict (optional): pre-computed result of extract_jd_keywords().
          If provided, skips the keyword extraction API call entirely.
          Pass this in from build_tailored_resume to avoid making the same
          API call twice (FIX #7).

        BULLET SOURCE PRIORITY:
          1. bullet-bank-keepers-audited.csv — pre-vetted, rewritten bullets.
             Used automatically when the file exists and contains at least one row.
             This is the preferred source.
          2. bullet-bank-clean.csv — fallback for when keepers-audited.csv is
             absent or empty (e.g. rewrite run hasn't started yet).

        TWO-STAGE PIPELINE:
          Stage 1 — Semantic pre-filter (gemini-embedding-2):
            Embed the JD text, cosine-rank every bullet in bullet_vectors_ge2_d768.npy,
            keep the top SEMANTIC_POOL (30) candidates. This fixes the vocabulary-gap
            problem (e.g. "content strategy" now matches "editorial planning" because
            they land close in embedding space). Falls back gracefully to Stage 2 alone
            if the .npy file doesn't exist (i.e. embed_bullet_bank.py hasn't been run yet).

          Stage 2 — Strength-tier sort + keyword re-rank + gem boost (pandas, zero API calls):
            Sort the Stage 1 candidates by STRENGTH_ORDER first (Hidden Gem > Strong >
            Solid > Needs Work), then by match_score descending within each tier.
            This guarantees Hidden Gems are always prioritized over weaker bullets
            regardless of keyword overlap noise. Set GEM_BOOST_WEIGHT=0.0 to disable
            the gem score additive bonus while keeping the tier sort.
        """
        keepers_path = os.path.join(self.kb_dir, "bullet-bank-keepers-audited.csv")
        clean_path   = os.path.join(self.kb_dir, "bullet-bank-clean.csv")
        csv_path     = clean_path  # default

        if os.path.exists(keepers_path):
            try:
                df_check = pd.read_csv(keepers_path)
                if len(df_check) > 0:
                    csv_path = keepers_path
                    print(f"  Mining bullet-bank-keepers-audited.csv for the top {top_k} best matches ({len(df_check)} pre-vetted bullets available)...")
                else:
                    print(f"  keepers-audited.csv exists but is empty — falling back to bullet-bank-clean.csv.")
                    print(f"  Mining bullet-bank-clean.csv for the top {top_k} best matches...")
            except Exception as e:
                print(f"  keepers-audited.csv unreadable ({e}), falling back to bullet-bank-clean.csv.")
                print(f"  Mining bullet-bank-clean.csv for the top {top_k} best matches...")
        else:
            print(f"  Mining bullet-bank-clean.csv for the top {top_k} best matches...")

        if not os.path.exists(csv_path):
            print(f"  ⚠️  Warning: {csv_path} not found. Skipping extraction.")
            return [], {}

        try:
            df = pd.read_csv(csv_path)
        except Exception as e:
            print(f"  ⚠️  Error reading CSV: {e}")
            return [], {}

        # --- STAGE 1: SEMANTIC PRE-FILTER ---
        # NOTE: If you see a matmul dimension mismatch error here (e.g. "size 3072
        # is different from 768"), the local .npy file was built with the old
        # gemini-embedding-exp-03-07 model at 3072d despite having 'd768' in its
        # filename. Regenerate it:
        #   rm resume-engine/knowledge_base/bullet_vectors_ge2_d768.npy
        #   python scripts/embed_bullet_bank.py
        npy_path = os.path.join(self.kb_dir, f"bullet_vectors_ge2_d{EMBED_DIM}.npy")
        semantic_indices = None
        if os.path.exists(npy_path):
            try:
                print(f"  Semantic pre-filter — embedding JD via {EMBED_MODEL}...")
                jd_vec      = np.array(GeminiClient.embed(jd_text), dtype=np.float32)
                bullet_matrix = np.load(npy_path)
                if bullet_matrix.shape[0] != len(df):
                    print(f"  ⚠️  Vector count ({bullet_matrix.shape[0]}) != CSV rows ({len(df)}). "
                          f"Re-run embed_bullet_bank.py. Falling back to keyword-only.")
                else:
                    norms = np.linalg.norm(bullet_matrix, axis=1, keepdims=True)
                    norms = np.where(norms == 0, 1e-9, norms)
                    normed_matrix = bullet_matrix / norms
                    jd_norm = np.linalg.norm(jd_vec)
                    if jd_norm == 0:
                        jd_norm = 1e-9
                    normed_jd     = jd_vec / jd_norm
                    cosine_scores = normed_matrix @ normed_jd
                    pool_size     = min(SEMANTIC_POOL, len(df))
                    semantic_indices = np.argsort(cosine_scores)[-1:-pool_size-1:-1]
                    print(f"  Semantic pool: top {pool_size} candidates by cosine similarity.")
            except Exception as e:
                print(f"  ⚠️  Semantic pre-filter error: {e}. Falling back to keyword-only.")
                semantic_indices = None
        else:
            print(f"  No vector cache found ({npy_path}).")
            print(f"  Run scripts/embed_bullet_bank.py to enable semantic pre-filtering.")

        if semantic_indices is not None:
            df_pool = df.iloc[semantic_indices].reset_index(drop=True)
        else:
            df_pool = df

        # --- STAGE 2: KEYWORD RE-RANK + GEM BOOST ---
        # FIX #7: Accept pre-computed keywords_dict to avoid a redundant API call.
        # If not provided (e.g. mine_bullet_bank called standalone), compute it now.
        if keywords_dict is None:
            keywords_dict = self.extract_jd_keywords(jd_text)

        weighted_kws  = {kw.lower(): 2 for kw in keywords_dict.get("tools", [])}
        weighted_kws.update({kw.lower(): 1 for kw in keywords_dict.get("hard_skills", [])})
        weighted_kws.update({kw.lower(): 1 for kw in keywords_dict.get("core_functions", [])})

        gem_boost_enabled = GEM_BOOST_WEIGHT > 0 and "hidden_gem_score" in df_pool.columns
        if gem_boost_enabled:
            print(f"  Gem boost active (GEM_BOOST_WEIGHT={GEM_BOOST_WEIGHT}). "
                  f"A score-90 gem gets {90 * GEM_BOOST_WEIGHT:.1f} pts on top of keyword relevance.")

        def score_row(row):
            row_str      = " ".join(str(val).lower() for val in row.values)
            keyword_score = sum(weight for kw, weight in weighted_kws.items() if kw in row_str)
            if gem_boost_enabled:
                gem_score = pd.to_numeric(row.get("hidden_gem_score", 0), errors="coerce")
                gem_score = gem_score if pd.notna(gem_score) else 0.0
                return keyword_score + gem_score * GEM_BOOST_WEIGHT
            return keyword_score

        df_pool = df_pool.copy()
        df_pool["match_score"] = df_pool.apply(score_row, axis=1)

        # Strength-tier sort (Bug 4 fix)
        if "strength_category" in df_pool.columns:
            df_pool["strength_rank"] = df_pool["strength_category"].map(STRENGTH_ORDER).fillna(99)
            df_sorted = df_pool.sort_values(
                by=["strength_rank", "match_score"], ascending=[True, False]
            )
            print("  Strength-tier sort active: Hidden Gem > Strong > Solid > Needs Work.")
        else:
            df_sorted = df_pool.sort_values(by="match_score", ascending=False)
            print("  No strength_category column found — sorting by match_score only.")

        top_matches = df_sorted.head(top_k)

        extracted_bullets = []
        for _, row in top_matches.iterrows():
            clean_row     = row.drop([c for c in ["match_score", "strength_rank"] if c in row.index])
            bullet_string = str(row.get("bullet") or row.get("achievement") or clean_row)
            extracted_bullets.append(bullet_string)

        pipeline_label = (
            "semantic→keyword+gem+tier" if gem_boost_enabled and semantic_indices is not None else
            "semantic→keyword+tier"      if semantic_indices is not None else
            "keyword+gem+tier"           if gem_boost_enabled else
            "keyword+tier"
        )
        print(f"  🎯 Extracted {len(extracted_bullets)} bullets ({pipeline_label} pipeline).")
        return extracted_bullets, keywords_dict

    def extract_evidence(self, bullet_text):
        base_prompt       = self.load_prompt("extract_evidence.md")
        truthfulness_rules = self.load_yaml(self.rules_dir,   "truthfulness_rules.yaml")
        ai_risk_rules      = self.load_yaml(self.scoring_dir, "ai_risk.yaml")
        system_instruction = (
            f"{base_prompt}"
            f"\n\nTruthfulness Rules:\n{json.dumps(truthfulness_rules)}"
            f"\n\nAI Risk Definitions:\n{json.dumps(ai_risk_rules)}"
        )
        response_text, _ = GeminiClient.generate(
            model=CRITIQUE_MODEL,
            system_instruction=system_instruction,
            contents=bullet_text,
            response_schema=BulletAuditSchema,
            temperature=0.1,
        )
        return GeminiClient.parse_json(response_text)

    def critique_assembled_resume(self, resume_json: dict, job_description: str) -> dict:
        """
        Holistic post-build review of the assembled resume against the JD.
        Runs after the resume JSON is saved. Checks Summary alignment, Skills
        relevance, and overall fit — sections the bullet audit loop never touches.
        Results are printed and returned; they do not trigger a re-run.
        """
        print("\nRunning post-build holistic resume critique...")
        critique_prompt = self.load_prompt("critique_resume.md")
        contents = (
            f"ASSEMBLED RESUME:\n{json.dumps(resume_json, indent=2)}"
            f"\n\nTARGET JD:\n{job_description}"
        )
        response_text, _ = GeminiClient.generate(
            model=CRITIQUE_MODEL,
            system_instruction=critique_prompt,
            contents=contents,
            response_schema=ResumeCritiqueSchema,
            temperature=0.0,
        )
        result = GeminiClient.parse_json(response_text)
        print(f"  Summary alignment:  {result.get('summary_alignment_score')}/100")
        print(f"  Skills relevance:   {result.get('skills_relevance_score')}/100")
        print(f"  Overall fit:        {result.get('overall_fit_score')}/100")
        flags = result.get("flags", [])
        if flags:
            print(f"  Flags ({len(flags)}):")
            for flag in flags:
                print(f"    • {flag}")
        else:
            print("  No flags raised.")
        return result

    def build_tailored_resume(self, parsed_json_filename, jd_filename,
                               output_filename="tailored_resume.json"):
        print("\n" + "="*60)
        print("  INITIALIZING TAILORING ENGINE")
        print("="*60)
        print(f"  Critique model: {CRITIQUE_MODEL}")
        print(f"  Builder model:  {BUILDER_MODEL}")
        print(f"  Embed model:    {EMBED_MODEL} ({EMBED_DIM}d pre-filter)")

        parsed_json_path = os.path.join(self.output_json_dir, parsed_json_filename)
        jd_path          = os.path.join(self.jds_dir, jd_filename)
        output_path      = os.path.join(self.output_json_dir, output_filename)

        # FIX #5: Wrap file reads in try/except so missing files produce a clear,
        # actionable error instead of a raw Python traceback.
        try:
            with open(parsed_json_path, "r") as f:
                master_resume = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"❌ parsed_resume.json not found at:\n    {parsed_json_path}\n"
                f"   Run 'python scripts/ingest.py' first to generate it."
            )

        try:
            with open(jd_path, "r") as f:
                job_description = f.read()
        except FileNotFoundError:
            raise FileNotFoundError(
                f"❌ Job description file not found at:\n    {jd_path}\n"
                f"   Check that '{jd_filename}' exists in the /jds/ folder."
            )

        knowledge_context = self.load_knowledge_base()

        # FIX #7: Extract JD keywords once here and pass the result into
        # mine_bullet_bank. Previously, mine_bullet_bank called
        # extract_jd_keywords internally, meaning the JD was sent to the
        # API for keyword extraction AND again for the final build call
        # (plus the embed call) = 3 API calls touching the same JD text.
        # Now it's 2: embed + final build. Saves one BUILDER_MODEL call
        # per run, which matters on the free tier.
        print("\nExtracting JD keywords (shared between mining and build steps)...")
        keywords_dict = self.extract_jd_keywords(job_description)

        raw_mined_bullets, _ = self.mine_bullet_bank(
            job_description, keywords_dict=keywords_dict
        )

        if not isinstance(raw_mined_bullets, list) or len(raw_mined_bullets) == 0:
            print("  No bullets mined. Skipping audit loop.")
            polished_bullets = ""
        else:
            # FIX: Pass knowledge_context as static_prefix so the Skeptical Editor
            # has full grounding in the candidate's background and verified claims.
            # Previously this was passed as "" (empty string), meaning bullets were
            # critiqued and rewritten by an AI with zero context about who wrote them.
            polished_bullets = self.audit_and_refine_bullets(
                raw_mined_bullets, static_prefix=knowledge_context
            )

        prompt_template = self.load_prompt("tailor_resume.md")

        # FIX: system_instruction contains only the lean prompt (~3.5k tokens).
        # The KB context (~95k tokens) moves to the TOP of contents so it still
        # forms the stable cacheable prefix Google looks for, but no longer blows
        # past gemini-3.1-flash-lite's 32k system_instruction token limit.
        system_instruction = prompt_template
        combined_contents  = (
            f"{knowledge_context}"
            f"\n\nCANDIDATE DATA:\n{master_resume}"
            f"\n\nTARGET JD:\n{job_description}"
            f"\n\nTARGET JD - POLISHED BULLETS (Audited & Refined):\n{polished_bullets}"
        )

        response_text, _ = GeminiClient.generate(
            model=BUILDER_MODEL,
            system_instruction=system_instruction,
            contents=combined_contents,
            response_schema=TemplateSchema,
            temperature=0.2,
        )

        # FIX #4: Guard against an empty/None API response writing a blank {} to
        # disk and printing a false "Success!" message. A failed API call used to
        # silently produce an empty resume with no indication anything went wrong.
        if not response_text:
            raise RuntimeError(
                "❌ Builder model returned no response. "
                "Check your API quota, key validity, and network connection."
            )
        resume_json = GeminiClient.parse_json(response_text)
        if not resume_json:
            raise RuntimeError(
                "❌ Builder model response was not valid JSON. "
                f"Raw response (first 500 chars): {str(response_text)[:500]}"
            )

        with open(output_path, "w") as f:
            json.dump(resume_json, f, indent=2)
        print(f"\n  ✅ Success! Tailored resume saved to {output_path}")

        try:
            self.critique_assembled_resume(resume_json, job_description)
        except Exception as e:
            print(f"  ⚠️  Holistic critique failed (non-fatal): {e}")

    def render_pdf(self, json_filename="tailored_resume.json",
                   output_pdf_name="final_resume.pdf"):
        print("\n" + "="*60)
        print("  INITIALIZING RENDER PIPELINE")
        print("="*60)
        import subprocess

        json_path    = os.path.join(self.output_json_dir, json_filename)
        template_path = os.path.join(self.templates_dir, "cv-template.html")

        with open(json_path, "r") as f:
            resume_data = json.load(f)
        with open(template_path, "r") as f:
            html_content = f.read()

        # --- EXPERIENCE ---
        experience_html = ""
        for job in resume_data.get("EXPERIENCE", []):
            bullets = "\n".join(f"<li>{b}</li>" for b in job.get("achievements", []))
            location_html = f'<div class="job-location">{job.get("location", "")}</div>' if job.get("location") else ""
            experience_html += (
                f'<div class="job">'
                f'<div class="job-header">'
                f'<div class="job-company">{job.get("company", "")}'
                f'</div>'
                f'<div class="job-period">{job.get("period", "")}'
                f'</div>'
                f'</div>'
                f'<div class="job-role">{job.get("title", "")}'
                f'</div>'
                f'{location_html}'
                f'<ul>{bullets}</ul>'
                f'</div>'
            )

        # --- COMPETENCIES ---
        competencies_html = "\n".join(
            f'<span class="competency-tag">{c}</span>'
            for c in resume_data.get("COMPETENCIES", [])
        )

        # --- PROJECTS (structured rich HTML) ---
        projects_html = ""
        for p in resume_data.get("PROJECTS", []):
            # Support both dict (new TemplateSchema) and plain string (legacy JSON)
            if isinstance(p, dict):
                badge_html = f'<span class="project-badge">{p.get("badge")}</span>' if p.get("badge") else ""
                tech_html  = f'<div class="project-tech">{p.get("tech")}</div>' if p.get("tech") else ""
                projects_html += (
                    f'<div class="project">'
                    f'<div class="project-title">{p.get("title", "")}{badge_html}</div>'
                    f'<div class="project-desc">{p.get("description", "")}</div>'
                    f'{tech_html}'
                    f'</div>'
                )
            else:
                projects_html += f'<div class="project"><div class="project-desc">{p}</div></div>'

        # --- EDUCATION (structured rich HTML) ---
        education_html = ""
        for e in resume_data.get("EDUCATION", []):
            if isinstance(e, dict):
                desc_html = f'<div class="edu-desc">{e.get("description")}</div>' if e.get("description") else ""
                education_html += (
                    f'<div class="edu-item">'
                    f'<div class="edu-header">'
                    f'<span class="edu-title">{e.get("degree", "")} — <span class="edu-org">{e.get("institution", "")}</span></span>'
                    f'<span class="edu-year">{e.get("year", "")}</span>'
                    f'</div>'
                    f'{desc_html}'
                    f'</div>'
                )
            else:
                education_html += f'<div class="edu-item"><div class="edu-title">{e}</div></div>'

        # --- CERTIFICATIONS (structured cert-item grid) ---
        certs_html = ""
        for c in resume_data.get("CERTIFICATIONS", []):
            if isinstance(c, dict):
                certs_html += (
                    f'<div class="cert-item">'
                    f'<span class="cert-title">{c.get("title", "")}</span>'
                    f'<span class="cert-org">{c.get("org", "")}</span>'
                    f'<span class="cert-year">{c.get("year", "")}</span>'
                    f'</div>'
                )
            else:
                certs_html += f'<div class="cert-item"><span class="cert-title">{c}</span></div>'

        # --- SKILLS (skills-grid layout) ---
        skills_html = (
            '<div class="skills-grid">'
            + "".join(f'<span class="skill-item">{s}</span>' for s in resume_data.get("SKILLS", []))
            + '</div>'
        ) if resume_data.get("SKILLS") else ""

        replacements = {
            "{{LANG}}":               "en",
            "{{PAGE_WIDTH}}":         "8.5in",
            "{{NAME}}":               resume_data.get("NAME", ""),
            "{{TAGLINE}}":            resume_data.get("TAGLINE", ""),
            "{{PHONE}}":              resume_data.get("PHONE", ""),
            "{{EMAIL}}":              resume_data.get("EMAIL", ""),
            "{{LINKEDIN_URL}}":       resume_data.get("LINKEDIN_URL", ""),
            "{{LINKEDIN_DISPLAY}}":   resume_data.get("LINKEDIN_DISPLAY", ""),
            "{{PORTFOLIO_URL}}":      resume_data.get("PORTFOLIO_URL", ""),
            "{{PORTFOLIO_DISPLAY}}":  resume_data.get("PORTFOLIO_DISPLAY", ""),
            "{{LOCATION}}":           resume_data.get("LOCATION", ""),
            "{{SECTION_SUMMARY}}":    resume_data.get("SECTION_SUMMARY", "Professional Summary"),
            "{{SUMMARY_TEXT}}":       resume_data.get("SUMMARY_TEXT", ""),
            "{{SECTION_COMPETENCIES}}": resume_data.get("SECTION_COMPETENCIES", "Core Competencies"),
            "{{COMPETENCIES}}":       competencies_html,
            "{{SECTION_EXPERIENCE}}": resume_data.get("SECTION_EXPERIENCE", "Work Experience"),
            "{{EXPERIENCE}}":         experience_html,
            "{{SECTION_PROJECTS}}":   resume_data.get("SECTION_PROJECTS", "Projects"),
            "{{PROJECTS}}":           projects_html,
            "{{SECTION_EDUCATION}}":  resume_data.get("SECTION_EDUCATION", "Education"),
            "{{EDUCATION}}":          education_html,
            "{{SECTION_CERTIFICATIONS}}": resume_data.get("SECTION_CERTIFICATIONS", "Training & Certifications"),
            "{{CERTIFICATIONS}}":     certs_html,
            "{{SECTION_SKILLS}}":     resume_data.get("SECTION_SKILLS", "Skills"),
            "{{SKILLS}}":             skills_html,
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
        print(f"  Firing Playwright → {node_script}")
        try:
            subprocess.run(
                ["node", node_script, temp_html_path, final_pdf_path, "--format=letter"],
                check=True
            )
            print(f"  ✅ ATS-Optimized PDF successfully rendered at {final_pdf_path}")
        except subprocess.CalledProcessError as e:
            print(f"  ❌ PDF Generation Failed: {e}")


if __name__ == "__main__":
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description="Resume Builder — Tailoring Pipeline")
    parser.add_argument(
        "--jd",
        default="dummy_jd.txt",
        help="Filename of the job description in the /jds/ folder (default: dummy_jd.txt)"
    )
    args = parser.parse_args()

    engine = ResumeEngine()
    print("Engine Ready. Starting the full Pipeline...")
    print(f"   📄 JD: {args.jd}")

    # --- PREFLIGHT: ensure parsed_resume.json exists ---
    # ingest.py reads cv.md from resume-engine/knowledge_base/ and writes
    # output/json/parsed_resume.json. If that file is missing, the build call
    # below will crash immediately with a FileNotFoundError, so we auto-run
    # ingest.py here before anything else touches the file.
    parsed_resume_path = os.path.join(PROJECT_ROOT, "output", "json", "parsed_resume.json")
    ingest_script = os.path.join(SCRIPT_DIR, "ingest.py")
    if not os.path.exists(parsed_resume_path):
        print("⚙️  parsed_resume.json not found — running ingest.py first...")
        try:
            subprocess.run(["python3", ingest_script], check=True)
            print("✅  ingest.py complete — parsed_resume.json ready.")
        except subprocess.CalledProcessError as e:
            print(f"❌  ingest.py failed: {e}")
            print("    Please check that resume-engine/knowledge_base/cv.md exists and your GEMINI_API_KEY is set.")
            raise SystemExit(1)
    else:
        print("✅  parsed_resume.json found — skipping ingest.")

    input_parsed_json = "parsed_resume.json"
    input_jd_file = args.jd

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
