"""
gemini_client.py — Shared Gemini REST client.

Imported by both orchestrator.py and rewrite_bullets.py to break
the circular import between them.
"""

import json
import os
import random
import re
import time

import requests

API_KEY  = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

RETRYABLE          = {429, 500, 502, 503, 504}
SERVER_ERRORS      = {500, 502, 503, 504}
HIGH_DEMAND_STATUS = 503
BASE_BACKOFF_SECS  = 8
MAX_BACKOFF_SECS   = 90

# Fallback model used when primary fails repeatedly
REWRITE_FALLBACK_MODEL = "gemini-3.1-flash-lite"

# Embedding model + dimension (matches orchestrator.py constants)
EMBED_MODEL = "gemini-embedding-2"
EMBED_DIM   = 768   # gemini-embedding-2 native dimension


class GeminiClient:

    _timeout = 90

    @staticmethod
    def sanitize_schema(schema: dict) -> dict:
        UNSUPPORTED = {"title", "description", "$defs", "$schema", "default", "examples", "additionalProperties"}
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
        url = f"{BASE_URL}/{model}:generateContent?key={API_KEY}"

        valid_tiers = {"standard", "priority", "flex"}
        tier = (service_tier or "standard").strip().lower()
        if tier not in valid_tiers:
            raise ValueError(f"Invalid service_tier {service_tier!r}.")

        failure_streak = 0

        for attempt in range(max_retries):
            current_temp = 0.0 if response_schema is not None else temperature

            generation_config: dict = {"temperature": current_temp}
            if max_output_tokens is not None:
                generation_config["maxOutputTokens"] = int(max_output_tokens)

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
                    generation_config["responseSchema"] = GeminiClient.sanitize_schema(raw_schema)

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
                if (failure_streak >= 2
                        and model != REWRITE_FALLBACK_MODEL
                        and ("pro" in model.lower() or "gemma" in model.lower())):
                    print(f"    WARNING: Transport failures — falling back to {REWRITE_FALLBACK_MODEL}...")
                    model = REWRITE_FALLBACK_MODEL
                    url = f"{BASE_URL}/{model}:generateContent?key={API_KEY}"
                    failure_streak = 0
                sleep_dur = min(BASE_BACKOFF_SECS * (2 ** attempt), MAX_BACKOFF_SECS) + random.uniform(1, 4)
                print(f"    WARNING: Network error ({GeminiClient._timeout}s): {str(e).split()[-1].strip()}. "
                      f"Waiting {sleep_dur:.1f}s before retry {attempt+1}/{max_retries}...")
                time.sleep(sleep_dur)
                continue

            if resp.status_code in SERVER_ERRORS:
                failure_streak += 1
            elif resp.status_code == 429:
                failure_streak = max(failure_streak, 1)

            if resp.status_code == HIGH_DEMAND_STATUS:
                print("    WARNING: Model high demand (503). Treating as transient.")

            if resp.status_code in RETRYABLE:
                if (failure_streak >= 2
                        and model != REWRITE_FALLBACK_MODEL
                        and ("pro" in model.lower() or "gemma" in model.lower())):
                    print(f"    WARNING: Server failures — falling back to {REWRITE_FALLBACK_MODEL}...")
                    model = REWRITE_FALLBACK_MODEL
                    url = f"{BASE_URL}/{model}:generateContent?key={API_KEY}"
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
            return text, usage

        return None, {}

    @staticmethod
    def embed(text: str) -> list[float] | None:
        """
        Generates an embedding vector for the given text using EMBED_MODEL.
        Used by orchestrator.py's mine_bullet_bank() for semantic similarity.
        Native output dimension: 768 (gemini-embedding-2).
        """
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
            print(f"    WARNING: Embed error: {e}")
            return None
