"""
Smoke test for models hosted on NVIDIA's NIM API (OpenAI-compatible).

Standalone by design: nothing here is wired into the resume pipeline. It
auditions a model on the tasks the pipeline depends on -- constraint
obedience, structured JSON, and job-fit judgement -- and saves every result
under scratch/nim-results/ (gitignored) so models can be compared later.

Usage:
    RESUME_PROFILE=morgan python scripts/nim_smoke_test.py
    python scripts/nim_smoke_test.py --model google/gemma-4-31b-it
    python scripts/nim_smoke_test.py --stage rewrite --stage json
    python scripts/nim_smoke_test.py --jd jds/morgan/some_role.json

Stages (run serially; free NIM limits are shared and per-model):
  ping     one-line reply: does the endpoint + key work at all?
  rewrite  28-word bullet rewrite: constraint obedience, invented facts?
  json     strict schema (tries response_format, guided_json, then prompt-only), checked in code
  fit      1-5 fit judgement on a real JD, compared with the stored score
           (read-only: nothing is saved to the JD or data.db)

The key is read from NVIDIA_API_KEY in the active profile's .env (or the
shell). It is never printed.
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
RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scratch",
    "nim-results",
)
ALL_STAGES = ("ping", "rewrite", "json", "fit")

SOURCE_BULLET = (
    "Documented campaign workflows and audience logic to support scalable execution."
)
# Anything here appearing in a rewrite is an invented claim -- the source has
# no metric, tool, or employer.
INVENTION_TELLS = re.compile(
    r"\d|%|\$|salesforce|hubspot|marketo|eloqua|adobe|led a team|increased|reduced",
    re.IGNORECASE,
)

JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rewritten_bullet": {"type": "string"},
        "source_facts_preserved": {"type": "array", "items": {"type": "string"}},
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
        "recommendation": {"type": "string", "enum": ["Pursue", "Consider", "Skip"]},
        "top_matches": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["fit_score", "recommendation", "top_matches", "gaps"],
}


# Per-model request settings, read off each model's NVIDIA "Body Params" page
# (2026-09-24). Only parameters a page LISTS are sent -- an unlisted one is
# ignored at best and, for reasoning_effort, was seen falling back to the
# slowest mode at worst.
#   effort   top-level reasoning_effort (None = the page has no such control)
#   temp     fixed temperature where the model's page recommends one; None
#            keeps whatever the caller asked for
#   max_out  the page's max_tokens ceiling (a larger request 500s/empties)
#   seed     pinned so reruns are comparable (only where the page lists it)
#   body     extra_body fields (reasoning_budget, chat_template_kwargs)
MODEL_SETTINGS: dict[str, dict[str, Any]] = {
    "nvidia/nemotron-3-super-120b-a12b": {
        "effort": "none",
        "max_out": 32768,
        "seed": 42,
    },
    "nvidia/nemotron-3.5-lightning-30b-a3b": {
        "max_out": 32768,
        "seed": 42,
        "body": {"reasoning_budget": 0},
    },
    "z-ai/glm-5.3": {"max_out": 16384, "seed": 42},
    "z-ai/glm-5.3-flash": {"max_out": 16384, "seed": 42},
    "moonshotai/kimi-k3": {"effort": "low", "temp": 1.0, "max_out": 65536, "seed": 42},
    "mistralai/mistral-nemotron": {"max_out": 4096},
    "deepseek-ai/deepseek-v4.1-flash": {"temp": 1.0, "max_out": 65536},
    "meta/muse-glimmer-30b": {
        "effort": "none",
        "temp": 0.95,
        "max_out": 131072,
        "seed": 42,
    },
    "openai/gpt-oss-20b": {"effort": "low", "max_out": 4096},
    "poolside/laguna-xs-2.1": {"max_out": 16384},
    "google/gemma-4-31b-it": {
        "max_out": 32768,
        "seed": 42,
        "body": {"chat_template_kwargs": {"enable_thinking": False}},
    },
}
REASONING_EFFORTS = ("auto", "none", "low", "medium", "high", "max")


def effort_override(requested: str) -> str | None:
    """CLI value -> explicit override; "auto" means use the model's table."""
    return None if requested == "auto" else requested


def apply_settings(model: str, kwargs: dict) -> dict:
    """Overlay the model's documented settings on a call's kwargs."""
    cfg = MODEL_SETTINGS.get(model, {})
    out = dict(kwargs)
    override = out.pop("reasoning_effort", None)
    effort = override or cfg.get("effort")
    if effort:
        out["reasoning_effort"] = effort
    if cfg.get("temp") is not None and "temperature" in out:
        out["temperature"] = cfg["temp"]
    if out.get("max_tokens") and cfg.get("max_out"):
        out["max_tokens"] = min(out["max_tokens"], cfg["max_out"])
    if cfg.get("seed") is not None:
        out["seed"] = cfg["seed"]
    if cfg.get("body"):
        out["extra_body"] = {**cfg["body"], **(out.get("extra_body") or {})}
    return out


# Models whose NVIDIA model page lists "Structured Output". Everything else
# goes straight to the prompt-only route instead of burning calls on 400s.
STRUCTURED_OUTPUT_MODELS = frozenset(
    {
        "z-ai/glm-5.3",
        "z-ai/glm-5.3-flash",
        "moonshotai/kimi-k3",
        "nvidia/nemotron-3.5-lightning-30b-a3b",
        "nvidia/nemotron-3-super-120b-a12b",
    }
)

# NVIDIA documents "up to 40 rpm"; 1.6s between calls keeps us just under it.
MIN_CALL_GAP_SECONDS = 1.6
CALL_TIMEOUT_SECONDS = 150.0
_last_call_at = 0.0


def _client() -> OpenAI:
    key = os.getenv("NVIDIA_API_KEY")
    if not key:
        raise SystemExit(
            "NVIDIA_API_KEY is not set (checked the shell and the active "
            f"profile's .env: {profile_paths.env_path()})."
        )
    # max_retries=0: the SDK's silent retries would hide exactly the stalls
    # and rate limits this harness exists to report.
    return OpenAI(
        base_url=BASE_URL, api_key=key, timeout=CALL_TIMEOUT_SECONDS, max_retries=0
    )


def _pace() -> None:
    global _last_call_at
    wait = MIN_CALL_GAP_SECONDS - (time.perf_counter() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.perf_counter()


def _diagnose_error(exc: Exception, seconds: float, got_first_token: bool) -> str:
    """Plain-English reason a call failed, from the exception and timing."""
    name = type(exc).__name__
    status = getattr(exc, "status_code", None)
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    retry_after = headers.get("retry-after") if headers else None
    if "Timeout" in name:
        if got_first_token:
            return (
                f"stalled mid-generation: tokens had started, then nothing for "
                f"{CALL_TIMEOUT_SECONDS:.0f}s (overloaded or dropped stream)"
            )
        return (
            f"no first token within {CALL_TIMEOUT_SECONDS:.0f}s: request was "
            "probably queued behind other free-tier users, or the model is cold"
        )
    if status == 429:
        hint = f", retry-after={retry_after}s" if retry_after else ""
        return f"HTTP 429 rate limited (40 rpm cap or shared-queue limit{hint})"
    if status in (502, 503, 504):
        return f"HTTP {status}: model/gateway unavailable or overloaded (transient)"
    if status in (401, 403):
        return f"HTTP {status}: key not authorised for this model or endpoint"
    if status == 404:
        return "HTTP 404: model id not found on this endpoint"
    if status == 400:
        return "HTTP 400: request rejected (unsupported parameter or bad schema)"
    if "Connection" in name:
        return f"connection error after {seconds:.0f}s (network or endpoint down)"
    return f"{name} (status={status})"


def _call(client: OpenAI, model: str, messages: list, **kwargs) -> dict:
    """One streamed chat call. Failures are data, not raises.

    Streaming lets a slow call be classified: a long wait for the FIRST token
    is queueing/cold start; a long generation after a quick first token is
    just a slow or verbose model.
    """
    kwargs = apply_settings(model, kwargs)
    _pace()
    started = time.perf_counter()
    first_token_at = None
    parts, reasoning_chars, finish, model_returned, usage = [], 0, None, None, None
    try:
        stream = client.chat.completions.create(
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
                parts.append(piece)
            if thought:
                reasoning_chars += len(thought)
            finish = choice.finish_reason or finish
    except Exception as exc:  # noqa: BLE001 — any transport/API error is a result
        seconds = time.perf_counter() - started
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}"[:600],
            "diagnosis": _diagnose_error(exc, seconds, first_token_at is not None),
            "seconds": round(seconds, 1),
            "ttft": round(first_token_at - started, 1) if first_token_at else None,
        }
    total = time.perf_counter() - started
    ttft = (first_token_at - started) if first_token_at else total
    out_tokens = usage.completion_tokens if usage else None
    return {
        "ok": True,
        "text": "".join(parts).strip(),
        # Reasoning models can spend the whole budget thinking and return no
        # content; surface that instead of reporting a mysterious empty string.
        "had_reasoning": reasoning_chars > 0,
        "finish_reason": finish,
        "model_returned": model_returned,
        "seconds": round(total, 1),
        "ttft": round(ttft, 1),
        "diagnosis": _diagnose_timing(ttft, total, out_tokens),
        "tokens": (
            {"in": usage.prompt_tokens, "out": usage.completion_tokens}
            if usage
            else None
        ),
    }


def _diagnose_timing(ttft: float, total: float, out_tokens: int | None) -> str:
    """Where a slow-but-successful call spent its time."""
    if total < 20:
        return "fast"
    gen = max(total - ttft, 0.01)
    rate = f"{out_tokens / gen:.0f} tok/s" if out_tokens else "n/a"
    if ttft > 0.6 * total:
        return f"queued/cold: {ttft:.0f}s to first token, then {gen:.0f}s generating"
    return (
        f"slow generation: first token in {ttft:.0f}s, {gen:.0f}s generating ({rate})"
    )


def warmup(client: OpenAI, model: str) -> dict:
    """Cheap first call so a cold start is paid (and timed) once, up front."""
    res = _call(
        client,
        model,
        [{"role": "user", "content": "Reply with exactly the word: ready"}],
        temperature=0,
        max_tokens=64,
    )
    state = "ok" if res["ok"] else "FAILED"
    print(f"  warmup {state} in {res['seconds']}s " f"({res.get('diagnosis', '')})")
    return res


def _structured_call(
    client: OpenAI, model: str, messages: list, schema: dict, **kwargs
) -> dict:
    """Try each structured-output route until one works; record which.

    The hosted endpoint rejects nvext.guided_json for some models, so the
    routes are: OpenAI-style response_format, top-level guided_json, and
    finally a prompt-only instruction (parsed and checked in code).
    """
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
        ("guided_json", {"extra_body": {"guided_json": schema}}, messages),
        (
            "prompt_only",
            {},
            messages
            + [
                {
                    "role": "user",
                    "content": "Reply with ONLY a JSON object matching this "
                    f"schema, no prose or code fences:\n{json.dumps(schema)}",
                }
            ],
        ),
    ]
    attempts: list[dict[str, Any]] = []
    base_body = kwargs.pop("extra_body", None) or {}
    if model not in STRUCTURED_OUTPUT_MODELS:
        routes = routes[-1:]  # no listed structured-output support: prompt-only
    for mode, extra, msgs in routes:
        extra = dict(extra)
        body = {**base_body, **extra.pop("extra_body", {})}
        if body:
            extra["extra_body"] = body
        result = _call(client, model, msgs, **kwargs, **extra)
        result["mode"] = mode
        if result["ok"]:
            result["rejected_routes"] = attempts
            return result
        attempts.append({"mode": mode, "error": result["error"][:200]})
    result["rejected_routes"] = attempts
    return result


def stage_ping(client: OpenAI, model: str) -> dict:
    return _call(
        client,
        model,
        [{"role": "user", "content": "Reply with exactly the word: ready"}],
        temperature=0,
        max_tokens=400,
    )


def stage_rewrite(client: OpenAI, model: str) -> dict:
    result = _call(
        client,
        model,
        [
            {
                "role": "system",
                "content": (
                    "You are a precise resume editor. Follow constraints "
                    "exactly. Do not invent facts."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Rewrite this resume bullet in 28 words or fewer. Preserve "
                    "every factual claim. Do not add a metric, employer, tool, "
                    "responsibility, or result not in the source. Reply with "
                    f"the bullet only.\n\nSource: {SOURCE_BULLET}"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=1200,
    )
    if result["ok"]:
        words = len(result["text"].split())
        result["checks"] = {
            "word_count": words,
            "within_28_words": 0 < words <= 28,
            "no_invented_tells": not INVENTION_TELLS.search(result["text"]),
        }
    return result


def stage_json(client: OpenAI, model: str) -> dict:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an evidence-grounded resume editor. Never add a "
                "metric, tool, employer, or result absent from the source."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Source bullet:\n{SOURCE_BULLET}\n\nRewrite it in 28 words "
                "or fewer and return the structured assessment."
            ),
        },
    ]
    result = _structured_call(
        client, model, messages, JSON_SCHEMA, temperature=0.1, max_tokens=1500
    )
    if not result["ok"]:
        return result
    result["checks"] = _check_json(result["text"], JSON_SCHEMA)
    rewritten = (result["checks"].get("parsed") or {}).get("rewritten_bullet", "")
    result["checks"]["no_invented_tells"] = not INVENTION_TELLS.search(rewritten)
    return result


def _check_json(raw: str, schema: dict) -> dict:
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


def _load_fit_inputs(jd_path: str | None) -> tuple[str, str, dict]:
    """Return (jd_text, candidate_summary, stored_evaluation)."""
    import jd_manager

    if jd_path is None:
        candidates = [
            p
            for p in getattr(jd_manager, "get_pending_jds", lambda: [])()
            if jd_manager.read_evaluation(p)
        ]
        if not candidates:
            raise SystemExit("No evaluated JD found; pass --jd PATH.")
        jd_path = candidates[0]
    # read_jd_text strips persisted _metadata keys so they cannot leak in.
    text = jd_manager.read_jd_text(jd_path)[:9000]
    evaluation = jd_manager.read_evaluation(jd_path) or {}
    summary = _candidate_summary()
    return text, summary, {"path": jd_path, "stored": evaluation}


def _candidate_summary() -> str:
    """A compact profile excerpt: headline + skills. Never the full CV."""
    try:
        profile = profile_paths.profile_yaml()
    except Exception:  # noqa: BLE001 — a missing profile should not kill the test
        profile = {}
    cand = profile.get("candidate", {}) if isinstance(profile, dict) else {}
    parts = [
        str(cand.get("headline") or cand.get("title") or "").strip(),
        str(profile.get("north_star", "")).strip()[:600] if profile else "",
    ]
    return "\n".join(p for p in parts if p) or "(no profile summary available)"


def stage_fit(client: OpenAI, model: str, jd_path: str | None) -> dict:
    jd_text, summary, meta = _load_fit_inputs(jd_path)
    result = _structured_call(
        client,
        model,
        [
            {
                "role": "system",
                "content": (
                    "You are a candid recruiter-side evaluator. Judge fit from "
                    "the evidence given only; do not assume unstated experience."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"CANDIDATE:\n{summary}\n\nJOB DESCRIPTION:\n{jd_text}\n\n"
                    "Score fit 1-5 (5 = strong), give a recommendation, the top "
                    "matches, and the gaps."
                ),
            },
        ],
        FIT_SCHEMA,
        temperature=0.1,
        max_tokens=2500,
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


def _save(model: str, stage: str, result: dict) -> str:
    os.makedirs(RESULTS_DIR, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", model).strip("-")
    path = os.path.join(
        RESULTS_DIR, f"{datetime.now():%Y-%m-%d_%H%M%S}_{slug}_{stage}.json"
    )
    record = {"provider": "nvidia_nim", "model": model, "task": stage, **result}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    return path


def _summarize(stage: str, r: dict) -> str:
    if not r["ok"]:
        return f"FAIL  {r['seconds']}s  {r.get('diagnosis', '')}  [{r['error'][:160]}]"
    bits = [
        f"{r['seconds']}s",
        f"[{r.get('diagnosis', '')}]",
        f"tokens={r['tokens']}",
        f"finish={r['finish_reason']}",
    ]
    if not r["text"]:
        bits.append(
            "EMPTY CONTENT" + (" (reasoning only)" if r["had_reasoning"] else "")
        )
    if r.get("mode"):
        bits.append(f"mode={r['mode']}")
    checks = {k: v for k, v in r.get("checks", {}).items() if k != "parsed"}
    if checks:
        bits.append(f"checks={checks}")
    return "ok    " + "  ".join(bits)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--stage", action="append", choices=ALL_STAGES)
    ap.add_argument("--jd", help="JD json path for the fit stage")
    args = ap.parse_args()

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
        print(f"[{stage}] {_summarize(stage, result)}")
        if result["ok"] and result["text"]:
            print("        " + result["text"][:400].replace("\n", "\n        "))
        if stage == "fit":
            print(f"        stored baseline: {result['stored_baseline']}")
        print(f"        saved: {os.path.relpath(path)}\n")
        if stage == "ping" and not result["ok"]:
            print("Endpoint/key/model failed -- skipping remaining stages.")
            break


if __name__ == "__main__":
    main()
