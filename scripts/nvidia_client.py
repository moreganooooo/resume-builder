"""Small, fail-closed NVIDIA hosted-NIM client for benchmark experiments.

The production application remains on GeminiClient. This adapter intentionally
implements the same ``generate`` call shape so the evaluator benchmark can send
its real prompts and Pydantic schemas to NVIDIA's OpenAI-compatible endpoint
without changing ResumeEngine.
"""

from __future__ import annotations

import copy
import json
import os
import random
import re
import sys
import time
from typing import Any, cast

import requests

BASE_URL = os.environ.get(
    "NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"
).rstrip("/")
RETRYABLE = {429, 500, 502, 503, 504}
_TEST_NETWORK_ENV = "RESUME_ALLOW_TEST_NETWORK"


class TestNetworkBlockedError(RuntimeError):
    """Raised when an unmocked unit test reaches NVIDIA's hosted endpoint."""


def _blocked_under_test() -> bool:
    return (
        "unittest" in sys.modules or "pytest" in sys.modules
    ) and not os.environ.get(_TEST_NETWORK_ENV)


def api_key() -> str:
    """Return the hosted-NIM key without caching it or exposing it in metadata."""
    return (
        os.environ.get("NVIDIA_API_KEY") or os.environ.get("NGC_API_KEY") or ""
    ).strip()


def _auth_headers() -> dict[str, str]:
    if _blocked_under_test():
        raise TestNetworkBlockedError(
            "A test tried to call NVIDIA's hosted NIM API. Mock requests.post, "
            f"or set {_TEST_NETWORK_ENV}=1 for an intentional live test."
        )
    key = api_key()
    if not key:
        raise RuntimeError(
            "NVIDIA_API_KEY is not configured in the active profile's .env. "
            "Create a free hosted-endpoint key on build.nvidia.com first."
        )
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _schema_dict(
    response_schema, extra_schema_properties, extra_required
) -> dict | None:
    if response_schema is None:
        return None
    if hasattr(response_schema, "model_json_schema"):
        raw = response_schema.model_json_schema()
    elif hasattr(response_schema, "schema") and callable(response_schema.schema):
        raw = response_schema.schema()
    elif isinstance(response_schema, dict):
        raw = copy.deepcopy(response_schema)
    elif isinstance(response_schema, str):
        raw = json.loads(response_schema)
    else:
        raise TypeError(
            f"Unsupported response_schema type: {type(response_schema).__name__}"
        )
    raw = copy.deepcopy(raw)
    if extra_schema_properties:
        raw["properties"] = {
            **raw.get("properties", {}),
            **extra_schema_properties,
        }
    if extra_required:
        raw["required"] = list(
            dict.fromkeys([*raw.get("required", []), *extra_required])
        )
    return cast(dict, raw)


def _structured_modes() -> list[str]:
    """Preferred hosted-NIM schema dialects, overridable for reproducibility."""
    raw = os.environ.get(
        "NVIDIA_STRUCTURED_MODES", "json_schema,guided_json,json_object"
    )
    allowed = {"json_schema", "guided_json", "json_object"}
    modes = [item.strip() for item in raw.split(",") if item.strip() in allowed]
    return modes or ["json_schema", "guided_json", "json_object"]


def _schema_name(schema: dict) -> str:
    title = str(schema.get("title") or "evaluation_result")
    name = re.sub(r"[^A-Za-z0-9_-]", "_", title).strip("_")
    return name[:64] or "evaluation_result"


def _request_body(
    *,
    model: str,
    system_instruction: str,
    contents: str,
    temperature: float,
    max_output_tokens: int | None,
    schema: dict | None,
    mode: str | None,
) -> dict[str, Any]:
    system = system_instruction
    if schema and mode == "json_object":
        system += (
            "\n\nReturn only one JSON object matching this exact JSON Schema. "
            "Do not add markdown fences or commentary:\n"
            + json.dumps(schema, separators=(",", ":"))
        )
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": contents},
        ],
        "temperature": temperature,
        "max_tokens": int(
            max_output_tokens or os.environ.get("NVIDIA_MAX_OUTPUT_TOKENS", "8192")
        ),
        "stream": False,
    }
    if schema and mode == "json_schema":
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": _schema_name(schema),
                "strict": True,
                "schema": schema,
            },
        }
    elif schema and mode == "guided_json":
        body["nvext"] = {"guided_json": schema}
    elif schema and mode == "json_object":
        body["response_format"] = {"type": "json_object"}
    return body


def _retry_after(response) -> float | None:
    value = response.headers.get("retry-after") if response is not None else None
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _sleep(attempt: int, response=None) -> None:
    if (
        os.environ.get("CI") == "true"
        or os.environ.get("RESUME_BUILDER_TESTING") == "1"
    ):
        return
    hinted = _retry_after(response)
    delay = hinted if hinted is not None else min(2**attempt, 30)
    time.sleep(delay + random.uniform(0.2, 1.0))  # nosec B311


def _extract_text(data: dict) -> tuple[str | None, dict]:
    choices = data.get("choices") or []
    usage = data.get("usage") or {}
    if not choices:
        return None, usage
    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        )
    if content is not None and not isinstance(content, str):
        content = str(content)
    return (content.strip() or None) if content else None, {
        **usage,
        "finish_reason": choice.get("finish_reason"),
        "reasoning_present": bool(message.get("reasoning_content")),
    }


class NvidiaNimClient:
    """OpenAI-compatible hosted-NIM transport used only when explicitly selected."""

    _timeout = int(os.environ.get("NVIDIA_NIM_TIMEOUT", "180"))

    @staticmethod
    def generate(
        model: str,
        system_instruction: str,
        contents: str,
        response_schema=None,
        extra_schema_properties: dict | None = None,
        extra_required: list | None = None,
        temperature: float = 0.0,
        max_retries: int = 3,
        max_output_tokens: int | None = None,
        service_tier: str = "standard",
        model_fallback: bool = False,
        tools: list | None = None,
        inline_file: tuple[bytes, str] | None = None,
        fallbacks: dict | None = None,
    ) -> tuple[str | None, dict]:
        del service_tier, model_fallback, fallbacks
        if tools:
            raise ValueError("NVIDIA evaluator benchmark calls do not support tools")
        if inline_file is not None:
            raise ValueError("NVIDIA evaluator benchmark calls are text-only")
        schema = _schema_dict(response_schema, extra_schema_properties, extra_required)
        modes: list[str | None] = _structured_modes() if schema else [None]
        last_meta: dict[str, Any] = {
            "provider": "nvidia_nim",
            "model": model,
            "structured_mode": None,
        }
        url = f"{BASE_URL}/chat/completions"
        headers = _auth_headers()

        for mode in modes:
            body = _request_body(
                model=model,
                system_instruction=system_instruction,
                contents=contents,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                schema=schema,
                mode=mode,
            )
            for attempt in range(max_retries):
                started = time.monotonic()
                try:
                    response = requests.post(
                        url,
                        headers=headers,
                        json=body,
                        timeout=NvidiaNimClient._timeout,
                    )
                except requests.exceptions.RequestException as exc:
                    last_meta = {
                        "provider": "nvidia_nim",
                        "model": model,
                        "structured_mode": mode,
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    }
                    if attempt + 1 < max_retries:
                        _sleep(attempt)
                        continue
                    break

                elapsed = round(time.monotonic() - started, 3)
                if response.status_code == 200:
                    try:
                        text, usage = _extract_text(response.json())
                    except (ValueError, TypeError) as exc:
                        return None, {
                            "provider": "nvidia_nim",
                            "model": model,
                            "structured_mode": mode,
                            "http_status": 200,
                            "elapsed_seconds": elapsed,
                            "error_type": type(exc).__name__,
                            "error": "hosted NIM returned an unreadable JSON envelope",
                        }
                    return text, {
                        "provider": "nvidia_nim",
                        "model": model,
                        "structured_mode": mode,
                        "http_status": 200,
                        "elapsed_seconds": elapsed,
                        **usage,
                    }

                try:
                    detail = response.json().get("detail") or response.json().get(
                        "error"
                    )
                except ValueError:
                    detail = response.text[:300]
                last_meta = {
                    "provider": "nvidia_nim",
                    "model": model,
                    "structured_mode": mode,
                    "http_status": response.status_code,
                    "elapsed_seconds": elapsed,
                    "error": str(detail)[:500],
                }
                if response.status_code in (400, 404, 422) and schema:
                    # Hosted models do not all expose the same guided-decoding
                    # backend. Try the next documented schema dialect, but
                    # never switch the model being measured.
                    break
                if response.status_code in RETRYABLE and attempt + 1 < max_retries:
                    _sleep(attempt, response)
                    continue
                return None, last_meta
        return None, last_meta
