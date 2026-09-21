"""Measure the zero-shot `role_track` classifier against the hand-labeled holdout.

WHY THIS EXISTS

`role_track` (see docs/role_track.md) is an LLM judgment call with no measured
accuracy -- it is display-only today specifically because nobody has checked
whether it clears the >=90% precision bar the spec sets for the "manager"
(excluded) class. `scripts/build_role_track_holdout.py` produced 134 blind,
stratified hand labels for exactly this purpose; this script is the other
half -- it re-runs the SAME evaluate_capability.md call the real pipeline
makes, against each holdout posting's preserved original text, and reports
precision/recall against those labels.

Preserved text, not live re-scrape: `role_track_holdout_source.json` snapshots
each holdout posting's raw_text at label time, so this measures the
classifier against the exact text a human labeled -- not whatever the
posting looks like today (edited, expired, or gone).

This makes real Gemini calls (one per holdout row) and costs accordingly;
it is a manual, deliberate measurement, not something that runs in CI or on
a schedule.

Usage:
    python scripts/eval_role_track.py --profile morgan
    python scripts/eval_role_track.py --profile morgan --limit 20   # smoke test
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_role_track_holdout as holdout  # noqa: E402
import profile_paths  # noqa: E402

# Model verdicts that count as "manager" for the excluded-class precision
# bar -- a player-coach still manages people, which is exactly the case
# `docs/role_track.md`'s Jobs-pane display treats as "flag this one".
MANAGER_VERDICTS = ("manager", "player_coach")


def _holdout_paths(profile: str | None) -> tuple[str, str]:
    root = (
        profile_paths.profile_root(profile) if profile else profile_paths.profile_root()
    )
    return (
        os.path.join(root, "role_track_holdout.csv"),
        os.path.join(root, "role_track_holdout_source.json"),
    )


def _jd_text_from_raw(raw_text: str) -> str:
    """Mirrors jd_manager.read_jd_text()'s underscore-key stripping, but
    operating on an in-memory string instead of a file path -- the holdout
    source JSON preserves raw_text exactly as it sat in data.db, before any
    file ever existed for these rows."""
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    if isinstance(data, dict) and any(k.startswith("_") for k in data):
        data = {k: v for k, v in data.items() if not k.startswith("_")}
        return json.dumps(data, indent=2)
    return raw_text


def _predict(engine, jd_text: str) -> dict:
    import orchestrator

    fit_context = engine.build_fit_evaluation_context(jd_text)
    capability_prompt = engine.load_prompt("evaluate_capability.md")
    cap_text, _ = orchestrator.GeminiClient.generate(
        model=orchestrator.BUILDER_MODEL,
        system_instruction=capability_prompt,
        contents=fit_context,
        response_schema=orchestrator.CapabilityEvaluationSchema,
        temperature=0.0,
    )
    return orchestrator.GeminiClient.parse_json(cap_text or "") or {}


def _confusion_matrix(rows: list[dict]) -> None:
    predicted_values = ("ic", "manager", "player_coach", "unknown")
    label_values = ("ic", "manager", "unclear", "n/a")
    grid: dict[str, dict[str, int]] = {
        p: {l: 0 for l in label_values} for p in predicted_values
    }
    for r in rows:
        grid[r["predicted"]][r["label"]] += 1

    header = "predicted \\ label"
    print(f"\n{header:<18} " + " ".join(f"{l:>8}" for l in label_values))
    for p in predicted_values:
        cells = " ".join(f"{grid[p][l]:>8}" for l in label_values)
        print(f"{p:<18} {cells}")


def _pr_counts(rows: list[dict]) -> tuple[float, float, int, int, int]:
    """Manager-class precision/recall over one slice of scoreable rows.

    Returns (precision, recall, true_positives, flagged, actual), with a
    ratio of NaN where its denominator is empty.
    """
    flagged = [r for r in rows if r["predicted"] in MANAGER_VERDICTS]
    true_positives = [r for r in flagged if r["label"] == "manager"]
    actual = [r for r in rows if r["label"] == "manager"]
    precision = len(true_positives) / len(flagged) if flagged else float("nan")
    recall = len(true_positives) / len(actual) if actual else float("nan")
    return precision, recall, len(true_positives), len(flagged), len(actual)


def _print_breakdown(scoreable: list[dict], key: str, levels, width: int) -> None:
    """Prints precision/recall for each value of `key` present in the rows."""
    for level in levels:
        sub = [r for r in scoreable if r[key] == level]
        if not sub:
            continue
        precision, recall, _, _, _ = _pr_counts(sub)
        print(
            f"  {level:<{width}} precision={precision:>6.1%}  "
            f"recall={recall:>6.1%}  n={len(sub)}"
        )


def _precision_recall(rows: list[dict]) -> None:
    # Excluded-class bar: of postings the model flags manager/player_coach,
    # how many a human actually labeled "manager"? Rows the human called
    # "n/a" (not a real job) or "unclear" (human couldn't tell either) are
    # excluded from this ratio -- neither is evidence the model was wrong.
    scoreable = [r for r in rows if r["label"] in ("ic", "manager")]
    precision, recall, tp, flagged, actual = _pr_counts(scoreable)
    print(f"\nManager-class precision: {precision:.1%} ({tp}/{flagged} flagged)")
    print(f"Manager-class recall:    {recall:.1%} ({tp}/{actual} actual)")
    print(f"(excludes {len(rows) - len(scoreable)} row(s) labeled unclear/n/a)")

    print("\nPer stratum (scoreable rows only):")
    _print_breakdown(
        scoreable, "stratum", sorted({r["stratum"] for r in scoreable}), 12
    )

    print("\nPer confidence level (scoreable rows only):")
    _print_breakdown(scoreable, "confidence", ("high", "medium", "low"), 8)


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
        print(f"No holdout at {csv_path} -- run build_role_track_holdout.py first.")
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
        label = holdout.normalize_label(row.get("label", ""))
        if not label:
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
            prediction = _predict(engine, jd_text)
        except Exception as e:
            print(f"FAILED: {e}")
            skipped += 1
            continue

        predicted = prediction.get("role_track", "unknown")
        confidence = prediction.get("role_track_confidence", "low")
        print(f"predicted={predicted} ({confidence}) label={label}")

        results.append(
            {
                "job_id": job_id,
                "stratum": row["stratum"],
                "label": label,
                "predicted": predicted,
                "confidence": confidence,
                "evidence": prediction.get("role_track_evidence", ""),
            }
        )

    print(f"\n{'=' * 60}")
    print(f"Evaluated {len(results)}/{len(rows_to_run)} rows ({skipped} skipped)")
    if results:
        _confusion_matrix(results)
        _precision_recall(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
