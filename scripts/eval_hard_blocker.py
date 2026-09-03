"""Measure the zero-shot years/degree AND field/domain hard-blocker
classifiers against the hand-labeled holdout.

WHY THIS EXISTS

Categorizing hard_blockers stopped years_experience/degree items from
auto-zeroing composite_score, but that carve-out was itself never
holdout-measured -- same reasoning as role_track before ITS measurement
(see docs/role_track.md). scripts/build_hard_blocker_holdout.py produces
blind, stratified hand labels for exactly this purpose; this script is
the other half -- it re-runs the SAME evaluate_recruiter.md call the real
pipeline makes, against each holdout posting's preserved original text,
and reports precision/recall against those labels.

field_domain (required industry/functional background) is measured here
too, on the same holdout sample via its separate `field_domain_label`
column -- it currently falls into the catch-all `other` category, which
still force-zeroes the score with no measurement at all, the same
unvalidated-gate problem years/degree had before this script existed.

WHAT "CORRECT" MEANS HERE

Unlike role_track, the model isn't being scored on whether it can read a
posting -- it's being scored on whether it correctly tags a stated
requirement as a blocker, at all. The candidate-specific judgment of
whether that requirement actually blocks you is the label; the model is
only ever asked to identify and categorize what the posting states, so
"predicted" here means "did the model emit a blocker in this category for
this posting", and precision/recall are computed against whether a human
labeled the row `blocks` (a real, disqualifying requirement is present)
vs. `does_not_block`/`n/a` (no real disqualifying requirement is
present). years_experience/degree and field_domain are scored as two
independent dimensions on the same rows.

Preserved text, not live re-scrape: hard_blocker_holdout_source.json
snapshots each holdout posting's raw_text at label time.

This makes real Gemini calls (one per holdout row) and costs accordingly;
it is a manual, deliberate measurement, not something that runs in CI or
on a schedule.

Usage:
    python scripts/eval_hard_blocker.py --profile morgan
    python scripts/eval_hard_blocker.py --profile morgan --limit 20   # smoke test
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_hard_blocker_holdout as holdout  # noqa: E402
import profile_paths  # noqa: E402

EXPERIENCE_CATEGORIES = ("years_experience", "degree")
FIELD_DOMAIN_CATEGORIES = ("field_domain",)


def _holdout_paths(profile: str | None) -> tuple[str, str]:
    root = (
        profile_paths.profile_root(profile) if profile else profile_paths.profile_root()
    )
    return (
        os.path.join(root, "hard_blocker_holdout.csv"),
        os.path.join(root, "hard_blocker_holdout_source.json"),
    )


def _jd_text_from_raw(raw_text: str) -> str:
    """Mirrors jd_manager.read_jd_text()'s underscore-key stripping, but
    operating on an in-memory string instead of a file path."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    if isinstance(data, dict) and any(k.startswith("_") for k in data):
        data = {k: v for k, v in data.items() if not k.startswith("_")}
        return json.dumps(data, indent=2)
    return raw_text


def _predict(engine, jd_text: str) -> list[dict]:
    """Runs the real recruiter-eval call and returns whatever hard_blockers
    it produced (list of {text, category} dicts per the current schema)."""
    import orchestrator

    fit_context = engine.build_fit_evaluation_context(jd_text)
    recruiter_prompt = engine.load_prompt("evaluate_recruiter.md")
    recruiter_text, _ = orchestrator.GeminiClient.generate(
        model=orchestrator.BUILDER_MODEL,
        system_instruction=recruiter_prompt,
        contents=fit_context,
        response_schema=orchestrator.RecruiterEvaluationSchema,
        temperature=0.0,
    )
    parsed = orchestrator.GeminiClient.parse_json(recruiter_text or "") or {}
    return parsed.get("hard_blockers", [])


def _confusion_matrix(rows: list[dict], label_key: str, predicted_key: str) -> None:
    predicted_values = ("flagged", "not_flagged")
    label_values = ("blocks", "does_not_block", "unclear", "n/a")
    grid: dict[str, dict[str, int]] = {
        p: {l: 0 for l in label_values} for p in predicted_values
    }
    for r in rows:
        grid[r[predicted_key]][r[label_key]] += 1

    print(f"\n{'predicted \\ label':<18} " + " ".join(f"{l:>15}" for l in label_values))
    for p in predicted_values:
        cells = " ".join(f"{grid[p][l]:>15}" for l in label_values)
        print(f"{p:<18} {cells}")


def _precision_recall(rows: list[dict], label_key: str, predicted_key: str) -> None:
    # Excluded-class bar, mirroring eval_role_track.py: of postings the
    # model flags with a blocker in this category, how many did a human
    # actually confirm as blocking? Rows labeled unclear/n/a are excluded
    # -- neither is evidence the model was right or wrong.
    scoreable = [r for r in rows if r[label_key] in ("blocks", "does_not_block")]
    flagged = [r for r in scoreable if r[predicted_key] == "flagged"]
    true_positives = [r for r in flagged if r[label_key] == "blocks"]
    actual_blocks = [r for r in scoreable if r[label_key] == "blocks"]

    precision = len(true_positives) / len(flagged) if flagged else float("nan")
    recall = len(true_positives) / len(actual_blocks) if actual_blocks else float("nan")
    print(
        f"\nBlocker-class precision: {precision:.1%} ({len(true_positives)}/{len(flagged)} flagged)"
    )
    print(
        f"Blocker-class recall:    {recall:.1%} ({len(true_positives)}/{len(actual_blocks)} actual)"
    )
    print(f"(excludes {len(rows) - len(scoreable)} row(s) labeled unclear/n/a)")

    print("\nPer stratum (scoreable rows only):")
    for stratum in sorted({r["stratum"] for r in scoreable}):
        sub = [r for r in scoreable if r["stratum"] == stratum]
        sub_flagged = [r for r in sub if r[predicted_key] == "flagged"]
        sub_tp = [r for r in sub_flagged if r[label_key] == "blocks"]
        sub_actual = [r for r in sub if r[label_key] == "blocks"]
        p = len(sub_tp) / len(sub_flagged) if sub_flagged else float("nan")
        r_ = len(sub_tp) / len(sub_actual) if sub_actual else float("nan")
        print(f"  {stratum:<14} precision={p:>6.1%}  recall={r_:>6.1%}  n={len(sub)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--profile")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Evaluate only the first N rows (smoke test)",
    )
    args = parser.parse_args()

    csv_path, source_path = _holdout_paths(args.profile)
    if not os.path.exists(csv_path):
        print(f"No holdout at {csv_path} -- run build_hard_blocker_holdout.py first.")
        return 1
    if not os.path.exists(source_path):
        print(f"No preserved source text at {source_path}.")
        return 1

    labels = holdout.read_labels(csv_path)
    with open(source_path, "r", encoding="utf-8") as fh:
        sources = json.load(fh)

    if args.profile:
        profile_paths.set_active_profile(args.profile)

    import orchestrator

    engine = orchestrator.ResumeEngine()

    rows_to_run = labels[: args.limit] if args.limit else labels
    results = []
    skipped = 0
    for i, row in enumerate(rows_to_run, 1):
        job_id = row["job_id"]
        label_yd = holdout.normalize_label(row.get("label", ""))
        label_fd = holdout.normalize_label(row.get("field_domain_label", ""))
        if not label_yd and not label_fd:
            skipped += 1
            continue
        source = sources.get(job_id)
        if not source:
            skipped += 1
            continue

        jd_text = _jd_text_from_raw(source["raw_text"])
        print(
            f"[{i}/{len(rows_to_run)}] {row['title']!r} @ {row['company']!r} ...",
            end=" ",
        )
        try:
            blockers = _predict(engine, jd_text)
        except Exception as e:
            print(f"FAILED: {e}")
            skipped += 1
            continue

        predicted_yd = (
            "flagged"
            if any(
                isinstance(b, dict) and b.get("category") in EXPERIENCE_CATEGORIES
                for b in blockers
            )
            else "not_flagged"
        )
        predicted_fd = (
            "flagged"
            if any(
                isinstance(b, dict) and b.get("category") in FIELD_DOMAIN_CATEGORIES
                for b in blockers
            )
            else "not_flagged"
        )
        print(
            f"predicted_yd={predicted_yd} label_yd={label_yd or '-'}  "
            f"predicted_fd={predicted_fd} label_fd={label_fd or '-'}"
        )

        results.append(
            {
                "job_id": job_id,
                "stratum": row["stratum"],
                "label": label_yd,
                "predicted": predicted_yd,
                "field_domain_label": label_fd,
                "predicted_field_domain": predicted_fd,
                "blockers": blockers,
            }
        )

    print(f"\n{'=' * 60}")
    print(f"Evaluated {len(results)}/{len(rows_to_run)} rows ({skipped} skipped)")
    if results:
        yd_results = [r for r in results if r["label"]]
        fd_results = [r for r in results if r["field_domain_label"]]
        if yd_results:
            print("\n### years_experience / degree ###")
            _confusion_matrix(yd_results, "label", "predicted")
            _precision_recall(yd_results, "label", "predicted")
        if fd_results:
            print("\n### field_domain ###")
            _confusion_matrix(
                fd_results, "field_domain_label", "predicted_field_domain"
            )
            _precision_recall(
                fd_results, "field_domain_label", "predicted_field_domain"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
