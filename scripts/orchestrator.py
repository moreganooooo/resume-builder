import os
import time
import yaml
import json
import re
import requests
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List


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

# BULLET_SLEEP: pause between audit-loop calls (seconds).
# A critique+rewrite pair fires two back-to-back calls on the same bullet,
# momentarily doubling effective RPM. 25s keeps worst-case rate at ~2.4 RPM
# even when every bullet triggers a rewrite — well under the free-tier ceiling.
BULLET_SLEEP = 25

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

    def __init__(self, api_key: str, timeout: int = 120):
        self.api_key = api_key
        self.timeout = timeout

    @staticmethod
    def parse_json(text: str) -> dict:
        """Strip markdown fencing and parse JSON. Falls back to regex extraction."""
        if not text or not text.strip():
            raise ValueError("parse_json received an empty string — the model returned no content.")

        cleaned = text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
            cleaned = cleaned.rsplit("```", 1)[0]

        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        preview = cleaned[:300].replace("\n", " ")
        raise ValueError(f"JSON parse failed — could not extract valid JSON.\nRaw preview: {preview!r}")

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

    def generate(self, model: str, system_instruction: str, contents: str,
                 response_schema: type = None, temperature: float = 0.1,
                 max_retries: int = 6) -> str:
        """Call generateContent and return the response text.

        Retries with exponential backoff on 429 rate-limit errors.
        max_retries=6 gives a backoff window of up to 315s
        (5+10+20+40+80+160) so transient quota spikes recover
        instead of dropping bullets.
        """
        url = f"{BASE_URL}/{model}:generateContent?key={self.api_key}"

        generation_config = {"temperature": temperature}

        if response_schema is not None:
            generation_config["responseMimeType"] = "application/json"

        body = {
            "system_instruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": contents}]}],
            "generationConfig": generation_config,
        }

        for attempt in range(max_retries):
            resp = requests.post(url, json=body, timeout=self.timeout)

            RETRYABLE = (429, 500, 502, 503, 504)
            if resp.status_code in RETRYABLE:
                print(f"\n===== HTTP {resp.status_code} RESPONSE BODY =====")
                try:
                    print(json.dumps(resp.json(), indent=2))
                except Exception:
                    print(resp.text)
                print("=============================\n")
                wait = 5 * (2 ** attempt)
                print(f"         ⏳ Rate limited. Waiting {wait}s before retry {attempt + 1}/{max_retries}...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            data = resp.json()

            # --- DIAGNOSTIC: log token usage on every successful response ---
            usage = data.get("usageMetadata", {})
            if usage:
                print(f"         📊 tokens — prompt: {usage.get('promptTokenCount', '?')} | "
                      f"output: {usage.get('candidatesTokenCount', '?')} | "
                      f"total: {usage.get('totalTokenCount', '?')}")

            candidate = data.get("candidates", [{}])[0]
            finish_reason = candidate.get("finishReason", "UNKNOWN")
            if finish_reason not in ("STOP", "MAX_TOKENS"):
                print(f"         ⚠️  Unexpected finishReason: {finish_reason}")
                print(f"         Raw API response: {json.dumps(data, indent=2)[:600]}")

            return candidate.get("content", {}).get("parts", [{}])[0].get("text", "")

        resp = requests.post(url, json=body, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


client = GeminiClient(api_key=API_KEY, timeout=120)


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
    accuracy_score: int = Field(description="0-100 score")
    believability_score: int = Field(description="0-100 score based on believability.yaml")
    clarity_score: int = Field(description="0-100 score")
    ats_value: int = Field(description="0-100 score")
    manager_test: str = Field(description="Strictly 'PASS' or 'FAIL'")
    weaknesses: str = Field(description="Explanation of flaws")


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
        """
        master_context = "=== SYSTEM KNOWLEDGE BASE ===\n\n"

        if os.path.exists(self.kb_dir):
            for filename in sorted(os.listdir(self.kb_dir)):
                if filename.endswith(('.md', '.yml', '.yaml', '.txt')):
                    filepath = os.path.join(self.kb_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f:
                        master_context += f"--- START OF {filename} ---\n{f.read()}\n--- END OF {filename} ---\n\n"
        return master_context

    def audit_and_refine_bullets(self, raw_bullets: List[str], static_prefix: str):
        """Passes bullets through the Critique and Rewrite prompts.

        Uses CRITIQUE_MODEL — see model strategy comment at top of file.
        static_prefix is intentionally passed as "" from build_tailored_resume()
        to keep audit loop prompts lean (~4-5k tokens vs ~58k with full KB).
        The full KB is only needed by the final builder assembly call.
        """
        print("🛡️ Starting the Skeptical Editor Audit Loop...")
        print(f"   Model: {CRITIQUE_MODEL}")

        # --- DIAGNOSTIC: log prompt sizes before the first API call ---
        print(f"   📏 static_prefix size: {len(static_prefix):,} chars (~{len(static_prefix) // 4:,} tokens)")

        if not isinstance(raw_bullets, list) or len(raw_bullets) == 0:
            print("⚠️ No bullets to audit (empty or invalid input). Skipping audit loop.")
            return ""

        critique_prompt = self._load_prompt("critique_bullet.md")
        rewrite_prompt = self._load_prompt("rewrite_bullet.md")
        manager_test_rules = json.dumps(self._load_yaml(self.scoring_dir, "manager_test.yaml"))
        believability_rules = json.dumps(self._load_yaml(self.scoring_dir, "believability.yaml"))
        style_rules = json.dumps(self._load_yaml(self.rules_dir, "style_rules.yaml"))

        critique_system = (
            f"{static_prefix}"
            f"\n\n{critique_prompt}"
            f"\n\nRULES:\n{manager_test_rules}"
            f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
        )
        rewrite_system = (
            f"{static_prefix}"
            f"\n\n{rewrite_prompt}"
            f"\n\nSTYLE RULES:\n{style_rules}"
        )

        # --- DIAGNOSTIC: log full critique system prompt size ---
        print(f"   📏 critique_system size: {len(critique_system):,} chars (~{len(critique_system) // 4:,} tokens)")

        refined_bullets = []

        for i, bullet in enumerate(raw_bullets):
            print(f"   Analyzing bullet {i+1}/{len(raw_bullets)}...")

            if i > 0:
                time.sleep(BULLET_SLEEP)

            try:
                critique_text = client.generate(
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

                if critique_data.get('manager_test') == 'FAIL' or critique_data.get('believability_score', 100) < 80:
                    print(f"      ⚠️ Bullet failed Manager Test. Rewriting...")

                    time.sleep(BULLET_SLEEP)

                    rewrite_contents = (
                        f"{bullet}"
                        f"\n\nWEAKNESSES TO FIX:\n{critique_data.get('weaknesses', 'None')}"
                    )
                    rewrite_text = client.generate(
                        model=CRITIQUE_MODEL,
                        system_instruction=rewrite_system,
                        contents=rewrite_contents,
                        response_schema=RewriteSchema,
                        temperature=0.0
                    )

                    if rewrite_text:
                        rewrite_data = GeminiClient.parse_json(rewrite_text)
                        refined_bullets.append(rewrite_data.get('rewritten', bullet))
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

        response_text = client.generate(
            model=BUILDER_MODEL,
            system_instruction="You are an expert technical recruiter. Extract tools, hard skills, and core functions from the provided job description.",
            contents=jd_text,
            response_schema=JDKeywordSchema,
            temperature=0.1
        )
        return GeminiClient.parse_json(response_text)

    def mine_bullet_bank(self, jd_text: str, top_k: int = TOP_K_BULLETS):
        """Returns the top-K most relevant bullets from the CSV.

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
        print(f"⛏️  Mining bullet-bank-clean.csv for the top {top_k} best matches...")

        csv_path = os.path.join(self.kb_dir, "bullet-bank-clean.csv")
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
                jd_vec = np.array(client.embed(jd_text), dtype=np.float32)  # (768,)
                bullet_matrix = np.load(npy_path)                           # (N, 768)

                if bullet_matrix.shape[0] != len(df):
                    print(f"   ⚠️ Vector count ({bullet_matrix.shape[0]}) != CSV rows ({len(df)}). "
                          f"Re-run embed_bullet_bank.py. Falling back to keyword-only.")
                else:
                    # Cosine similarity: normalise both sides, then dot product.
                    norms = np.linalg.norm(bullet_matrix, axis=1, keepdims=True)
                    norms = np.where(norms == 0, 1e-9, norms)  # avoid div-by-zero
                    normed_matrix = bullet_matrix / norms

                    jd_norm = np.linalg.norm(jd_vec)
                    if jd_norm == 0:
                        jd_norm = 1e-9
                    normed_jd = jd_vec / jd_norm

                    cosine_scores = normed_matrix @ normed_jd  # (N,)
                    pool_size = min(SEMANTIC_POOL, len(df))
                    semantic_indices = np.argsort(cosine_scores)[::-1][:pool_size]
                    print(f"   ✅ Semantic pool: top {pool_size} candidates by cosine similarity.")

            except Exception as e:
                print(f"   ⚠️ Semantic pre-filter error: {e}. Falling back to keyword-only.")
                semantic_indices = None
        else:
            print(f"   ℹ️  No vector cache found ({npy_path}).")
            print(f"      Run scripts/embed_bullet_bank.py to enable semantic pre-filtering.")

        # Narrow the DataFrame to the semantic pool (or use all rows as fallback)
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

        response_text = client.generate(
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
        response_text = client.generate(
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

        # Full KB loaded here for the final builder assembly call only.
        # The audit loop receives static_prefix="" to keep critique prompts lean.
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

        response_text = client.generate(
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

        # Post-build holistic critique — checks Summary, Skills, Competencies against JD
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
