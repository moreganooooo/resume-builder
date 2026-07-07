# Menu Flow, Merged Pickers & Title Banner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the interactive menu's entries to describe the pipeline they support, merge the redundant "pick from list"/"specific JD" tailor and cover-letter options into one cost-free picker each, add a "what's next" chain prompt after each action that follows the natural Scan -> Liveness -> Evaluate -> Customize -> Cover Letter -> Polish order, and replace the menu's small text banner with a bigger block-letter title screen.

**Architecture:** `scripts/picker.py` gets one new lightweight, non-evaluating picker function. `scripts/cli_art.py` gets one new banner constant/function. `scripts/menu.py` is rewritten in place: every `_handle_*` function now returns a bool signaling whether it did something worth chaining from, a new `_CHAIN` dict maps each action to its next-step choices, and a new `_run_with_chain()` recursive runner replaces the loop's direct handler dispatch.

**Tech Stack:** Python 3.10+, `questionary` (interactive prompts), `rich` (console/banner rendering), `unittest` (stdlib, project's only test framework).

## Global Constraints

- Python 3.10+ syntax (`str | None`, etc.) — matches the rest of `scripts/`.
- Scope is `menu.py`/`cli_art.py`/`picker.py` only — `cli.py`'s `run --pick`/`coverletter --pick` flags and `picker.pick_and_process()` itself are untouched.
- No auto-chaining without an explicit prompt — every step in the chain remains a user choice, "Back to Menu" always available.
- The chain prompt only appears when a handler reports it did something meaningful (see each handler's bool-return rule in Task 3) — a no-op returns straight to the main menu.
- Tests: stdlib `unittest`, `tests/test_*.py` naming (auto-discovered), `sys.path.insert(0, SCRIPTS_DIR)` + plain `import <module>`, mocks via `unittest.mock.patch("<module>.<name>")` targeting the name where it's *used*.
- Run the suite with `python -m unittest discover -s tests -v` from the project root with `.venv/` activated (or `resume test -v`).

---

### Task 1: `picker.pick_one_pending_jd()` — lightweight, non-evaluating picker

**Files:**
- Modify: `scripts/picker.py`
- Modify: `tests/test_picker.py`

**Interfaces:**
- Consumes: `jd_manager.extract_job_meta(path: str) -> tuple[str, str]` (returns `(job_title, company_name)`, pre-existing, no changes).
- Produces: `picker.pick_one_pending_jd(pending_paths: list) -> str | None`. Task 3's `_handle_tailor_one`/`_handle_coverletter_one` call this with `jd_manager.get_pending_jds()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_picker.py`:

```python
class TestPickOnePendingJd(unittest.TestCase):

    def test_empty_list_returns_none_without_prompting(self):
        with patch("picker.questionary.select") as mock_select:
            result = picker.pick_one_pending_jd([])
        self.assertIsNone(result)
        mock_select.assert_not_called()

    @patch("picker.jd_manager.extract_job_meta")
    @patch("picker.questionary.select")
    def test_label_uses_company_and_title_when_present(self, mock_select, mock_meta):
        mock_meta.return_value = ("Campaign Manager", "4MINDS")
        mock_select.return_value.ask.return_value = "jds/a.json"

        result = picker.pick_one_pending_jd(["jds/a.json"])

        self.assertEqual(result, "jds/a.json")
        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].title, "4MINDS - Campaign Manager")
        self.assertEqual(choices[0].value, "jds/a.json")

    @patch("picker.jd_manager.extract_job_meta", return_value=("", ""))
    @patch("picker.questionary.select")
    def test_label_falls_back_to_filename_when_meta_is_empty(self, mock_select, mock_meta):
        mock_select.return_value.ask.return_value = "jds/some_file.json"

        picker.pick_one_pending_jd(["jds/some_file.json"])

        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].title, "some_file.json")

    @patch("picker.jd_manager.extract_job_meta", return_value=("Title", "Company"))
    @patch("picker.questionary.select")
    def test_returns_the_users_selection(self, mock_select, mock_meta):
        mock_select.return_value.ask.return_value = "jds/b.json"
        result = picker.pick_one_pending_jd(["jds/a.json", "jds/b.json"])
        self.assertEqual(result, "jds/b.json")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_picker -v`
Expected: FAIL — `AttributeError: module 'picker' has no attribute 'pick_one_pending_jd'`.

- [ ] **Step 3: Add the imports and `pick_one_pending_jd()` to `scripts/picker.py`**

Add this import at the top of `scripts/picker.py`, alongside the existing ones:

```python
import os

import jd_manager
```

Append to `scripts/picker.py`:

```python
def pick_one_pending_jd(pending_paths: list) -> str | None:
    """Lightweight single-choice picker over pending_paths -- no fit
    evaluation, no Gemini call, just labeled via jd_manager.extract_job_meta()
    (a free, deterministic parse of the JD file itself). Used by the menu's
    merged "for a Specific JD" entries (tailor/coverletter), which used to
    prompt for an arbitrary filesystem path."""
    if not pending_paths:
        cli_art.console.print("Nothing to pick from -- no pending JDs.")
        return None

    choices = []
    for path in pending_paths:
        title, company = jd_manager.extract_job_meta(path)
        label = f"{company} - {title}" if (company or title) else os.path.basename(path)
        choices.append(questionary.Choice(title=label, value=path))

    return questionary.select(
        "Which JD?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_picker -v`
Expected: PASS (all `TestPickAndProcess` tests plus the 4 new `TestPickOnePendingJd` tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/picker.py tests/test_picker.py
git commit -m "feat: add pick_one_pending_jd() lightweight picker"
```

---

### Task 2: Block-letter title banner

**Files:**
- Modify: `scripts/cli_art.py`
- Modify: `scripts/menu.py`

**Interfaces:**
- Produces: `cli_art.MAIN_BANNER: str`, `cli_art.display_main_banner() -> None`.
- Consumes (in `menu.py`): nothing new — this task only swaps which `cli_art` banner call `run_interactive_menu()` makes.

- [ ] **Step 1: Add `MAIN_BANNER` and `display_main_banner()` to `scripts/cli_art.py`**

No test-first cycle for this step — this file's existing banner/table helpers (`display_banner`, `render_fit_table`) have no dedicated unit tests either (per this project's established convention of verifying static art/console output live rather than asserting on it), so this one follows the same pattern. Correctness is verified by actually rendering it in Step 2.

Append to `scripts/cli_art.py`, after the existing `QUESTIONARY_STYLE` definition and before `_RECOMMENDATION_COLORS`:

```python
# Block-letter title banner, same ansi_shadow-style box-drawing glyphs as
# job_automater-main's MAIN_BANNER -- stacked on two lines since "RESUME
# BUILDER" is too long for one line at this scale (each line is 53 columns,
# safe for any real terminal width).
MAIN_BANNER = """
[bold cyan]
██████╗ ███████╗███████╗██╗   ██╗███╗   ███╗███████╗
██╔══██╗██╔════╝██╔════╝██║   ██║████╗ ████║██╔════╝
██████╔╝█████╗  ███████╗██║   ██║██╔████╔██║█████╗
██╔══██╗██╔══╝  ╚════██║██║   ██║██║╚██╔╝██║██╔══╝
██║  ██║███████╗███████║╚██████╔╝██║ ╚═╝ ██║███████╗
╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝

██████╗ ██╗   ██╗██╗██╗     ██████╗ ███████╗██████╗
██╔══██╗██║   ██║██║██║     ██╔══██╗██╔════╝██╔══██╗
██████╔╝██║   ██║██║██║     ██║  ██║█████╗  ██████╔╝
██╔══██╗██║   ██║██║██║     ██║  ██║██╔══╝  ██╔══██╗
██████╔╝╚██████╔╝██║███████╗██████╔╝███████╗██║  ██║
╚═════╝  ╚═════╝ ╚═╝╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═╝
[/bold cyan]
[dim]          Tailored resumes & cover letters, powered by Gemini[/dim]
"""


def display_main_banner() -> None:
    console.print(MAIN_BANNER)
```

- [ ] **Step 2: Verify it renders cleanly**

Run:
```bash
source .venv/bin/activate && python3 -c "
import sys; sys.path.insert(0, 'scripts')
import cli_art
cli_art.display_main_banner()
"
```
Expected: the block-letter "RESUME" / "BUILDER" art prints in bold cyan with the dim tagline below, no Rich markup errors, no misaligned/wrapped lines.

- [ ] **Step 3: Wire it into `menu.py`'s menu launch**

In `scripts/menu.py`, change:

```python
def run_interactive_menu() -> None:
    cli_art.display_banner("Interactive Menu")
```

to:

```python
def run_interactive_menu() -> None:
    cli_art.display_main_banner()
```

- [ ] **Step 4: Commit**

```bash
git add scripts/cli_art.py scripts/menu.py
git commit -m "feat: add block-letter title banner, shown once at menu launch"
```

---

### Task 3: Relabel menu entries, merge tailor/cover-letter pickers, add bool returns

**Files:**
- Modify: `scripts/menu.py`
- Create: `tests/test_menu.py`

**Interfaces:**
- Consumes: `picker.pick_one_pending_jd(pending_paths: list) -> str | None` (Task 1).
- Produces: every `_handle_*` function in `menu.py` now returns `bool` (`True` if it did something worth chaining from, `False` for a no-op). `_CHOICES` no longer has `tailor_pick`/`coverletter_pick` entries. `_HANDLERS` no longer has `tailor_pick`/`coverletter_pick` keys. Task 4's `_run_with_chain()` calls `_HANDLERS[value]()` and relies on this bool return.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_menu.py`:

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import menu  # noqa: E402


class TestChoicesAndHandlers(unittest.TestCase):

    def test_pick_from_list_entries_are_gone(self):
        values = [c.value for c in menu._CHOICES]
        self.assertNotIn("tailor_pick", values)
        self.assertNotIn("coverletter_pick", values)
        self.assertNotIn("tailor_pick", menu._HANDLERS)
        self.assertNotIn("coverletter_pick", menu._HANDLERS)

    def test_choices_have_the_renamed_labels(self):
        labels = {c.value: c.title for c in menu._CHOICES}
        self.assertEqual(labels["scan"], "Scan for New Postings")
        self.assertEqual(labels["liveness"], "Check Posting Liveness")
        self.assertEqual(labels["evaluate_all"], "Evaluate ALL Pending JDs")
        self.assertEqual(labels["evaluate_one"], "Evaluate a Specific JD")
        self.assertEqual(labels["tailor_all"], "Customize Resume for ALL Pending JDs (batch)")
        self.assertEqual(labels["tailor_one"], "Customize Resume for a Specific JD")
        self.assertEqual(labels["coverletter_one"], "Write cover letter for a Specific JD")
        self.assertEqual(labels["polish"], "Polish a resume or cover letter")


class TestHandleScan(unittest.TestCase):

    @patch("menu.scan_module.run_scan", return_value=3)
    def test_returns_true_when_postings_written(self, mock_run):
        self.assertTrue(menu._handle_scan())

    @patch("menu.scan_module.run_scan", return_value=0)
    def test_returns_false_when_nothing_written(self, mock_run):
        self.assertFalse(menu._handle_scan())


class TestHandleLiveness(unittest.TestCase):

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_true_when_something_checked(self, mock_check):
        mock_check.return_value = {"active": 1, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 2, "moved": 0}
        self.assertTrue(menu._handle_liveness())

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_false_when_nothing_checked(self, mock_check):
        mock_check.return_value = {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 5, "moved": 0}
        self.assertFalse(menu._handle_liveness())

    @patch("menu.liveness_module.run_liveness_check")
    def test_returns_false_on_error(self, mock_check):
        mock_check.return_value = {"active": 0, "likely_active": 0, "expired": 0, "uncertain": 0, "skipped": 0, "moved": 0, "error": True}
        self.assertFalse(menu._handle_liveness())


class TestHandleEvaluateAll(unittest.TestCase):

    @patch("menu.jd_manager.get_pending_jds", return_value=[])
    def test_returns_false_when_no_pending(self, mock_pending):
        self.assertFalse(menu._handle_evaluate_all())

    @patch("menu.picker.should_proceed", return_value=False)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_declined(self, mock_pending, mock_proceed):
        with patch("menu.batch_evaluate.evaluate_all_pending") as mock_eval:
            self.assertFalse(menu._handle_evaluate_all())
        mock_eval.assert_not_called()

    @patch("menu.cli_art.render_fit_table")
    @patch("menu.batch_evaluate.evaluate_all_pending", return_value=[{"error": False}])
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_true_when_results_returned(self, mock_pending, mock_proceed, mock_eval, mock_table):
        self.assertTrue(menu._handle_evaluate_all())


class TestHandleEvaluateOne(unittest.TestCase):

    @patch("menu.questionary.path")
    def test_returns_false_when_no_path(self, mock_path):
        mock_path.return_value.ask.return_value = None
        self.assertFalse(menu._handle_evaluate_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.questionary.path")
    def test_returns_false_when_result_falsy(self, mock_path, mock_engine_cls):
        mock_path.return_value.ask.return_value = "jds/a.json"
        mock_engine_cls.return_value.evaluate_fit.return_value = {}
        self.assertFalse(menu._handle_evaluate_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.questionary.path")
    def test_returns_true_when_result_truthy(self, mock_path, mock_engine_cls):
        mock_path.return_value.ask.return_value = "jds/a.json"
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "archetype": "x", "composite_score": 4.0, "recommendation": "Strong pursue",
        }
        self.assertTrue(menu._handle_evaluate_one())


class TestHandleTailorAll(unittest.TestCase):

    @patch("menu.jd_manager.get_pending_jds", return_value=[])
    def test_returns_false_when_no_pending(self, mock_pending):
        self.assertFalse(menu._handle_tailor_all())

    @patch("menu.picker.should_proceed", return_value=False)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_declined(self, mock_pending, mock_proceed):
        with patch("menu.orchestrator.run_pipeline") as mock_run:
            self.assertFalse(menu._handle_tailor_all())
        mock_run.assert_not_called()

    @patch("menu.orchestrator.run_pipeline", return_value=(2, 0))
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_true_when_completed_gt_zero(self, mock_pending, mock_proceed, mock_run):
        self.assertTrue(menu._handle_tailor_all())

    @patch("menu.orchestrator.run_pipeline", return_value=(0, 1))
    @patch("menu.picker.should_proceed", return_value=True)
    @patch("menu.jd_manager.get_pending_jds", return_value=["jds/a.json"])
    def test_returns_false_when_completed_zero(self, mock_pending, mock_proceed, mock_run):
        self.assertFalse(menu._handle_tailor_all())


class TestHandleTailorOne(unittest.TestCase):

    @patch("menu.picker.pick_one_pending_jd", return_value=None)
    def test_returns_false_when_no_path_picked(self, mock_pick):
        self.assertFalse(menu._handle_tailor_one())

    @patch("menu.orchestrator.run_pipeline", return_value=(1, 0))
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_true_when_completed(self, mock_pick, mock_run):
        self.assertTrue(menu._handle_tailor_one())
        mock_run.assert_called_once_with(jd_path="jds/a.json")


class TestHandleCoverletterOne(unittest.TestCase):

    @patch("menu.picker.pick_one_pending_jd", return_value=None)
    def test_returns_false_when_no_path_picked(self, mock_pick):
        self.assertFalse(menu._handle_coverletter_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_true_when_letter_built(self, mock_pick, mock_engine_cls):
        mock_engine_cls.return_value.build_tailored_coverletter.return_value = {"company_name": "Acme"}
        self.assertTrue(menu._handle_coverletter_one())

    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_false_when_build_fails(self, mock_pick, mock_engine_cls):
        mock_engine_cls.return_value.build_tailored_coverletter.return_value = {}
        self.assertFalse(menu._handle_coverletter_one())


class TestHandlePolish(unittest.TestCase):

    @patch("menu.polish_module.run")
    def test_always_returns_false(self, mock_run):
        self.assertFalse(menu._handle_polish())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_menu -v`
Expected: FAIL — e.g. `AssertionError: 'tailor_pick' unexpectedly found` and `TypeError: cannot unpack non-iterable NoneType` (handlers don't return values yet).

- [ ] **Step 3: Rewrite `scripts/menu.py`**

Replace the entire contents of `scripts/menu.py` with:

```python
"""
menu.py -- the interactive top-level menu launched by a bare `resume`
invocation (see cli.py's group callback). Modeled on job_automater's own
interactive() menu (job_automater/cli.py:954-1011): a while-loop
presenting a questionary.select() of every available action, dispatching
to the same underlying modules the Click commands already call, looping
back after each action until Exit (or a cancelled top-level prompt).

Each _handle_* function returns a bool: whether it did something worth
offering a "what's next" chain prompt for (see _CHAIN/_run_with_chain in
the next section of this file) -- a no-op (nothing pending, declined
confirmation, zero results) returns False and goes straight back to the
main menu instead.
"""

import questionary

import cli_art
import orchestrator
import jd_manager
import batch_evaluate
import picker
import scan as scan_module
import liveness as liveness_module
import polish as polish_module

_CHOICES = [
    questionary.Choice(title="Scan for New Postings", value="scan"),
    questionary.Choice(title="Check Posting Liveness", value="liveness"),
    questionary.Choice(title="Evaluate ALL Pending JDs", value="evaluate_all"),
    questionary.Choice(title="Evaluate a Specific JD", value="evaluate_one"),
    questionary.Choice(title="Customize Resume for ALL Pending JDs (batch)", value="tailor_all"),
    questionary.Choice(title="Customize Resume for a Specific JD", value="tailor_one"),
    questionary.Choice(title="Write cover letter for a Specific JD", value="coverletter_one"),
    questionary.Choice(title="Polish a resume or cover letter", value="polish"),
    questionary.Choice(title="Exit", value="exit"),
]


def _handle_scan() -> bool:
    written = scan_module.run_scan(None)
    return written > 0


def _handle_liveness() -> bool:
    summary = liveness_module.run_liveness_check()
    if summary.get("error"):
        return False
    checked = summary["active"] + summary["likely_active"] + summary["expired"] + summary["uncertain"]
    return checked > 0


def _handle_evaluate_all() -> bool:
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to evaluate -- no pending JDs.")
        return False
    if not picker.should_proceed(len(pending), skip_confirm=False):
        cli_art.console.print("Aborted.")
        return False
    results = batch_evaluate.evaluate_all_pending(pending)
    cli_art.render_fit_table(results)
    return bool(results)


def _handle_evaluate_one() -> bool:
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return False
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        return False
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
    cli_art.console.print(f"[bold]Composite score:[/bold] {result['composite_score']}/5")
    cli_art.console.print(f"[bold]Recommendation:[/bold] {result.get('recommendation', 'unknown')}\n")
    return True


def _handle_tailor_all() -> bool:
    pending = jd_manager.get_pending_jds()
    if not pending:
        cli_art.console.print("Nothing to tailor -- no pending JDs.")
        return False
    if not picker.should_proceed(len(pending), skip_confirm=False):
        cli_art.console.print("Aborted.")
        return False
    completed, _failed = orchestrator.run_pipeline()
    return completed > 0


def _handle_tailor_one() -> bool:
    path = picker.pick_one_pending_jd(jd_manager.get_pending_jds())
    if not path:
        return False
    completed, _failed = orchestrator.run_pipeline(jd_path=path)
    return completed > 0


def _handle_coverletter_one() -> bool:
    path = picker.pick_one_pending_jd(jd_manager.get_pending_jds())
    if not path:
        return False
    engine = orchestrator.ResumeEngine()
    return bool(engine.build_tailored_coverletter(path))


def _handle_polish() -> bool:
    polish_module.run(None)
    return False


_HANDLERS = {
    "scan": _handle_scan,
    "liveness": _handle_liveness,
    "evaluate_all": _handle_evaluate_all,
    "evaluate_one": _handle_evaluate_one,
    "tailor_all": _handle_tailor_all,
    "tailor_one": _handle_tailor_one,
    "coverletter_one": _handle_coverletter_one,
    "polish": _handle_polish,
}


def run_interactive_menu() -> None:
    cli_art.display_main_banner()

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

(This still calls `_HANDLERS[choice]()` directly and discards the bool for
now -- Task 4 replaces that last line with `_run_with_chain(choice)`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_menu -v`
Expected: PASS (all tests in `tests/test_menu.py`).

- [ ] **Step 5: Run the full suite to confirm nothing else broke**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test, including `test_menu.py` and `test_picker.py`).

- [ ] **Step 6: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "feat: relabel menu entries, merge specific-JD pickers, add handler bool returns"
```

---

### Task 4: "What's next" chain prompt

**Files:**
- Modify: `scripts/menu.py`
- Modify: `tests/test_menu.py`

**Interfaces:**
- Consumes: `menu._HANDLERS: dict[str, Callable[[], bool]]` (Task 3).
- Produces: `menu._CHAIN: dict[str, list[tuple[str, str]]]`, `menu._run_with_chain(value: str) -> None`. `run_interactive_menu()`'s dispatch line calls this instead of `_HANDLERS[choice]()` directly.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_menu.py`:

```python
class TestChainContent(unittest.TestCase):

    def test_chain_matches_the_designed_pipeline_order(self):
        self.assertEqual(menu._CHAIN["scan"], [("Check Liveness", "liveness")])
        self.assertEqual(menu._CHAIN["liveness"], [("Evaluate All JDs", "evaluate_all")])
        self.assertEqual(menu._CHAIN["evaluate_all"], [("Customize Resume", "tailor_all")])
        self.assertEqual(menu._CHAIN["evaluate_one"], [("Customize Resume", "tailor_all")])
        self.assertEqual(
            menu._CHAIN["tailor_all"],
            [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
        )
        self.assertEqual(
            menu._CHAIN["tailor_one"],
            [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
        )
        self.assertEqual(menu._CHAIN["coverletter_one"], [("Polish with Gemini", "polish")])

    def test_polish_has_no_chain_entry(self):
        self.assertNotIn("polish", menu._CHAIN)


class TestRunWithChain(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_no_op_handler_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: False}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake")
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_handler_with_no_chain_entry_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False):
            menu._run_with_chain("fake")
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_chain_prompt_appends_back_to_menu_choice(self, mock_select):
        mock_select.return_value.ask.return_value = "__back__"
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake")
        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual([c.title for c in choices], ["Next", "Back to Menu"])
        self.assertEqual([c.value for c in choices], ["somewhere", "__back__"])

    @patch("menu.questionary.select")
    def test_back_to_menu_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = "__back__"
        with patch.dict(menu._HANDLERS, {"fake": lambda: calls.append("fake") or True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake")
        self.assertEqual(calls, ["fake"])

    @patch("menu.questionary.select")
    def test_cancelled_prompt_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = None
        with patch.dict(menu._HANDLERS, {"fake": lambda: calls.append("fake") or True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake")
        self.assertEqual(calls, ["fake"])

    @patch("menu.questionary.select")
    def test_picking_a_next_step_recurses_into_it(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = "second"
        with patch.dict(
            menu._HANDLERS,
            {
                "first": lambda: calls.append("first") or True,
                "second": lambda: calls.append("second") or False,
            },
            clear=False,
        ), patch.dict(menu._CHAIN, {"first": [("Do Second", "second")]}, clear=False):
            menu._run_with_chain("first")
        self.assertEqual(calls, ["first", "second"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_menu -v`
Expected: FAIL — `AttributeError: module 'menu' has no attribute '_CHAIN'`.

- [ ] **Step 3: Add `_CHAIN` and `_run_with_chain()` to `scripts/menu.py`, and wire the loop to use it**

In `scripts/menu.py`, add this right after the `_HANDLERS` dict definition:

```python
_CHAIN = {
    "scan": [("Check Liveness", "liveness")],
    "liveness": [("Evaluate All JDs", "evaluate_all")],
    "evaluate_all": [("Customize Resume", "tailor_all")],
    "evaluate_one": [("Customize Resume", "tailor_all")],
    "tailor_all": [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
    "tailor_one": [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
    "coverletter_one": [("Polish with Gemini", "polish")],
}


def _run_with_chain(value: str) -> None:
    did_something = _HANDLERS[value]()
    next_options = _CHAIN.get(value)
    if not did_something or not next_options:
        return

    choices = [questionary.Choice(title=label, value=v) for label, v in next_options]
    choices.append(questionary.Choice(title="Back to Menu", value="__back__"))
    choice = questionary.select(
        "What's next?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    if not choice or choice == "__back__":
        return
    _run_with_chain(choice)
```

Then change `run_interactive_menu()`'s last line from:

```python
        _HANDLERS[choice]()
```

to:

```python
        _run_with_chain(choice)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_menu -v`
Expected: PASS (every test in `tests/test_menu.py`).

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (all tests across the project).

- [ ] **Step 6: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "feat: add what's-next chain prompt to the interactive menu"
```

- [ ] **Step 7: Live verification**

Run `resume` (bare invocation, or `python scripts/cli.py`) and confirm:
1. The new block-letter banner renders cleanly at launch (no wrapping/misalignment in your real terminal).
2. Pick "Scan for New Postings" (or any action that finds/does something) and confirm the "What's next?" prompt appears with the right next-step options plus "Back to Menu".
3. Walk at least one full chain through to "Polish a resume or cover letter" (or as far as you're willing to let it run for real), confirming each step's options match the designed order.
4. Pick "Back to Menu" mid-chain at least once and confirm it returns cleanly to the main menu instead of continuing to prompt.

---

## Self-Review Notes

- **Spec coverage:** Goal 1 (relabeling) + Goal 2 (merged pickers) -> Task 3. Goal 3 (chain prompt) + Goal 4 (no-op suppression) -> Tasks 3 (bool returns) and 4 (`_CHAIN`/`_run_with_chain`). Goal 5 (banner) -> Task 2. All five spec goals have a task.
- **Placeholder scan:** No TBD/TODO markers; every step has complete, runnable code.
- **Type consistency:** `picker.pick_one_pending_jd(pending_paths: list) -> str | None` (Task 1) is called identically in Task 3's `_handle_tailor_one`/`_handle_coverletter_one`. Every `_handle_*` function returns `bool` consistently from Task 3 onward, which is exactly what Task 4's `_run_with_chain(value: str) -> None` relies on via `_HANDLERS[value]()`. `_CHAIN`'s value shape (`list[tuple[str, str]]`) matches what `_run_with_chain` iterates (`for label, v in next_options`).
