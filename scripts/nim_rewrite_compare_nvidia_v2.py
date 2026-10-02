#!/usr/bin/env python3
"""Compare NVIDIA NIM bullet rewrites against production rewrite safeguards.

Read-only: no bullet-bank CSV, JD, or database is changed. The test uses the
real production rewrite prompt, KnowledgeBase context, response schema, and
rejection guard. It intentionally permits production-style corrective retries:
a cold or initially-invalid response can receive the guard's exact rejection
note on the next attempt. Transport/API failures stop immediately.
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nim_smoke_test_nvidia_v2 as nim  # noqa: E402
import pandas as pd  # noqa: E402
import rewrite_bullets as rb  # noqa: E402


def _sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Mostly KEEP rows, plus up to two MANUAL rows for hard cases."""
    keep = df[df["rewrite_status"] == "KEEP"]
    manual = df[df["rewrite_status"] == "MANUAL"].head(2)
    wanted_keep = max(0, n - len(manual))
    step = max(1, len(keep) // max(1, wanted_keep))
    return pd.concat([keep.iloc[::step].head(wanted_keep), manual]).head(n)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9%$ ]+", " ", text.lower()).split())


def _score_line(scores: dict[str, Any]) -> str:
    return (
        f"acc={scores.get('accuracy_score')} bel={scores.get('believability_score')} "
        f"clr={scores.get('clarity_score')} ats={scores.get('ats_value')} "
        f"mgr={scores.get('manager_test')}"
    )


def _mean_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cols = ("accuracy_score", "believability_score", "clarity_score", "ats_value")
    out: dict[str, Any] = {}
    for column in cols:
        values = [
            row[column] for row in rows if isinstance(row.get(column), (int, float))
        ]
        out[column] = round(sum(values) / len(values), 1) if values else None
    out["mgr_pass"] = sum(1 for row in rows if row.get("manager_test") == "PASS")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=nim.DEFAULT_MODEL)
    parser.add_argument("--n", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument(
        "--reasoning-effort", choices=nim.REASONING_EFFORTS, default="auto"
    )
    parser.add_argument(
        "--attempts",
        type=int,
        default=rb.MAX_ATTEMPTS,
        help="production-style maximum attempts per bullet; guard feedback reaches later attempts",
    )
    parser.add_argument("--no-warmup", action="store_true")
    parser.add_argument(
        "--match",
        action="append",
        help="only source bullets containing this text; repeatable",
    )
    parser.add_argument(
        "--score",
        action="store_true",
        help="also use Gemini as a judge; slow/unavailable Gemini disables it",
    )
    args = parser.parse_args()

    client = nim._client()
    df = pd.read_csv(rb.CLUSTER_MAP_OUT)
    if args.match:
        sample = df[
            df["Bullet Point"].apply(
                lambda bullet: any(match in str(bullet) for match in args.match)
            )
        ]
    else:
        sample = _sample(df, args.n)

    rules = rb.RulesBundle(rb.RULES_DIR, rb.SCORING_DIR)
    kb = rb.KnowledgeBase()
    rewrite_system, _, score_system = rb.build_system_prompts(rules, kb)
    schema = rb.RewriteOutputSchema.model_json_schema()

    print(
        f"\nModel: {args.model} | bullets: {len(sample)} | max attempts: {args.attempts}\n"
    )
    if not args.no_warmup:
        nim.warmup(client, args.model)

    nim_scores: list[dict[str, Any]] = []
    ref_scores: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    rejected = errors = first_shot_rejected = 0

    for _, row in sample.iterrows():
        source = str(row["Bullet Point"]).strip()
        tags = str(row.get("Tags", ""))
        role = str(row.get("Role / Company", ""))
        reference = str(row.get("final_bullet", "")).strip()
        weaknesses = str(row.get("weaknesses", ""))
        evidence = f"{source}\n{source}\n{kb.company_scoped_context(role, tags)}"
        attempts: list[dict[str, Any]] = []
        rewritten = ""
        rejection = None
        last_result: dict[str, Any] | None = None

        for attempt_number in range(1, args.attempts + 1):
            prompt = rb.build_rewrite_prompt(
                bullet=source,
                tags=tags,
                weaknesses=weaknesses,
                kb_context=kb.context_block_for_bullet(role, tags),
                attempt=attempt_number,
            )
            result = nim._structured_call(
                client,
                args.model,
                [
                    {"role": "system", "content": rewrite_system},
                    {"role": "user", "content": prompt},
                ],
                schema,
                temperature=0.7,
                max_tokens=args.max_tokens,
                reasoning_effort=nim.effort_override(args.reasoning_effort),
            )
            last_result = result
            attempt_log: dict[str, Any] = {
                "attempt": attempt_number,
                "seconds": result["seconds"],
                "ok": result["ok"],
                "diagnosis": result.get("diagnosis"),
                "mode": result.get("mode"),
            }
            attempts.append(attempt_log)

            if not result["ok"]:
                break

            try:
                rewritten = str(
                    json.loads(result["text"]).get("rewritten_bullet", "")
                ).strip()
            except json.JSONDecodeError:
                rewritten = ""

            rejection = (
                rb._rejection_reason(rewritten, evidence, role, kb)
                if rewritten
                else None
            )
            attempt_log["rewritten"] = rewritten
            attempt_log["unchanged"] = bool(rewritten) and _norm(rewritten) == _norm(
                source
            )
            if attempt_log["unchanged"] and not rejection:
                rejection = (
                    "rewrite identical to source",
                    "Your last rewrite was identical to the original. Improve it with a stronger verb or clearer outcome without adding facts.",
                )
            attempt_log["rejected"] = rejection[0] if rejection else None

            if rewritten and not rejection:
                break
            weaknesses = (
                rejection[1] if rejection else "Return a non-empty rewritten_bullet."
            )

        record: dict[str, Any] = {
            "role": role,
            "source": source,
            "reference": reference,
            "rewritten": rewritten,
            "attempts": attempts,
            "nim": last_result,
            "rejected": rejection[0] if rejection else None,
        }
        results.append(record)
        first_shot_rejected += int(bool(attempts and attempts[0].get("rejected")))

        print(f"[{row.get('rewrite_status')}] {role[:55]}")
        print(f" source: {source}")
        if not last_result or not last_result["ok"]:
            errors += 1
            print(
                f" ERROR: {last_result.get('diagnosis') if last_result else 'no result'} [{last_result.get('error', '')[:160] if last_result else ''}]\n"
            )
            continue
        if not rewritten:
            errors += 1
            print(" ERROR: no usable rewritten_bullet in response\n")
            continue

        total_seconds = round(sum(item["seconds"] for item in attempts), 1)
        print(
            f" nvidia: {rewritten} ({total_seconds}s, {len(attempts)} attempt(s); {last_result.get('diagnosis')})"
        )
        if reference:
            print(f" reference: {reference}")
        if attempts and attempts[0].get("rejected"):
            print(f" first shot: {attempts[0]['rejected']}")
        if rejection:
            rejected += 1
            print(f" GUARD after {len(attempts)} attempts: rejection reason redacted")

        if args.score:
            try:
                score = rb.score_bullet(
                    rewritten, tags, score_system, role_company=role
                )
                record["nim_scores"] = score
                nim_scores.append(score)
                print(f" nvidia score: {_score_line(score)}")
                if reference:
                    baseline = rb.score_bullet(
                        reference, tags, score_system, role_company=role
                    )
                    record["ref_scores"] = baseline
                    ref_scores.append(baseline)
                    print(f" reference score: {_score_line(baseline)}")
            except Exception as exc:  # noqa: BLE001
                print(
                    f" Gemini judge unavailable: {type(exc).__name__}; disabling scoring for remaining bullets"
                )
                args.score = False
        print()

    print("=" * 72)
    print(
        f"first-shot guard rejections: {first_shot_rejected}/{len(sample)} | "
        f"still rejected after {args.attempts} attempts: {rejected}/{len(sample)} | errors: {errors}"
    )
    unchanged_first = sum(
        1 for record in results if (record.get("attempts") or [{}])[0].get("unchanged")
    )
    unchanged_final = sum(
        1
        for record in results
        if record.get("attempts") and record["attempts"][-1].get("unchanged")
    )
    print(
        f"returned source unchanged: first shot {unchanged_first}/{len(sample)}, final {unchanged_final}/{len(sample)}"
    )
    if nim_scores:
        print(f"nvidia score means: {_mean_scores(nim_scores)} (n={len(nim_scores)})")
        print(
            f"reference score means: {_mean_scores(ref_scores)} (n={len(ref_scores)})"
        )

    path = nim._save(args.model, "rewrite_compare", {"ok": True, "results": results})
    print(f"saved: {os.path.relpath(path, nim.PROJECT_ROOT)}")


if __name__ == "__main__":
    started = time.perf_counter()
    main()
    print(f"\nelapsed {time.perf_counter() - started:.0f}s")
