# Interactive Top-Level Menu (borrowing from job_automater) — Design

## Problem

Using resume-builder currently means remembering and typing a specific
`resume <command> [flags]` invocation every time -- `run --pick`,
`coverletter --pick`, `evaluate`, `scan`, `liveness`, etc. Morgan asked
(2026-07-05/06) whether it's possible to start the program and navigate
purely via a menu instead of individual commands, and whether the sibling
project job_automater already has something like this to borrow.

Investigation (2026-07-06) confirmed job_automater has a real, working
top-level interactive menu (`job_automater/cli.py:954-1011`, function
`interactive()`) built on the same stack this project already uses
(Click, Rich, `questionary`) -- a `while True` loop presenting
`questionary.select()` choices and dispatching to the same underlying
actions its Click subcommands already expose. It also has a reusable
`questionary.Style` theme (`cli.py:47-57`) and a Rich-Table-based scored/
sorted job list (`display_job_table()`, `cli.py:73-142`). Its pickers are
all single-select (`questionary.select`), never multi-select -- the
checkbox-based `--pick` mechanism already built in resume-builder is not
something job_automater has to offer.

## Goals

1. Bare `resume` (both the shell shortcut and `python scripts/cli.py`
   directly) launches an interactive menu instead of printing today's
   static shortcut list -- confirmed 2026-07-06 as the preferred trigger,
   matching Morgan's stated want to navigate the whole program via menu.
2. The menu exposes every existing action, including single-file variants
   (tailor/coverletter/evaluate one named JD) -- confirmed 2026-07-06;
   single-file items prompt for a path via `questionary.path()` (built-in
   tab-completion, existence validation).
3. Borrow directly from job_automater: its `questionary.Style` theme and
   its Rich-Table scored-list pattern, both ported into `cli_art.py` so
   the existing `--pick` pickers (already built) get the same visual
   upgrade, not just new menu code.
4. `resume evaluate`'s batch-mode table upgrades from today's plain
   f-string table to the new Rich Table renderer, in this same pass --
   confirmed 2026-07-06, since the menu needs this rendering anyway and
   doing it once keeps the feature visually consistent everywhere.
5. Deduplicate the "confirm gate -> evaluate every pending JD -> checkbox
   picker -> process each selection" flow -- currently implemented twice
   (`resume run --pick`, `resume coverletter --pick`) and about to be
   needed a third and fourth time (the menu's own tailor-pick and
   coverletter-pick items) -- into one shared function both the existing
   commands and the new menu call.

## Non-Goals

- No new capabilities beyond what already exists as CLI commands -- the
  menu is a navigation layer over `orchestrator`, `batch_evaluate`,
  `scan`, `liveness`, and `ResumeEngine`, not new pipeline behavior.
- No change to any existing command's direct-invocation behavior (`resume
  tailor <file>`, `resume run --pick`, etc. all still work exactly as
  before when typed directly) -- only bare `resume`'s behavior changes.
- No porting of job_automater's ASCII-art banners, `CustomGroup` help
  override, or its own ProgressColumn/spinner usage -- out of scope for
  this pass; revisit only if it comes up again.
- No ongoing state/history in the menu (e.g. a "since you last ran this"
  dashboard) -- that was raised as a separate, smaller idea in the
  original conversation and is not part of this design.

## Architecture

```
scripts/picker.py (new)
  pick_and_process(pending_paths: list, process_one: callable,
                    action_verb: str, skip_confirm: bool = False)
      -> (completed: int, failed: int)
    -- confirm gate (reuses cli._should_proceed's exact logic, duplicated
       here as a standalone function -- see Components) -> evaluate_all_
       pending(pending_paths) -> cli_art.render_fit_table() then a
       questionary.checkbox() prompt (style=cli_art.QUESTIONARY_STYLE,
       message built from action_verb) -> for each selected path, calls
       process_one(path) (expected to return truthy/falsy) and
       accumulates completed/failed. Returns (0, 0) on any abort/empty/
       nothing-selected path, after printing a clear message.

scripts/menu.py (new)
  run_interactive_menu() -> None
    -- a while True loop: questionary.select() (style=cli_art.
       QUESTIONARY_STYLE) with 10 choices (9 actions + Exit), dispatches
       to the underlying modules directly (orchestrator, batch_evaluate,
       scan_module, liveness_module, picker, questionary.path() for
       single-file prompts). Loops back to the select prompt after every
       action except Exit (or Ctrl-C/cancel at the top-level select,
       which also exits).

scripts/cli.py (modify)
  @click.group(invoke_without_command=True)
  def cli(ctx):
      if ctx.invoked_subcommand is None:
          menu.run_interactive_menu()
  -- existing subcommands (tailor, run, coverletter, evaluate, scan,
     liveness) are entirely unchanged in behavior; run --pick and
     coverletter --pick are refactored internally to call
     picker.pick_and_process() instead of their current inline duplicate
     logic (no change to their external behavior or tests).

scripts/cli_art.py (modify)
  QUESTIONARY_STYLE -- ported from job_automater/cli.py:47-57.
  render_fit_table(results: list) -> None
    -- Rich Table modeled on job_automater's display_job_table()
       (cli.py:73-142): columns #/Score/Recommendation/Company/Title,
       sorted (already sorted going in, from evaluate_all_pending),
       colored by recommendation tier (see Components).

scripts/resume-cli.sh (modify)
  The `*)` default case currently prints a static shortcut list inline.
  It changes to call `python scripts/cli.py` (no args) -- same as any
  other pass-through case -- so both entry points launch the menu
  identically. The static list moves to a new `help)` case for anyone
  who wants the quick-reference text without launching the menu.
```

## Components

- **`scripts/picker.py`** (new) --
  - `_should_proceed_standalone(count: int, skip_confirm: bool) -> bool`:
    a private copy of `cli._should_proceed`'s exact logic. Duplicated
    rather than imported from `cli.py` to avoid `picker.py` depending on
    `cli.py` (which will depend on `menu.py`, which depends on
    `picker.py` -- importing the other direction would create a cycle).
    Both copies are small (4 lines) and this plan's Task 1 keeps them
    behaviorally identical; `cli.py`'s existing `_should_proceed` is left
    in place and untouched (still used by `evaluate`'s own batch mode,
    which doesn't go through `picker.py`).
  - `pick_and_process(pending_paths, process_one, action_verb,
    skip_confirm=False) -> (int, int)`: the full shared flow described in
    Architecture above.

- **`scripts/menu.py`** (new) --
  - `run_interactive_menu() -> None`: the loop. Choices (in order):
    `Scan for new postings`, `Check posting liveness`,
    `Evaluate all pending JDs`, `Evaluate a specific JD`,
    `Tailor -- pick from list`, `Tailor ALL pending JDs (batch)`,
    `Tailor a specific JD`, `Generate cover letter -- pick from list`,
    `Generate cover letter for a specific JD`, `Exit`.
  - Each non-Exit choice's handler is a small private function
    (`_handle_scan()`, `_handle_liveness()`, `_handle_evaluate_all()`,
    `_handle_evaluate_one()`, `_handle_tailor_pick()`,
    `_handle_tailor_all()`, `_handle_tailor_one()`,
    `_handle_coverletter_pick()`, `_handle_coverletter_one()`) -- kept
    separate so each is independently readable/testable, even though
    none carry automated tests per the Testing section below.
  - `_handle_tailor_all()` reuses `picker._should_proceed_standalone()`
    before calling `orchestrator.run_pipeline()` with no `jd_path` --
    same real-cost-guard reasoning as every other batch-scoring action.

- **`scripts/cli_art.py`** (modify) --
  - `QUESTIONARY_STYLE = questionary.Style([...])`: exact values ported
    from job_automater's `custom_style` (`cli.py:47-57`) -- qmark/pointer
    purple, selected/answer green/blue per that file's own definition.
  - `render_fit_table(results: list) -> None`: builds a Rich `Table` with
    columns `#`, `Score`, `Recommendation`, `Company`, `Title`. Row style
    by `recommendation`: `"Strong pursue"` -> green, `"Selective
    pursue"` -> cyan, `"Low-priority pursue"` -> yellow, `"Skip"` -> dim
    red, and any `error: True` entry (from `batch_evaluate`'s result
    shape) -> red with `Score` rendered as `"ERROR"`. Prints via
    `cli_art.console.print(table)`.

- **`scripts/cli.py`** (modify) --
  - `@click.group(invoke_without_command=True)` + `ctx.invoked_subcommand
    is None` check dispatching to `menu.run_interactive_menu()`.
  - `run`'s `--pick` branch and `coverletter`'s `--pick` branch both
    replace their current inline confirm/evaluate/checkbox/loop logic
    with a single call to `picker.pick_and_process(pending, process_one,
    action_verb, skip_confirm=yes)`, where `process_one` is a small
    lambda wrapping `orchestrator.run_pipeline` (returns `completed > 0`)
    or `engine.build_tailored_coverletter` (returns `bool(result)`)
    respectively.

- **`scripts/resume-cli.sh`** (modify) -- `*)` case calls `python
  scripts/cli.py` (no args); a new `help)` case prints the shortcut list
  text that used to live in `*)`, unchanged in content.

## Data Flow

See the "Data flow for a menu session" walkthrough already approved in
conversation -- reproduced here for the written record:

```
resume  (no subcommand, either entry point)
  -> cli.py's group callback -> menu.run_interactive_menu()
  -> loop:
       questionary.select(style=QUESTIONARY_STYLE, choices=[...]) -> choice
       "Scan for new postings"              -> scan_module.run_scan(None)
       "Check posting liveness"              -> liveness_module.run_liveness_check()
       "Evaluate all pending JDs"            -> batch_evaluate.evaluate_all_pending() -> cli_art.render_fit_table()
       "Evaluate a specific JD"               -> questionary.path() -> engine.evaluate_fit(path) -> print (same format as today's single-file evaluate)
       "Tailor -- pick from list"             -> picker.pick_and_process(pending, tailor_one, "tailor")
       "Tailor ALL pending JDs (batch)"        -> picker._should_proceed_standalone(...) -> orchestrator.run_pipeline()
       "Tailor a specific JD"                  -> questionary.path() -> orchestrator.run_pipeline(jd_path=path)
       "Generate cover letter -- pick from list" -> picker.pick_and_process(pending, coverletter_one, "generate a cover letter for")
       "Generate cover letter for a specific JD" -> questionary.path() -> engine.build_tailored_coverletter(path)
       "Exit"                                  -> break
     -> loop back to the select prompt after every action except Exit
```

## Error Handling

- `questionary.path()`'s built-in validator only accepts existing paths --
  no separate existence check needed for single-file menu prompts.
- Any "nothing to do" outcome (empty pending queue, nothing selected, all
  evaluations errored, confirmation declined) prints the same message its
  corresponding CLI command already prints, then returns control to the
  menu loop rather than exiting the whole program.
- Ctrl-C or a cancelled prompt (`questionary` returns `None`) at the
  top-level `questionary.select()` exits the menu loop cleanly, same as
  choosing `Exit` -- no stack trace.
- A cancelled prompt at any *inner* prompt (e.g. `questionary.path()` for
  a single-file action, or the checkbox inside `pick_and_process`)
  returns to the menu loop rather than crashing or exiting the whole
  program -- only the top-level select's cancellation exits entirely.
- `pick_and_process()`'s per-selection processing already relies on each
  underlying pipeline's own existing error resilience (`run_pipeline`,
  `build_tailored_coverletter`) -- one selection failing doesn't stop the
  rest, matching `run --pick`'s and `coverletter --pick`'s current
  behavior exactly (this is a refactor, not a behavior change).

## Testing

- `picker.pick_and_process()`: real unit tests (new
  `tests/test_picker.py`) -- mock `questionary.checkbox`,
  `batch_evaluate.evaluate_all_pending`, and a fake `process_one`;
  confirm completed/failed counting, the abort-on-declined-confirmation
  path, the empty-pending path, and the all-errored/nothing-to-pick path
  all behave correctly with zero real Gemini calls.
- `run --pick` and `coverletter --pick`'s existing tests
  (`test_cli_coverletter_pick.py` and the equivalent live-verification
  from the prior plan) must keep passing unchanged after the refactor --
  this is the regression guard that proves the refactor didn't change
  either command's external behavior.
- `cli_art.render_fit_table()`: no automated test (Rich console output,
  visually verified) -- spot-checked live against real evaluate results
  during implementation.
- `menu.py`: no automated tests (an interactive loop over already-tested
  pieces) -- live-verified the same way `run --pick`/`coverletter --pick`
  were originally: mock the interactive prompts (`questionary.select`,
  `questionary.path`), let the real underlying calls run against a small,
  cost-conscious real JD subset, confirm each menu path dispatches
  correctly and loops back afterward.
