# Console Output Polish & Color System — Design

## Problem

A real live-verification run (2026-07-07) surfaced two related complaints
about the terminal experience:

1. **Noise.** The PDF-generation block (Input/Output/Format/ATS
   normalization/Pages/Size — 6 lines) reprints in full on every trim
   attempt during Step 7's page-fit loop; the JD-keyword extraction step
   dumps raw pretty-printed JSON; and the top-level Step 1-7 headers don't
   visually separate from their own sub-output, even though the
   bullet-audit loop already solved exactly this with a `────` divider.
2. **Color.** The interactive menu's block-letter title banner (added
   2026-07-07) is essentially invisible against Morgan's actual terminal
   background — confirmed via screenshots, not assumed: her terminal uses
   a dark teal background, and her terminal's color theme renders Rich's
   named `cyan` as a muted, low-contrast sage-gray that blends into it.
   Meanwhile `questionary`'s own custom hex-based theme (purple pointer,
   blue "answer" highlight) renders vividly in the same screenshots — the
   difference is named ANSI colors (theme-dependent) vs. explicit hex
   colors (theme-independent).

## Goals

1. Collapse the trim loop's repeated full PDF block to one line per
   intermediate attempt; only the truly final PDF (success or exhausted)
   gets the full block.
2. Replace the keyword-extraction JSON dump with a one-line count summary.
3. Extend the bullet-audit loop's existing plain `'─' * 60` divider
   convention to the top-level Step 1-7 headers.
4. Fix the banner's invisibility by moving off theme-dependent named
   colors (`cyan`) onto explicit hex colors, confirmed by direct visual
   comparison against a simulation of Morgan's actual terminal background:
   blue (`#4dabf7`) for the banner text, green (`#4caf50` — already the
   hex behind `QUESTIONARY_STYLE`'s `selected` and the existing `✓`
   success color) for a bordered `Panel` around it, borrowing
   job_automater's actual `Panel(border_style=..., box=box.DOUBLE)`
   pattern rather than the current unbordered plain-text banner.
5. Give the "What's next?" chain prompt (from the menu-flow feature) the
   same bordered treatment, so a completed action visually reads as "here's
   your next move" the same way the banner reads as "here's where you are."

## Non-Goals

- No change to purple (`#673ab7`, questionary's existing pointer/qmark
  color) or the existing named-color `SUCCESS`/`ERROR`/`WARNING` symbols in
  `cli_art.py` — none of those were reported as broken, and this stays
  scoped to what's actually confirmed problematic (the banner) plus what
  was explicitly requested (borders on the banner and the chain prompt).
- No bordered treatment for the main, recurring "What would you like to
  do?" menu prompt — that one reprints every loop iteration; boxing it
  too would reintroduce the exact noise this design is cutting elsewhere.
  Only the once-per-launch banner and the after-action chain prompts get
  the fancy treatment.
- No new `cli_art`/Rich dependency inside `orchestrator.py`. The Step
  header dividers stay plain-text (matching the bullet-audit loop's
  existing convention exactly), not colorized — `orchestrator.py` has zero
  Rich/`cli_art` imports today, and colorizing one cosmetic divider isn't
  worth introducing that coupling.
- No change to the "Warming segment cache" per-(company, tag) listing —
  explicitly requested to stay as-is.
- No change to `evaluate_all`'s fit-table rendering or any other
  already-Rich-rendered output (`cli_art.render_fit_table`, etc.) — those
  weren't reported as having a color problem.

## Architecture

### 1. Trim loop PDF-block collapse (`orchestrator.py`, Step 7)

Extract page-count/size parsing into a small testable helper:

```python
def _parse_pdf_result(stdout: str) -> tuple:
    """Extracts (page_count, size_str) from generate-pdf.mjs's stdout --
    page_count is None and size_str is "unknown size" if either line
    isn't found (matches the pdf_result.stdout format already parsed
    inline today, just pulled into its own testable function)."""
    page_count_match = re.search(r"Pages:\s*(\d+)", stdout)
    page_count = int(page_count_match.group(1)) if page_count_match else None
    size_match = re.search(r"Size:\s*([\d.]+\s*\w+)", stdout)
    size_str = size_match.group(1) if size_match else "unknown size"
    return page_count, size_str
```

The trim `while True:` loop changes from unconditionally printing
`pdf_result.stdout` every iteration to only printing it when this
iteration is the final one (matches today's existing break condition,
just evaluated before printing instead of after):

```python
while True:
    pdf_result = subprocess.run([...], capture_output=True, text=True)
    if pdf_result.returncode != 0:
        print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
        return {}

    page_count, size_str = _parse_pdf_result(pdf_result.stdout)
    is_final = page_count is None or page_count <= 2 or trim_attempt >= max_trim_attempts
    if is_final:
        print(pdf_result.stdout)
        break

    if not dropped_optional_clients:
        ...
        if has_optional_clients:
            print(f"  PDF is {page_count} pages ({size_str}), dropping optional client rosters...")
            ...
            continue

    print(f"  PDF is {page_count} pages ({size_str}), applying trim step {trim_attempt + 1}/{max_trim_attempts}...")
    ...
```

Both of the two existing non-final narration lines ("dropping optional
client rosters" / "applying trim step N/M") already report `page_count` —
this just adds `size_str` to them and removes the now-redundant full
block that used to precede them.

### 2. Keyword-extraction one-liner (`orchestrator.py`, Step 1)

```python
def _summarize_keywords(jd_keywords: dict) -> str:
    """One-line count summary of a JDKeywordSchema-shaped dict (tools,
    hard_skills, core_functions today, but iterates generically over
    whatever keys are present rather than hardcoding those three names).
    Full values remain in the checkpoint JSON for anyone who needs them."""
    parts = [f"{len(v)} {k.replace('_', ' ')}" for k, v in jd_keywords.items() if v]
    return ", ".join(parts) if parts else "none found"
```

Replaces:
```python
print(f"  Keywords extracted: {json.dumps(jd_keywords, indent=2)[:400]}")
```
with:
```python
print(f"  Keywords extracted: {_summarize_keywords(jd_keywords)}")
```

### 3. Step header dividers (`orchestrator.py`, Steps 1/2/3/4/5/5.5/7)

Each of the 7 existing `print("\nStep N: ...")` call sites (including
both branches of Step 5.5) gets the exact same plain divider the
bullet-audit loop already uses at `orchestrator.py:1311`
(`print(f"\n{'─'*60}")`), immediately before the header line -- e.g.:

```python
print(f"\n{'─'*60}")
print("\nStep 1: Extracting JD keywords...")
```

(Step 6 has no dedicated header today — just a comment, `# --- Step 6:
Save output ---` — so nothing to add there.)

### 4. Color system + bordered banner (`cli_art.py`)

```python
from rich import box
```

`MAIN_BANNER`'s `[bold cyan]` / `[/bold cyan]` markup becomes `[bold
#4dabf7]` / `[/bold #4dabf7]` (text only -- the `[dim]` tagline line is
unchanged, matching the confirmed-good mockup). `display_main_banner()`
wraps it in a bordered panel instead of printing it raw:

```python
def display_main_banner() -> None:
    console.print(Panel(MAIN_BANNER, border_style="#4caf50", box=box.DOUBLE, padding=(1, 2)))
```

New function for the chain prompt's panel:

```python
def display_whats_next_panel() -> None:
    console.print(Panel("What's next?", border_style="#4caf50", box=box.ROUNDED, padding=(0, 2)))
```

### 5. Chain prompt wiring (`menu.py`)

`_run_with_chain()` prints the new panel immediately before the
`questionary.select()` call, and the prompt's own text shortens since the
panel now states the question:

```python
def _run_with_chain(value: str) -> None:
    did_something = _HANDLERS[value]()
    next_options = _CHAIN.get(value)
    if not did_something or not next_options:
        return

    choices = [questionary.Choice(title=label, value=v) for label, v in next_options]
    choices.append(questionary.Choice(title="Back to Menu", value="__back__"))
    cli_art.display_whats_next_panel()
    choice = questionary.select(
        "Choose one:", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()

    if not choice or choice == "__back__":
        return
    _run_with_chain(choice)
```

## Data Flow

```
run_interactive_menu()
  -> cli_art.display_main_banner()          # once, bordered, blue-on-green-panel
  -> loop: questionary.select(main menu)     # unchanged, no panel
       -> _run_with_chain(choice)
            -> _HANDLERS[choice]()           # unchanged
            -> if did_something and has next steps:
                 cli_art.display_whats_next_panel()   # new, bordered
                 questionary.select("Choose one:", ...)

build_tailored_resume() -- Step 1:
  -> jd_keywords extracted -> print(_summarize_keywords(jd_keywords))   # one line, was multi-line JSON

build_tailored_resume() -- Step 7 trim loop:
  -> subprocess.run(generate-pdf.mjs) -> _parse_pdf_result(stdout)
       -> is_final? print full stdout block : print one enhanced narration line
```

## Error Handling

- `_parse_pdf_result()` already tolerates a missing "Pages:"/"Size:" line
  (returns `None`/`"unknown size"`) -- same defensive posture as today's
  inline regex, just relocated.
- `_summarize_keywords({})` (empty dict, shouldn't happen given
  `JDKeywordSchema` requires all three fields, but defensively handled)
  returns `"none found"` rather than an empty string.
- No error-handling changes needed for the Panel/banner work -- `Panel`/`box`
  are already-proven Rich APIs (job_automater uses this exact pattern
  today), and `console.print()` doesn't raise on any string content.

## Testing

- `_parse_pdf_result()`: unit tests -- a real `generate-pdf.mjs`-shaped
  stdout string extracts the correct `(page_count, size_str)`; a stdout
  missing the "Pages:" line returns `(None, ...)`; one missing "Size:"
  returns `(..., "unknown size")`.
- `_summarize_keywords()`: unit tests -- a normal 3-key dict produces the
  expected comma-joined summary; a key with an empty list is omitted from
  the summary; an all-empty dict returns `"none found"`.
- Trim loop: existing tests in `test_orchestrator_build_checkpoint.py`
  (`test_trim_loop_survives_one_unparseable_attempt_and_still_succeeds`,
  `test_page_count_trim_loop_retries_then_succeeds`,
  `test_page_count_trim_loop_exhausts_and_returns_empty`) already assert
  on `resume_data`/return-value outcomes, not console text -- confirming
  they still pass after this change verifies the collapse is purely
  cosmetic, not a behavior change.
- No dedicated tests for `display_main_banner()`/`display_whats_next_panel()`
  or the plain-text Step dividers -- matches this file's existing
  convention of verifying static banner/art output live rather than
  asserting on it (same as `display_banner`/`render_fit_table` today).
- Live verification: run `resume` and eyeball the banner (bordered, blue
  text, green border, legible against the actual terminal background this
  was designed against) and one real chain step's "What's next?" panel;
  run a real `resume tailor <file>` that needs at least one trim attempt
  and confirm only the final PDF's full block prints, with the
  intermediate attempts collapsed to one line each including size.
