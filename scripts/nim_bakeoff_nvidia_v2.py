#!/usr/bin/env python3
"""Run the NIM bake-off (3 JD evals + bullet rewrite) for each model, serially.

Drives nim_eval_compare_nvidia_v2.py and nim_rewrite_compare_nvidia_v2.py as
subprocesses so one model's crash or timeout cannot stop the rest. Read-only
like the scripts it wraps; raw outputs land in scratch/nim-results/ and a run
log in scratch/nim-results/bakeoff_<timestamp>.log.

Usage:
    RESUME_PROFILE=dominick python scripts/nim_bakeoff_nvidia_v2.py
    python scripts/nim_bakeoff_nvidia_v2.py --dry-run
    python scripts/nim_bakeoff_nvidia_v2.py --model google/gemma-4-31b-it --model z-ai/glm-5.3
    python scripts/nim_bakeoff_nvidia_v2.py --skip-eval --n 10 --score
"""

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nim_smoke_test_nvidia_v2 as nim  # noqa: E402

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
JD_DIR_NAME = "jds"
# The three JDs used in the 2026-09-24 run, spanning the stored score range.
EVAL_JDS = (
    "2026-09-11_WaveMobileMoney_AppliedAIScientistLLMsVoice.json",
    "2026-09-18_MTBank_LeadQualityEngineerTestDataManagement.json",
    "2026-09-23_OpenTrainAI_DataScientistAIModelEvaluationRemoteContract.json",
)


def _commands(model: str, args: argparse.Namespace, jd_paths: list[str]):
    """Yield (label, argv) for one model."""
    if not args.skip_eval:
        yield "eval", [
            sys.executable,
            os.path.join(SCRIPTS, "nim_eval_compare_nvidia_v2.py"),
            "--model",
            model,
            *jd_paths,
        ]
    if not args.skip_rewrite:
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS, "nim_rewrite_compare_nvidia_v2.py"),
            "--model",
            model,
            "--n",
            str(args.n),
        ]
        if args.score:
            cmd.append("--score")
        yield "rewrite", cmd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--model",
        action="append",
        help="repeatable; default: every model in MODEL_SETTINGS",
    )
    ap.add_argument("--n", type=int, default=8, help="bullets for the rewrite test")
    ap.add_argument("--skip-eval", action="store_true")
    ap.add_argument("--skip-rewrite", action="store_true")
    ap.add_argument(
        "--score", action="store_true", help="Gemini judge on rewrites (slow)"
    )
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per script run")
    ap.add_argument("--dry-run", action="store_true", help="print commands only")
    args = ap.parse_args()

    models = args.model or list(nim.MODEL_SETTINGS)
    profile_dir = os.path.join(
        nim.PROJECT_ROOT, JD_DIR_NAME, os.environ.get("RESUME_PROFILE", "dominick")
    )
    jd_paths = [os.path.join(profile_dir, name) for name in EVAL_JDS]
    missing = [p for p in jd_paths if not os.path.exists(p)]
    if missing and not args.skip_eval:
        print("Missing JD file(s) (moved to completed/ or wrong RESUME_PROFILE?):")
        print("\n".join(f"  {p}" for p in missing))
        return 2

    os.makedirs(nim.RESULTS_DIR, exist_ok=True)
    log_path = os.path.join(
        nim.RESULTS_DIR, f"bakeoff_{datetime.now():%Y-%m-%d_%H%M%S}.log"
    )
    summary: list[tuple[str, str, str]] = []
    with open(log_path, "w") as log:
        for model in models:
            for label, argv in _commands(model, args, jd_paths):
                print(f"\n=== {model} [{label}]\n$ {' '.join(argv)}", flush=True)
                if args.dry_run:
                    continue
                started = time.time()
                log.write(f"\n=== {model} [{label}] {datetime.now():%H:%M:%S}\n")
                try:
                    proc = subprocess.run(
                        argv,
                        capture_output=True,
                        text=True,
                        timeout=args.timeout,
                    )
                    out = proc.stdout + proc.stderr
                    status = "ok" if proc.returncode == 0 else f"exit {proc.returncode}"
                except subprocess.TimeoutExpired as exc:
                    out = (
                        (exc.stdout or b"").decode()
                        if isinstance(exc.stdout, bytes)
                        else (exc.stdout or "")
                    )
                    status = f"TIMEOUT {args.timeout}s"
                log.write(out)
                log.flush()
                print(out[-1500:], flush=True)
                summary.append(
                    (model, label, f"{status} ({time.time() - started:.0f}s)")
                )

    print("\n=== Summary")
    for model, label, status in summary:
        print(f"  {model:45s} {label:8s} {status}")
    if not args.dry_run:
        print(f"\nFull log: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
