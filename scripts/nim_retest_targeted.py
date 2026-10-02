#!/usr/bin/env python3
"""Re-test Gemma 4, Kimi K3, and Mistral Nemotron with corrected configurations.

Each model failed or produced incomplete results in the 2026-09-24/25 bakeoff for
specific, fixable reasons. This script re-runs both eval and rewrite with the
documented parameter fixes, then applies the strict hallucination audit (ported
from nim_profile_neutral_rewrite_benchmark.py) so each model's output is
examined beyond the production foreign-numbers guard.

Config rationale
----------------
Gemma 4 31B:
  - enable_thinking MUST be False (default is True — breaks structured output)
  - max_tokens=5000 for BOTH stages (rec eval schema is large; 2500 was too small)
  - temperature=0, seed=42

Kimi K3:
  - reasoning_effort="low" (documented valid values: "low"/"high"/"max"; "none" is NOT valid)
  - Default is "max" — the previous run used "low" but with only 2500 max_tokens,
    leaving no room for output after the reasoning chain consumed the budget.
  - max_tokens=10000 gives ~8K for reasoning + ~2K for JSON output at effort="low"
  - temperature=0, seed=42

Mistral Nemotron:
  - No special config needed; all evals 500'd in the first bakeoff window.
  - max_tokens=4096 (model hard cap), temperature=0
  - frequency_penalty=0, presence_penalty=0 (baseline; see nim_penalty_experiment.py)
  - No seed support (documented parameter list omits it).

Usage
-----
  source .venv/bin/activate
  RESUME_PROFILE=morgan python scripts/nim_retest_targeted.py
  RESUME_PROFILE=morgan python scripts/nim_retest_targeted.py --skip-eval
  RESUME_PROFILE=morgan python scripts/nim_retest_targeted.py --model kimi
  RESUME_PROFILE=morgan python scripts/nim_retest_targeted.py --n 12
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

import nim_smoke_test_nvidia_v2 as nim  # noqa: E402
import pandas as pd  # noqa: E402
import profile_paths  # noqa: E402
import rewrite_bullets as rb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(profile_paths.env_path(), override=False)

# ---------------------------------------------------------------------------
# Model configs — only documented parameters for each model
# ---------------------------------------------------------------------------

GEMMA = "google/gemma-4-31b-it"
KIMI = "moonshotai/kimi-k3"
MISTRAL = "mistralai/mistral-nemotron"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"
SUPER = "nvidia/nemotron-3-super-120b-a12b"

TARGET_MODELS: dict[str, dict[str, Any]] = {
    "gemma": {
        "id": GEMMA,
        "temperature": 0,
        "seed": 42,
        "cap_max_tokens": 5000,
        "rec_max_tokens": 8000,  # 5000 hit cap mid-doc on rec eval; raised to 8000
        "rewrite_max_tokens": 1500,
        # thinking MUST be disabled — default is True and breaks JSON output
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        "structured_output": False,  # no json_schema support; prompt_only only
        "note": "enable_thinking=False required; rec_max_tokens raised 5000→8000 (still failing rec eval)",
    },
    "kimi": {
        "id": KIMI,
        "temperature": 0,
        "seed": 42,
        "reasoning_effort": "low",  # "none" is not documented; valid: low/high/max
        "cap_max_tokens": 10000,
        "rec_max_tokens": 10000,
        "rewrite_max_tokens": 6000,
        "structured_output": True,  # documented structured output support
        "note": "reasoning_effort=low with max_tokens=10000; confirmed working",
    },
    "mistral": {
        "id": MISTRAL,
        "temperature": 0,
        # no seed support per NVIDIA docs
        "cap_max_tokens": 4096,
        "rec_max_tokens": 4096,
        "rewrite_max_tokens": 1500,
        "structured_output": False,  # no json_schema; prompt_only only
        "note": "eval confirmed non-viable (0/6); rewrite baseline for penalty experiment",
    },
    "lightning": {
        "id": LIGHTNING,
        "temperature": 0,
        "seed": 42,
        # enable_thinking=False required — same as Gemma; model supports reasoning_budget
        "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        "cap_max_tokens": 8000,
        "rec_max_tokens": 8000,
        "rewrite_max_tokens": 2000,
        "structured_output": True,  # in STRUCTURED_OUTPUT_MODELS in v2
        "note": "bakeoff 'approved' — first strict hallucination audit; cookie-cutter and JSON-literal-key bugs seen in bakeoff",
    },
    "super": {
        "id": SUPER,
        "temperature": 0,
        "seed": 42,
        # effort="none" per MODEL_SETTINGS — disables chain-of-thought
        "reasoning_effort": "none",
        "cap_max_tokens": 8000,
        "rec_max_tokens": 8000,
        "rewrite_max_tokens": 2000,
        "structured_output": True,  # in STRUCTURED_OUTPUT_MODELS in v2
        "note": "bakeoff 'approved' — first strict hallucination audit; numeric leakage seen in bakeoff",
    },
}

# The same 3 JDs used in every bakeoff run for cross-model comparability.
EVAL_JD_NAMES = (
    "2026-09-11_WaveMobileMoney_AppliedAIScientistLLMsVoice.json",
    "2026-09-18_MTBank_LeadQualityEngineerTestDataManagement.json",
    "2026-09-23_OpenTrainAI_DataScientistAIModelEvaluationRemoteContract.json",
)

# ---------------------------------------------------------------------------
# Strict hallucination audit (from nim_profile_neutral_rewrite_benchmark.py)
# ---------------------------------------------------------------------------

NUMBER_RE = re.compile(r"(?<![A-Za-z])\$?\d[\d,.]*\s*(?:%|[kKmMbB]|\+)?")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:[-/][A-Z0-9]+)*\b")
OUTCOME_CUES = re.compile(
    r"\b(improved?|improving|reduced?|reducing|increased?|increasing|"
    r"enabled?|enabling|accelerated?|accelerating|driven?|driving|"
    r"supported?|supporting|delivered?|delivering|resulted?|resulting|leading to)\b",
    re.I,
)
LEGAL_SUFFIXES = re.compile(
    r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|co|company)\b", re.I
)
TOOLISH_TERMS = frozenset(
    {
        "aws",
        "azure",
        "gcp",
        "glue",
        "sagemaker",
        "s3",
        "rds",
        "snowflake",
        "databricks",
        "python",
        "sql",
        "spacy",
        "nlp",
        "tensorflow",
        "pytorch",
        "tableau",
        "power bi",
        "salesforce",
        "hubspot",
        "marketo",
        "etl",
        "api",
    }
)
# Guard for cookie-cutter: identical rewrites across multiple source bullets.
_seen_rewrites: dict[str, list[str]] = {}


def _numbers(text: str) -> set[str]:
    return {m.group(0).lower().replace(" ", "") for m in NUMBER_RE.finditer(text)}


def _tool_audit(rewrite: str, evidence: str) -> list[str]:
    low_ev = evidence.lower()
    return sorted(
        term
        for term in TOOLISH_TERMS
        if re.search(rf"\b{re.escape(term)}\b", rewrite, re.I)
        and not re.search(rf"\b{re.escape(term)}\b", low_ev, re.I)
    )


def _proper_noun_audit(source: str, rewrite: str, evidence: str) -> list[str]:
    """Flag capitalized multi-word phrases in the rewrite absent from source+evidence.

    Targets invented university names, company names, award names, etc.
    Only fires on Title Case sequences of 2+ words to avoid triggering on
    normal sentence-start capitalization.
    """
    src_ev = f"{source}\n{evidence}".lower()
    # Match Title Case sequences: "Word Word" or "Word Word Word"
    pattern = re.compile(r"\b([A-Z][a-z]+(?:\s+(?:of\s+)?[A-Z][a-z]+){1,4})\b")
    flags: list[str] = []
    for match in pattern.finditer(rewrite):
        phrase = match.group(1)
        # Skip short common phrases unlikely to be proper nouns
        if len(phrase) < 8:
            continue
        if phrase.lower() not in src_ev:
            flags.append(f"unsupported proper noun: {phrase!r}")
    return flags


def _elaboration_flags(source: str, rewrite: str, evidence: str) -> list[str]:
    flags: list[str] = []
    src_ev = f"{source}\n{evidence}".lower()
    for acronym in sorted(set(ACRONYM_RE.findall(rewrite))):
        if acronym.lower() not in src_ev:
            flags.append(f"unsupported acronym: {acronym}")
    if OUTCOME_CUES.search(rewrite) and not OUTCOME_CUES.search(source):
        cue_tail = re.split(OUTCOME_CUES, rewrite.lower(), maxsplit=1)[-1]
        evidence_words = set(re.findall(r"[a-z]{4,}", src_ev))
        novel = list(
            dict.fromkeys(
                w for w in re.findall(r"[a-z]{5,}", cue_tail) if w not in evidence_words
            )
        )[:6]
        if len(novel) >= 3:
            flags.append("outcome elaboration with novel terms: " + ", ".join(novel))
    return flags


def _cookie_cutter_check(rewrite: str, role: str) -> str | None:
    """Return a description if this exact rewrite was produced for a different source."""
    key = " ".join(rewrite.lower().split())
    if key in _seen_rewrites:
        prior_roles = _seen_rewrites[key]
        if role not in prior_roles:
            return f"identical output already produced for: {prior_roles}"
    _seen_rewrites.setdefault(key, []).append(role)
    return None


def _json_literal_check(rewrite: str) -> bool:
    """True when the model returned a JSON schema key name as the output text."""
    schema_keys = {"rewritten_bullet", "bullet_text", "output", "result", "text"}
    return rewrite.strip().lower().strip('"') in schema_keys


def strict_audit(source: str, rewrite: str, evidence: str, role: str) -> dict[str, Any]:
    evidence_nums = _numbers(f"{source}\n{evidence}")
    output_nums = _numbers(rewrite)
    unsupported_numbers = sorted(output_nums - evidence_nums)
    unsupported_tools = _tool_audit(rewrite, evidence)
    proper_nouns = _proper_noun_audit(source, rewrite, evidence)
    elaboration = _elaboration_flags(source, rewrite, evidence)
    cookie = _cookie_cutter_check(rewrite, role)
    literal_key = _json_literal_check(rewrite)

    issues = (
        unsupported_numbers
        + unsupported_tools
        + proper_nouns
        + elaboration
        + ([cookie] if cookie else [])
        + (["JSON key returned as output value"] if literal_key else [])
    )
    return {
        "unsupported_numbers": unsupported_numbers,
        "unsupported_tools": unsupported_tools,
        "unsupported_proper_nouns": proper_nouns,
        "elaboration_flags": elaboration,
        "cookie_cutter": cookie,
        "json_literal_key": literal_key,
        "strict_auto_pass": not issues,
        "total_issues": len(issues),
    }


# ---------------------------------------------------------------------------
# Structured call with model-specific routing
# ---------------------------------------------------------------------------


def _structured_call(
    client: Any,
    cfg: dict[str, Any],
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    max_tokens: int,
) -> dict[str, Any]:
    """Route through json_schema if supported, else prompt_only."""
    model = cfg["id"]
    common: dict[str, Any] = {
        "temperature": cfg["temperature"],
        "max_tokens": max_tokens,
    }
    if cfg.get("seed") is not None:
        common["seed"] = cfg["seed"]
    if cfg.get("reasoning_effort"):
        common["reasoning_effort"] = cfg["reasoning_effort"]
    if cfg.get("extra_body"):
        common["extra_body"] = cfg["extra_body"]

    routes = []
    if cfg.get("structured_output"):
        routes.append(
            (
                "response_format.json_schema",
                {
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "result",
                            "schema": schema,
                            "strict": True,
                        },
                    }
                },
                messages,
            )
        )
    prompt_msgs = nim._append_json_instruction(messages, schema)
    routes.append(("prompt_only", {}, prompt_msgs))

    failures: list[dict[str, str]] = []
    for mode, additions, route_msgs in routes:
        kwargs = {**common, **additions}
        result = nim._call(client, model, route_msgs, **kwargs)
        result["mode"] = mode
        if result["ok"]:
            result["rejected_routes"] = failures
            return result
        failures.append({"mode": mode, "error": result.get("error", "")[:200]})
    result["rejected_routes"] = failures
    return result


# ---------------------------------------------------------------------------
# Eval stage
# ---------------------------------------------------------------------------


def run_eval(
    client: Any,
    cfg: dict[str, Any],
    jd_paths: list[str],
) -> list[dict[str, Any]]:
    import jd_manager
    import orchestrator
    from schemas import CapabilityEvaluationSchema, RecruiterEvaluationSchema

    engine = orchestrator.ResumeEngine()
    rows: list[dict[str, Any]] = []

    for path in jd_paths:
        name = os.path.basename(path).removesuffix(".json")[:58]
        baseline = jd_manager.read_evaluation(path) or {}
        jd_text = jd_manager.read_jd_text(path)
        context = engine.build_fit_evaluation_context(jd_text, [])
        system = engine.load_prompt("evaluate_capability.md")

        started = time.perf_counter()
        cap = _structured_call(
            client,
            cfg,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
            ],
            CapabilityEvaluationSchema.model_json_schema(),
            cfg["cap_max_tokens"],
        )
        cap_valid = False
        if cap["ok"]:
            try:
                CapabilityEvaluationSchema.model_validate(json.loads(cap["text"]))
                cap_valid = True
            except Exception as exc:  # noqa: BLE001
                cap["schema_error"] = str(exc)[:200]

        system = engine.load_prompt("evaluate_recruiter.md")
        rec = _structured_call(
            client,
            cfg,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
            ],
            RecruiterEvaluationSchema.model_json_schema(),
            cfg["rec_max_tokens"],
        )
        rec_valid = False
        if rec["ok"]:
            try:
                RecruiterEvaluationSchema.model_validate(json.loads(rec["text"]))
                rec_valid = True
            except Exception as exc:  # noqa: BLE001
                rec["schema_error"] = str(exc)[:200]

        elapsed = round(time.perf_counter() - started, 1)
        cap_data = json.loads(cap["text"]) if cap_valid else {}
        rec_data = json.loads(rec["text"]) if rec_valid else {}

        row: dict[str, Any] = {
            "jd": name,
            "seconds": elapsed,
            "cap_status": (
                "OK"
                if cap_valid
                else f"FAIL {cap.get('diagnosis') or cap.get('schema_error', '')}"
            ),
            "rec_status": (
                "OK"
                if rec_valid
                else f"FAIL {rec.get('diagnosis') or rec.get('schema_error', '')}"
            ),
            "recommendation": (
                rec_data.get("recommendation"),
                baseline.get("recommendation"),
            ),
            "gaps": (
                len(cap_data.get("capability_gaps") or []),
                len(baseline.get("capability_gaps") or []),
            ),
            "blockers": (
                len(rec_data.get("hard_blockers") or []),
                len(baseline.get("hard_blockers") or []),
            ),
            "role_track": (
                cap_data.get("role_track"),
                cap_data.get("role_track_confidence"),
            ),
            "tokens_cap": (cap.get("tokens") or {}).get("out"),
            "tokens_rec": (rec.get("tokens") or {}).get("out"),
            "modes": (cap.get("mode"), rec.get("mode")),
            "stored_composite": baseline.get("composite_score"),
            "cap_raw": cap,
            "rec_raw": rec,
        }
        rows.append(row)
        print(f"\n  JD: {name}")
        for k, v in row.items():
            if k not in {"jd", "cap_raw", "rec_raw"}:
                print(f"    {k:<20} {v}")
    return rows


# ---------------------------------------------------------------------------
# Rewrite stage (with strict audit)
# ---------------------------------------------------------------------------


def run_rewrite(
    client: Any,
    cfg: dict[str, Any],
    n: int,
) -> list[dict[str, Any]]:
    global _seen_rewrites
    _seen_rewrites = {}

    df = pd.read_csv(rb.CLUSTER_MAP_OUT)
    keep = df[df["rewrite_status"] == "KEEP"]
    manual = df[df["rewrite_status"] == "MANUAL"].head(2)
    wanted_keep = max(0, n - len(manual))
    step = max(1, len(keep) // max(1, wanted_keep))
    sample = pd.concat([keep.iloc[::step].head(wanted_keep), manual]).head(n)

    rules = rb.RulesBundle(rb.RULES_DIR, rb.SCORING_DIR)
    kb = rb.KnowledgeBase()
    rewrite_system, _, _ = rb.build_system_prompts(rules, kb)
    schema = rb.RewriteOutputSchema.model_json_schema()

    rows: list[dict[str, Any]] = []
    auto_pass = final_reject = errors = 0

    for _, row in sample.iterrows():
        source = str(row["Bullet Point"]).strip()
        role = str(row.get("Role / Company", "")).strip()
        tags = str(row.get("Tags", ""))
        weaknesses = str(row.get("weaknesses", ""))
        evidence = f"{source}\n{kb.company_scoped_context(role, tags)}"

        attempts: list[dict[str, Any]] = []
        final_text = ""
        production_rejection = None
        last_result: dict[str, Any] | None = None

        for attempt_no in range(1, rb.MAX_ATTEMPTS + 1):
            prompt = rb.build_rewrite_prompt(
                bullet=source,
                tags=tags,
                weaknesses=weaknesses,
                kb_context=kb.context_block_for_bullet(role, tags),
                attempt=attempt_no,
            )
            result = _structured_call(
                client,
                cfg,
                [
                    {"role": "system", "content": rewrite_system},
                    {"role": "user", "content": prompt},
                ],
                schema,
                cfg["rewrite_max_tokens"],
            )
            last_result = result
            log: dict[str, Any] = {
                "attempt": attempt_no,
                "ok": result["ok"],
                "seconds": result["seconds"],
                "mode": result.get("mode"),
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

        audit = strict_audit(source, final_text, evidence, role) if final_text else {}
        record: dict[str, Any] = {
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
                if (last_result and not last_result["ok"])
                else None
            ),
        }
        rows.append(record)

        if not final_text or (last_result and not last_result["ok"]):
            errors += 1
        elif production_rejection:
            final_reject += 1
        else:
            auto_pass += 1

        outcome = "AUTO-PASS" if not production_rejection and final_text else "REJECT"
        strict_ok = (
            "strict✓"
            if audit.get("strict_auto_pass")
            else f"strict✗({audit.get('total_issues', '?')} issues)"
        )
        print(f"  [{row.get('rewrite_status'):6}] {role[:40]:40} {outcome} {strict_ok}")
        if final_text:
            print(f"    {final_text}")
        if audit.get("unsupported_proper_nouns"):
            print(f"    ⚠ proper nouns: {audit['unsupported_proper_nouns']}")
        if audit.get("cookie_cutter"):
            print(f"    ⚠ cookie-cutter: {audit['cookie_cutter']}")
        if audit.get("json_literal_key"):
            print(f"    ⚠ JSON literal key returned as output")

    print(
        f"\n  Summary: auto-pass={auto_pass}/{n}  final-reject={final_reject}/{n}  errors={errors}/{n}"
    )
    strict_passes = sum(
        1 for r in rows if r.get("strict_audit", {}).get("strict_auto_pass")
    )
    all_issues = [
        issue
        for r in rows
        for field in (
            "unsupported_numbers",
            "unsupported_tools",
            "unsupported_proper_nouns",
            "elaboration_flags",
            "cookie_cutter",
            "json_literal_key",
        )
        for issue in (
            r["strict_audit"].get(field, [])
            if isinstance(r["strict_audit"].get(field), list)
            else ([r["strict_audit"][field]] if r["strict_audit"].get(field) else [])
        )
    ]
    print(
        f"  Strict audit: {strict_passes}/{len(rows)} passed  |  total issues: {len(all_issues)}"
    )
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _jd_paths(profile: str) -> list[str]:
    jd_dir = os.path.join(nim.PROJECT_ROOT, "jds", profile)
    paths = [os.path.join(jd_dir, name) for name in EVAL_JD_NAMES]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise SystemExit(
            f"Missing JD files (moved to completed/? wrong RESUME_PROFILE={profile}?):\n"
            + "\n".join(f"  {p}" for p in missing)
        )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--model",
        action="append",
        choices=list(TARGET_MODELS),
        help="one or more of: gemma kimi mistral lightning super (default: all)",
    )
    parser.add_argument("--n", type=int, default=10, help="bullets per rewrite run")
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--skip-rewrite", action="store_true")
    parser.add_argument("--no-warmup", action="store_true")
    args = parser.parse_args()

    models = args.model or list(TARGET_MODELS)
    profile = os.environ.get("RESUME_PROFILE", "morgan")
    client = nim._client()

    print(f"\nProfile: {profile}  |  Models: {', '.join(models)}  |  Bullets: {args.n}")
    jd_paths = [] if args.skip_eval else _jd_paths(profile)

    all_results: dict[str, Any] = {}
    for name in models:
        cfg = TARGET_MODELS[name]
        model_id = cfg["id"]
        print(f"\n{'='*70}")
        print(f"MODEL: {model_id}")
        print(f"  Note: {cfg['note']}")
        print(
            f"  Config: temp={cfg['temperature']}  seed={cfg.get('seed')}  "
            f"reasoning_effort={cfg.get('reasoning_effort')}  "
            f"cap_max_tokens={cfg['cap_max_tokens']}  rec_max_tokens={cfg['rec_max_tokens']}"
        )

        if not args.no_warmup:
            print("\n  Warm-up:")
            nim.warmup(client, model_id)

        result: dict[str, Any] = {"config": cfg, "model": model_id}

        if not args.skip_eval:
            print(f"\n  --- EVAL ---")
            result["eval"] = run_eval(client, cfg, jd_paths)
            nim._save(
                model_id, f"retest_eval_{name}", {"ok": True, "rows": result["eval"]}
            )

        if not args.skip_rewrite:
            print(f"\n  --- REWRITE (n={args.n}) ---")
            result["rewrite"] = run_rewrite(client, cfg, args.n)
            nim._save(
                model_id,
                f"retest_rewrite_{name}",
                {"ok": True, "rows": result["rewrite"]},
            )

        all_results[name] = result

    # Combined summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    for name, result in all_results.items():
        model_id = result["model"]
        print(f"\n  {model_id}")
        if "eval" in result:
            rows = result["eval"]
            cap_ok = sum(1 for r in rows if r["cap_status"] == "OK")
            rec_ok = sum(1 for r in rows if r["rec_status"] == "OK")
            print(f"    eval: cap {cap_ok}/{len(rows)} OK  rec {rec_ok}/{len(rows)} OK")
        if "rewrite" in result:
            rows = result["rewrite"]
            ap = sum(
                1 for r in rows if not r["production_rejection"] and r["final_text"]
            )
            sp = sum(
                1 for r in rows if r.get("strict_audit", {}).get("strict_auto_pass")
            )
            print(
                f"    rewrite: production pass {ap}/{len(rows)}  strict pass {sp}/{len(rows)}"
            )

    path = nim._save(
        "retest-targeted",
        f"retest_all_{datetime.now():%Y-%m-%d_%H%M%S}",
        {"ok": True, "results": all_results},
    )
    print(f"\nFull results: {os.path.relpath(path, nim.PROJECT_ROOT)}")


if __name__ == "__main__":
    started = time.perf_counter()
    main()
    print(f"\nelapsed {time.perf_counter() - started:.0f}s")
