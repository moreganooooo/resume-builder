#!/usr/bin/env python3
"""Standalone NVIDIA NIM settings experiment for Lightning and GPT-OSS.

Depends only on the working scripts/nim_smoke_test_nvidia_v2.py. It patches the
v2 structured-output helper in memory so Lightning thinking settings and the
guided_json route share one merged extra_body rather than crashing.

Tests:
  Lightning rewrites: temperature 0.4 vs 0.7, production retry/guard path.
  Lightning evals: thinking off/on (512 budget) x temperature 0.0/1.0.
  GPT-OSS evals: reasoning low vs none.

Read-only: no JD, data.db, or bullet-bank source is changed.
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

import jd_manager  # noqa: E402
import nim_smoke_test_nvidia_v2 as nim  # noqa: E402
import orchestrator  # noqa: E402
import pandas as pd  # noqa: E402
import rewrite_bullets as rb  # noqa: E402
from schemas import CapabilityEvaluationSchema, RecruiterEvaluationSchema  # noqa: E402

LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
GPT_OSS = "openai/gpt-oss-20b"
DEFAULT_JDS = (
    "2026-09-11_WaveMobileMoney_AppliedAIScientistLLMsVoice.json",
    "2026-09-18_MTBank_LeadQualityEngineerTestDataManagement.json",
    "2026-09-23_OpenTrainAI_DataScientistAIModelEvaluationRemoteContract.json",
)

LIGHTNING_VARIANTS = (
    (
        "lightning_off_t0",
        LIGHTNING,
        0.0,
        None,
        None,
        {"chat_template_kwargs": {"enable_thinking": False}},
    ),
    (
        "lightning_off_t1_top_p095",
        LIGHTNING,
        1.0,
        0.95,
        None,
        {"chat_template_kwargs": {"enable_thinking": False}},
    ),
    (
        "lightning_think512_t0",
        LIGHTNING,
        0.0,
        None,
        None,
        {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 512},
    ),
    (
        "lightning_think512_t1_top_p095",
        LIGHTNING,
        1.0,
        0.95,
        None,
        {"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 512},
    ),
)
GPT_VARIANTS = (
    ("gpt_oss_low", GPT_OSS, 0.0, None, "low", None),
    ("gpt_oss_none", GPT_OSS, 0.0, None, "none", None),
)
REWRITE_VARIANTS = (("lightning_rewrite_t04", 0.4), ("lightning_rewrite_t07", 0.7))


def _fixed_structured_call(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """v2 structured output with merged extra_body arguments."""
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
        ("prompt_only", {}, nim._prompt_only_messages(messages, schema)),
    ]
    if model not in nim.STRUCTURED_OUTPUT_MODELS:
        routes = routes[-1:]

    rejected: list[dict[str, str]] = []
    for mode, additions, route_messages in routes:
        call_kwargs = dict(kwargs)
        if additions.get("extra_body"):
            call_kwargs["extra_body"] = nim._merge(
                call_kwargs.get("extra_body") or {},
                additions["extra_body"],
            )
        call_kwargs.update(
            {key: value for key, value in additions.items() if key != "extra_body"}
        )
        result = nim._call(client, model, route_messages, **call_kwargs)
        result["mode"] = mode
        if result["ok"]:
            result["rejected_routes"] = rejected
            return result
        rejected.append({"mode": mode, "error": result["error"][:220]})
    result["rejected_routes"] = rejected
    return result


# Patch only this process; the working v2 helper file on disk remains unchanged.
nim._structured_call = _fixed_structured_call


def _mean(values: dict[str, Any] | None) -> float | None:
    nums = [
        value for value in (values or {}).values() if isinstance(value, (int, float))
    ]
    return round(sum(nums) / len(nums), 2) if nums else None


def _validate(result: dict[str, Any], schema_cls: Any) -> dict[str, Any]:
    if not result["ok"]:
        return result
    try:
        result["parsed"] = json.loads(result["text"])
        schema_cls.model_validate(result["parsed"])
        result["schema_valid"] = True
    except Exception as exc:  # noqa: BLE001
        result["parsed"] = None
        result["schema_valid"] = False
        result["schema_error"] = str(exc)[:300]
    return result


def _eval_stage(
    client: Any,
    engine: Any,
    variant: tuple,
    prompt_file: str,
    schema_cls: Any,
    context: str,
    max_tokens: int,
) -> dict[str, Any]:
    _name, model, temperature, top_p, effort, extra_body = variant
    kwargs: dict[str, Any] = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "reasoning_effort": effort,
    }
    if top_p is not None:
        kwargs["top_p"] = top_p
    if extra_body:
        kwargs["extra_body"] = extra_body
    result = nim._structured_call(
        client,
        model,
        [
            {"role": "system", "content": engine.load_prompt(prompt_file)},
            {"role": "user", "content": context},
        ],
        schema_cls.model_json_schema(),
        **kwargs,
    )
    return _validate(result, schema_cls)


def _run_eval_variant(
    client: Any, engine: Any, variant: tuple, paths: list[str], max_tokens: int
) -> dict[str, Any]:
    name = variant[0]
    print(f"\n=== {name} ===")
    rows = []
    for path in paths:
        jd_name = os.path.basename(path).removesuffix(".json")
        baseline = jd_manager.read_evaluation(path) or {}
        context = engine.build_fit_evaluation_context(jd_manager.read_jd_text(path), [])
        started = time.perf_counter()
        cap = _eval_stage(
            client,
            engine,
            variant,
            "evaluate_capability.md",
            CapabilityEvaluationSchema,
            context,
            max_tokens,
        )
        rec = _eval_stage(
            client,
            engine,
            variant,
            "evaluate_recruiter.md",
            RecruiterEvaluationSchema,
            context,
            max_tokens,
        )
        elapsed = round(time.perf_counter() - started, 1)
        cap_data, rec_data = cap.get("parsed") or {}, rec.get("parsed") or {}
        row = {
            "jd": jd_name,
            "seconds": elapsed,
            "cap_schema": bool(cap.get("schema_valid")),
            "rec_schema": bool(rec.get("schema_valid")),
            "fit_mean": _mean(cap_data.get("fit_subscores")),
            "odds_mean": _mean(rec_data.get("interview_odds_subscores")),
            "pursue_mean": _mean(rec_data.get("practical_pursue_subscores")),
            "recommendation": rec_data.get("recommendation"),
            "baseline_composite": baseline.get("composite_score"),
            "cap_diagnosis": cap.get("diagnosis"),
            "rec_diagnosis": rec.get("diagnosis"),
            "cap_error": cap.get("error") or cap.get("schema_error"),
            "rec_error": rec.get("error") or rec.get("schema_error"),
        }
        rows.append(row)
        print(
            f" {jd_name[:42]:42} | {elapsed:6.1f}s | "
            f"cap={row['fit_mean']} ({'ok' if row['cap_schema'] else 'FAIL'}) | "
            f"rec={row['odds_mean']} ({'ok' if row['rec_schema'] else 'FAIL'}) | "
            f"baseline={row['baseline_composite']}"
        )
    return {
        "variant": name,
        "settings": {
            "temperature": variant[2],
            "top_p": variant[3],
            "reasoning_effort": variant[4],
            "extra_body": variant[5],
        },
        "rows": rows,
    }


def _sample_bullets(n: int) -> pd.DataFrame:
    df = pd.read_csv(rb.CLUSTER_MAP_OUT)
    keep = df[df["rewrite_status"] == "KEEP"]
    manual = df[df["rewrite_status"] == "MANUAL"].head(2)
    wanted_keep = max(0, n - len(manual))
    step = max(1, len(keep) // max(1, wanted_keep))
    return pd.concat([keep.iloc[::step].head(wanted_keep), manual]).head(n)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%$ ]+", " ", text.lower()).split())


def _run_rewrite_variant(
    client: Any, name: str, temperature: float, sample: pd.DataFrame, max_tokens: int
) -> dict[str, Any]:
    print(f"\n=== {name} ===")
    rules = rb.RulesBundle(rb.RULES_DIR, rb.SCORING_DIR)
    kb = rb.KnowledgeBase()
    rewrite_system, _, _ = rb.build_system_prompts(rules, kb)
    schema = rb.RewriteOutputSchema.model_json_schema()
    rows = []

    for _, row in sample.iterrows():
        source = str(row["Bullet Point"]).strip()
        tags = str(row.get("Tags", ""))
        role = str(row.get("Role / Company", ""))
        evidence = f"{source}\n{source}\n{kb.company_scoped_context(role, tags)}"
        weaknesses = str(row.get("weaknesses", ""))
        attempts, final_text, final_rejection = [], "", None

        for attempt_number in range(1, rb.MAX_ATTEMPTS + 1):
            prompt = rb.build_rewrite_prompt(
                source,
                tags,
                weaknesses,
                kb.context_block_for_bullet(role, tags),
                attempt_number,
            )
            result = nim._structured_call(
                client,
                LIGHTNING,
                [
                    {"role": "system", "content": rewrite_system},
                    {"role": "user", "content": prompt},
                ],
                schema,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            log = {
                "attempt": attempt_number,
                "ok": result["ok"],
                "seconds": result["seconds"],
            }
            attempts.append(log)
            if not result["ok"]:
                log["error"] = result.get("error")
                break
            try:
                final_text = str(
                    json.loads(result["text"]).get("rewritten_bullet", "")
                ).strip()
            except json.JSONDecodeError:
                final_text = ""
            final_rejection = (
                rb._rejection_reason(final_text, evidence, role, kb)
                if final_text
                else None
            )
            log["unchanged"] = bool(final_text) and _norm(final_text) == _norm(source)
            if log["unchanged"] and not final_rejection:
                final_rejection = (
                    "identical",
                    "Improve the wording without adding facts.",
                )
            log["rejected"] = final_rejection[0] if final_rejection else None
            if final_text and not final_rejection:
                break
            weaknesses = (
                final_rejection[1]
                if final_rejection
                else "Return a non-empty rewritten_bullet."
            )

        rows.append(
            {
                "source": source,
                "role": role,
                "attempts": attempts,
                "final_text": final_text,
                "final_rejection": final_rejection[0] if final_rejection else None,
            }
        )
        print(
            f" {role[:28]:28} | attempts={len(attempts)} | first={attempts[0].get('rejected') if attempts else None} | final={'OK' if final_text and not final_rejection else 'REJECT/FAIL'}"
        )
    return {"variant": name, "temperature": temperature, "rows": rows}


def _default_paths() -> list[str]:
    profile = os.environ.get("RESUME_PROFILE", "dominick")
    root = os.path.join(nim.PROJECT_ROOT, "jds", profile)
    return [os.path.join(root, name) for name in DEFAULT_JDS]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--rewrite-n", type=int, default=8)
    parser.add_argument("--rewrite-max-tokens", type=int, default=1200)
    parser.add_argument("--eval-max-tokens", type=int, default=2500)
    parser.add_argument("--skip-rewrite", action="store_true")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument("jds", nargs="*", help="explicit three evaluated JD JSON paths")
    args = parser.parse_args()

    paths = args.jds or _default_paths()
    missing = [path for path in paths if not os.path.exists(path)]
    if missing and not args.skip_eval:
        raise SystemExit("Missing JD path(s):\n" + "\n".join(missing))

    client = nim._client()
    output: dict[str, Any] = {"eval": [], "rewrite": []}
    if not args.skip_eval:
        engine = orchestrator.ResumeEngine()
        for model in (LIGHTNING, GPT_OSS):
            if not args.no_warmup:
                print(f"\nWarm-up: {model}")
                nim.warmup(client, model)
        for variant in LIGHTNING_VARIANTS + GPT_VARIANTS:
            output["eval"].append(
                _run_eval_variant(client, engine, variant, paths, args.eval_max_tokens)
            )
    if not args.skip_rewrite:
        if not args.no_warmup:
            print(f"\nWarm-up: {LIGHTNING}")
            nim.warmup(client, LIGHTNING)
        sample = _sample_bullets(args.rewrite_n)
        for name, temperature in REWRITE_VARIANTS:
            output["rewrite"].append(
                _run_rewrite_variant(
                    client, name, temperature, sample, args.rewrite_max_tokens
                )
            )

    stage = f"settings_tuning_{datetime.now():%Y-%m-%d_%H%M%S}"
    path = nim._save("settings-experiment", stage, {"ok": True, **output})
    print(f"\nSaved results: {os.path.relpath(path, nim.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
