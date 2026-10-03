#!/usr/bin/env python3
"""Smoke test NVIDIA NIM models against resume-builder-like tasks.

Standalone by design: this never writes to JDs or data.db. It tests endpoint
health, a constrained bullet rewrite, structured JSON, and one read-only fit
evaluation, saving every result under scratch/nim-results/ for comparison.

Examples:
  RESUME_PROFILE=morgan python scripts/nim_smoke_test_v2.py
  RESUME_PROFILE=morgan python scripts/nim_smoke_test_v2.py \
    --model nvidia/nemotron-3-super-120b-a12b
  RESUME_PROFILE=morgan python scripts/nim_smoke_test_v2.py \
    --stage rewrite --stage json
  RESUME_PROFILE=morgan python scripts/nim_smoke_test_v2.py \
    --stage fit --jd jds/morgan/some_role.json

The active profile's .env supplies NVIDIA_API_KEY. It is never printed.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths
from dotenv import load_dotenv

load_dotenv(profile_paths.env_path(), override=False)

from openai import OpenAI  # noqa: E402

BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(PROJECT_ROOT, "scratch", "nim-results")
ALL_STAGES = ("ping", "rewrite", "json", "fit")

SOURCE_BULLET = (
    "Documented campaign workflows and audience logic to support scalable execution."
)

INVENTION_TELLS = re.compile(
    r"\d|%|\$|salesforce|hubspot|marketo|eloqua|adobe|led a team|increased|reduced",
    re.IGNORECASE,
)

JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rewritten_bullet": {"type": "string"},
        "source_facts_preserved": {
            "type": "array",
            "items": {"type": "string"},
        },
        "invented_claims_detected": {"type": "boolean"},
        "needs_human_review": {"type": "boolean"},
    },
    "required": [
        "rewritten_bullet",
        "source_facts_preserved",
        "invented_claims_detected",
        "needs_human_review",
    ],
}

FIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "fit_score": {"type": "number", "minimum": 1, "maximum": 5},
        "recommendation": {
            "type": "string",
            "enum": ["Pursue", "Consider", "Skip"],
        },
        "top_matches": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fit_score", "recommendation", "top_matches", "gaps"],
}

# Only documented, model-specific request fields belong here. max_out is a
# safety ceiling; individual stages make the much smaller task-specific choice.
# Do not apply one model's thinking/reasoning control to another model.
MODEL_SETTINGS: dict[str, dict[str, Any]] = {
    "nvidia/nemotron-3-super-120b-a12b": {
        "effort": "none",
        "max_out": 32768,
        "seed": 42,
    },
    "nvidia/nemotron-3-ultra-550b-a55b": {
        "effort": "none",
        "max_out": 16384,
        "seed": 42,
    },
    "nvidia/nemotron-3.5-lightning-30b-a3b": {
        "max_out": 32768,
        "seed": 42,
        "body": {"chat_template_kwargs": {"enable_thinking": False}},
    },
    "z-ai/glm-5.3": {
        "max_out": 16384,
        "seed": 42,
    },
    "z-ai/glm-5.3-flash": {
        "max_out": 16384,
        "seed": 42,
    },
    "moonshotai/kimi-k3": {
        "effort": "low",
        "temp": 1.0,
        "max_out": 65536,
        "seed": 42,
    },
    "mistralai/mistral-nemotron": {
        "max_out": 4096,
    },
    "deepseek-ai/deepseek-v4.1-flash": {
        "temp": 1.0,
        "max_out": 65536,
    },
    "meta/muse-glimmer-30b": {
        "effort": "none",
        "temp": 0.95,
        "top_p": 1.0,
        "max_out": 131072,
        "seed": 42,
    },
    "openai/gpt-oss-20b": {
        "effort": "low",
        "max_out": 4096,
    },
    "poolside/laguna-xs-2.1": {
        "max_out": 16384,
    },
    "google/gemma-4-31b-it": {
        "max_out": 32768,
        "seed": 42,
        "body": {"chat_template_kwargs": {"enable_thinking": False}},
    },
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": {
        "max_out": 16384,
        "seed": 42,
    },
}

# These model pages document only user/assistant messages. For a fair test,
# merge our system instruction into the first user turn rather than submitting
# an unsupported system role and mistaking a 400 for model weakness.
SYSTEMLESS_MODELS = frozenset(
    {
        "deepseek-ai/deepseek-v4.1-flash",
        "z-ai/glm-5.3",
        "z-ai/glm-5.3-flash",
    }
)

# Models whose NVIDIA pages list structured output. Others skip directly to
# prompt-only JSON rather than spending probe calls discovering a 400.
STRUCTURED_OUTPUT_MODELS = frozenset(
    {
        "z-ai/glm-5.3",
        "z-ai/glm-5.3-flash",
        "moonshotai/kimi-k3",
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nvidia/nemotron-3-super-120b-a12b",
    }
)

REASONING_EFFORTS = ("auto", "none", "low", "medium", "high", "max")


def effort_override(requested: str) -> str | None:
    """CLI value -> explicit override; "auto" means use the model's table."""
    return None if requested == "auto" else requested


def warmup(client: "OpenAI", model: str) -> dict[str, Any]:
    result = stage_ping(client, model)
    status = "ok" if result["ok"] else "FAILED"
    print(f" warmup {status} in {result['seconds']}s ({result.get('diagnosis', '')})")
    return result


MIN_CALL_GAP_SECONDS = 1.6
CALL_TIMEOUT_SECONDS = 150.0
_last_call_at = 0.0


def _client() -> OpenAI:
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        raise SystemExit(
            "NVIDIA_API_KEY is not set (checked shell and active profile .env: "
            f"{profile_paths.env_path()})."
        )
    return OpenAI(
        base_url=BASE_URL,
        api_key=key,
        timeout=CALL_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _pace() -> None:
    global _last_call_at
    wait = MIN_CALL_GAP_SECONDS - (time.perf_counter() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.perf_counter()


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


# _merge is the canonical public name; _merge_dicts is the private implementation.
_merge = _merge_dicts


def apply_settings(model: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Apply only the documented configuration for this specific model."""
    cfg = MODEL_SETTINGS.get(model, {})
    out = dict(kwargs)

    if cfg.get("effort"):
        out["reasoning_effort"] = cfg["effort"]
    if cfg.get("temp") is not None:
        out["temperature"] = cfg["temp"]
    if cfg.get("top_p") is not None:
        out["top_p"] = cfg["top_p"]
    if out.get("max_tokens") and cfg.get("max_out"):
        out["max_tokens"] = min(int(out["max_tokens"]), int(cfg["max_out"]))
    if cfg.get("seed") is not None:
        out["seed"] = cfg["seed"]
    if cfg.get("body"):
        out["extra_body"] = _merge_dicts(cfg["body"], out.get("extra_body") or {})

    return out


def _prepare_messages(
    model: str, messages: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Use model-supported message roles without weakening the instructions."""
    copied = [dict(message) for message in messages]
    if model not in SYSTEMLESS_MODELS:
        return copied

    system_text = "\n\n".join(
        str(message.get("content", ""))
        for message in copied
        if message.get("role") == "system"
    ).strip()
    non_system = [message for message in copied if message.get("role") != "system"]

    if not system_text:
        return non_system
    if non_system and non_system[0].get("role") == "user":
        content = str(non_system[0].get("content", ""))
        non_system[0]["content"] = (
            "[Instructions]\n" f"{system_text}\n\n" "[Task]\n" f"{content}"
        )
        return non_system

    return [{"role": "user", "content": system_text}] + non_system


def _diagnose_error(exc: Exception, seconds: float, got_first_token: bool) -> str:
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    retry_after = headers.get("retry-after") if headers else None

    if "Timeout" in name:
        if got_first_token:
            return "stalled mid-generation after tokens started"
        return f"no first token within {CALL_TIMEOUT_SECONDS:.0f}s; queued, cold, or overloaded"
    if status == 429:
        hint = f", retry-after={retry_after}s" if retry_after else ""
        return f"HTTP 429 rate limited/shared queue limit{hint}"
    if status in (500, 502, 503, 504):
        return f"HTTP {status}: model/gateway unavailable or overloaded"
    if status in (401, 403):
        return f"HTTP {status}: key not authorized for this model/endpoint"
    if status == 404:
        return "HTTP 404: model ID not found on this endpoint"
    if status == 400:
        return "HTTP 400: unsupported parameter, message role, or schema"
    if "Connection" in name:
        return f"connection error after {seconds:.0f}s"
    return f"{name} (status={status})"


def _diagnose_timing(ttft: float, total: float, output_tokens: int | None) -> str:
    if total < 20:
        return "fast"
    generation_seconds = max(total - ttft, 0.01)
    rate = f"{output_tokens / generation_seconds:.0f} tok/s" if output_tokens else "n/a"
    if ttft > total * 0.6:
        return f"queued/cold: {ttft:.0f}s to first token, then {generation_seconds:.0f}s generating"
    return f"slow generation: first token {ttft:.0f}s, {generation_seconds:.0f}s generating ({rate})"


def _call(
    client: OpenAI,
    model: str,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> dict[str, Any]:
    """Make one streamed request; failures are benchmark data, not exceptions."""
    kwargs = apply_settings(model, kwargs)
    messages = _prepare_messages(model, messages)
    _pace()

    started = time.perf_counter()
    first_token_at = None
    parts: list[str] = []
    reasoning_chars = 0
    finish_reason = None
    model_returned = None
    usage = None

    try:
        create_completion: Any = client.chat.completions.create
        stream = create_completion(
            model=model,
            messages=messages,
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        for chunk in stream:
            model_returned = getattr(chunk, "model", None) or model_returned
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if not chunk.choices:
                continue

            choice = chunk.choices[0]
            delta = choice.delta
            piece = getattr(delta, "content", None)
            thought = getattr(delta, "reasoning_content", None) or getattr(
                delta, "reasoning", None
            )

            if (piece or thought) and first_token_at is None:
                first_token_at = time.perf_counter()
            if piece:
                parts.append(piece if isinstance(piece, str) else str(piece))
            if thought:
                reasoning_chars += len(thought)
            finish_reason = choice.finish_reason or finish_reason

    except Exception as exc:  # noqa: BLE001
        seconds = time.perf_counter() - started
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:600],
            "diagnosis": _diagnose_error(exc, seconds, first_token_at is not None),
            "seconds": round(seconds, 1),
            "ttft": round(first_token_at - started, 1) if first_token_at else None,
            "sent_settings": kwargs,
        }

    total = time.perf_counter() - started
    ttft = first_token_at - started if first_token_at else total
    output_tokens = getattr(usage, "completion_tokens", None) if usage else None

    return {
        "ok": True,
        "text": "".join(parts).strip(),
        "had_reasoning": reasoning_chars > 0,
        "finish_reason": finish_reason,
        "model_returned": model_returned,
        "seconds": round(total, 1),
        "ttft": round(ttft, 1),
        "diagnosis": _diagnose_timing(ttft, total, output_tokens),
        "tokens": (
            {
                "in": getattr(usage, "prompt_tokens", None),
                "out": getattr(usage, "completion_tokens", None),
            }
            if usage
            else None
        ),
        "sent_settings": kwargs,
    }


def _json_instruction(schema: dict[str, Any]) -> str:
    return (
        "Reply with ONLY a JSON object matching this schema. "
        "No prose, markdown, or code fences.\n\n"
        f"Schema:\n{json.dumps(schema)}"
    )


def _append_json_instruction(
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
) -> list[dict[str, Any]]:
    copied = [dict(message) for message in messages]
    instruction = _json_instruction(schema)
    if copied and copied[-1].get("role") == "user":
        copied[-1]["content"] = f"{copied[-1].get('content', '')}\n\n{instruction}"
    else:
        copied.append({"role": "user", "content": instruction})
    return copied


def _prompt_only_messages(
    messages: list[dict[str, Any]], schema: dict[str, Any]
) -> list[dict[str, Any]]:
    return _append_json_instruction(messages, schema)


def _structured_call(
    client: OpenAI,
    model: str,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Try supported JSON mechanisms, then a portable prompt-only fallback."""
    routes: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = [
        (
            "response_format.json_schema",
            {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "result", "schema": schema, "strict": True},
                }
            },
            messages,
        ),
        (
            "guided_json",
            {"extra_body": {"guided_json": schema}},
            messages,
        ),
        ("prompt_only", {}, _append_json_instruction(messages, schema)),
    ]

    if model not in STRUCTURED_OUTPUT_MODELS:
        routes = routes[-1:]

    rejected_routes: list[dict[str, str]] = []
    for mode, additions, route_messages in routes:
        result = _call(client, model, route_messages, **kwargs, **additions)
        result["mode"] = mode
        if result["ok"]:
            result["rejected_routes"] = rejected_routes
            return result
        rejected_routes.append({"mode": mode, "error": result["error"][:220]})

    result["rejected_routes"] = rejected_routes
    return result


def _check_json(raw: str, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"valid_json": False, "error": str(exc)[:200]}

    if not isinstance(parsed, dict):
        return {"valid_json": True, "correct_shape": False}

    missing = sorted(set(schema["required"]) - set(parsed))
    extra = sorted(set(parsed) - set(schema["properties"]))
    return {
        "valid_json": True,
        "correct_shape": not missing and not extra,
        "missing_keys": missing,
        "unexpected_keys": extra,
        "parsed": parsed,
    }


def stage_ping(client: OpenAI, model: str) -> dict[str, Any]:
    return _call(
        client,
        model,
        [{"role": "user", "content": "Reply with exactly the word: ready"}],
        temperature=0,
        max_tokens=64,
    )


def stage_rewrite(client: OpenAI, model: str) -> dict[str, Any]:
    result = _call(
        client,
        model,
        [
            {
                "role": "system",
                "content": "You are a precise resume editor. Follow constraints exactly. Do not invent facts.",
            },
            {
                "role": "user",
                "content": (
                    "Rewrite this resume bullet in 28 words or fewer. Preserve every factual claim. "
                    "Do not add a metric, employer, tool, responsibility, or result not in the source. "
                    f"Reply with the bullet only.\n\nSource: {SOURCE_BULLET}"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=350,
    )

    if result["ok"]:
        words = len(result["text"].split())
        result["checks"] = {
            "word_count": words,
            "within_28_words": 0 < words <= 28,
            "no_invented_tells": not bool(INVENTION_TELLS.search(result["text"])),
        }
    return result


def stage_json(client: OpenAI, model: str) -> dict[str, Any]:
    messages = [
        {
            "role": "system",
            "content": "You are an evidence-grounded resume editor. Never add a metric, tool, employer, or result absent from the source.",
        },
        {
            "role": "user",
            "content": f"Source bullet:\n{SOURCE_BULLET}\n\nRewrite it in 28 words or fewer and return the structured assessment.",
        },
    ]
    result = _structured_call(
        client,
        model,
        messages,
        JSON_SCHEMA,
        temperature=0.1,
        max_tokens=650,
    )
    if not result["ok"]:
        return result

    result["checks"] = _check_json(result["text"], JSON_SCHEMA)
    rewritten = (result["checks"].get("parsed") or {}).get("rewritten_bullet", "")
    result["checks"]["no_invented_tells"] = not bool(INVENTION_TELLS.search(rewritten))
    return result


def _candidate_summary() -> str:
    """Compact profile excerpt only; this is not a full-CV test."""
    try:
        profile = profile_paths.profile_yaml()
    except Exception:  # noqa: BLE001
        profile = {}

    candidate = profile.get("candidate", {}) if isinstance(profile, dict) else {}
    parts = [
        str(candidate.get("headline") or candidate.get("title") or "").strip(),
        str(profile.get("north_star") or "").strip()[:600] if profile else "",
    ]
    return "\n".join(part for part in parts if part) or "(no profile summary available)"


def _load_fit_inputs(jd_path: str | None) -> tuple[str, str, dict[str, Any]]:
    import jd_manager

    if jd_path is None:
        candidates = [
            path
            for path in getattr(jd_manager, "get_pending_jds", lambda: [])()
            if jd_manager.read_evaluation(path)
        ]
        if not candidates:
            raise SystemExit("No evaluated JD found; pass --jd PATH.")
        jd_path = candidates[0]

    text = jd_manager.read_jd_text(jd_path)[:9000]
    evaluation = jd_manager.read_evaluation(jd_path) or {}
    return text, _candidate_summary(), {"path": jd_path, "stored": evaluation}


def stage_fit(client: OpenAI, model: str, jd_path: str | None) -> dict[str, Any]:
    jd_text, summary, meta = _load_fit_inputs(jd_path)
    result = _structured_call(
        client,
        model,
        [
            {
                "role": "system",
                "content": "You are a candid recruiter-side evaluator. Judge fit from supplied evidence only; do not assume unstated experience.",
            },
            {
                "role": "user",
                "content": (
                    f"CANDIDATE:\n{summary}\n\nJOB DESCRIPTION:\n{jd_text}\n\n"
                    "Score fit 1-5, where 5 is strong. Return a recommendation, top matches, and gaps."
                ),
            },
        ],
        FIT_SCHEMA,
        temperature=0.1,
        max_tokens=1500,
    )
    result["jd_path"] = meta["path"]
    stored = meta["stored"]
    result["stored_baseline"] = {
        "composite_score": stored.get("composite_score"),
        "fit_score": stored.get("fit_score"),
        "recommendation": stored.get("recommendation"),
    }
    if result["ok"]:
        result["checks"] = _check_json(result["text"], FIT_SCHEMA)
    return result


def _save(model: str, stage: str, result: dict[str, Any]) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", model).strip("-")
    path = os.path.join(
        RESULTS_DIR,
        f"{datetime.now():%Y-%m-%d_%H%M%S}_{slug}_{stage}.json",
    )
    record = {"provider": "nvidia_nim", "model": model, "task": stage, **result}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2, ensure_ascii=False, default=str)
    return path


def _summarize(result: dict[str, Any]) -> str:
    if not result["ok"]:
        return f"FAIL {result['seconds']}s {result.get('diagnosis', '')} [{result['error'][:160]}]"

    bits = [
        f"{result['seconds']}s",
        f"ttft={result['ttft']}s",
        f"[{result.get('diagnosis', '')}]",
        f"tokens={result['tokens']}",
        f"finish={result['finish_reason']}",
    ]
    if not result["text"]:
        suffix = " (reasoning only)" if result["had_reasoning"] else ""
        bits.append(f"EMPTY CONTENT{suffix}")
    if result.get("mode"):
        bits.append(f"mode={result['mode']}")

    checks = {
        key: value for key, value in result.get("checks", {}).items() if key != "parsed"
    }
    if checks:
        bits.append(f"checks={checks}")
    return "ok " + " ".join(bits)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--stage", action="append", choices=ALL_STAGES)
    parser.add_argument("--jd", help="JD JSON path for the fit stage")
    args = parser.parse_args()

    client = _client()
    stages = args.stage or list(ALL_STAGES)
    print(f"\nModel: {args.model}\nStages: {', '.join(stages)}\n")

    for stage in stages:
        print(f"[{stage}] ...", flush=True)
        if stage == "ping":
            result = stage_ping(client, args.model)
        elif stage == "rewrite":
            result = stage_rewrite(client, args.model)
        elif stage == "json":
            result = stage_json(client, args.model)
        else:
            result = stage_fit(client, args.model, args.jd)

        path = _save(args.model, stage, result)
        print(f"[{stage}] {_summarize(result)}")
        if result["ok"] and result["text"]:
            print("  " + result["text"][:700].replace("\n", "\n  "))
        if stage == "fit":
            print(f"  stored baseline: {result['stored_baseline']}")
        print(f"  saved: {os.path.relpath(path, PROJECT_ROOT)}\n")

        if stage == "ping" and not result["ok"]:
            print("Endpoint/key/model failed -- skipping remaining stages.")
            break


if __name__ == "__main__":
    main()
