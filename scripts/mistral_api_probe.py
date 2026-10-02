#!/usr/bin/env python3
"""Phase 1 probe: Mistral's own API (api.mistral.ai) as a fallback candidate.

Tests Ministral 3B/8B/14B on rewrites (can small models handle bullet
rewriting?) and 14B on eval. Also tests Codestral on rewrites for
completeness. Uses the same infrastructure as the NIM bakeoff scripts.

Mistral's API is OpenAI-compatible, so we reuse the OpenAI client with
a different base_url and MISTRAL_API_KEY instead of NVIDIA_API_KEY.

Usage:
  RESUME_PROFILE=dominick python scripts/mistral_api_probe.py rewrite
  RESUME_PROFILE=dominick python scripts/mistral_api_probe.py rewrite --model ministral-3b-2512
  RESUME_PROFILE=dominick python scripts/mistral_api_probe.py rewrite --model ministral-14b-2512 --score
  RESUME_PROFILE=dominick python scripts/mistral_api_probe.py eval
  RESUME_PROFILE=dominick python scripts/mistral_api_probe.py eval --jd path/to/jd.json [...]

The rewrite subcommand runs all four models by default (3B, 8B, 14B,
codestral) with n=8 bullets each. Pass --model to test one.

The eval subcommand runs only 14B (3B/8B are too small for the full
eval schema). Pass JD paths as positional args, or it picks 5.
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

MISTRAL_BASE_URL = "https://api.mistral.ai/v1"

MISTRAL_MODELS = {
    "ministral-3b-2512": {
        "max_out": 32768,
        "temp": 0.7,
    },
    "ministral-8b-2512": {
        "max_out": 32768,
        "temp": 0.7,
    },
    "ministral-14b-2512": {
        "max_out": 32768,
        "temp": 0.7,
    },
    "codestral-2508": {
        "max_out": 32768,
        "temp": 0.7,
    },
}

REWRITE_MODELS = [
    "ministral-3b-2512",
    "ministral-8b-2512",
    "ministral-14b-2512",
    "codestral-2508",
]

EVAL_MODELS = ["ministral-14b-2512"]


def _mistral_client() -> OpenAI:
    key = os.getenv("MISTRAL_API_KEY")
    if not key:
        raise SystemExit(
            "MISTRAL_API_KEY is not set (checked shell and active profile .env: "
            f"{profile_paths.env_path()})."
        )
    return OpenAI(
        base_url=MISTRAL_BASE_URL,
        api_key=key,
        timeout=nim.CALL_TIMEOUT_SECONDS,
        max_retries=0,
    )


def _patch_nim_for_mistral():
    """Monkey-patch the NIM module to use Mistral's API."""
    nim._client = _mistral_client
    nim.BASE_URL = MISTRAL_BASE_URL
    nim.MODEL_SETTINGS.update(MISTRAL_MODELS)
    # Mistral supports response_format json_schema with strict mode on all
    # models (verified). Enable structured output for all.
    nim.STRUCTURED_OUTPUT_MODELS = frozenset(MISTRAL_MODELS.keys())
    nim.SYSTEMLESS_MODELS = frozenset()

    # Patch _save to record provider as "mistral_api"
    _original_save = nim._save

    def _mistral_save(model, stage, result):
        path = _original_save(model, stage, result)
        import json

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["provider"] = "mistral_api"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        return path

    nim._save = _mistral_save


def cmd_rewrite(args):
    """Run rewrite comparison for specified models."""
    _patch_nim_for_mistral()

    models = [args.model] if args.model else REWRITE_MODELS

    # Build argv for nim_rewrite_compare_nvidia_v2
    import nim_rewrite_compare_nvidia_v2 as rewrite_compare

    for model in models:
        print(f"\n{'='*72}")
        print(f"  MISTRAL API REWRITE PROBE: {model}")
        print(f"{'='*72}\n")

        sys.argv = [
            "mistral_api_probe.py",
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
    """Run eval comparison for 14B."""
    _patch_nim_for_mistral()

    model = args.model or "ministral-14b-2512"

    import nim_eval_compare_nvidia_v2 as eval_compare

    jd_paths = args.jds
    if not jd_paths:
        # Pick 5 diverse JDs from the profile
        import picker

        all_jds = picker.list_all_evaluated_jds()
        if len(all_jds) >= 5:
            step = len(all_jds) // 5
            jd_paths = [all_jds[i * step]["path"] for i in range(5)]
        else:
            jd_paths = [j["path"] for j in all_jds[:5]]

    print(f"\n{'='*72}")
    print(f"  MISTRAL API EVAL PROBE: {model} ({len(jd_paths)} JDs)")
    print(f"{'='*72}\n")

    sys.argv = ["mistral_api_probe.py", "--model", model] + jd_paths

    try:
        eval_compare.main()
    except SystemExit:
        pass
    except Exception as exc:
        print(f"\n  FATAL: {type(exc).__name__}: {exc}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Probe Mistral API models as resume-builder fallbacks."
    )
    subs = parser.add_subparsers(dest="command", required=True)

    rw = subs.add_parser("rewrite", help="Run rewrite comparison")
    rw.add_argument(
        "--model",
        choices=REWRITE_MODELS,
        help="Test one model (default: all four)",
    )
    rw.add_argument("--n", type=int, default=8, help="Bullets per model")
    rw.add_argument("--attempts", type=int, default=3, help="Max attempts per bullet")
    rw.add_argument("--score", action="store_true", help="Gemini judge scoring")
    rw.add_argument("--match", action="append", help="Filter bullets by text")
    rw.set_defaults(func=cmd_rewrite)

    ev = subs.add_parser("eval", help="Run eval comparison (14B only)")
    ev.add_argument(
        "--model",
        choices=EVAL_MODELS + ["ministral-8b-2512"],
        default=None,
        help="Model to eval (default: ministral-14b-2512)",
    )
    ev.add_argument("jds", nargs="*", help="JD file paths")
    ev.set_defaults(func=cmd_eval)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    started = time.perf_counter()
    main()
    print(f"\ntotal elapsed {time.perf_counter() - started:.0f}s")
