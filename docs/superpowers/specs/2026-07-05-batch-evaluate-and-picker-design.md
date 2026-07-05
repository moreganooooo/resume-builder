# Batch Evaluation + Interactive Job Picker — Design

## Problem

`resume evaluate` only scores one JD at a time, but the documented/
recommended workflow (and this project's own real usage) explicitly calls
for triaging a large pile of scanned JDs before running `resume run` --
right now there are 208 real pending JDs sitting untriaged in `jds/`,
which would mean invoking `resume evaluate <file>` 208 times by hand.

Separately, `resume run` (batch mode) has no way to process a *subset* of
pending JDs -- it's all-or-nothing, with no safety gate regardless of how
many JDs are pending. Confirmed 2026-07-05: Morgan wants the ability to
either run the full batch (unchanged) or interactively select specific
JD(s) to tailor from a list.

These two asks turn out to share the same underlying mechanism once "the
picker always shows live scores" was chosen (2026-07-05): both need to
evaluate every pending JD and both carry the same real cost (one Gemini
call per pending JD -- 208 calls against today's real pile). They're
built on one shared function with a shared safety gate.

## Goals

1. `resume evaluate` (no file argument) evaluates every pending JD and
   prints a sorted summary table -- `resume evaluate <file>` (existing,
   single-JD behavior) is unchanged.
2. `resume run --pick` shows an interactive checkbox picker (sorted
   best-score-first) of every pending JD with its live score/
   recommendation, lets Morgan select which one(s) to actually tailor,
   then runs the normal single-file pipeline on just those --
   `resume run` (no flag, existing batch-everything behavior) is
   unchanged.
3. A confirmation gate (print the pending count, require y/n, `--yes`
   skips it) fires before any batch scoring begins -- for both consumers,
   since both now carry the same real per-JD Gemini cost.
4. One shared function (`batch_evaluate.evaluate_all_pending()`) is the
   single source of truth for "evaluate every pending JD," reused by both
   commands -- no duplicated scoring logic.

## Non-Goals

- No persistence/caching of evaluate results across invocations -- every
  `resume evaluate` or `resume run --pick` call re-scores fresh (Morgan's
  explicit choice 2026-07-05: always live, never stale cached scores).
- No filtering/search within the picker for this pass -- the full sorted
  list is shown as-is; `questionary`'s own scroll behavior handles length.
  Revisit only if 208+ items proves genuinely unwieldy in practice.
- No change to `resume run`'s or `resume evaluate <file>`'s existing
  default behavior -- both additions are purely additive (a new optional
  flag, a new no-argument mode).
- No new terminal-UI framework beyond `questionary` -- it's the one new
  dependency this pass needs, chosen for its standard `checkbox()` prompt
  and built-in `value=`-based selection mapping (no custom index-mapping
  code needed).

## Architecture

```
scripts/batch_evaluate.py (new)
  evaluate_all_pending(pending_paths: list = None) -> list[dict]
    -- pending_paths defaults to jd_manager.get_pending_jds() if None
    -- for each JD: ResumeEngine.evaluate_fit(path); on failure/{} result,
       record {..., error: True} instead of crashing the batch
    -- returns list of {job_key, source_file, company_name, job_title,
       composite_score, recommendation, hard_blockers, error} sorted via
       _sort_key() -- highest composite_score first, error=True entries
       always last regardless of score

  cli.py:
    resume evaluate  (jd_file now optional)
      no file  -> confirmation gate -> evaluate_all_pending() -> sorted
                  table printed to console
      <file>   -> today's existing single-JD behavior, unchanged

    resume run --pick
      confirmation gate -> evaluate_all_pending() -> questionary.checkbox
      (each choice's value = source_file, title = "score | rec | company
      | title") -> for each selected file: orchestrator.run_pipeline(
      jd_path=file) sequentially -> completed/failed summary, same shape
      as today's batch `resume run` summary

    resume run  (no --pick, no file)
      unchanged -- processes every pending JD, exactly as today
```

## Components

- **`scripts/batch_evaluate.py`** (new) --
  - `evaluate_all_pending(pending_paths: list = None) -> list[dict]`:
    the shared scoring loop. Live-verified only (calls Gemini per JD, same
    convention as every other Gemini-calling piece in this project).
  - `_sort_key(result: dict) -> tuple`: pure helper, exact formula
    `(1 if result.get("error") else 0, -(result.get("composite_score") or 0))`
    -- errored entries always get `1` (sorts after all `0`s regardless of
    score), and `(result.get("composite_score") or 0)` safely defaults a
    missing/`None` score to `0` before negating, so an errored entry with
    no score key at all never raises. Python's default ascending sort then
    puts non-errored entries first, highest score first within that.
    Unit-tested directly -- deterministic, easy to get subtly wrong.

- **`cli.py`** (modify) --
  - `_should_proceed(count: int, skip_confirm: bool) -> bool`: small
    helper wrapping `click.confirm`; `skip_confirm=True` (the `--yes`
    flag) returns `True` immediately with no prompt. Unit-tested with
    `click.confirm` mocked.
  - `evaluate` command: `jd_file` becomes `required=False`. No file and no
    pending JDs -> "nothing to check" message (matches `scan`/`liveness`).
    No file, pending JDs exist -> gate -> `evaluate_all_pending()` ->
    print a sorted table (`#`, `Score`, `Recommendation`, `Company`,
    `Title`).
  - `run` command gains `--pick` (boolean flag). With `--pick`: gate ->
    `evaluate_all_pending()` -> if all entries errored, print a message
    and exit (no picker shown) -> `questionary.checkbox()` with each
    choice's `value` set to `source_file` directly (no custom
    index-to-path mapping needed -- the library returns the selected
    values verbatim) -> if the user selects nothing, print "No jobs
    selected, nothing to do." and exit -> otherwise, for each selected
    file path, call `orchestrator.run_pipeline(jd_path=path)` in
    sequence, accumulating completed/failed counts, printing the same
    summary shape `resume run` already prints today.

- **`requirements.txt`** (modify) -- add `questionary`.

## Data Flow

```
resume evaluate  (no file)
  → pending = jd_manager.get_pending_jds()
  → if empty: print "nothing pending", return
  → _should_proceed(len(pending), skip_confirm=args.yes)
      False -> abort, print nothing further
      True  -> results = batch_evaluate.evaluate_all_pending(pending)
               print sorted table

resume run --pick
  → pending = jd_manager.get_pending_jds()
  → if empty: print "nothing pending", return
  → _should_proceed(len(pending), skip_confirm=args.yes)
      False -> abort
      True  -> results = batch_evaluate.evaluate_all_pending(pending)
               valid = [r for r in results if not r["error"]]
               if not valid: print "nothing could be evaluated", return
               selected_paths = questionary.checkbox(choices=valid).ask()
               if not selected_paths: print "no jobs selected", return
               for path in selected_paths:
                   orchestrator.run_pipeline(jd_path=path)
               print completed/failed summary
```

## Error Handling

- Confirmation declined (or `--yes` omitted and user answers anything
  other than "y") -> abort before any scoring call is made, zero API cost
  incurred.
- Individual JD fails to evaluate -> `error: True` in its result dict,
  sorted last, printed with a `⚠️` marker in the table; does not stop the
  rest of the batch (mirrors `scan.py`/`liveness.py`'s per-item
  resilience).
- Empty pending queue -> same "nothing to check" pattern as `scan`/
  `liveness`, no confirmation gate shown (nothing to confirm).
- All entries errored in `--pick` mode -> skip the picker, print a clear
  message, exit -- never show an empty/all-broken checkbox list.
- Zero selections made in the picker -> print "No jobs selected, nothing
  to do." and exit without touching `run_pipeline`.
- Each selected JD's tailor call uses `run_pipeline`'s own existing
  per-file error handling unchanged -- one failure doesn't abort the rest
  of the selected set.

## Testing

- `batch_evaluate._sort_key()`: real unit tests -- confirms higher scores
  sort first, `error: True` entries always sort last regardless of score
  (including the edge case of an errored entry with no `composite_score`
  key at all).
- `cli.py`'s `_should_proceed()`: real unit tests with `click.confirm`
  mocked -- confirms `--yes` (`skip_confirm=True`) never calls
  `click.confirm` at all, and a mocked "no" answer returns `False`.
- `evaluate_all_pending()` itself: no mocks, live-verified against the
  real pending JDs (same convention as every other Gemini-calling piece
  built this session).
- The picker's `questionary.checkbox` selection-to-path mapping: no
  custom test needed -- it's the library's own `value=` passthrough
  behavior, not new code.
- Live verification: run `resume evaluate` (batch) and `resume run
  --pick` against the real 208 pending JDs, confirm the confirmation gate
  fires with the correct count, spot-check the sorted table/picker output
  and that a real selection correctly tailors only the chosen JD(s).
