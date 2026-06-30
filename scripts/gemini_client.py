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


class GeminiClient:

    _timeout = 90

    @staticmethod
    def sanitize_schema(schema: dict) -> dict:
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

            content = candidates[0].get("content", {})
            parts   = content.get("parts", [])
            text    = parts[0].get("text", "") if parts else ""
            usage   = data.get("usageMetadata", {})
            failure_streak = 0
            return text, usage

        return None, {}