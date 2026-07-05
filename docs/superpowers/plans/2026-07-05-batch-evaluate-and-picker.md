# Batch Evaluation + Interactive Job Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Morgan evaluate every pending JD at once (`resume evaluate`, no file arg) instead of one at a time, and let her interactively select which pending JD(s) to actually tailor (`resume run --pick`) instead of only "everything" or "one named file."

**Architecture:** One shared function (`batch_evaluate.evaluate_all_pending()`) runs `ResumeEngine.evaluate_fit()` over every pending JD and returns a sorted (best-first) list of results; both `resume evaluate` (prints a table) and `resume run --pick` (feeds a `questionary` checkbox picker, then tailors just the selection) consume it. A shared confirmation-gate helper in `cli.py` guards both entry points, since both now carry the same real per-JD Gemini cost.

**Tech Stack:** Python 3.10+, Click (existing CLI framework), `questionary` (new dependency, arrow-key checkbox prompts), existing `orchestrator`/`jd_manager` modules.

## Global Constraints

- No persistence/caching of evaluate results across invocations -- every call re-scores fresh (Morgan's explicit choice: always live, never stale).
- No filtering/search within the picker for this pass -- full sorted list, `questionary`'s own scroll handles length.
- `resume run` (no `--pick`) and `resume evaluate <file>` (with a file) keep their exact current behavior -- both additions are purely additive.
- Confirmation gate: print the pending count, require y/n; a `--yes` flag skips it. Applies to both `resume evaluate` (batch) and `resume run --pick`.
- `questionary` is the one new dependency this plan introduces (add to `requirements.txt`).
- Spec: `docs/superpowers/specs/2026-07-05-batch-evaluate-and-picker-design.md` (approved 2026-07-05).

---

### Task 1: `scripts/batch_evaluate.py` -- shared scoring loop

**Files:**
- Create: `scripts/batch_evaluate.py`
- Test: `tests/test_batch_evaluate.py`

**Interfaces:**
- Consumes: `jd_manager.get_pending_jds() -> list[str]`, `jd_manager.extract_job_meta(jd_path: str) -> (job_title, company_name)`, `jd_manager.compute_job_key(jd_path: str) -> str`, `orchestrator.ResumeEngine().evaluate_fit(jd_path: str) -> dict` (returns `{}` on failure; on success has keys `archetype`, `hard_blockers`, `dimension_scores`, `recommendation`, `why`, `composite_score`).
- Produces: `batch_evaluate.evaluate_all_pending(pending_paths: list = None) -> list[dict]` (each dict: `job_key`, `source_file`, `company_name`, `job_title`, `composite_score`, `recommendation`, `hard_blockers`, `error`) and `batch_evaluate._sort_key(result: dict) -> tuple`, both consumed directly by Task 3 and Task 4.

- [ ] **Step 1: Write the failing tests for `_sort_key`**

Create `tests/test_batch_evaluate.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import batch_evaluate  # noqa: E402


class TestSortKey(unittest.TestCase):

    def test_higher_score_sorts_first(self):
        results = [
            {"composite_score": 3.0, "error": False},
            {"composite_score": 4.8, "error": False},
            {"composite_score": 1.2, "error": False},
        ]
        results.sort(key=batch_evaluate._sort_key)
        scores = [r["composite_score"] for r in results]
        self.assertEqual(scores, [4.8, 3.0, 1.2])

    def test_errored_entries_always_sort_last_regardless_of_score(self):
        results = [
            {"composite_score": 1.0, "error": False},
            {"composite_score": None, "error": True},
            {"composite_score": 4.9, "error": False},
        ]
        results.sort(key=batch_evaluate._sort_key)
        self.assertFalse(results[0]["error"])
        self.assertFalse(results[1]["error"])
        self.assertTrue(results[2]["error"])
        self.assertEqual(results[0]["composite_score"], 4.9)

    def test_errored_entry_with_missing_score_key_does_not_raise(self):
        results = [
            {"error": True},
            {"composite_score": 2.0, "error": False},
        ]
        results.sort(key=batch_evaluate._sort_key)
        self.assertFalse(results[0]["error"])
        self.assertTrue(results[1]["error"])

    def test_errored_entry_with_none_score_does_not_raise(self):
        results = [
            {"composite_score": None, "error": True},
            {"composite_score": 3.5, "error": False},
        ]
        results.sort(key=batch_evaluate._sort_key)
        self.assertFalse(results[0]["error"])
        self.assertTrue(results[1]["error"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_batch_evaluate -v`
Expected: `ModuleNotFoundError: No module named 'batch_evaluate'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/batch_evaluate.py`:

```python
"""
batch_evaluate.py -- the shared "evaluate every pending JD" scoring loop,
reused by both `resume evaluate` (batch mode) and `resume run --pick` (the
interactive picker). Real Gemini cost: one call per pending JD. See
docs/superpowers/specs/2026-07-05-batch-evaluate-and-picker-design.md.
"""

import jd_manager
import orchestrator


def _sort_key(result: dict) -> tuple:
    """Errored entries always sort last, regardless of score; otherwise
    highest composite_score first. Safe against a missing/None score on
    an errored entry -- `or 0` defaults it before negating."""
    return (1 if result.get("error") else 0, -(result.get("composite_score") or 0))


def evaluate_all_pending(pending_paths: list = None) -> list:
    """
    Runs ResumeEngine.evaluate_fit() over every path in pending_paths
    (defaults to jd_manager.get_pending_jds() if None). Returns a list of
    {job_key, source_file, company_name, job_title, composite_score,
    recommendation, hard_blockers, error} sorted via _sort_key() --
    highest score first, errored entries always last. A JD that fails to
    evaluate gets error=True instead of crashing the whole batch.
    """
    if pending_paths is None:
        pending_paths = jd_manager.get_pending_jds()

    engine = orchestrator.ResumeEngine()
    results = []

    for path in pending_paths:
        job_title, company_name = jd_manager.extract_job_meta(path)
        evaluation = engine.evaluate_fit(path)

        if not evaluation:
            results.append({
                "job_key": jd_manager.compute_job_key(path),
                "source_file": path,
                "company_name": company_name or "unknown",
                "job_title": job_title or "unknown",
                "composite_score": None,
                "recommendation": None,
                "hard_blockers": [],
                "error": True,
            })
            continue

        results.append({
            "job_key": jd_manager.compute_job_key(path),
            "source_file": path,
            "company_name": company_name or "unknown",
            "job_title": job_title or "unknown",
            "composite_score": evaluation.get("composite_score"),
            "recommendation": evaluation.get("recommendation"),
            "hard_blockers": evaluation.get("hard_blockers") or [],
            "error": False,
        })

    results.sort(key=_sort_key)
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_batch_evaluate -v`
Expected: all 4 tests pass.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 4 from the prior total (202 → 206).

- [ ] **Step 6: Live verification -- real evaluate_fit calls against a small, cost-conscious subset**

`evaluate_all_pending()` itself is not unit-tested (it calls Gemini) -- verify it live against just 2 real pending JDs, not the full 208-JD pile, to keep this check cheap:

```bash
source .venv/bin/activate
python3 -c "
import sys
sys.path.insert(0, 'scripts')
import batch_evaluate

paths = [
    'jds/2026-07-04_3DSource_SocialMediaMarketingSpecialist.json',
    'jds/2026-07-04_4MINDS_CampaignManager.json',
]
results = batch_evaluate.evaluate_all_pending(paths)
for r in results:
    print(r['company_name'], '|', r['job_title'], '|', r['composite_score'], '|', r['recommendation'], '|', 'ERROR' if r['error'] else 'ok')
"
```

Expected: 2 rows printed, sorted with the higher `composite_score` first, both `error: False` (both are real, well-formed JD files), no crash.

- [ ] **Step 7: Commit**

```bash
git add scripts/batch_evaluate.py tests/test_batch_evaluate.py
git commit -m "$(cat <<'EOF'
Add shared evaluate_all_pending() scoring loop

The one function both resume evaluate (batch mode) and resume run
--pick will consume -- runs evaluate_fit() over every pending JD,
returns a sorted (best-first, errors-last) list. Part of the batch
evaluate + interactive picker design (spec 2026-07-05).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `cli.py`'s `_should_proceed` confirmation-gate helper

**Files:**
- Modify: `scripts/cli.py` (add `_should_proceed`, no command wiring yet -- that's Tasks 3 and 4)
- Test: `tests/test_cli_should_proceed.py`

**Interfaces:**
- Consumes: `click.confirm` (mocked in tests).
- Produces: `cli._should_proceed(count: int, skip_confirm: bool) -> bool`, consumed directly by Task 3 and Task 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_should_proceed.py`:

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import cli  # noqa: E402


class TestShouldProceed(unittest.TestCase):

    def test_skip_confirm_returns_true_without_prompting(self):
        with patch("cli.click.confirm") as mock_confirm:
            result = cli._should_proceed(208, skip_confirm=True)
        self.assertTrue(result)
        mock_confirm.assert_not_called()

    @patch("cli.click.confirm")
    def test_confirm_declined_returns_false(self, mock_confirm):
        mock_confirm.return_value = False
        result = cli._should_proceed(208, skip_confirm=False)
        self.assertFalse(result)
        mock_confirm.assert_called_once()

    @patch("cli.click.confirm")
    def test_confirm_accepted_returns_true(self, mock_confirm):
        mock_confirm.return_value = True
        result = cli._should_proceed(5, skip_confirm=False)
        self.assertTrue(result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_cli_should_proceed -v`
Expected: `AttributeError: module 'cli' has no attribute '_should_proceed'`.

- [ ] **Step 3: Add the helper to `cli.py`**

In `scripts/cli.py`, find:

```python
import cli_art
import orchestrator
import scan as scan_module
import liveness as liveness_module


@click.group()
def cli():
    """resume-builder: tailor and render resumes per job description."""
```

Change to:

```python
import cli_art
import orchestrator
import scan as scan_module
import liveness as liveness_module


def _should_proceed(count: int, skip_confirm: bool) -> bool:
    """Confirmation gate for anything that scores every pending JD (real
    Gemini cost, one call per JD). skip_confirm=True (the --yes flag)
    bypasses the prompt entirely."""
    if skip_confirm:
        return True
    return click.confirm(f"About to evaluate {count} pending JD(s) -- one real Gemini call each. Continue?")


@click.group()
def cli():
    """resume-builder: tailor and render resumes per job description."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_cli_should_proceed -v`
Expected: all 3 tests pass.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 3 from Task 1's total (206 → 209).

- [ ] **Step 6: Commit**

```bash
git add scripts/cli.py tests/test_cli_should_proceed.py
git commit -m "$(cat <<'EOF'
Add cli._should_proceed() confirmation-gate helper

Not wired into any command yet -- resume evaluate (batch) and resume
run --pick both consume it in the next two tasks. --yes bypasses the
prompt entirely for scripting.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Wire `resume evaluate` batch mode

**Files:**
- Modify: `scripts/cli.py` (the `evaluate` command)

**Interfaces:**
- Consumes: `batch_evaluate.evaluate_all_pending(pending_paths) -> list[dict]` (Task 1), `cli._should_proceed(count, skip_confirm) -> bool` (Task 2), `jd_manager.get_pending_jds() -> list[str]`.
- Produces: no new public interface -- `resume evaluate <file>`'s existing behavior is unchanged; `resume evaluate` (no file) is new user-facing behavior only.

No automated tests for this task -- it's CLI wiring around `evaluate_all_pending()` (already covered) and `_should_proceed()` (already covered); the only new thing is print formatting, verified live.

- [ ] **Step 1: Add the import**

In `scripts/cli.py`, find:

```python
import cli_art
import orchestrator
import scan as scan_module
import liveness as liveness_module
```

Change to:

```python
import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import scan as scan_module
import liveness as liveness_module
```

- [ ] **Step 2: Make `jd_file` optional and add batch mode**

In `scripts/cli.py`, find:

```python
@cli.command()
@click.argument("jd_file", type=click.Path(exists=True))
def evaluate(jd_file):
    """Score a JD's fit (go/no-go) without building a resume."""
    cli_art.display_banner(f"Evaluating: {jd_file}")
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(jd_file)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        raise SystemExit(1)

    scores = result.get("dimension_scores", {})
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")

    for dim, weight in orchestrator.FIT_DIMENSION_WEIGHTS.items():
        cli_art.console.print(f"  {dim:<22} {scores.get(dim, '-')}/5  (weight {weight:.0%})")

    blockers = result.get("hard_blockers") or []
    if blockers:
        cli_art.console.print(f"\n{cli_art.WARNING} Hard blockers:")
        for b in blockers:
            cli_art.console.print(f"  - {b}")

    cli_art.console.print(f"\n[bold]Why:[/bold] {result.get('why', '')}\n")
```

Change to:

```python
@cli.command()
@click.argument("jd_file", required=False, type=click.Path(exists=True))
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt for batch mode")
def evaluate(jd_file, yes):
    """Score a JD's fit (go/no-go) without building a resume. Omit JD_FILE to evaluate every pending JD."""
    if jd_file is None:
        pending = jd_manager.get_pending_jds()
        if not pending:
            cli_art.console.print("Nothing to evaluate -- no pending JDs.")
            return
        if not _should_proceed(len(pending), yes):
            cli_art.console.print("Aborted.")
            return

        cli_art.display_banner(f"Evaluating {len(pending)} pending JD(s)")
        results = batch_evaluate.evaluate_all_pending(pending)

        cli_art.console.print(f"\n{'#':<4}{'Score':<8}{'Rec.':<20}{'Company':<25}{'Title'}")
        for i, r in enumerate(results, 1):
            score_str = "ERROR" if r["error"] else f"{r['composite_score']}/5"
            rec_str = r["recommendation"] or "-"
            cli_art.console.print(f"{i:<4}{score_str:<8}{rec_str:<20}{r['company_name']:<25}{r['job_title']}")
        cli_art.console.print()
        return

    cli_art.display_banner(f"Evaluating: {jd_file}")
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(jd_file)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        raise SystemExit(1)

    scores = result.get("dimension_scores", {})
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")

    for dim, weight in orchestrator.FIT_DIMENSION_WEIGHTS.items():
        cli_art.console.print(f"  {dim:<22} {scores.get(dim, '-')}/5  (weight {weight:.0%})")

    blockers = result.get("hard_blockers") or []
    if blockers:
        cli_art.console.print(f"\n{cli_art.WARNING} Hard blockers:")
        for b in blockers:
            cli_art.console.print(f"  - {b}")

    cli_art.console.print(f"\n[bold]Why:[/bold] {result.get('why', '')}\n")
```

- [ ] **Step 3: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same count as Task 2 (209) -- no new automated tests this task.

- [ ] **Step 4: Live verification -- single-file mode still works unchanged**

```bash
source .venv/bin/activate
python scripts/cli.py evaluate jds/2026-07-04_3DSource_SocialMediaMarketingSpecialist.json
```

Expected: identical output shape to before this task (archetype, composite score, recommendation, dimension breakdown, blockers if any, why) -- confirms the optional-arg change didn't break single-file mode.

- [ ] **Step 5: Live verification -- batch mode against a small, cost-conscious subset**

Batch mode always scans `jd_manager.get_pending_jds()` (all 208 real pending JDs) -- to verify the CLI wiring without incurring that full cost, temporarily move all but 2 real JDs out of `jds/` for this one check:

```bash
mkdir -p /tmp/jds_holdback
cd /Users/morganescott/resume-builder
find jds -maxdepth 1 -name "*.json" ! -name "2026-07-04_3DSource_SocialMediaMarketingSpecialist.json" ! -name "2026-07-04_4MINDS_CampaignManager.json" -exec mv {} /tmp/jds_holdback/ \;
ls jds/*.json
```

Expected: only the 2 held-back files remain in `jds/`.

```bash
source .venv/bin/activate
python scripts/cli.py evaluate
```

Expected: prompt reads "About to evaluate 2 pending JD(s)..." -- type `y` -- a 2-row sorted table prints (score, recommendation, company, title), no crash.

```bash
python scripts/cli.py evaluate --yes
```

Expected: no prompt at all, straight to the table.

Restore the held-back JDs:

```bash
mv /tmp/jds_holdback/*.json jds/
rmdir /tmp/jds_holdback
ls jds/*.json | wc -l
```

Expected: count back to 208.

- [ ] **Step 6: Commit**

```bash
git add scripts/cli.py
git commit -m "$(cat <<'EOF'
Wire resume evaluate's batch mode (no file arg = evaluate every pending JD)

Existing single-file behavior (resume evaluate <file>) unchanged. Batch
mode gates on cli._should_proceed() before running
batch_evaluate.evaluate_all_pending(), then prints a sorted summary
table. --yes skips the confirmation prompt.

Live-verified: single-file mode unchanged, batch mode's confirmation
gate and table both work against a real (small) subset of pending JDs.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Wire `resume run --pick` interactive picker

**Files:**
- Modify: `scripts/cli.py` (the `run` command)
- Modify: `requirements.txt` (add `questionary`)
- Modify: `scripts/resume-cli.sh` (forward `--pick`/`--yes` through the existing `run` case, which already does `"$@"` forwarding when args are present)

**Interfaces:**
- Consumes: `batch_evaluate.evaluate_all_pending(pending_paths) -> list[dict]` (Task 1), `cli._should_proceed(count, skip_confirm) -> bool` (Task 2), `orchestrator.run_pipeline(jd_path=..., master_resume_path=...) -> (completed: int, failed: int)`, `questionary.checkbox(message, choices) -> Question` / `questionary.Choice(title, value)`.
- Produces: no new public interface -- `resume run` (no flags) keeps its exact current behavior; `resume run --pick` is new.

No automated tests for this task -- `questionary.checkbox(...).ask()` is an interactive terminal prompt (blocks on real keyboard input) and `run_pipeline` is the already-proven existing pipeline; this is CLI wiring around two already-tested/already-proven pieces, verified live.

- [ ] **Step 1: Add `questionary` to `requirements.txt`**

In `requirements.txt`, find:

```
browser_cookie3
```

Change to:

```
browser_cookie3
questionary
```

Install it:

```bash
source .venv/bin/activate && pip install questionary
```

- [ ] **Step 2: Add the import**

In `scripts/cli.py`, find:

```python
import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import scan as scan_module
import liveness as liveness_module
```

Change to:

```python
import questionary

import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import scan as scan_module
import liveness as liveness_module
```

- [ ] **Step 3: Add `--pick`/`--yes` to the `run` command**

In `scripts/cli.py`, find:

```python
@cli.command(name="run")
@click.option("--master", default=None, help="Path to master resume JSON (optional)")
def run_batch(master):
    """Batch-process every pending JD in jds/."""
    cli_art.display_banner("Batch run: all pending JDs")
    orchestrator.run_pipeline(master_resume_path=master)
```

Change to:

```python
@cli.command(name="run")
@click.option("--master", default=None, help="Path to master resume JSON (optional)")
@click.option("--pick", is_flag=True, default=False, help="Interactively select which pending JD(s) to tailor")
@click.option("--yes", is_flag=True, default=False, help="Skip the confirmation prompt for --pick")
def run_batch(master, pick, yes):
    """Batch-process every pending JD in jds/."""
    if not pick:
        cli_art.display_banner("Batch run: all pending JDs")
        orchestrator.run_pipeline(master_resume_path=master)
        return

    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to pick from -- no pending JDs.")
        return
    if not _should_proceed(len(pending), yes):
        cli_art.console.print("Aborted.")
        return

    cli_art.display_banner(f"Evaluating {len(pending)} pending JD(s) for picker")
    results = batch_evaluate.evaluate_all_pending(pending)
    valid = [r for r in results if not r["error"]]
    if not valid:
        cli_art.console.print("Nothing could be evaluated -- no picker to show.")
        return

    choices = [
        questionary.Choice(
            title=f"{r['composite_score']}/5 | {r['recommendation']} | {r['company_name']} | {r['job_title']}",
            value=r["source_file"],
        )
        for r in valid
    ]
    selected_paths = questionary.checkbox("Select JD(s) to tailor:", choices=choices).ask()
    if not selected_paths:
        cli_art.console.print("No jobs selected, nothing to do.")
        return

    completed = 0
    failed = 0
    for path in selected_paths:
        c, f = orchestrator.run_pipeline(jd_path=path, master_resume_path=master)
        completed += c
        failed += f
    cli_art.console.print(f"\nPicked batch summary: {completed} completed, {failed} failed.")
```

- [ ] **Step 4: Confirm the shell shortcut already forwards these flags**

`scripts/resume-cli.sh`'s `run)` case already does:

```bash
run)
  ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate
    if [ $# -gt 0 ]; then
      python scripts/cli.py tailor "$@"
    else
      python scripts/cli.py run
    fi )
  ;;
```

This has a real bug for the new flag: `resume run --pick` has `$# -gt 0` (one arg, `--pick`), so it would route to `tailor "--pick"` instead of `run --pick` -- `tailor` expects a JD file path, not a flag, and would fail with a confusing Click path-validation error. Fix it to route flags (anything starting with `-`) to `run`, and only route non-flag arguments to `tailor`:

In `scripts/resume-cli.sh`, find:

```bash
    run)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate
        if [ $# -gt 0 ]; then
          python scripts/cli.py tailor "$@"
        else
          python scripts/cli.py run
        fi )
      ;;
```

Change to:

```bash
    run)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate
        if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then
          python scripts/cli.py tailor "$@"
        else
          python scripts/cli.py run "$@"
        fi )
      ;;
```

(`"${1#-}" = "$1"` is true only when `$1` does NOT start with `-` -- i.e. it's a file path, not a flag. A bare `resume run` still has `$# -eq 0`, so it still takes the `else` branch unchanged.)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same count as Task 3 (209) -- no new automated tests this task.

- [ ] **Step 6: Live verification -- `resume run` (no flags) still works unchanged**

This is the expensive, well-known real batch path (208 real JDs) -- do NOT run it live for this check. Instead confirm via `--help` that the command still parses correctly and the flag is additive:

```bash
source .venv/bin/activate
python scripts/cli.py run --help
```

Expected:

```
Usage: cli.py run [OPTIONS]

  Batch-process every pending JD in jds/.

Options:
  --master TEXT  Path to master resume JSON (optional)
  --pick         Interactively select which pending JD(s) to tailor
  --yes          Skip the confirmation prompt for --pick
  --help         Show this message and exit.
```

- [ ] **Step 7: Live verification -- `resume run --pick` against a small, cost-conscious subset**

Same holdback technique as Task 3's Step 5, so the picker's evaluate pass only costs 2 real Gemini calls instead of 208:

```bash
mkdir -p /tmp/jds_holdback
cd /Users/morganescott/resume-builder
find jds -maxdepth 1 -name "*.json" ! -name "2026-07-04_3DSource_SocialMediaMarketingSpecialist.json" ! -name "2026-07-04_4MINDS_CampaignManager.json" -exec mv {} /tmp/jds_holdback/ \;
ls jds/*.json
```

Expected: only the 2 held-back files remain.

```bash
source .venv/bin/activate
python scripts/cli.py run --pick
```

Expected: prompt reads "About to evaluate 2 pending JD(s)..." -- type `y` -- a 2-item checkbox list appears, each line showing `score/5 | recommendation | company | title`. Select one with space, confirm with enter. Confirm the tailor pipeline runs for just that one JD (watch for the usual Step 1-7 tailor output), and the final line reads "Picked batch summary: 1 completed, 0 failed." (or 0 completed/1 failed if that JD's build genuinely fails for an unrelated reason -- either way, confirms only the selected JD ran, not both).

Restore the held-back JDs:

```bash
mv /tmp/jds_holdback/*.json jds/
rmdir /tmp/jds_holdback
ls jds/*.json | wc -l
```

Expected: count back to 208 minus however many the picker just completed/moved to `jds/completed/` in the prior step (check `jds/completed/` for the newly tailored one).

- [ ] **Step 8: Live verification -- `resume run --pick` shell shortcut routes correctly**

Confirm the shell wrapper's flag-vs-path routing fix from Step 4 sends a flag argument to `run`, not `tailor`:

```bash
source scripts/resume-cli.sh
resume run --help
```

Expected: the same `run` help output as Step 6 (not a `tailor`-shaped error about a missing/invalid JD file) -- confirms the shell shortcut correctly routes a flag-shaped argument (`--help`, same code path as `--pick`) to `cli.py run` rather than `cli.py tailor`.

- [ ] **Step 9: Commit**

```bash
git add scripts/cli.py scripts/resume-cli.sh requirements.txt
git commit -m "$(cat <<'EOF'
Add resume run --pick interactive job picker

Confirmation-gated (same cli._should_proceed() as batch evaluate) ->
batch_evaluate.evaluate_all_pending() -> a questionary checkbox list
(score/recommendation/company/title, best-first) -> tailors just the
selected JD(s) via the existing orchestrator.run_pipeline(), one at a
time. resume run (no --pick) is completely unchanged.

Also fixed a real routing bug in resume-cli.sh's run case, caught while
wiring this in: it only checked "any args present" to decide tailor vs
run, so `resume run --pick` would have been misrouted to `tailor
"--pick"` (a flag, not a JD file path) instead of `run --pick`. Now
routes flag-shaped args (leading "-") to run, non-flag args to tailor.

New dependency: questionary (arrow-key checkbox prompts).

Live-verified against a small (2-JD) real subset: the confirmation gate
fires with the correct count, the picker displays and selects
correctly, and only the selected JD gets tailored. resume run (no
flags) and the shell shortcut's flag routing both confirmed unchanged/
fixed via --help checks rather than a full 208-JD run.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
