#!/usr/bin/env python3
"""Mistral API Ministral 8B tuning experiment.

Tests four levers that could improve rewrite quality:
  1. frequency_penalty / presence_penalty grid (proved effective on NIM Mistral)
  2. Temperature sweep (0.3, 0.5 vs current 0.7)
  3. n=3 multi-completion (pick best that passes guard)
  4. random_seed (reproducibility + variance reduction)

Uses the same infrastructure as the NIM bakeoff scripts, monkey-patched
to hit Mistral's own API.

Usage:
  RESUME_PROFILE=dominick python scripts/mistral_tuning_experiment.py penalty
  RESUME_PROFILE=dominick python scripts/mistral_tuning_experiment.py temperature
  RESUME_PROFILE=dominick python scripts/mistral_tuning_experiment.py multi
  RESUME_PROFILE=dominick python scripts/mistral_tuning_experiment.py seed
  RESUME_PROFILE=dominick python scripts/mistral_tuning_experiment.py all
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from itertools import product as grid_product
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import profile_paths
from dotenv import load_dotenv

load_dotenv(profile_paths.env_path(), override=False)

import nim_smoke_test_nvidia_v2 as nim  # noqa: E402
import pandas as pd  # noqa: E402
import rewrite_bullets as rb  # noqa: E402
from openai import OpenAI  # noqa: E402

MODEL = "ministral-8b-2512"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"

# Penalty grid — tighter than the NIM 12-combo sweep, focused on the
# sweet spot found on NIM Mistral (f=0.60/p=0.30 was the winner)
PENALTY_GRID_FREQ = (0.0, 0.30, 0.60, 0.90)
PENALTY_GRID_PRES = (0.0, 0.15, 0.30)

# Temperature values to test (current probe default is 0.7)
TEMP_VALUES = (0.3, 0.5, 0.7)

# Multi-completion: generate N per call, pick first passing
MULTI_N = 3

# Import strict audit from the penalty experiment
from nim_penalty_experiment import _combo_seen, strict_audit  # noqa: E402


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


def _patch_nim():
    """Redirect NIM module to use Mistral API."""
    nim._client = _mistral_client
    nim.BASE_URL = MISTRAL_BASE_URL
    nim.MODEL_SETTINGS[MODEL] = {"max_out": 4096, "temp": 0.7}
    nim.STRUCTURED_OUTPUT_MODELS = frozenset([MODEL])
    nim.SYSTEMLESS_MODELS = frozenset()


def _sample_bullets(n: int) -> pd.DataFrame:
    df = pd.read_csv(rb.CLUSTER_MAP_OUT)
    keep = df[df["rewrite_status"] == "KEEP"]
    manual = df[df["rewrite_status"] == "MANUAL"].head(2)
    wanted_keep = max(0, n - len(manual))
    step = max(1, len(keep) // max(1, wanted_keep))
    sample = pd.concat([keep.iloc[::step].head(wanted_keep), manual]).head(n)
    return sample.reset_index(drop=True)


def _run_one_bullet(
    client: OpenAI,
    row: pd.Series,
    kb: rb.KnowledgeBase,
    rewrite_system: str,
    schema: dict[str, Any],
    combo_key: str,
    *,
    temperature: float = 0.7,
    frequency_penalty: float | None = None,
    presence_penalty: float | None = None,
    seed: int | None = None,
    n_completions: int = 1,
) -> dict[str, Any]:
    source = str(row["Bullet Point"]).strip()
    role = str(row.get("Role / Company", "")).strip()
    tags = str(row.get("Tags", ""))
    weaknesses = str(row.get("weaknesses", ""))
    evidence = f"{source}\n{kb.company_scoped_context(role, tags)}"

    final_text = ""
    production_rejection = None
    attempts: list[dict[str, Any]] = []
    last_result: dict[str, Any] | None = None

    for attempt_no in range(1, rb.MAX_ATTEMPTS + 1):
        prompt = rb.build_rewrite_prompt(
            bullet=source,
            tags=tags,
            weaknesses=weaknesses,
            kb_context=kb.context_block_for_bullet(role, tags),
            attempt=attempt_no,
        )
        prompt_msgs = nim._append_json_instruction(
            [
                {"role": "system", "content": rewrite_system},
                {"role": "user", "content": prompt},
            ],
            schema,
        )

        extra_kwargs: dict[str, Any] = {}
        if frequency_penalty is not None:
            extra_kwargs["frequency_penalty"] = frequency_penalty
        if presence_penalty is not None:
            extra_kwargs["presence_penalty"] = presence_penalty
        if seed is not None:
            extra_kwargs["seed"] = seed

        if n_completions > 1:
            # Non-streaming multi-completion
            best_text = ""
            best_rejection = None
            candidates: list[str] = []
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=prompt_msgs,
                    temperature=temperature,
                    max_tokens=4096,
                    n=n_completions,
                    stream=False,
                    **extra_kwargs,
                )
                for choice in resp.choices:
                    raw = getattr(choice.message, "content", "") or ""
                    try:
                        txt = str(json.loads(raw).get("rewritten_bullet", "")).strip()
                    except (json.JSONDecodeError, AttributeError):
                        txt = ""
                    candidates.append(txt)
                    if not txt:
                        continue
                    rej = rb._rejection_reason(txt, evidence, role, kb)
                    if not rej:
                        best_text = txt
                        best_rejection = None
                        break
                    if not best_text:
                        best_text = txt
                        best_rejection = rej
            except Exception as exc:
                attempts.append(
                    {
                        "attempt": attempt_no,
                        "ok": False,
                        "error": f"{type(exc).__name__}: {exc}"[:300],
                        "n_candidates": 0,
                    }
                )
                last_result = {"ok": False, "error": str(exc)}
                continue

            final_text = best_text
            production_rejection = best_rejection
            attempts.append(
                {
                    "attempt": attempt_no,
                    "ok": True,
                    "n_candidates": len(candidates),
                    "passed_guard": [
                        not rb._rejection_reason(c, evidence, role, kb) if c else False
                        for c in candidates
                    ],
                    "rewritten": final_text,
                    "production_rejected": (
                        production_rejection[0] if production_rejection else None
                    ),
                }
            )
            last_result = {"ok": True}
            if final_text and not production_rejection:
                break
            if production_rejection:
                weaknesses = production_rejection[1]
        else:
            result = nim._call(
                client,
                MODEL,
                prompt_msgs,
                temperature=temperature,
                max_tokens=4096,
                **extra_kwargs,
            )
            last_result = result
            log: dict[str, Any] = {
                "attempt": attempt_no,
                "ok": result["ok"],
                "seconds": result.get("seconds"),
            }
            attempts.append(log)

            if not result["ok"]:
                break
            try:
                final_text = str(
                    json.loads(result["text"]).get("rewritten_bullet", "")
                ).strip()
            except json.JSONDecodeError:
                final_text = ""
            log["rewritten"] = final_text

            production_rejection = (
                rb._rejection_reason(final_text, evidence, role, kb)
                if final_text
                else ("empty rewritten_bullet", "Return a non-empty rewritten_bullet.")
            )
            log["production_rejected"] = (
                production_rejection[0] if production_rejection else None
            )

            if final_text and not production_rejection:
                break
            weaknesses = (
                production_rejection[1]
                if production_rejection
                else "Return a non-empty rewritten_bullet."
            )

    audit = (
        strict_audit(source, final_text, evidence, role, combo_key)
        if final_text
        else {}
    )
    return {
        "role": role,
        "source": source,
        "final_text": final_text,
        "attempts": attempts,
        "production_rejection": (
            production_rejection[0] if production_rejection else None
        ),
        "strict_audit": audit,
        "api_error": (
            (last_result.get("diagnosis") or last_result.get("error", ""))
            if (last_result and not last_result.get("ok"))
            else None
        ),
    }


def _run_config(
    client: OpenAI,
    bullets: pd.DataFrame,
    kb: rb.KnowledgeBase,
    rewrite_system: str,
    schema: dict[str, Any],
    label: str,
    **kwargs: Any,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    auto_pass = final_reject = errors = 0

    for _, row in bullets.iterrows():
        record = _run_one_bullet(
            client, row, kb, rewrite_system, schema, label, **kwargs
        )
        rows.append(record)
        if not record["final_text"] or record.get("api_error"):
            errors += 1
        elif record["production_rejection"]:
            final_reject += 1
        else:
            auto_pass += 1

    strict_passes = sum(
        1 for r in rows if r.get("strict_audit", {}).get("strict_auto_pass")
    )
    return {
        "config": label,
        "n": len(rows),
        "auto_pass": auto_pass,
        "final_reject": final_reject,
        "errors": errors,
        "strict_pass": strict_passes,
        "rows": rows,
        **{k: v for k, v in kwargs.items() if not callable(v)},
    }


def _print_header():
    print(
        f"{'config':<28} {'prod_pass':>9} {'final_rej':>9} {'strict':>7} {'errors':>6}"
    )
    print("-" * 65)


def _print_result(r: dict[str, Any]):
    n = r["n"]
    print(
        f"  {r['config']:<26} "
        f"{r['auto_pass']:>4}/{n}"
        f"  {r['final_reject']:>5}/{n}"
        f"  {r['strict_pass']:>3}/{n}"
        f"  {r['errors']:>3}/{n}"
    )


def _save_results(results: list[dict[str, Any]], experiment: str):
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = os.path.join(
        nim.PROJECT_ROOT, "scratch", "nim-results", f"{ts}_mistral-8b_{experiment}.json"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "model": MODEL,
                "provider": "mistral_api",
                "experiment": experiment,
                "timestamp": ts,
                "configs": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    print(f"\nSaved: {os.path.relpath(path, nim.PROJECT_ROOT)}")


# ---------------------------------------------------------------------------
# Experiment runners
# ---------------------------------------------------------------------------


def run_penalty(client: OpenAI, bullets: pd.DataFrame, kb, sys_prompt, schema):
    """Experiment 1: frequency_penalty x presence_penalty grid."""
    combos = list(grid_product(PENALTY_GRID_FREQ, PENALTY_GRID_PRES))
    print(f"\n{'='*65}")
    print(
        f"  EXPERIMENT 1: Penalty Grid ({len(combos)} combos × {len(bullets)} bullets)"
    )
    print(f"  freq={list(PENALTY_GRID_FREQ)}  press={list(PENALTY_GRID_PRES)}")
    print(f"{'='*65}\n")

    results = []
    _print_header()
    for freq, press in combos:
        label = f"f={freq:.2f}/p={press:.2f}"
        _combo_seen.clear()
        r = _run_config(
            client,
            bullets,
            kb,
            sys_prompt,
            schema,
            label,
            frequency_penalty=freq,
            presence_penalty=press,
        )
        results.append(r)
        _print_result(r)

    # Sort by prod_pass desc, then strict_pass desc
    best = sorted(results, key=lambda r: (-r["auto_pass"], -r["strict_pass"]))
    print("\nTop 5 combos:")
    for r in best[:5]:
        print(
            f"  {r['config']:<26}  pass {r['auto_pass']}/{r['n']}  strict {r['strict_pass']}/{r['n']}"
        )

    _save_results(results, "penalty_grid")
    return results


def run_temperature(client: OpenAI, bullets: pd.DataFrame, kb, sys_prompt, schema):
    """Experiment 2: Temperature sweep."""
    print(f"\n{'='*65}")
    print(
        f"  EXPERIMENT 2: Temperature Sweep ({len(TEMP_VALUES)} values × {len(bullets)} bullets)"
    )
    print(f"  temps={list(TEMP_VALUES)}")
    print(f"{'='*65}\n")

    results = []
    _print_header()
    for temp in TEMP_VALUES:
        label = f"temp={temp:.1f}"
        _combo_seen.clear()
        r = _run_config(
            client,
            bullets,
            kb,
            sys_prompt,
            schema,
            label,
            temperature=temp,
        )
        results.append(r)
        _print_result(r)

    _save_results(results, "temperature")
    return results


def run_multi(client: OpenAI, bullets: pd.DataFrame, kb, sys_prompt, schema):
    """Experiment 3: n=3 multi-completion (pick best passing)."""
    print(f"\n{'='*65}")
    print(f"  EXPERIMENT 3: Multi-Completion n={MULTI_N} ({len(bullets)} bullets)")
    print(f"  Generates {MULTI_N} candidates per call, picks first passing guard")
    print(f"{'='*65}\n")

    results = []
    _print_header()

    # Baseline: n=1 (normal)
    _combo_seen.clear()
    r_baseline = _run_config(
        client,
        bullets,
        kb,
        sys_prompt,
        schema,
        "n=1 (baseline)",
        n_completions=1,
    )
    results.append(r_baseline)
    _print_result(r_baseline)

    # Multi: n=3
    _combo_seen.clear()
    r_multi = _run_config(
        client,
        bullets,
        kb,
        sys_prompt,
        schema,
        f"n={MULTI_N} (pick best)",
        n_completions=MULTI_N,
    )
    results.append(r_multi)
    _print_result(r_multi)

    _save_results(results, "multi_completion")
    return results


def run_seed(client: OpenAI, bullets: pd.DataFrame, kb, sys_prompt, schema):
    """Experiment 4: random_seed for deterministic output."""
    print(f"\n{'='*65}")
    print(f"  EXPERIMENT 4: Random Seed ({len(bullets)} bullets × 2 configs)")
    print(f"{'='*65}\n")

    results = []
    _print_header()

    # No seed (current behavior)
    _combo_seen.clear()
    r_no_seed = _run_config(
        client,
        bullets,
        kb,
        sys_prompt,
        schema,
        "no seed (baseline)",
    )
    results.append(r_no_seed)
    _print_result(r_no_seed)

    # With seed=42
    _combo_seen.clear()
    r_seed = _run_config(
        client,
        bullets,
        kb,
        sys_prompt,
        schema,
        "seed=42",
        seed=42,
    )
    results.append(r_seed)
    _print_result(r_seed)

    # Second run with same seed=42 to test reproducibility
    _combo_seen.clear()
    r_seed2 = _run_config(
        client,
        bullets,
        kb,
        sys_prompt,
        schema,
        "seed=42 (run 2)",
        seed=42,
    )
    results.append(r_seed2)
    _print_result(r_seed2)

    # Check reproducibility
    matches = sum(
        1
        for a, b in zip(r_seed["rows"], r_seed2["rows"])
        if a.get("final_text") == b.get("final_text") and a.get("final_text")
    )
    print(
        f"\nReproducibility (seed=42 run1 vs run2): {matches}/{r_seed['n']} identical outputs"
    )

    _save_results(results, "seed")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "experiment",
        choices=["penalty", "temperature", "multi", "seed", "all"],
        help="Which experiment to run",
    )
    parser.add_argument("--n", type=int, default=8, help="Bullets per config")
    parser.add_argument(
        "--score", action="store_true", help="Run Gemini judge scoring on results"
    )
    args = parser.parse_args()

    _patch_nim()

    client = _mistral_client()
    bullets = _sample_bullets(args.n)

    rules = rb.RulesBundle(rb.RULES_DIR, rb.SCORING_DIR)
    kb = rb.KnowledgeBase()
    rewrite_system, _, _ = rb.build_system_prompts(rules, kb)
    schema = rb.RewriteOutputSchema.model_json_schema()

    print(f"\nProfile: {os.environ.get('RESUME_PROFILE', 'morgan')}")
    print(f"Model: {MODEL} (Mistral API)")
    print(f"Bullets: {len(bullets)}")

    # Warmup
    print("\nWarm-up:")
    nim.warmup(client, MODEL)

    started = time.perf_counter()

    experiments = {
        "penalty": run_penalty,
        "temperature": run_temperature,
        "multi": run_multi,
        "seed": run_seed,
    }

    if args.experiment == "all":
        for name, func in experiments.items():
            func(client, bullets, kb, rewrite_system, schema)
    else:
        experiments[args.experiment](client, bullets, kb, rewrite_system, schema)

    print(f"\nTotal elapsed: {time.perf_counter() - started:.0f}s")


if __name__ == "__main__":
    main()
