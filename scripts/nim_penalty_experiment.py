#!/usr/bin/env python3
"""Mistral Nemotron frequency_penalty / presence_penalty parameter sweep.

Mistral Nemotron is the ONLY model in the tested set that supports both
frequency_penalty and presence_penalty (confirmed via NVIDIA docs 2026-09-26).
No other model tested — Lightning, Nemotron Super, Gemma 4, or Kimi K3 —
supports either parameter.

What we're measuring
--------------------
frequency_penalty (0-2, docs default 0):
  Penalizes tokens proportionally to how many times they've already appeared.
  Higher values reduce repetition of specific words/phrases.

presence_penalty (0-2, docs default 0):
  Flat penalty for any token that has appeared at all in the output so far.
  Nudges the model toward new topics/words — diversity more than de-repetition.

Cookie-cutter pattern (the hallucination type we're targeting):
  The bakeoff found Nemotron producing near-identical rewrites for DIFFERENT
  source bullets from the same employer — same framing, same verbs, same
  outcome claim — probably because the instruction pattern dominates the
  source material in the context. Neither penalty directly prevents semantic
  repetition across bullets in DIFFERENT calls, but presence_penalty does
  reduce within-call token repetition, which could help when multiple bullets
  are batched or when the model is heavily repeating its own instruction echo.

Test design
-----------
- Grid: frequency_penalty ∈ {0.0, 0.3, 0.6, 1.0}
         presence_penalty  ∈ {0.0, 0.3, 0.6}
  = 12 combos × N bullets each.
- Each combo uses the SAME bullet sample in the SAME order so differences are
  attributable to the penalty values, not sampling.
- Strict audit (ported from nim_profile_neutral_rewrite_benchmark.py) runs on
  every output so we can measure whether penalties reduce cookie-cutter output
  or introduce new hallucination types.
- Production rejection rate is tracked per combo alongside strict-audit rate.

Hypothesis
----------
Moderate presence_penalty (0.3) may reduce the near-identical framing seen
across bullets within a single employer block, since it penalizes reusing the
same sentence-opening tokens. frequency_penalty is less targeted but may also
help. High values (≥ 1.0) risk incoherence or forced vocabulary variety that
produces new hallucinations.

Usage
-----
  source .venv/bin/activate
  RESUME_PROFILE=morgan python scripts/nim_penalty_experiment.py
  RESUME_PROFILE=morgan python scripts/nim_penalty_experiment.py --n 8
  RESUME_PROFILE=morgan python scripts/nim_penalty_experiment.py \\
      --freq 0.0 0.3 --pres 0.0 0.3
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from itertools import product as grid_product
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nim_smoke_test_nvidia_v2 as nim  # noqa: E402
import pandas as pd  # noqa: E402
import profile_paths  # noqa: E402
import rewrite_bullets as rb  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(profile_paths.env_path(), override=False)

MODEL = "mistralai/mistral-nemotron"
BASE_TEMP = 0.0
BASE_MAX_TOKENS = 1500  # nemotron cap is 4096; rewrite output is short

# Default parameter grid — override with CLI args
DEFAULT_FREQ = (0.0, 0.3, 0.6, 1.0)
DEFAULT_PRES = (0.0, 0.3, 0.6)

# ---------------------------------------------------------------------------
# Strict hallucination audit (same implementation as nim_retest_targeted.py)
# ---------------------------------------------------------------------------

NUMBER_RE = re.compile(r"(?<![A-Za-z])\$?\d[\d,.]*\s*(?:%|[kKmMbB]|\+)?")
ACRONYM_RE = re.compile(r"\b[A-Z]{2,}(?:[-/][A-Z0-9]+)*\b")
OUTCOME_CUES = re.compile(
    r"\b(improved?|improving|reduced?|reducing|increased?|increasing|"
    r"enabled?|enabling|accelerated?|accelerating|driven?|driving|"
    r"supported?|supporting|delivered?|delivering|resulted?|resulting|leading to)\b",
    re.I,
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


# Cookie-cutter: track per-combo so combos don't contaminate each other.
_combo_seen: dict[str, dict[str, list[str]]] = {}


def _cookie_cutter_check(rewrite: str, role: str, combo_key: str) -> str | None:
    seen = _combo_seen.setdefault(combo_key, {})
    key = " ".join(rewrite.lower().split())
    if key in seen:
        prior = seen[key]
        if role not in prior:
            return f"identical output for: {prior}"
    seen.setdefault(key, []).append(role)
    return None


def strict_audit(
    source: str, rewrite: str, evidence: str, role: str, combo_key: str
) -> dict[str, Any]:
    evidence_nums = _numbers(f"{source}\n{evidence}")
    output_nums = _numbers(rewrite)
    unsupported_numbers = sorted(output_nums - evidence_nums)
    unsupported_tools = _tool_audit(rewrite, evidence)
    elaboration = _elaboration_flags(source, rewrite, evidence)
    cookie = _cookie_cutter_check(rewrite, role, combo_key)
    literal_key = rewrite.strip().lower().strip('"') in {
        "rewritten_bullet",
        "bullet_text",
        "output",
        "result",
        "text",
    }

    issues = (
        unsupported_numbers
        + unsupported_tools
        + elaboration
        + ([cookie] if cookie else [])
        + (["JSON key returned as output value"] if literal_key else [])
    )
    return {
        "unsupported_numbers": unsupported_numbers,
        "unsupported_tools": unsupported_tools,
        "elaboration_flags": elaboration,
        "cookie_cutter": cookie,
        "json_literal_key": literal_key,
        "strict_auto_pass": not issues,
        "total_issues": len(issues),
    }


# ---------------------------------------------------------------------------
# Single-combo rewrite run
# ---------------------------------------------------------------------------


def run_combo(
    client: Any,
    bullets: pd.DataFrame,
    freq: float,
    press: float,
    rules: rb.RulesBundle,
    kb: rb.KnowledgeBase,
    rewrite_system: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    combo_key = f"f{freq:.2f}_p{press:.2f}"
    rows: list[dict[str, Any]] = []
    auto_pass = final_reject = errors = 0

    for _, row in bullets.iterrows():
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
            result = nim._call(
                client,
                MODEL,
                prompt_msgs,
                temperature=BASE_TEMP,
                max_tokens=BASE_MAX_TOKENS,
                frequency_penalty=freq,
                presence_penalty=press,
            )
            last_result = result
            log: dict[str, Any] = {
                "attempt": attempt_no,
                "ok": result["ok"],
                "seconds": result["seconds"],
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

    strict_passes = sum(
        1 for r in rows if r.get("strict_audit", {}).get("strict_auto_pass")
    )
    cookie_hits = sum(1 for r in rows if r.get("strict_audit", {}).get("cookie_cutter"))
    return {
        "combo": combo_key,
        "freq": freq,
        "press": press,
        "n": len(rows),
        "auto_pass": auto_pass,
        "final_reject": final_reject,
        "errors": errors,
        "strict_pass": strict_passes,
        "cookie_cutter_hits": cookie_hits,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _sample_bullets(n: int) -> pd.DataFrame:
    df = pd.read_csv(rb.CLUSTER_MAP_OUT)
    keep = df[df["rewrite_status"] == "KEEP"]
    manual = df[df["rewrite_status"] == "MANUAL"].head(2)
    wanted_keep = max(0, n - len(manual))
    step = max(1, len(keep) // max(1, wanted_keep))
    sample = pd.concat([keep.iloc[::step].head(wanted_keep), manual]).head(n)
    return sample.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--n", type=int, default=8, help="bullets per combo")
    parser.add_argument(
        "--freq",
        nargs="+",
        type=float,
        default=list(DEFAULT_FREQ),
        metavar="F",
        help="frequency_penalty values to test",
    )
    parser.add_argument(
        "--pres",
        nargs="+",
        type=float,
        default=list(DEFAULT_PRES),
        metavar="P",
        help="presence_penalty values to test",
    )
    parser.add_argument("--no-warmup", action="store_true")
    args = parser.parse_args()

    profile = os.environ.get("RESUME_PROFILE", "morgan")
    client = nim._client()
    combos = list(grid_product(args.freq, args.press))

    print(f"\nProfile: {profile}  |  Model: {MODEL}")
    print(
        f"Grid: freq={args.freq}  press={args.press}  ({len(combos)} combos × {args.n} bullets)"
    )
    print(f"Expected calls: ~{len(combos) * args.n * rb.MAX_ATTEMPTS} (with retries)")

    if not args.no_warmup:
        print("\nWarm-up:")
        nim.warmup(client, MODEL)

    bullets = _sample_bullets(args.n)
    rules = rb.RulesBundle(rb.RULES_DIR, rb.SCORING_DIR)
    kb = rb.KnowledgeBase()
    rewrite_system, _, _ = rb.build_system_prompts(rules, kb)
    schema = rb.RewriteOutputSchema.model_json_schema()

    all_results: list[dict[str, Any]] = []
    started = time.perf_counter()

    print(
        f"\n{'combo':<16} {'prod_pass':>9} {'strict_pass':>11} {'cookie':>6} {'errors':>6}"
    )
    print("-" * 55)
    for freq, press in combos:
        combo_started = time.perf_counter()
        result = run_combo(
            client, bullets, freq, press, rules, kb, rewrite_system, schema
        )
        elapsed = round(time.perf_counter() - combo_started, 1)
        all_results.append(result)
        n = result["n"]
        print(
            f"  f={freq:.2f} p={press:.2f}   "
            f"{result['auto_pass']:>4}/{n}"
            f"  {result['strict_pass']:>5}/{n}"
            f"  {result['cookie_cutter_hits']:>4}/{n}"
            f"  {result['errors']:>4}/{n}"
            f"  ({elapsed}s)"
        )

    print(f"\nTotal elapsed: {time.perf_counter() - started:.0f}s")

    # Summary table sorted by strict_pass desc, then cookie_cutter_hits asc
    sorted_results = sorted(
        all_results, key=lambda r: (-r["strict_pass"], r["cookie_cutter_hits"])
    )
    print("\nTop combos (by strict pass rate, then fewest cookie-cutter hits):")
    for r in sorted_results[:5]:
        print(
            f"  {r['combo']:<14}  strict {r['strict_pass']}/{r['n']}"
            f"  cookie {r['cookie_cutter_hits']}/{r['n']}"
            f"  prod_pass {r['auto_pass']}/{r['n']}"
        )

    path = nim._save(
        MODEL,
        f"penalty_experiment_{datetime.now():%Y-%m-%d_%H%M%S}",
        {
            "ok": True,
            "model": MODEL,
            "n_bullets": args.n,
            "freq_values": args.freq,
            "pres_values": args.press,
            "combos": all_results,
        },
    )
    print(f"\nFull results: {os.path.relpath(path, nim.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
