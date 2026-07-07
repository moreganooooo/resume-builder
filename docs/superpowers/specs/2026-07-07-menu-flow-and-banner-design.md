# Interactive Menu Flow, Merged Pickers & Title Banner — Design

## Problem

The interactive menu (`menu.py`) works, but its options are named after their
implementation ("Tailor -- pick from list" vs. "Tailor a specific JD") rather
than the pipeline they support, and after every action it dumps you back at
the top-level menu with no sense of "what's next" in the natural
scan-to-polish flow. Separately, "pick from list" and "a specific JD" are
functionally redundant for a single-JD action, except that "pick from list"
silently pays for a real Gemini fit-evaluation call across every pending JD
just to build the picker table. And the menu's title screen is a plain text
panel, while a bigger, more graphic banner (in the style of
`job_automater-main`'s `MAIN_BANNER`) was discussed previously and never
followed up on.

## Goals

1. Rename every menu entry to describe the action in pipeline terms (see the
   table in Architecture), scoped to `menu.py` only — `cli.py`'s
   `run --pick`/`coverletter --pick` flags are untouched.
2. Merge "pick from list" and "a specific JD" for both Tailor and Cover
   Letter into one entry each, backed by a lightweight picker over
   `jd_manager.get_pending_jds()` (labeled via the free, deterministic
   `jd_manager.extract_job_meta()` — no Gemini call, no fit table).
3. After an action completes, offer a "what's next" chain of choices matching
   the natural pipeline order (Scan -> Liveness -> Evaluate -> Customize ->
   Cover Letter -> Polish), always with "Back to Menu" as an escape hatch,
   and never auto-running the next step without that explicit choice.
4. The chain prompt only appears when the action did something meaningful
   (see Architecture's per-action rules) — a no-op returns straight to the
   main menu.
5. A new block-letter ASCII title banner (RESUME / BUILDER, stacked,
   `ansi_shadow`-style block glyphs matching `job_automater-main`'s visual
   style) shown once when the interactive menu launches, replacing today's
   small text panel.

## Non-Goals

- No changes to `cli.py`'s standalone commands or flags (`run --pick`,
  `coverletter --pick`, `tailor <file>`, etc.) — this is a `menu.py`/
  `cli_art.py`-only change.
- No auto-chaining without a prompt. Evaluation in particular costs a real
  Gemini call per JD; every step in the chain remains an explicit choice,
  consistent with the existing `_should_proceed` cost-confirmation gate.
- No change to `picker.pick_and_process()` itself (still used by `cli.py`'s
  `--pick` flags) — the new lightweight picker is a separate, additive
  function.
- No new "batch cover letter" concept — cover letters remain single-JD-only,
  matching today's behavior.

## Architecture

### 1. Menu relabeling + merged pickers

| Value | New label | Behavior change |
|---|---|---|
| `scan` | Scan for New Postings | none |
| `liveness` | Check Posting Liveness | none |
| `evaluate_all` | Evaluate ALL Pending JDs | none |
| `evaluate_one` | Evaluate a Specific JD | none (still `questionary.path()`) |
| `tailor_all` | Customize Resume for ALL Pending JDs (batch) | none |
| `tailor_one` | Customize Resume for a Specific JD | **merged**: replaces both the old raw-path prompt and "pick from list"; now `picker.pick_one_pending_jd()` |
| `coverletter_one` | Write cover letter for a Specific JD | **merged**: replaces both old cover-letter entries; now `picker.pick_one_pending_jd()` |
| `polish` | Polish a resume or cover letter | none |
| `exit` | Exit | none |

`coverletter_pick` and `tailor_pick` are removed from `_CHOICES` entirely
(their behavior is absorbed into `tailor_one`/`coverletter_one`).

**New shared helper**, `picker.pick_one_pending_jd(pending_paths: list) -> str | None`:
lists `pending_paths` via `questionary.select` (single choice, not a
checkbox), each labeled `f"{company} - {title}"` from
`jd_manager.extract_job_meta(path)` (falling back to the bare filename if
both are empty). Returns `None` (with a "Nothing to pick from" message) if
`pending_paths` is empty, or the user's selection otherwise. No fit
evaluation, no Gemini call — this is a plain file picker, not a scored one.

`_handle_tailor_one()` and `_handle_coverletter_one()` change from
prompting `questionary.path()` for an arbitrary filesystem path to calling
`picker.pick_one_pending_jd(jd_manager.get_pending_jds())` — meaning they now
only offer JDs the system is actually tracking as pending, not any file on
disk. The CLI's `resume tailor <path>` command is unaffected and remains the
way to point at an arbitrary file.

### 2. Chain mechanism

Each `_handle_*` function is changed to **return a bool**: whether it did
something worth chaining from. Rules per action:

- `_handle_scan` -> `True` if `scan_module.run_scan(None)` (returns an int)
  is `> 0`.
- `_handle_liveness` -> `True` if `run_liveness_check()`'s summary dict has
  no `error` key and `active + likely_active + expired + uncertain > 0`
  (i.e. at least one JD was actually checked, not just "nothing to check").
- `_handle_evaluate_all` -> `True` if the pending-check/confirm gate passes
  *and* `evaluate_all_pending()` returns a non-empty list.
- `_handle_evaluate_one` -> `True` if `engine.evaluate_fit(path)` returns a
  truthy result.
- `_handle_tailor_all` -> `True` if the pending-check/confirm gate passes
  *and* `run_pipeline()` (capturing its `(completed, failed)` return, which
  the current handler doesn't do today) returns `completed > 0`.
- `_handle_tailor_one` -> `True` if a path was picked *and*
  `run_pipeline(jd_path=path)` returns `completed > 0`.
- `_handle_coverletter_one` -> `True` if a path was picked *and*
  `build_tailored_coverletter(path)` returns a truthy (non-`{}`) result.
- `_handle_polish` -> always `False` (irrelevant — `polish` has no chain
  entry anyway).

**New `_CHAIN` dict** (next-step label -> value; "Back to Menu" is always
appended automatically, not stored here):

```python
_CHAIN = {
    "scan":            [("Check Liveness", "liveness")],
    "liveness":        [("Evaluate All JDs", "evaluate_all")],
    "evaluate_all":    [("Customize Resume", "tailor_all")],
    "evaluate_one":    [("Customize Resume", "tailor_all")],
    "tailor_all":      [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
    "tailor_one":      [("Write Cover Letter", "coverletter_one"), ("Polish with Gemini", "polish")],
    "coverletter_one": [("Polish with Gemini", "polish")],
}
```

**New recursive runner**, replacing the loop's direct `_HANDLERS[choice]()`
call:

```python
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

`run_interactive_menu()`'s while-loop calls `_run_with_chain(choice)` instead
of `_HANDLERS[choice]()`. Because `_run_with_chain` recurses into whatever
chain choice is picked (running *that* action, then offering *its* chain),
a full Scan -> Liveness -> Evaluate -> Customize -> Cover Letter -> Polish
run-through is possible without ever returning to the main menu — but "Back
to Menu" (or a no-op action) bails out to the outer loop at any point.

### 3. Title banner

New constants/function in `cli_art.py`:

```python
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

`run_interactive_menu()` calls `cli_art.display_main_banner()` once, above
the `while True:` loop, in place of today's `cli_art.display_banner("Interactive Menu")`
call. `display_banner(subtitle)` itself is untouched and keeps being used
for every other per-action panel elsewhere in the app.

## Data Flow

```
resume  (bare invocation)
  -> menu.run_interactive_menu()
       cli_art.display_main_banner()      # once
       while True:
         choice = questionary.select(main menu, _CHOICES)
         if choice in (None, "exit"): break
         _run_with_chain(choice)
           did_something = _HANDLERS[choice]()   # runs the action
           if did_something and _CHAIN.get(choice):
             next_choice = questionary.select("What's next?", ...)
             if next_choice not in (None, "__back__"):
               _run_with_chain(next_choice)       # recurse
         # loop back to main menu
```

## Error Handling

- `run_pipeline()` (batch mode, `jd_path=None`) already returns
  `(completed, failed)` per its docstring — `_handle_tailor_all` uses
  `completed > 0` directly, same signal `_handle_tailor_one` uses.
- `picker.pick_one_pending_jd([])` (no pending JDs) prints "Nothing to pick
  from -- no pending JDs." and returns `None`; the calling handler treats a
  `None` path as a no-op (returns `False`, no chain prompt).
- A cancelled `questionary.select`/`questionary.path()` prompt (`Esc`/Ctrl-C,
  returns `None`) is treated the same as an explicit "nothing picked" —
  handler returns `False`.
- Declining the batch confirm gate (`_should_proceed` -> `False`) counts as
  a no-op — `False`, no chain prompt, straight back to the main menu.

## Testing

- `picker.pick_one_pending_jd()`: unit tests — empty list returns `None`
  without prompting; labels use `"{company} - {title}"` when
  `extract_job_meta` returns both; falls back to the bare filename when it
  returns `("", "")`; returns the user's `questionary.select` choice
  (mocked).
- `menu._run_with_chain()`: unit tests (mocking `_HANDLERS`/`_CHAIN`
  entries or using the real small dicts with mocked handler functions) —
  a handler returning `False` never triggers the "what's next" prompt; a
  handler returning `True` with no `_CHAIN` entry (e.g. `polish`) never
  prompts either; a handler returning `True` with a `_CHAIN` entry prompts,
  and picking a next-step value recurses into `_run_with_chain` for it;
  picking "Back to Menu" (or cancelling) does not recurse.
- Each `_handle_*` function's new bool return: unit tests per function,
  mocking its underlying call (`scan_module.run_scan`,
  `liveness_module.run_liveness_check`, `orchestrator.run_pipeline`,
  `engine.evaluate_fit`, `engine.build_tailored_coverletter`,
  `batch_evaluate.evaluate_all_pending`) to cover both the "did something"
  and "no-op" return paths.
- `cli_art.display_main_banner()`: no dedicated test — matches this file's
  existing convention of not unit-testing static banner/art content
  (`display_banner`/`render_fit_table` aren't tested either); verified live
  by running `resume` and eyeballing the output.
- Live verification: run `resume` (bare invocation), confirm the new banner
  renders without misalignment in a real terminal, then walk one full
  chain (Scan -> Liveness -> Evaluate -> Customize -> Cover Letter ->
  Polish) end to end, confirming each "what's next" prompt offers the right
  options and "Back to Menu" exits the chain cleanly at least once
  mid-flow.
