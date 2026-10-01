"""
Bullet-rewrite audition for an NVIDIA NIM model. Read-only: no bank file, JD
or database is written; raw outputs go to scratch/nim-results/.

For each sampled bullet it reuses the production rewrite path up to the model
call -- `rewrite_bullets.build_rewrite_prompt()`, the full-context system
prompt and `KnowledgeBase` context -- makes ONE attempt (no retry loop, so the
first-shot quality is what gets measured), then applies the pipeline's own
`_rejection_reason()` guard (foreign numbers / borrowed tools / date anchors)
and scores the result with the pipeline's Gemini scorer. The bullet the
pipeline already kept (`final_bullet`) is scored the same way as a reference.
The judge is Gemini, not the model under test, so it is not grading itself.

Usage:
    RESUME_PROFILE=dominick python scripts/nim_rewrite_compare.py
    RESUME_PROFILE=dominick python scripts/nim_rewrite_compare.py --n 10
    python scripts/nim_rewrite_compare.py --model google/gemma-4-31b-it
"""

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import nim_smoke_test as nim  # loads the profile .env  # noqa: E402
import pandas as pd  # noqa: E402
import rewrite_bullets as rb  # noqa: E402


def _sample(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Mostly KEEP rows (they have a reference), plus up to 2 MANUAL ones."""
    keep = df[df["rewrite_status"] == "KEEP"]
    manual = df[df["rewrite_status"] == "MANUAL"].head(2)
    step = max(1, len(keep) // max(1, n - len(manual)))
    return pd.concat([keep.iloc[::step].head(n - len(manual)), manual])


def _norm(text: str) -> str:
    """Case/punctuation/whitespace-insensitive form, for the unchanged check."""
    return " ".join(re.sub(r"[^a-z0-9%$ ]+", " ", text.lower()).split())


def _score_line(scores: dict) -> str:
    return (
        f"acc={scores.get('accuracy_score')} bel={scores.get('believability_score')} "
        f"clr={scores.get('clarity_score')} ats={scores.get('ats_value')} "
        f"mgr={scores.get('manager_test')}"
    )


def _mean_scores(rows: list[dict]) -> dict:
    cols = ("accuracy_score", "believability_score", "clarity_score", "ats_value")
    out = {}
    for c in cols:
        vals = [r[c] for r in rows if isinstance(r.get(c), (int, float))]
        out[c] = round(sum(vals) / len(vals), 1) if vals else None
    out["mgr_pass"] = sum(1 for r in rows if r.get("manager_test") == "PASS")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=nim.DEFAULT_MODEL)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--max-tokens", type=int, default=4000)
    ap.add_argument("--reasoning-effort", choices=nim.REASONING_EFFORTS, default="auto")
    ap.add_argument(
        "--attempts",
        type=int,
        default=rb.MAX_ATTEMPTS,
        help="attempts per bullet, as production (rejection note fed to the next try)",
    )
    ap.add_argument("--no-warmup", action="store_true")
    ap.add_argument(
        "--match",
        action="append",
        help="only bullets whose source contains this text (repeatable)",
    )
    ap.add_argument(
        "--score",
        action="store_true",
        help="also score with the pipeline's Gemini judge (slow when Gemini is down)",
    )
    args = ap.parse_args()

    client = nim._client()
    df = pd.read_csv(rb.CLUSTER_MAP_OUT)
    if args.match:
        sample = df[
            df["Bullet Point"].apply(lambda b: any(m in str(b) for m in args.match))
        ]
    else:
        sample = _sample(df, args.n)

    rules = rb.RulesBundle(rb.RULES_DIR, rb.SCORING_DIR)
    kb = rb.KnowledgeBase()
    rewrite_system, _, score_system = rb.build_system_prompts(rules, kb)
    schema = rb.RewriteOutputSchema.model_json_schema()

    print(f"\nModel: {args.model}   bullets: {len(sample)}\n")
    if not args.no_warmup:
        nim.warmup(client, args.model)
    nim_scores, ref_scores, results = [], [], []
    rejected = errors = first_shot_rejected = 0

    for _, row in sample.iterrows():
        source = str(row["Bullet Point"]).strip()
        tags = str(row.get("Tags", ""))
        role = str(row.get("Role / Company", ""))
        reference = str(row.get("final_bullet", "")).strip()
        evidence = f"{source}\n{source}\n{kb.company_scoped_context(role, tags)}"
        weaknesses = str(row.get("weaknesses", ""))
        res, rewritten, rejection, attempts_log = None, "", None, []
        for attempt in range(1, args.attempts + 1):
            prompt = rb.build_rewrite_prompt(
                bullet=source,
                tags=tags,
                weaknesses=weaknesses,
                kb_context=kb.context_block_for_bullet(role, tags),
                attempt=attempt,
            )
            res = nim._structured_call(
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
            entry = {"attempt": attempt, "seconds": res["seconds"], "ok": res["ok"]}
            attempts_log.append(entry)
            if not res["ok"]:
                entry["diagnosis"] = res.get("diagnosis")
                break  # a transport failure is not something a retry note fixes
            try:
                rewritten = str(
                    json.loads(res["text"]).get("rewritten_bullet", "")
                ).strip()
            except json.JSONDecodeError:
                rewritten = ""
            rejection = (
                rb._rejection_reason(rewritten, evidence, role, kb)
                if rewritten
                else None
            )
            entry["unchanged"] = bool(rewritten) and _norm(rewritten) == _norm(source)
            if entry["unchanged"] and not rejection:
                # the production guard accepts a no-op; the harness must not
                rejection = (
                    "rewrite identical to source",
                    "Your last rewrite was identical to the original. Improve it "
                    "(stronger verb, clearer outcome) without adding facts.",
                )
            entry["rewritten"] = rewritten
            entry["rejected"] = rejection[0] if rejection else None
            if rewritten and not rejection:
                break
            # production feeds the rejection note back as the next "weaknesses"
            weaknesses = (
                rejection[1] if rejection else "Return a non-empty rewritten_bullet."
            )
        first_shot_rejected += (
            1 if attempts_log and attempts_log[0].get("rejected") else 0
        )
        print(f"[{row.get('rewrite_status')}] {role[:50]}")
        print(f"  source:    {source}")
        record = {"role": role, "source": source, "reference": reference, "nim": res}

        if not res["ok"]:
            errors += 1
            print(f"  ERROR: {res.get('diagnosis')}  [{res['error'][:160]}]\n")
            results.append(record)
            continue
        record["rewritten"] = rewritten
        record["attempts"] = attempts_log
        if not rewritten:
            errors += 1
            print("  ERROR: no usable rewritten_bullet in response\n")
            results.append(record)
            continue

        total_s = round(sum(a["seconds"] for a in attempts_log), 1)
        print(
            f"  nemotron:  {rewritten}  ({total_s}s, {len(attempts_log)} attempt(s); {res.get('diagnosis')})"
        )
        if reference:
            print(f"  reference: {reference}")

        record["rejected"] = rejection[0] if rejection else None
        if attempts_log[0].get("rejected"):
            print(f"  first shot: {attempts_log[0]['rejected']}")
        if rejection:
            rejected += 1
            print(f"  GUARD (still failing after {len(attempts_log)}): {rejection[0]}")
        if args.score:
            try:
                s = rb.score_bullet(rewritten, tags, score_system, role_company=role)
                record["nim_scores"] = s
                nim_scores.append(s)
                print(f"  nim score: {_score_line(s)}")
                if reference:
                    r = rb.score_bullet(
                        reference, tags, score_system, role_company=role
                    )
                    record["ref_scores"] = r
                    ref_scores.append(r)
                    print(f"  ref score: {_score_line(r)}")
            except (
                Exception
            ) as exc:  # noqa: BLE001 — judge outage is not a model result
                print(f"  (judge unavailable: {type(exc).__name__}; skipping scores)")
                args.score = False
        print()
        results.append(record)

    print("=" * 70)
    print(
        f"first-shot guard rejections: {first_shot_rejected}/{len(sample)}   "
        f"still rejected after {args.attempts} attempts: {rejected}/{len(sample)}   errors: {errors}"
    )
    unchanged_first = sum(
        1 for r in results if (r.get("attempts") or [{}])[0].get("unchanged")
    )
    unchanged_final = sum(
        1 for r in results if r.get("attempts") and r["attempts"][-1].get("unchanged")
    )
    print(
        f"returned source unchanged: first shot {unchanged_first}/{len(sample)}, "
        f"final {unchanged_final}/{len(sample)}"
    )
    if nim_scores:
        print(f"nemotron means:   {_mean_scores(nim_scores)}  (n={len(nim_scores)})")
        print(f"reference means:  {_mean_scores(ref_scores)}  (n={len(ref_scores)})")
    nim._save(args.model, "rewrite_compare", {"ok": True, "results": results})


if __name__ == "__main__":
    t = time.perf_counter()
    main()
    print(f"\nelapsed {time.perf_counter() - t:.0f}s")
