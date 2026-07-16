"""
gemini_client.py — Shared Gemini REST client.

Imported by both orchestrator.py and rewrite_bullets.py to break
the circular import between them.
"""

import copy
import json
import os
import random
import re
import time

import requests
from dotenv import load_dotenv

# Resolved from this file's own location, matching every other script in
# this pipeline (cluster_bullet_bank.py, audit_keepers.py,
# score_keeper_gems.py, embed_bullet_bank.py all do the same). override=True
# is the important part -- without it, a GEMINI_API_KEY already exported in
# the shell (e.g. from an earlier manual export while juggling API keys)
# silently wins over whatever's actually in .env, since dotenv's default
# behavior is to never overwrite an existing environment variable.
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"), override=True)

API_KEY  = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"
# x-goog-api-key header, not ?key= query param -- current docs (ai.google.dev)
# only show the header form; query params also risk landing in server/proxy
# logs. Doesn't affect ACCESS_TOKEN_TYPE_UNSUPPORTED (verified: identical 401
# with either transport) -- this is a hygiene/future-proofing change only.
AUTH_HEADERS = {"x-goog-api-key": API_KEY}

RETRYABLE          = {429, 500, 502, 503, 504}
SERVER_ERRORS      = {500, 502, 503, 504}
HIGH_DEMAND_STATUS = 503
BASE_BACKOFF_SECS  = 8
MAX_BACKOFF_SECS   = 90

# Fallback model used when primary fails repeatedly
REWRITE_FALLBACK_MODEL = "gemini-3.1-flash-lite"

# Per-model fallback targets: after failure_streak reaches 2 within one
# generate() call, switch to the mapped model rather than continuing to
# retry the one that's struggling. gemini-3.1-flash-lite has a 250k TPM
# cap and is the model builder/fix/trim calls use directly (with nowhere
# to fall back to previously, since REWRITE_FALLBACK_MODEL pointed at
# itself) -- gemma-4-31b-it has TPM Unlimited on this account's quota
# tiers, making it a real rescue path when flash-lite is under high
# demand, not just a same-model retry with backoff.
MODEL_FALLBACKS = {
    "gemma-4-31b-it": REWRITE_FALLBACK_MODEL,
    "gemini-3.1-flash-lite": "gemma-4-31b-it",
}

# Embedding model + dimension (matches orchestrator.py constants)
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM   = 768   # gemini-embedding-2 native dimension


class SustainedFailureError(RuntimeError):
    """Raised when GeminiClient.generate() has exhausted retries and the
    model fallback on SUSTAINED_FAILURE_THRESHOLD consecutive calls --
    a signal this is a quota-level issue, not a transient blip."""


class GeminiClient:

    # Was 90 -- verified live (2026-07-16) that large-context calls to
    # gemini-3.1-flash-lite can genuinely take 100-140+s to respond right
    # now (confirmed by re-running an identical payload with a 180s cap,
    # which succeeded at 138s). 90s was cutting off requests that would
    # otherwise have completed, not detecting genuinely stuck ones.
    _timeout = 180
    _consecutive_full_failures = 0
    SUSTAINED_FAILURE_THRESHOLD = 2

    # gemma-4-31b-it's TPM cap is 16k tokens/minute (confirmed 2026-07-16),
    # and a single call's context now regularly runs 12k-17k tokens even
    # after slimming -- close enough to the full budget that two Gemma
    # calls landing in the same rolling minute can collide even though
    # each one alone would have fit. Spacing successive Gemma calls this
    # far apart lets the token bucket clear before the next one arrives,
    # rather than gambling on retry/backoff to recover an avoidable 429.
    # Lives here (not in rewrite_bullets.py) so orchestrator.py's Gemma
    # calls -- which go through this same shared client -- get it too.
    GEMMA_MIN_INTERVAL_SECS = 65
    _last_gemma_call_ts = 0.0

    @staticmethod
    def resolve_refs(schema: dict) -> dict:
        """
        Inlines every "$ref": "#/$defs/X" pointer with a deep copy of
        $defs["X"], then drops $defs from the tree.

        Pydantic's model_json_schema() emits nested BaseModel fields as
        $ref/$defs, but sanitize_schema() deletes $defs unconditionally
        (Gemini's structured-output API doesn't support $ref/$defs) -- so
        a nested model's schema would be left with a dangling $ref if this
        resolution didn't happen first, most likely producing a 400 from
        the API. Must run before sanitize_schema, not after.
        """
        if not isinstance(schema, dict):
            return schema
        defs = schema.get("$defs", {})

        def _resolve(node, seen):
            if isinstance(node, dict):
                if "$ref" in node:
                    key = node["$ref"].rsplit("/", 1)[-1]
                    if key in seen:
                        raise ValueError(f"Circular $ref detected resolving schema: {node['$ref']}")
                    if key not in defs:
                        raise ValueError(f"Unresolvable $ref: {node['$ref']}")
                    return _resolve(copy.deepcopy(defs[key]), seen | {key})
                return {k: _resolve(v, seen) for k, v in node.items() if k != "$defs"}
            if isinstance(node, list):
                return [_resolve(item, seen) for item in node]
            return node

        return _resolve(schema, frozenset())

    @staticmethod
    def sanitize_schema(schema: dict) -> dict:
        UNSUPPORTED = {"title", "description", "$defs", "$schema", "default", "examples", "additionalProperties"}
        if not isinstance(schema, dict):
            return schema
        cleaned = {}
        for k, v in schema.items():
            if k == "properties" and isinstance(v, dict):
                # Keys here are field names, not schema metadata -- must
                # never be treated as candidates for UNSUPPORTED stripping,
                # even when a field happens to be named e.g. "title" (a job
                # title, not the $schema "title" keyword). A prior version
                # stripped this blindly and deleted a field literally named
                # "title" from properties while "required" still listed it,
                # producing "property is not defined" from the API. Each
                # property's own schema is still sanitized normally.
                cleaned[k] = {name: GeminiClient.sanitize_schema(prop) for name, prop in v.items()}
                continue
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
    def _salvage_fields(cleaned: str) -> dict:
        """
        Recovers top-level "key": value pairs by regex when json.loads()
        fails outright -- observed cause: the model produces a valid answer
        up front, then degenerates into repeating a phrase (e.g. echoing an
        instruction back at itself) until it runs out of output tokens,
        leaving the JSON string unterminated. The early, valid field(s)
        are still intact in the text even though the object as a whole
        never closes, so a full-string json.loads() throwing away
        everything is losing a real answer, not just discarding garbage.
        Only recovers string/number leaf values -- not lists/objects,
        which can't be delimited reliably without a real parser.
        """
        salvaged = {}
        for key, str_val in re.findall(r'"(\w+)"\s*:\s*"((?:\\.|[^"\\])*)"', cleaned):
            try:
                salvaged[key] = json.loads(f'"{str_val}"')
            except json.JSONDecodeError:
                continue
        for key, num_val in re.findall(r'"(\w+)"\s*:\s*(-?\d+(?:\.\d+)?)', cleaned):
            salvaged.setdefault(key, json.loads(num_val))
        return salvaged

    @staticmethod
    def parse_json(text: str) -> dict:
        if not text:
            return {}
        cleaned = re.sub(r"<think>.*?(?:</think>|<\/think>)", "", text, flags=re.DOTALL).strip()
        if not cleaned:
            raise ValueError("parse_json: string was empty after stripping thinking tokens.")
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return GeminiClient._salvage_fields(cleaned)

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
        model_fallback: bool = True,
    ) -> tuple[str | None, dict]:
        url = f"{BASE_URL}/{model}:generateContent"

        valid_tiers = {"standard", "priority", "flex"}
        tier = (service_tier or "standard").strip().lower()
        if tier not in valid_tiers:
            raise ValueError(f"Invalid service_tier {service_tier!r}.")

        failure_streak = 0

        for attempt in range(max_retries):
            if "gemma" in model.lower():
                elapsed = time.time() - GeminiClient._last_gemma_call_ts
                if elapsed < GeminiClient.GEMMA_MIN_INTERVAL_SECS:
                    wait = GeminiClient.GEMMA_MIN_INTERVAL_SECS - elapsed
                    print(f"    ⏳ Pacing Gemma call: waiting {wait:.1f}s (16k TPM cap)...")
                    time.sleep(wait)
                GeminiClient._last_gemma_call_ts = time.time()

            current_temp = 0.0 if response_schema is not None else temperature

            generation_config: dict = {"temperature": current_temp}
            if max_output_tokens is not None:
                generation_config["maxOutputTokens"] = int(max_output_tokens)

            if "gemma" in model.lower():
                # Gemma 4 emits a "thought" reasoning preamble by default
                # (see the thought-part filter below) -- those tokens are
                # discarded but still billed against the 16k TPM cap.
                # thinkingLevel: "minimal" suppresses them at the source.
                generation_config["thinkingConfig"] = {"thinkingLevel": "minimal"}

            raw_schema = None
            if response_schema is not None:
                generation_config["responseMimeType"] = "application/json"
                # Gemma must also get responseSchema, not just responseMimeType --
                # without it, Gemma defaults to emitting a "thought": true reasoning
                # part before the real answer, which breaks parts[0]-based extraction.
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
                if raw_schema:
                    generation_config["responseSchema"] = GeminiClient.sanitize_schema(
                        GeminiClient.resolve_refs(raw_schema)
                    )

            # systemInstruction as its own top-level field, same shape for
            # every model -- current Gemma-4-on-Gemini-API docs show it
            # supported natively; the earlier manual merge into `contents`
            # was a workaround for older Gemma versions that didn't respect
            # a separate systemInstruction field.
            body = {
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "contents": [{"role": "user", "parts": [{"text": contents}]}],
                "generationConfig": generation_config,
                "serviceTier": tier,
            }

            try:
                resp = requests.post(url, json=body, headers=AUTH_HEADERS, timeout=GeminiClient._timeout)
            except requests.exceptions.RequestException as e:
                failure_streak += 1
                if model_fallback and failure_streak >= 2 and model in MODEL_FALLBACKS:
                    fallback_model = MODEL_FALLBACKS[model]
                    print(f"    WARNING: Transport failures — falling back to {fallback_model}...")
                    model = fallback_model
                    url = f"{BASE_URL}/{model}:generateContent"
                    failure_streak = 0
                sleep_dur = min(BASE_BACKOFF_SECS * (2 ** attempt), MAX_BACKOFF_SECS) + random.uniform(1, 4)
                print(f"    WARNING: Network error ({GeminiClient._timeout}s): {str(e).split()[-1].strip()}. "
                      f"Waiting {sleep_dur:.1f}s before retry {attempt+1}/{max_retries}...")
                time.sleep(sleep_dur)
                continue

            if resp.status_code in SERVER_ERRORS:
                failure_streak += 1
            elif resp.status_code == 429:
                failure_streak += 1

            if resp.status_code == HIGH_DEMAND_STATUS:
                print("    WARNING: Model high demand (503). Treating as transient.")

            if resp.status_code in RETRYABLE:
                if model_fallback and failure_streak >= 2 and model in MODEL_FALLBACKS:
                    fallback_model = MODEL_FALLBACKS[model]
                    print(f"    WARNING: Server failures — falling back to {fallback_model}...")
                    model = fallback_model
                    url = f"{BASE_URL}/{model}:generateContent"
                    failure_streak = 0
                sleep_dur = min(BASE_BACKOFF_SECS * (2 ** attempt), MAX_BACKOFF_SECS) + random.uniform(1, 4)
                print(f"    WARNING: HTTP {resp.status_code}. Waiting {sleep_dur:.1f}s (retry {attempt+1}/{max_retries})...")
                time.sleep(sleep_dur)
                continue

            if resp.status_code in (400, 404):
                print(f"    WARNING: Gemini API permanent error {resp.status_code}: {resp.reason}. Not retrying.")
                try:
                    print(json.dumps(resp.json(), indent=2)[:800])
                except Exception:
                    print(resp.text[:800])
                return None, {}

            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(f"    WARNING: HTTP error {resp.status_code}: {e}. Not retrying.")
                return None, {}

            try:
                data = resp.json()
            except Exception:
                return None, {}

            candidates = data.get("candidates", [])
            if not candidates:
                return None, data.get("usageMetadata", {})

            usage = data.get("usageMetadata", {})

            finish_reason = candidates[0].get("finishReason")
            if finish_reason not in (None, "STOP", "MAX_TOKENS"):
                print(f"    WARNING: Unexpected finishReason={finish_reason!r}. Not retrying this attempt.")
                return None, usage

            content = candidates[0].get("content", {})
            parts   = content.get("parts", [])
            # Skip thinking parts (part.get("thought") is True) -- Gemma without
            # a schema puts its reasoning in parts[0] and the real answer later;
            # concatenate only the non-thought parts to get the actual response.
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            failure_streak = 0
            GeminiClient._consecutive_full_failures = 0
            return text, usage

        GeminiClient._consecutive_full_failures += 1
        if GeminiClient._consecutive_full_failures >= GeminiClient.SUSTAINED_FAILURE_THRESHOLD:
            failures = GeminiClient._consecutive_full_failures
            GeminiClient._consecutive_full_failures = 0
            raise SustainedFailureError(
                f"GeminiClient.generate() exhausted retries on {failures} consecutive "
                f"calls (model={model}) -- this looks like a sustained quota issue, not "
                "a transient blip. Swap GEMINI_API_KEY/GOOGLE_API_KEY in .env and re-run."
            )
        return None, {}

    @staticmethod
    def embed(text: str) -> list[float] | None:
        """
        Generates an embedding vector for the given text using EMBED_MODEL.
        Used by orchestrator.py's mine_bullet_bank() for semantic similarity.
        Native output dimension: 768 (gemini-embedding-2).
        """
        url = f"{BASE_URL}/{EMBED_MODEL}:embedContent"
        payload = {
            "model": f"models/{EMBED_MODEL}",
            "content": {"parts": [{"text": text}]},
            "outputDimensionality": EMBED_DIM,
        }
        try:
            resp = requests.post(url, json=payload, headers=AUTH_HEADERS, timeout=30)
            resp.raise_for_status()
            return resp.json().get("embedding", {}).get("values")
        except Exception as e:
            print(f"    WARNING: Embed error: {e}")
            return None
