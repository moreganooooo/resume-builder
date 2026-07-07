# Evaluated-Only, Scored, Sorted Resume Picker — Design

## Problem

"Customize Resume for a Specific JD" currently lists every pending JD via
`picker.pick_one_pending_jd()` — unfiltered, unsorted, no fit information.
With over 150 real pending JDs in `jds/` (from a recent scan), this list
is overwhelming to scroll and gives no signal about which roles are
actually worth building a resume for. Evaluation (`resume evaluate`)
already computes exactly that signal (`composite_score`, `recommendation`)
but never persists it anywhere — it's shown once in a table and
discarded, per `evaluate_fit()`'s explicit "no files are written" contract.

## Goals

1. "Customize Resume for a Specific JD" only lists JDs that have already
   been evaluated.
2. That list is sorted best-fit first (highest `composite_score`).
3. Each entry shows its score and recommendation alongside company/title.
4. An empty list (nothing evaluated yet) prints a hint pointing at
   "Evaluate ALL Pending JDs" / "Evaluate a Specific JD".
5. Evaluation results persist across runs without spending an extra
   Gemini call just to redisplay them.

## Non-Goals

- No change to the cover-letter picker (`_handle_coverletter_one`) —
  it already sources from `jds/completed/` for a different reason (a
  resume already exists) and wasn't part of this request.
- No staleness detection (e.g. re-evaluating if the JD file changes after
  its `_evaluation` was saved, or expiring old evaluations by age) — not
  a reported problem, and re-running evaluation naturally overwrites the
  stored result if someone wants a fresh score.
- No change to `pick_and_process()` / `resume run --pick`'s existing
  fresh-evaluate-every-time flow — that's a deliberately different,
  already-working picker (multi-select, always current); this design
  only touches the single-select "for a Specific JD" path.
- No change to `evaluate_fit()`'s signature or its callers' error
  handling — it still returns `{}` on failure exactly as today; the only
  change is what happens with a *successful* result.

## Architecture

### 1. Persisting an evaluation (`jd_manager.py`)

```python
def save_evaluation(jd_path: str, evaluation: dict) -> None:
    """Persists an evaluate_fit() result into the JD's own JSON file under
    an _evaluation key, so a later picker can filter/sort/label by it
    without re-running the (real, costly) Gemini evaluation call. No-ops
    silently for non-JSON-dict JDs (e.g. plain-text fixtures) -- they
    simply never become eligible for the evaluated-only picker."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    if not isinstance(data, dict):
        return

    data["_evaluation"] = {
        "composite_score": evaluation.get("composite_score"),
        "recommendation": evaluation.get("recommendation"),
        "hard_blockers": evaluation.get("hard_blockers") or [],
        "evaluated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(jd_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_evaluation(jd_path: str) -> dict | None:
    """Reads back a persisted _evaluation (see save_evaluation()), or None
    if the JD isn't a JSON dict or has never been evaluated."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_evaluation")
```

This matches the existing `_critique`/`_output_paths` convention already
used elsewhere in this codebase (metadata co-located in the JSON it
describes, under a leading-underscore key).

### 2. Keeping evaluation metadata out of Gemini prompts (`jd_manager.py`, `orchestrator.py`)

The JD file gets re-read as raw prompt text at three separate points in
its lifecycle: `evaluate_fit()`, `build_tailored_resume()`, and
`build_tailored_coverletter()` — all three currently do a plain
`open(jd_path).read()`. If `_evaluation` is embedded directly in the
file, it would leak into whichever of these runs *after* the evaluation
was saved (most commonly: evaluate, then later build) — Gemini would see
a stray scoring JSON blob mixed into what's supposed to be pure job
description text, which is quietly a data-quality bug, not just noise
(Step 1's keyword extraction reads directly from this text).

A single shared helper fixes it at the source:

```python
def read_jd_text(jd_path: str) -> str:
    """Reads a JD file's content for prompt use, stripping the persisted
    _evaluation key (see save_evaluation()) if present so a prior
    evaluation's score/recommendation never leaks into a Gemini prompt as
    if it were job-description content. Passes plain-text (or otherwise
    non-JSON-dict) JDs through unchanged. Raises FileNotFoundError exactly
    like a raw open() would, so existing call-site error handling needs
    no changes."""
    with open(jd_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    if isinstance(data, dict) and "_evaluation" in data:
        data = {k: v for k, v in data.items() if k != "_evaluation"}
        return json.dumps(data, indent=2)
    return raw_text
```

All three call sites change from:
```python
try:
    with open(jd_path, "r", encoding="utf-8") as f:
        jd_text = f.read()
except FileNotFoundError:
    print(f"  ERROR: JD file not found: {jd_path}")
    return {}
```
to:
```python
try:
    jd_text = jd_manager.read_jd_text(jd_path)
except FileNotFoundError:
    print(f"  ERROR: JD file not found: {jd_path}")
    return {}
```

### 3. Wiring the two evaluation entry points to persist

`batch_evaluate.evaluate_all_pending()` (covers both "Evaluate ALL
Pending JDs" and `resume run --pick`, since both call this function):

```python
for path in pending_paths:
    job_title, company_name = jd_manager.extract_job_meta(path)
    evaluation = engine.evaluate_fit(path)

    if not evaluation:
        results.append({...})  # unchanged
        continue

    jd_manager.save_evaluation(path, evaluation)  # new

    results.append({...})  # unchanged
```

`menu._handle_evaluate_one()` ("Evaluate a Specific JD" — calls
`evaluate_fit()` directly, not through `batch_evaluate`):

```python
def _handle_evaluate_one() -> bool:
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return False
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        return False
    jd_manager.save_evaluation(path, result)  # new
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")
    return True
```

### 4. The new picker (`picker.py`)

```python
def pick_one_evaluated_jd(pending_paths: list) -> str | None:
    """Single-choice picker restricted to pending JDs carrying a persisted
    _evaluation (jd_manager.save_evaluation(), written by a prior
    "Evaluate" run) -- sorted best composite_score first, each choice
    labeled with its score/recommendation. A JD with no _evaluation simply
    isn't eligible; it needs to be evaluated first."""
    evaluated = []
    for path in pending_paths:
        evaluation = jd_manager.read_evaluation(path)
        if not evaluation:
            continue
        title, company = jd_manager.extract_job_meta(path)
        evaluated.append((evaluation, path, title, company))

    if not evaluated:
        cli_art.console.print(
            "Nothing to pick from -- no evaluated JDs yet.\n"
            "Hint: Don't see the role you're expecting? Run an evaluation "
            "on it first (Evaluate ALL Pending JDs or Evaluate a Specific "
            "JD) -- then it'll appear in this list."
        )
        return None

    evaluated.sort(key=lambda item: -(item[0].get("composite_score") or 0))

    choices = [
        questionary.Choice(
            title=(
                f"{evaluation.get('composite_score')}/5 | {evaluation.get('recommendation')} | "
                f"{company or '?'} | {title or os.path.basename(path)}"
            ),
            value=path,
        )
        for evaluation, path, title, company in evaluated
    ]
    return questionary.select(
        "Which JD?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

`picker.py` already imports `os` and `questionary`, so no new imports
there. `pick_one_pending_jd()` stays untouched and in use (the
cover-letter picker still calls it).

### 5. Menu wiring (`menu.py`)

```python
def _handle_tailor_one() -> bool:
    path = picker.pick_one_evaluated_jd(jd_manager.get_pending_jds())
    if not path:
        return False
    completed, _failed = orchestrator.run_pipeline(jd_path=path)
    return completed > 0
```

(Was `picker.pick_one_pending_jd(...)`.)

## Data Flow

```
"Evaluate ALL Pending JDs" -> batch_evaluate.evaluate_all_pending()
  -> per JD: engine.evaluate_fit(path) [reads via jd_manager.read_jd_text()]
       -> success: jd_manager.save_evaluation(path, evaluation)  [writes _evaluation into the JD's own JSON]

"Evaluate a Specific JD" -> menu._handle_evaluate_one()
  -> engine.evaluate_fit(path) -> success: jd_manager.save_evaluation(path, result)

"Customize Resume for a Specific JD" -> menu._handle_tailor_one()
  -> picker.pick_one_evaluated_jd(jd_manager.get_pending_jds())
       -> per JD: jd_manager.read_evaluation(path) -- skip if None
       -> sort by composite_score desc, label, questionary.select()
  -> orchestrator.run_pipeline(jd_path=path)
       -> build_tailored_resume() reads via jd_manager.read_jd_text()
          (never sees the _evaluation block)
```

## Error Handling

- `save_evaluation()` silently no-ops on any read/parse failure or a
  non-dict JD (matches `_read_source_url_and_company()`'s existing
  defensive style elsewhere in `jd_manager.py`) -- evaluating a
  plain-text fixture still works exactly as it does today, it just can't
  be picked up later.
- `read_evaluation()` returns `None` under the same conditions, which
  `pick_one_evaluated_jd()` treats identically to "never evaluated."
- `read_jd_text()` raises `FileNotFoundError` exactly like today's raw
  `open()` did, so none of the three call sites' existing
  `except FileNotFoundError` handling needs to change.
- A JD with `composite_score: None` (shouldn't happen for a successful
  evaluation, since `fit_composite_score()` always returns a number, but
  defensively) sorts last via the same `or 0` pattern
  `batch_evaluate._sort_key()` already uses.

## Testing

- `jd_manager.save_evaluation()` / `read_evaluation()`: unit tests using
  a temp JSON JD file -- save then read-back returns the same
  score/recommendation; a plain-text (non-JSON) JD: `save_evaluation`
  no-ops without raising, `read_evaluation` returns `None`; a JD that was
  never evaluated returns `None`.
- `jd_manager.read_jd_text()`: unit tests -- a JD without `_evaluation`
  returns the raw text unchanged; a JD with `_evaluation` returns valid
  JSON text with that key stripped (and only that key -- other fields
  untouched); a plain-text JD returns the raw text unchanged; a missing
  file raises `FileNotFoundError`.
- `picker.pick_one_evaluated_jd()`: unit tests (same
  `patch("picker.jd_manager...")` / `patch("picker.questionary.select")`
  style already used in `tests/test_picker.py`'s
  `TestPickOnePendingJd`) -- an empty list returns `None` without
  prompting; JDs with no `_evaluation` are excluded from the choices;
  results are ordered best-`composite_score`-first regardless of input
  order; the printed hint appears (and `questionary.select` is never
  called) when nothing is evaluated.
- `batch_evaluate.evaluate_all_pending()`: existing tests continue to
  pass; add one confirming `jd_manager.save_evaluation` is called with
  the right arguments on a successful evaluation, and is *not* called on
  an errored one.
- `menu._handle_evaluate_one()`: existing tests continue to pass; add one
  confirming `jd_manager.save_evaluation` is called on success.
- Live verification: run "Evaluate ALL Pending JDs" against a handful of
  real pending JDs, then "Customize Resume for a Specific JD" and confirm
  only those JDs appear, sorted best-first, each labeled with its score.
