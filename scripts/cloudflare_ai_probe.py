#!/usr/bin/env python3
"""Phase 1 probe: Cloudflare Workers AI as a fallback candidate.

Tests four models on rewrites via Cloudflare's OpenAI-compatible endpoint.
Uses the same infrastructure as the NIM bakeoff scripts.

Cloudflare Workers AI endpoint:
  https://api.cloudflare.com/client/v4/accounts/{CLOUDFARE_ACCOUNT_ID}/ai/v1

Auth: Bearer {CLOUDFARE_API_TOKEN}
Structured output: guided_json (same as NIM)

Usage:
  RESUME_PROFILE=dominick python scripts/cloudflare_ai_probe.py rewrite
  RESUME_PROFILE=dominick python scripts/cloudflare_ai_probe.py rewrite --model gpt-oss-120b --score
  RESUME_PROFILE=dominick python scripts/cloudflare_ai_probe.py eval
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths
from dotenv import load_dotenv

load_dotenv(profile_paths.env_path(), override=False)

import nim_smoke_test_nvidia_v2 as nim  # noqa: E402
from openai import OpenAI  # noqa: E402

CF_MODELS = {
    "@cf/meta/llama-4-scout-17b-16e-instruct": {
        "max_out": 4096,
        "temp": 0.7,
    },
    "@cf/openai/gpt-oss-120b": {
        # Reasoning model -- needs headroom for thinking tokens
        "max_out": 8192,
        "temp": 0.7,
    },
    "@cf/mistralai/mistral-small-3.1-24b-instruct": {
        "max_out": 4096,
        "temp": 0.7,
    },
    "@cf/qwen/qwen3-30b-a3b-fp8": {
        # Reasoning model -- needs headroom for thinking tokens
        "max_out": 8192,
        "temp": 0.7,
    },
}

ALIASES = {
    "llama-4-scout": "@cf/meta/llama-4-scout-17b-16e-instruct",
    "gpt-oss-120b": "@cf/openai/gpt-oss-120b",
    "mistral-small-24b": "@cf/mistralai/mistral-small-3.1-24b-instruct",
    "qwen3-30b": "@cf/qwen/qwen3-30b-a3b-fp8",
}

REWRITE_MODELS = list(CF_MODELS.keys())

EVAL_MODELS = [
    "@cf/openai/gpt-oss-120b",
    "@cf/mistralai/mistral-small-3.1-24b-instruct",
]


def _resolve_model(name: str) -> str:
    return ALIASES.get(name, name)


def _cf_base_url() -> str:
    account_id = os.getenv("CLOUDFARE_ACCOUNT_ID")
    if not account_id:
        raise SystemExit(
            "CLOUDFARE_ACCOUNT_ID is not set (checked shell and active profile .env: "
            f"{profile_paths.env_path()})."
        )
    return f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"


def _cf_client() -> OpenAI:
    token = os.getenv("CLOUDFARE_API_TOKEN")
    if not token:
        raise SystemExit(
            "CLOUDFARE_API_TOKEN is not set (checked shell and active profile .env: "
            f"{profile_paths.env_path()})."
        )
    return OpenAI(
        base_url=_cf_base_url(),
        api_key=token,
        timeout=nim.CALL_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _patch_nim_for_cf():
    """Monkey-patch the NIM module to use Cloudflare Workers AI."""
    nim._client = _cf_client
    nim.BASE_URL = _cf_base_url()
    nim.MODEL_SETTINGS.update(CF_MODELS)
    # Cloudflare supports guided_json. Put models in STRUCTURED_OUTPUT_MODELS
    # so _structured_call tries json_schema first (may fail), then guided_json
    # (should work), then prompt_only.
    nim.STRUCTURED_OUTPUT_MODELS = frozenset(CF_MODELS.keys())
    nim.SYSTEMLESS_MODELS = frozenset()

    _original_save = nim._save

    def _cf_save(model, stage, result):
        path = _original_save(model, stage, result)
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["provider"] = "cloudflare_ai"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return path

    nim._save = _cf_save


def cmd_rewrite(args):
    """Run rewrite comparison for specified models."""
    _patch_nim_for_cf()

    models = [_resolve_model(args.model)] if args.model else REWRITE_MODELS

    import nim_rewrite_compare_nvidia_v2 as rewrite_compare

    for model in models:
        print(f"\n{'='*72}")
        print(f"  CLOUDFLARE AI REWRITE PROBE: {model}")
        print(f"{'='*72}\n")

        sys.argv = [
            "cloudflare_ai_probe.py",
            "--model",
            model,
            "--n",
            str(args.n),
            "--attempts",
            str(args.attempts),
        ]
        if args.score:
            sys.argv.append("--score")
        if args.match:
            for m in args.match:
                sys.argv.extend(["--match", m])

        try:
            rewrite_compare.main()
        except SystemExit:
            pass
        except Exception as exc:
            print(f"\n  FATAL: {type(exc).__name__}: {exc}\n")


def cmd_eval(args):
    """Run eval comparison for larger models."""
    _patch_nim_for_cf()

    model = _resolve_model(args.model) if args.model else "@cf/openai/gpt-oss-120b"

    import nim_eval_compare_nvidia_v2 as eval_compare

    jd_paths = args.jds
    if not jd_paths:
        import picker

        all_jds = picker.list_all_evaluated_jds()
        if len(all_jds) >= 5:
            step = len(all_jds) // 5
            jd_paths = [all_jds[i * step]["path"] for i in range(5)]
        else:
            jd_paths = [j["path"] for j in all_jds[:5]]

    print(f"\n{'='*72}")
    print(f"  CLOUDFLARE AI EVAL PROBE: {model} ({len(jd_paths)} JDs)")
    print(f"{'='*72}\n")

    sys.argv = ["cloudflare_ai_probe.py", "--model", model] + jd_paths

    try:
        eval_compare.main()
    except SystemExit:
        pass
    except Exception as exc:
        print(f"\n  FATAL: {type(exc).__name__}: {exc}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Probe Cloudflare Workers AI models as resume-builder fallbacks."
    )
    subs = parser.add_subparsers(dest="command", required=True)

    all_choices = list(CF_MODELS.keys()) + list(ALIASES.keys())

    rw = subs.add_parser("rewrite", help="Run rewrite comparison")
    rw.add_argument(
        "--model", choices=all_choices, help="Test one model (default: all four)"
    )
    rw.add_argument("--n", type=int, default=8, help="Bullets per model")
    rw.add_argument("--attempts", type=int, default=3, help="Max attempts per bullet")
    rw.add_argument("--score", action="store_true", help="Gemini judge scoring")
    rw.add_argument("--match", action="append", help="Filter bullets by text")
    rw.set_defaults(func=cmd_rewrite)

    ev = subs.add_parser("eval", help="Run eval comparison")
    ev.add_argument("--model", choices=all_choices, default=None, help="Model to eval")
    ev.add_argument("jds", nargs="*", help="JD file paths")
    ev.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    started = time.perf_counter()
    main()
    print(f"\ntotal elapsed {time.perf_counter() - started:.0f}s")
