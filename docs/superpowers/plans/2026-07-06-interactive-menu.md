# Interactive Top-Level Menu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bare `resume` (both the shell shortcut and `python scripts/cli.py` directly) launches an interactive `questionary`-driven menu covering every existing action, styled and structured after job_automater's own interactive menu -- and the "confirm gate → evaluate → checkbox picker → process selection" flow currently duplicated in `resume run --pick`/`resume coverletter --pick` becomes one shared function both those commands and the new menu call.

**Architecture:** `cli_art.py` gains a borrowed `questionary.Style` theme and a Rich-Table renderer for scored JD lists; a new `picker.py` houses the deduplicated pick-and-process flow; a new `menu.py` houses the top-level `while True` / `questionary.select()` loop; `cli.py`'s existing commands get refactored onto this shared infrastructure with zero external behavior change, and its `@click.group()` gains `invoke_without_command=True` so a bare invocation launches the menu.

**Tech Stack:** Python 3.10+, Click, `questionary` (already a dependency), `rich` (already a dependency).

## Global Constraints

- Bare `resume` (shell shortcut) and bare `python scripts/cli.py` (direct) must launch the menu identically -- both entry points stay in sync, per this project's existing convention.
- Every existing command's direct-invocation behavior (`resume tailor <file>`, `resume run --pick`, `resume evaluate`, etc.) must be externally unchanged after this plan -- these are refactors, not behavior changes, and existing tests must keep passing unchanged.
- The menu exposes single-file actions too (tailor/coverletter/evaluate one named JD), prompting for a path via `questionary.path()` when selected -- confirmed 2026-07-06.
- `resume evaluate`'s batch-mode table upgrades to the new Rich Table renderer in this same pass -- confirmed 2026-07-06.
- Spec: `docs/superpowers/specs/2026-07-06-interactive-menu-design.md` (approved 2026-07-06).

---

### Task 1: `cli_art.py` -- borrowed style + scored-table renderer

**Files:**
- Modify: `scripts/cli_art.py`

**Interfaces:**
- Consumes: nothing new (pure Rich/questionary presentation code).
- Produces: `cli_art.QUESTIONARY_STYLE` (a `questionary.Style` instance) and `cli_art.render_fit_table(results: list) -> None`, both consumed directly by Task 2 (`picker.py`), Task 3 (refactored `run --pick`/`coverletter --pick`), Task 4 (`evaluate`'s batch mode), and Task 5 (`menu.py`). `results` is the same list shape `batch_evaluate.evaluate_all_pending()` returns: `{job_key, source_file, company_name, job_title, composite_score, recommendation, hard_blockers, error}`.

No automated tests for this task -- Rich console output, visually verified live in Step 3 below (same convention as the rest of `cli_art.py`, which has no existing tests either).

- [ ] **Step 1: Add the borrowed style and the table renderer**

In `scripts/cli_art.py`, find:

```python
"""Lightweight banner/symbols for resume-builder's CLI, in job_automater's
cli_art.py style (rich Console/Panel) but trimmed down -- no hand-drawn ASCII
block art, just a clean styled banner."""

from rich.console import Console
from rich.panel import Panel

console = Console()

SUCCESS = "[bold green]✓[/bold green]"
ERROR = "[bold red]✗[/bold red]"
WARNING = "[bold yellow]⚠[/bold yellow]"


def display_banner(subtitle: str = "") -> None:
    body = "[bold cyan]RESUME BUILDER[/bold cyan]"
    if subtitle:
        body += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel(body, border_style="cyan"))
```

Change to:

```python
"""Lightweight banner/symbols for resume-builder's CLI, in job_automater's
cli_art.py style (rich Console/Panel) but trimmed down -- no hand-drawn ASCII
block art, just a clean styled banner."""

from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

SUCCESS = "[bold green]✓[/bold green]"
ERROR = "[bold red]✗[/bold red]"
WARNING = "[bold yellow]⚠[/bold yellow]"

# Ported from job_automater/cli.py:47-57 (its `custom_style`) so every
# questionary prompt in this project -- old (--pick checkboxes) and new
# (the interactive menu) -- shares one consistent theme.
QUESTIONARY_STYLE = Style([
    ('qmark', 'fg:#673ab7 bold'),
    ('question', 'bold'),
    ('answer', 'fg:#2196f3 bold'),
    ('pointer', 'fg:#673ab7 bold'),
    ('highlighted', 'fg:#673ab7 bold'),
    ('selected', 'fg:#4caf50'),
    ('separator', 'fg:#cc5454'),
    ('instruction', ''),
    ('text', ''),
])

# Recommendation values match orchestrator.py's FitEvaluationSchema Literal
# exactly: "Strong pursue", "Selective pursue", "Low-priority pursue", "Skip".
_RECOMMENDATION_COLORS = {
    "Strong pursue": "green",
    "Selective pursue": "cyan",
    "Low-priority pursue": "yellow",
    "Skip": "red dim",
}


def display_banner(subtitle: str = "") -> None:
    body = "[bold cyan]RESUME BUILDER[/bold cyan]"
    if subtitle:
        body += f"\n[dim]{subtitle}[/dim]"
    console.print(Panel(body, border_style="cyan"))


def render_fit_table(results: list) -> None:
    """Renders batch_evaluate.evaluate_all_pending()'s result list as a
    Rich Table, colored by recommendation tier (modeled on job_automater's
    display_job_table(), cli.py:73-142). results is expected pre-sorted
    (evaluate_all_pending() already sorts best-first, errors-last)."""
    table = Table(box=None, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    table.add_column("Company")
    table.add_column("Title")

    for i, r in enumerate(results, 1):
        if r["error"]:
            table.add_row(str(i), "[red]ERROR[/red]", "-", r["company_name"], r["job_title"])
            continue
        color = _RECOMMENDATION_COLORS.get(r["recommendation"], "white")
        table.add_row(
            str(i),
            f"[{color}]{r['composite_score']}/5[/{color}]",
            f"[{color}]{r['recommendation']}[/{color}]",
            r["company_name"],
            r["job_title"],
        )

    console.print(table)
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same count as before (214) -- pure addition, no existing behavior touched.

- [ ] **Step 3: Live verification -- confirm the table renders against real evaluate results**

```bash
source .venv/bin/activate
python3 -c "
import sys
sys.path.insert(0, 'scripts')
import cli_art

fake_results = [
    {'company_name': '4MINDS', 'job_title': 'Campaign Manager', 'composite_score': 4.67, 'recommendation': 'Strong pursue', 'error': False},
    {'company_name': '3D Source', 'job_title': 'Social Media Marketing Specialist', 'composite_score': 3.1, 'recommendation': 'Low-priority pursue', 'error': False},
    {'company_name': 'Acme Corp', 'job_title': 'Broken JD', 'composite_score': None, 'recommendation': None, 'error': True},
]
cli_art.render_fit_table(fake_results)
"
```

Expected: a 3-row table prints with no crash -- row 1 in green, row 2 in yellow, row 3 showing `ERROR` in red for the Score column.

- [ ] **Step 4: Commit**

```bash
git add scripts/cli_art.py
git commit -m "$(cat <<'EOF'
Add borrowed questionary style + Rich Table renderer to cli_art.py

QUESTIONARY_STYLE ported from job_automater/cli.py:47-57 so every
questionary prompt in this project shares one theme. render_fit_table()
is a Rich Table version of job_automater's display_job_table() pattern,
colored by recommendation tier -- not wired into anything yet, that's
the next few tasks.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `scripts/picker.py` -- shared pick-and-process flow

**Files:**
- Create: `scripts/picker.py`
- Test: `tests/test_picker.py`

**Interfaces:**
- Consumes: `cli_art.console`, `cli_art.display_banner`, `cli_art.render_fit_table` (Task 1), `batch_evaluate.evaluate_all_pending(pending_paths) -> list[dict]` (existing), `click.confirm` (mocked in tests).
- Produces: `picker.pick_and_process(pending_paths: list, process_one: callable, action_verb: str, skip_confirm: bool = False) -> tuple[int, int]`, consumed directly by Task 3 (refactored `run --pick`/`coverletter --pick`) and Task 5 (`menu.py`'s tailor-pick/coverletter-pick handlers). `process_one(path: str) -> Any` is expected truthy on success, falsy on failure.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_picker.py`:

```python
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import picker  # noqa: E402


class TestPickAndProcess(unittest.TestCase):

    def test_empty_pending_returns_zero_zero_without_confirming(self):
        with patch("picker.click.confirm") as mock_confirm:
            result = picker.pick_and_process([], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))
        mock_confirm.assert_not_called()

    def test_declined_confirmation_returns_zero_zero_without_evaluating(self):
        with patch("picker.click.confirm", return_value=False), \
             patch("picker.batch_evaluate.evaluate_all_pending") as mock_evaluate:
            result = picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))
        mock_evaluate.assert_not_called()

    def test_all_errored_results_returns_zero_zero_without_showing_picker(self):
        with patch("picker.click.confirm", return_value=True), \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": None, "recommendation": None, "error": True},
             ]), \
             patch("picker.questionary.checkbox") as mock_checkbox:
            result = picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))
        mock_checkbox.assert_not_called()

    def test_nothing_selected_returns_zero_zero(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = None
        with patch("picker.click.confirm", return_value=True), \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": 4.0, "recommendation": "Strong pursue", "error": False},
             ]), \
             patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor")
        self.assertEqual(result, (0, 0))

    def test_processes_only_selected_paths_and_counts_success_and_failure(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/a.json", "jds/b.json"]

        def fake_process(path):
            return path == "jds/a.json"  # a succeeds, b fails

        with patch("picker.click.confirm", return_value=True), \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": 4.0, "recommendation": "Strong pursue", "error": False},
                 {"source_file": "jds/b.json", "company_name": "B", "job_title": "Role B",
                  "composite_score": 3.0, "recommendation": "Selective pursue", "error": False},
             ]), \
             patch("picker.questionary.checkbox", return_value=mock_question):
            result = picker.pick_and_process(["jds/a.json", "jds/b.json"], fake_process, "tailor")
        self.assertEqual(result, (1, 1))

    def test_skip_confirm_true_never_calls_click_confirm(self):
        mock_question = MagicMock()
        mock_question.ask.return_value = ["jds/a.json"]
        with patch("picker.click.confirm") as mock_confirm, \
             patch("picker.batch_evaluate.evaluate_all_pending", return_value=[
                 {"source_file": "jds/a.json", "company_name": "A", "job_title": "Role A",
                  "composite_score": 4.0, "recommendation": "Strong pursue", "error": False},
             ]), \
             patch("picker.questionary.checkbox", return_value=mock_question):
            picker.pick_and_process(["jds/a.json"], lambda path: True, "tailor", skip_confirm=True)
        mock_confirm.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_picker -v`
Expected: `ModuleNotFoundError: No module named 'picker'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/picker.py`:

```python
"""
picker.py -- the shared "confirm gate -> evaluate every pending JD ->
checkbox picker -> process each selection" flow. Used by resume run
--pick, resume coverletter --pick, and the interactive menu's own
tailor-pick/coverletter-pick items -- one implementation instead of four.
"""

import click
import questionary

import cli_art
import batch_evaluate


def should_proceed(count: int, skip_confirm: bool) -> bool:
    """Standalone copy of cli._should_proceed's exact logic -- duplicated
    rather than imported, since cli.py will import menu.py (for the bare-
    invocation menu launch) which imports this module; cli.py importing
    picker.py directly too is fine, but picker.py must not import cli.py
    back, to avoid a cycle."""
    if skip_confirm:
        return True
    return click.confirm(f"About to evaluate {count} pending JD(s) -- one real Gemini call each. Continue?")


def pick_and_process(pending_paths: list, process_one, action_verb: str, skip_confirm: bool = False) -> tuple:
    """
    Shared flow: confirm gate -> batch_evaluate.evaluate_all_pending() ->
    cli_art.render_fit_table() -> questionary.checkbox() (labeled via
    action_verb) -> process_one(path) for each selected path. Returns
    (completed, failed) -- both 0 if aborted, empty, or nothing
    selected/evaluable. process_one(path) should return truthy on
    success, falsy on failure.
    """
    if not pending_paths:
        cli_art.console.print("Nothing to pick from -- no pending JDs.")
        return (0, 0)
    if not should_proceed(len(pending_paths), skip_confirm):
        cli_art.console.print("Aborted.")
        return (0, 0)

    cli_art.display_banner(f"Evaluating {len(pending_paths)} pending JD(s) for picker")
    results = batch_evaluate.evaluate_all_pending(pending_paths)
    valid = [r for r in results if not r["error"]]
    if not valid:
        cli_art.console.print("Nothing could be evaluated -- no picker to show.")
        return (0, 0)

    cli_art.render_fit_table(results)

    choices = [
        questionary.Choice(
            title=f"{r['composite_score']}/5 | {r['recommendation']} | {r['company_name']} | {r['job_title']}",
            value=r["source_file"],
        )
        for r in valid
    ]
    selected_paths = questionary.checkbox(
        f"Select JD(s) to {action_verb}:", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
    if not selected_paths:
        cli_art.console.print("No jobs selected, nothing to do.")
        return (0, 0)

    completed = 0
    failed = 0
    for path in selected_paths:
        if process_one(path):
            completed += 1
        else:
            failed += 1
    cli_art.console.print(f"\nPicked batch summary: {completed} completed, {failed} failed.")
    return (completed, failed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_picker -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Run the full suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 6 from Task 1's total (214 → 220).

- [ ] **Step 6: Commit**

```bash
git add scripts/picker.py tests/test_picker.py
git commit -m "$(cat <<'EOF'
Add shared pick_and_process() flow

Deduplicates the confirm-gate/evaluate/checkbox/process loop currently
duplicated in resume run --pick and resume coverletter --pick -- both
get refactored onto this in the next task, and it becomes what the
interactive menu's own picker items call too.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Refactor `run --pick`/`coverletter --pick` onto `picker.py`

**Files:**
- Modify: `scripts/cli.py`

**Interfaces:**
- Consumes: `picker.pick_and_process(pending_paths, process_one, action_verb, skip_confirm) -> (int, int)` (Task 2).
- Produces: no new public interface -- both commands' external behavior is unchanged; this is a pure refactor, proven by the existing tests (`tests/test_cli_coverletter_pick.py`) continuing to pass unchanged.

No new automated tests for this task -- `tests/test_cli_coverletter_pick.py`'s existing tests are the regression guard (they exercise the exact code paths being refactored and must keep passing with zero changes to the test file itself).

- [ ] **Step 1: Add the import**

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
import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import picker
import scan as scan_module
import liveness as liveness_module
```

- [ ] **Step 2: Refactor `run`'s `--pick` branch**

In `scripts/cli.py`, find:

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

    def _process_one(path):
        completed, failed = orchestrator.run_pipeline(jd_path=path, master_resume_path=master)
        return completed > 0

    picker.pick_and_process(jd_manager.get_pending_jds(), _process_one, "tailor", skip_confirm=yes)
```

- [ ] **Step 3: Refactor `coverletter`'s `--pick` branch**

In `scripts/cli.py`, find:

```python
    if pick:
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
        selected_paths = questionary.checkbox("Select JD(s) to generate a cover letter for:", choices=choices).ask()
        if not selected_paths:
            cli_art.console.print("No jobs selected, nothing to do.")
            return

        engine = orchestrator.ResumeEngine()
        completed = 0
        failed = 0
        for path in selected_paths:
            cli_art.display_banner(f"Cover letter: {path}")
            result = engine.build_tailored_coverletter(path)
            if result:
                completed += 1
            else:
                failed += 1
        cli_art.console.print(f"\nPicked batch summary: {completed} completed, {failed} failed.")
        return

    cli_art.display_banner(f"Cover letter: {jd_file}")
    engine = orchestrator.ResumeEngine()
    result = engine.build_tailored_coverletter(jd_file)
    if not result:
        raise SystemExit(1)
```

Change to:

```python
    engine = orchestrator.ResumeEngine()

    if pick:
        def _process_one(path):
            cli_art.display_banner(f"Cover letter: {path}")
            return bool(engine.build_tailored_coverletter(path))

        picker.pick_and_process(
            jd_manager.get_pending_jds(), _process_one, "generate a cover letter for", skip_confirm=yes,
        )
        return

    cli_art.display_banner(f"Cover letter: {jd_file}")
    result = engine.build_tailored_coverletter(jd_file)
    if not result:
        raise SystemExit(1)
```

- [ ] **Step 4: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same count as Task 2 (220) -- `tests/test_cli_coverletter_pick.py`'s tests (already covering this exact `coverletter --pick` code path) must all still pass unchanged, proving the refactor didn't change behavior.

- [ ] **Step 5: Live verification -- `run --pick` still works after the refactor**

Same cost-conscious holdback technique used originally:

```bash
mkdir -p /tmp/jds_holdback
cd /Users/morganescott/resume-builder
find jds -maxdepth 1 -name "*.json" ! -name "2026-07-04_3DSource_SocialMediaMarketingSpecialist.json" -exec mv {} /tmp/jds_holdback/ \;
ls jds/*.json
```

Expected: only 1 pending JD remains.

```bash
source .venv/bin/activate
python3 -c "
import sys
from unittest.mock import patch, MagicMock
sys.path.insert(0, 'scripts')
from click.testing import CliRunner
import cli

selected_path = 'jds/2026-07-04_3DSource_SocialMediaMarketingSpecialist.json'
mock_question = MagicMock()
mock_question.ask.return_value = [selected_path]

with patch('cli.picker.questionary.checkbox', return_value=mock_question) as mock_checkbox:
    runner = CliRunner()
    result = runner.invoke(cli.cli, ['run', '--pick', '--yes'])

print('exit code:', result.exit_code)
print('checkbox called:', mock_checkbox.called)
print(result.output[-500:])
"
```

Expected: exit code 0, `checkbox called: True`, output ends with a real tailor pipeline run and "Picked batch summary: 1 completed, 0 failed." (matching the original pre-refactor live verification's result shape).

```bash
mv /tmp/jds_holdback/*.json jds/
rmdir /tmp/jds_holdback
```

- [ ] **Step 6: Commit**

```bash
git add scripts/cli.py
git commit -m "$(cat <<'EOF'
Refactor run --pick and coverletter --pick onto picker.pick_and_process()

Pure refactor -- external behavior unchanged, proven by
tests/test_cli_coverletter_pick.py passing unchanged and a live
re-verification of run --pick's real tailor path. Removes the last
duplicated copy of the confirm/evaluate/checkbox/process loop; the menu
(next tasks) will be the third consumer of the same shared function.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Upgrade `resume evaluate`'s batch table to `render_fit_table`

**Files:**
- Modify: `scripts/cli.py` (the `evaluate` command's batch-mode branch)

**Interfaces:**
- Consumes: `cli_art.render_fit_table(results: list) -> None` (Task 1).
- Produces: no new public interface -- `resume evaluate`'s batch-mode output format changes (plain text -> colored Rich Table); its single-file mode is unaffected.

No automated tests for this task -- Rich console output, visually verified live.

- [ ] **Step 1: Replace the f-string table with `render_fit_table`**

In `scripts/cli.py`, find:

```python
        cli_art.display_banner(f"Evaluating {len(pending)} pending JD(s)")
        results = batch_evaluate.evaluate_all_pending(pending)

        cli_art.console.print(f"\n{'#':<4}{'Score':<8}{'Rec.':<20}{'Company':<25}{'Title'}")
        for i, r in enumerate(results, 1):
            score_str = "ERROR" if r["error"] else f"{r['composite_score']}/5"
            rec_str = r["recommendation"] or "-"
            cli_art.console.print(f"{i:<4}{score_str:<8}{rec_str:<20}{r['company_name']:<25}{r['job_title']}")
        cli_art.console.print()
        return
```

Change to:

```python
        cli_art.display_banner(f"Evaluating {len(pending)} pending JD(s)")
        results = batch_evaluate.evaluate_all_pending(pending)
        cli_art.render_fit_table(results)
        return
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same count as Task 3 (220) -- no automated tests exercised this print formatting either before or after.

- [ ] **Step 3: Live verification -- against a small, cost-conscious real subset**

```bash
mkdir -p /tmp/jds_holdback
cd /Users/morganescott/resume-builder
find jds -maxdepth 1 -name "*.json" ! -name "2026-07-04_3DSource_SocialMediaMarketingSpecialist.json" ! -name "2026-07-04_4MINDS_CampaignManager.json" -exec mv {} /tmp/jds_holdback/ \;
ls jds/*.json
```

Expected: only the 2 held-back files remain (adjust names if either has since moved to `jds/completed/` from earlier testing -- pick whatever 2 real pending `.json` files currently exist).

```bash
source .venv/bin/activate
python scripts/cli.py evaluate --yes
```

Expected: a colored Rich Table prints (no plain f-string columns), sorted best-first, matching `render_fit_table`'s Task 1 live check.

```bash
mv /tmp/jds_holdback/*.json jds/
rmdir /tmp/jds_holdback
```

- [ ] **Step 4: Commit**

```bash
git add scripts/cli.py
git commit -m "$(cat <<'EOF'
Upgrade resume evaluate's batch table to cli_art.render_fit_table

Colored by recommendation tier instead of plain text -- single-file
evaluate mode is unaffected. Live-verified against a real 2-JD subset.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `scripts/menu.py` -- the interactive menu loop

**Files:**
- Create: `scripts/menu.py`

**Interfaces:**
- Consumes: `cli_art.console`, `cli_art.display_banner`, `cli_art.QUESTIONARY_STYLE`, `cli_art.render_fit_table` (Task 1); `picker.pick_and_process(pending_paths, process_one, action_verb, skip_confirm) -> (int, int)` (Task 2); `jd_manager.get_pending_jds() -> list[str]`; `batch_evaluate.evaluate_all_pending(pending_paths) -> list[dict]`; `orchestrator.run_pipeline(jd_path=None, master_resume_path=None) -> (int, int)`, `orchestrator.ResumeEngine().evaluate_fit(path) -> dict`, `orchestrator.ResumeEngine().build_tailored_coverletter(path) -> dict`; `scan_module.run_scan(sources=None) -> int`; `liveness_module.run_liveness_check() -> dict`; `questionary.select`, `questionary.path`, `questionary.Choice`.
- Produces: `menu.run_interactive_menu() -> None`, consumed directly by Task 6's `cli.py` group callback.

No automated tests for this task -- an interactive loop over already-tested pieces, matching the established convention for `run --pick`/`coverletter --pick`. Verified live in Step 3 below with the interactive prompts mocked (same technique as every other `--pick` live verification this project has done) against a small, cost-conscious real JD subset.

- [ ] **Step 1: Write the module**

Create `scripts/menu.py`:

```python
"""
menu.py -- the interactive top-level menu launched by a bare `resume`
invocation (see cli.py's group callback). Modeled on job_automater's own
interactive() menu (job_automater/cli.py:954-1011): a while-loop
presenting a questionary.select() of every available action, dispatching
to the same underlying modules the Click commands already call, looping
back after each action until Exit (or a cancelled top-level prompt).
"""

import questionary

import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import picker
import scan as scan_module
import liveness as liveness_module

_CHOICES = [
    questionary.Choice(title="Scan for new postings", value="scan"),
    questionary.Choice(title="Check posting liveness", value="liveness"),
    questionary.Choice(title="Evaluate all pending JDs", value="evaluate_all"),
    questionary.Choice(title="Evaluate a specific JD", value="evaluate_one"),
    questionary.Choice(title="Tailor -- pick from list", value="tailor_pick"),
    questionary.Choice(title="Tailor ALL pending JDs (batch)", value="tailor_all"),
    questionary.Choice(title="Tailor a specific JD", value="tailor_one"),
    questionary.Choice(title="Generate cover letter -- pick from list", value="coverletter_pick"),
    questionary.Choice(title="Generate cover letter for a specific JD", value="coverletter_one"),
    questionary.Choice(title="Exit", value="exit"),
]


def _handle_scan():
    scan_module.run_scan(None)


def _handle_liveness():
    liveness_module.run_liveness_check()


def _handle_evaluate_all():
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to evaluate -- no pending JDs.")
        return
    if not picker.should_proceed(len(pending), skip_confirm=False):
        cli_art.console.print("Aborted.")
        return
    results = batch_evaluate.evaluate_all_pending(pending)
    cli_art.render_fit_table(results)


def _handle_evaluate_one():
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        return
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")


def _handle_tailor_pick():
    def _process_one(path):
        completed, _failed = orchestrator.run_pipeline(jd_path=path)
        return completed > 0

    picker.pick_and_process(jd_manager.get_pending_jds(), _process_one, "tailor")


def _handle_tailor_all():
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to tailor -- no pending JDs.")
        return
    if not picker.should_proceed(len(pending), skip_confirm=False):
        cli_art.console.print("Aborted.")
        return
    orchestrator.run_pipeline()


def _handle_tailor_one():
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return
    orchestrator.run_pipeline(jd_path=path)


def _handle_coverletter_pick():
    engine = orchestrator.ResumeEngine()

    def _process_one(path):
        cli_art.display_banner(f"Cover letter: {path}")
        return bool(engine.build_tailored_coverletter(path))

    picker.pick_and_process(jd_manager.get_pending_jds(), _process_one, "generate a cover letter for")


def _handle_coverletter_one():
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return
    engine = orchestrator.ResumeEngine()
    engine.build_tailored_coverletter(path)


_HANDLERS = {
    "scan": _handle_scan,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "evaluate_one": _handle_evaluate_one,
    "tailor_pick": _handle_tailor_pick,
    "tailor_all": _handle_tailor_all,
    "tailor_one": _handle_tailor_one,
    "coverletter_pick": _handle_coverletter_pick,
    "coverletter_one": _handle_coverletter_one,
}


def run_interactive_menu() -> None:
    cli_art.display_banner("Interactive Menu")

    while True:
        cli_art.console.print()
        choice = questionary.select(
            "What would you like to do?", choices=_CHOICES, style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if choice == "exit" or not choice:
            cli_art.console.print("\n[cyan]Goodbye![/cyan]\n")
            break

        _HANDLERS[choice]()
```

- [ ] **Step 2: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, same count as Task 4 (220) -- no automated tests for this module, per the convention noted above.

- [ ] **Step 3: Live verification -- exercise the menu's picker path against a small real subset**

```bash
mkdir -p /tmp/jds_holdback
cd /Users/morganescott/resume-builder
find jds -maxdepth 1 -name "*.json" ! -name "2026-07-04_3DSource_SocialMediaMarketingSpecialist.json" -exec mv {} /tmp/jds_holdback/ \;
ls jds/*.json
```

Expected: only 1 pending JD remains (adjust the filename if it's since moved to `jds/completed/` -- pick whatever 1 real pending `.json` file currently exists).

```bash
source .venv/bin/activate
python3 -c "
import sys
from unittest.mock import patch, MagicMock
sys.path.insert(0, 'scripts')
import menu

mock_select = MagicMock()
mock_select.ask.side_effect = ['evaluate_all', 'exit']

with patch('menu.questionary.select', return_value=mock_select), \
     patch('menu.picker.should_proceed', return_value=True):
    menu.run_interactive_menu()
"
```

Expected: the menu prints its banner, runs `evaluate_all` against the real 1-JD subset (a real Gemini call, a rendered table), then exits cleanly on the second `select()` call returning `'exit'` -- no crash, no stack trace.

```bash
mv /tmp/jds_holdback/*.json jds/
rmdir /tmp/jds_holdback
```

- [ ] **Step 4: Commit**

```bash
git add scripts/menu.py
git commit -m "$(cat <<'EOF'
Add the interactive menu module (menu.run_interactive_menu())

Modeled on job_automater's own interactive() menu (cli.py:954-1011) --
a while-loop over questionary.select(), dispatching to the same
underlying orchestrator/batch_evaluate/scan/liveness/picker calls the
existing Click commands already use. Not wired into bare `resume`
invocation yet -- that's the final task.

Live-verified against a real 1-JD subset: evaluate_all dispatches
correctly and the loop exits cleanly on Exit.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Wire bare `resume` to launch the menu

**Files:**
- Modify: `scripts/cli.py` (the `@click.group()` decorator and its callback)
- Modify: `scripts/resume-cli.sh` (the `*)` default case and a new `help)` case)
- Test: `tests/test_cli_bare_invocation.py`

**Interfaces:**
- Consumes: `menu.run_interactive_menu() -> None` (Task 5).
- Produces: no new public interface -- this is the final wiring step that makes bare `resume`/`python scripts/cli.py` launch the menu.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli_bare_invocation.py`:

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from click.testing import CliRunner  # noqa: E402
import cli  # noqa: E402


class TestBareInvocation(unittest.TestCase):

    def test_no_subcommand_launches_the_menu(self):
        with patch("cli.menu.run_interactive_menu") as mock_menu:
            runner = CliRunner()
            result = runner.invoke(cli.cli, [])
        self.assertEqual(result.exit_code, 0)
        mock_menu.assert_called_once()

    def test_a_real_subcommand_does_not_launch_the_menu(self):
        with patch("cli.menu.run_interactive_menu") as mock_menu, \
             patch("cli.scan_module.run_scan") as mock_scan:
            runner = CliRunner()
            result = runner.invoke(cli.cli, ["scan"])
        self.assertEqual(result.exit_code, 0)
        mock_menu.assert_not_called()
        mock_scan.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_cli_bare_invocation -v`
Expected: `AttributeError: module 'cli' has no attribute 'menu'` (or `mock_menu.assert_called_once()` failing since nothing calls it yet).

- [ ] **Step 3: Wire the group callback**

In `scripts/cli.py`, find:

```python
import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import picker
import scan as scan_module
import liveness as liveness_module
```

Change to:

```python
import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import picker
import menu
import scan as scan_module
import liveness as liveness_module
```

Then find:

```python
@click.group()
def cli():
    """resume-builder: tailor and render resumes per job description."""
```

Change to:

```python
@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """resume-builder: tailor and render resumes per job description."""
    if ctx.invoked_subcommand is None:
        menu.run_interactive_menu()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_cli_bare_invocation -v`
Expected: both tests pass.

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `source .venv/bin/activate && python -m unittest discover -s tests`
Expected: `OK`, test count increased by 2 from Task 5's total (220 → 222).

- [ ] **Step 6: Update `resume-cli.sh`'s default and add a `help` case**

In `scripts/resume-cli.sh`, find the `*)` default case (the final case in the `case "$cmd" in ... esac` block, which currently prints the shortcut list):

```bash
    *)
      echo "resume-builder shortcuts:"
      echo "  resume activate        cd into the project and activate the venv (stays active in this shell)"
      echo "  resume cd              just cd into the project"
      echo "  resume run             tailor+render every pending JD in jds/ (batch mode)"
      echo "  resume run jds/x.txt   tailor+render one specific JD file"
      echo "  resume coverletter jds/x.txt   generate + render a cover letter for one JD"
      echo "  resume evaluate jds/x.txt   score a JD's fit (go/no-go) without building a resume"
      echo "  resume scan             pull new postings from all configured sources into jds/"
      echo "  resume scan --source jobright   pull from just one source (jobright, linkedin)"
      echo "  resume liveness         check every pending JD's posting URL, move expired ones out"
      echo "  resume test            run the full test suite (compact: dots + summary)"
      echo "  resume test -v         same, but lists every test by name"
      echo "  resume test -vv        same, but shows the app's own logging too"
      ;;
  esac
}
```

Change to:

```bash
    help)
      echo "resume-builder shortcuts:"
      echo "  resume                 launch the interactive menu"
      echo "  resume activate        cd into the project and activate the venv (stays active in this shell)"
      echo "  resume cd              just cd into the project"
      echo "  resume run             tailor+render every pending JD in jds/ (batch mode)"
      echo "  resume run jds/x.txt   tailor+render one specific JD file"
      echo "  resume run --pick      interactively select which pending JD(s) to tailor"
      echo "  resume coverletter jds/x.txt   generate + render a cover letter for one JD"
      echo "  resume coverletter --pick   interactively select which pending JD(s) to generate a cover letter for"
      echo "  resume evaluate jds/x.txt   score a JD's fit (go/no-go) without building a resume"
      echo "  resume evaluate         score every pending JD at once"
      echo "  resume scan             pull new postings from all configured sources into jds/"
      echo "  resume scan --source jobright   pull from just one source (jobright, linkedin)"
      echo "  resume liveness         check every pending JD's posting URL, move expired ones out"
      echo "  resume test            run the full test suite (compact: dots + summary)"
      echo "  resume test -v         same, but lists every test by name"
      echo "  resume test -vv        same, but shows the app's own logging too"
      ;;
    *)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py "$@" )
      ;;
  esac
}
```

- [ ] **Step 7: Live verification -- bare `resume` and `resume help` both work as expected**

```bash
source scripts/resume-cli.sh
resume help
```

Expected: the static shortcut list prints (now including the two new lines about `resume` launching the menu and the `--pick`/batch-evaluate additions), no menu launches.

```bash
source .venv/bin/activate
python3 -c "
import sys
from unittest.mock import patch, MagicMock
sys.path.insert(0, 'scripts')
import cli

mock_select = MagicMock()
mock_select.ask.return_value = 'exit'

with patch('cli.menu.questionary.select', return_value=mock_select):
    from click.testing import CliRunner
    runner = CliRunner()
    result = runner.invoke(cli.cli, [])
print('exit code:', result.exit_code)
print(result.output)
"
```

Expected: exit code 0, output shows the menu banner, the "What would you like to do?" prompt firing once, and "Goodbye!" -- confirming a bare invocation of `cli.py` (matching what both `resume` and `python scripts/cli.py` now do) launches and cleanly exits the menu.

- [ ] **Step 8: Commit**

```bash
git add scripts/cli.py scripts/resume-cli.sh tests/test_cli_bare_invocation.py
git commit -m "$(cat <<'EOF'
Launch the interactive menu on bare resume invocation

cli.py's group gains invoke_without_command=True + a callback that
launches menu.run_interactive_menu() when no subcommand is given.
resume-cli.sh's old static-shortcut-list default case moves to a new
`resume help` case; the default case now forwards to `python scripts/
cli.py "$@"` unconditionally, so a bare `resume` and a bare `python
scripts/cli.py` launch the identical menu, keeping both entry points in
sync per this project's existing convention.

Live-verified: `resume help` still prints the reference list, and a
mocked bare invocation of the CLI group correctly launches and exits
the menu.

Completes the interactive top-level menu (design 2026-07-06).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
