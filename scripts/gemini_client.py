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

import profile_paths
import cli_art
import theme

# Resolved via profile_paths.env_path() -- each profile carries its own
# .env (GEMINI_API_KEY, JOBRIGHT_COOKIE_STRING), not one shared project-
# root file. override=True is the important part -- without it, a
# GEMINI_API_KEY already exported in the shell (e.g. from an earlier
# manual export while juggling API keys) silently wins over whatever's
# actually in .env, since dotenv's default behavior is to never overwrite
# an existing environment variable.
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
load_dotenv(profile_paths.env_path(), override=True)

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


# Gemini reports a refusal as a `finishReason` on an otherwise-successful
# 200 response -- there is no exception to catch, so this never reaches
# cli_art's exception classifier and needs its own plain-language map.
# Codes are Google's; the wording is ours. An unmapped code falls through
# to _FINISH_REASON_DEFAULT rather than being printed raw, so a value
# Google adds later still reads as a sentence.
_FINISH_REASON_EXPLANATIONS = {
    "SAFETY": "Gemini's safety filter blocked its own answer to this request.",
    "PROHIBITED_CONTENT": "Gemini's safety filter blocked its own answer to this request.",
    "BLOCKLIST": "Gemini's safety filter blocked its own answer to this request.",
    "SPII": "Gemini stopped because its answer looked like it contained personal identifying information.",
    "RECITATION": "Gemini stopped because its answer was reproducing copyrighted text too closely.",
    "MALFORMED_FUNCTION_CALL": "Gemini returned a malformed response that couldn't be read.",
    "LANGUAGE": "Gemini stopped because the request was in a language it won't answer in.",
    "OTHER": "Gemini stopped early without saying why.",
}
_FINISH_REASON_DEFAULT = "Gemini stopped before finishing its answer."


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
            salvaged = GeminiClient._salvage_fields(cleaned)
            if salvaged:
                cli_art.console.print(f"    {cli_art.WARNING} parse_json() salvaged {len(salvaged)} field(s) from unterminated "
                      "JSON -- the response was truncated or malformed; treat this result as partial.", soft_wrap=True)
            return salvaged

    @staticmethod
    def generate(
        model: str,
        system_instruction: str,
        contents: str,
        response_schema=None,
        extra_schema_properties: dict = None,
        extra_required: list = None,
        temperature: float = 0.0,
        max_retries: int = 6,
        max_output_tokens: int = None,
        service_tier: str = "standard",
        model_fallback: bool = True,
        tools: list = None,
    ) -> tuple[str | None, dict]:
        url = f"{BASE_URL}/{model}:generateContent"

        valid_tiers = {"standard", "priority", "flex"}
        tier = (service_tier or "standard").strip().lower()
        if tier not in valid_tiers:
            raise ValueError(f"Invalid service_tier {service_tier!r}.")

        # Google Search grounding (tools=[{"google_search": {}}]) and
        # structured JSON output (response_schema) have long been mutually
        # exclusive on Gemini's API -- a grounded call must return free-form
        # text with citations, not a schema-constrained object. Caught here
        # rather than surfacing as a confusing 400 from the API itself.
        if tools and response_schema is not None:
            raise ValueError("generate(): tools (e.g. search grounding) and response_schema cannot be combined in one call.")

        failure_streak = 0

        for attempt in range(max_retries):
            if "gemma" in model.lower():
                elapsed = time.time() - GeminiClient._last_gemma_call_ts
                if elapsed < GeminiClient.GEMMA_MIN_INTERVAL_SECS:
                    wait = GeminiClient.GEMMA_MIN_INTERVAL_SECS - elapsed
                    cli_art.console.print(f"    {theme.colorize_icon('hint')} Pacing Gemma call: waiting {wait:.1f}s (16k TPM cap)...", soft_wrap=True)
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
            elif "flash-lite" in model.lower():
                # B46/P5#1 (phase-5-modernization.md): every flash-lite call
                # (CRITIQUE_MODEL, BUILDER_MODEL, FIND_WEBSITE_MODEL,
                # SCORE_MODEL) previously sent no thinkingConfig at all, so
                # it ran at whatever Google's current default is for this
                # tier -- confirmed "minimal", but this tier's default has
                # already shifted once (Gemini 3.5 Flash rollout). Pinning
                # it explicitly keeps today's behavior identical while
                # making it immune to a future silent default change.
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
                        cli_art.console.print(f"{cli_art.ERROR} response_schema string is not valid JSON.", soft_wrap=True)
                if raw_schema and (extra_schema_properties or extra_required):
                    # Callers that need profile-specific enum fields not knowable
                    # at Pydantic class-definition time (e.g. orchestrator.py's
                    # per-profile education achievement-key options) merge them
                    # in here rather than passing a hand-built dict as
                    # response_schema -- this keeps response_schema=SomeModel
                    # identity-comparable in tests/mocks that route on it, and
                    # keeps the merge applied before resolve_refs/sanitize_schema
                    # so it goes through the exact same pipeline as every other
                    # property. Copies rather than mutates raw_schema in place,
                    # since a Pydantic-sourced dict could in principle be reused
                    # across calls.
                    raw_schema = dict(raw_schema)
                    raw_schema["properties"] = {**raw_schema.get("properties", {}), **(extra_schema_properties or {})}
                    raw_schema["required"] = list(raw_schema.get("required", [])) + list(extra_required or [])
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
            if tools:
                body["tools"] = tools

            try:
                resp = requests.post(url, json=body, headers=AUTH_HEADERS, timeout=GeminiClient._timeout)
            except requests.exceptions.RequestException as e:
                failure_streak += 1
                if model_fallback and failure_streak >= 2 and model in MODEL_FALLBACKS:
                    fallback_model = MODEL_FALLBACKS[model]
                    cli_art.console.print(f"    {cli_art.WARNING} Transport failures — falling back to {fallback_model}...", soft_wrap=True)
                    model = fallback_model
                    url = f"{BASE_URL}/{model}:generateContent"
                    failure_streak = 0
                sleep_dur = min(BASE_BACKOFF_SECS * (2 ** attempt), MAX_BACKOFF_SECS) + random.uniform(1, 4)
                cli_art.console.print(f"    {cli_art.WARNING} Network error ({GeminiClient._timeout}s): {type(e).__name__}: {str(e)[:120]}. "
                      f"Waiting {sleep_dur:.1f}s before retry {attempt+1}/{max_retries}...", soft_wrap=True)
                time.sleep(sleep_dur)
                continue

            if resp.status_code in SERVER_ERRORS:
                failure_streak += 1
            elif resp.status_code == 429:
                failure_streak += 1

            if resp.status_code == HIGH_DEMAND_STATUS:
                cli_art.console.print(f"    {cli_art.WARNING} Model high demand (503). Treating as transient.", soft_wrap=True)

            if resp.status_code in RETRYABLE:
                if model_fallback and failure_streak >= 2 and model in MODEL_FALLBACKS:
                    fallback_model = MODEL_FALLBACKS[model]
                    cli_art.console.print(f"    {cli_art.WARNING} Server failures — falling back to {fallback_model}...", soft_wrap=True)
                    model = fallback_model
                    url = f"{BASE_URL}/{model}:generateContent"
                    failure_streak = 0
                sleep_dur = min(BASE_BACKOFF_SECS * (2 ** attempt), MAX_BACKOFF_SECS) + random.uniform(1, 4)
                cli_art.console.print(f"    {cli_art.WARNING} HTTP {resp.status_code}. Waiting {sleep_dur:.1f}s (retry {attempt+1}/{max_retries})...", soft_wrap=True)
                time.sleep(sleep_dur)
                continue

            if resp.status_code in (400, 404):
                cli_art.console.print(f"    {cli_art.WARNING} Gemini API permanent error {resp.status_code}: {resp.reason}. Not retrying.", soft_wrap=True)
                try:
                    cli_art.console.print(json.dumps(resp.json(), indent=2)[:800], markup=False, soft_wrap=True)
                except Exception:
                    cli_art.console.print(resp.text[:800], markup=False, soft_wrap=True)
                return None, {}

            try:
                resp.raise_for_status()
            except requests.exceptions.HTTPError as e:
                cli_art.console.print(f"    {cli_art.WARNING} HTTP error {resp.status_code}: {e}. Not retrying.", soft_wrap=True)
                return None, {}

            try:
                data = resp.json()
            except Exception as e:
                cli_art.friendly_warning(
                    e, "reading the AI's response",
                    "treating this request as if it came back empty")
                return None, {}

            candidates = data.get("candidates", [])
            if not candidates:
                return None, data.get("usageMetadata", {})

            usage = data.get("usageMetadata", {})

            finish_reason = candidates[0].get("finishReason")
            if finish_reason not in (None, "STOP", "MAX_TOKENS"):
                cli_art.cli_warning(
                    f"{_FINISH_REASON_EXPLANATIONS.get(finish_reason, _FINISH_REASON_DEFAULT)} "
                    "Skipping this one and moving on."
                )
                # Raw API code kept as VERBOSE-only detail: it's the first
                # thing worth knowing when debugging a prompt, and the last
                # thing a job seeker needs on screen.
                cli_art.detail(f"    finishReason={finish_reason!r}")
                return None, usage
            if finish_reason == "MAX_TOKENS":
                usage["truncated"] = True

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
            cli_art.console.print(f"    {cli_art.WARNING} Embed error: {e}", soft_wrap=True)
            return None
