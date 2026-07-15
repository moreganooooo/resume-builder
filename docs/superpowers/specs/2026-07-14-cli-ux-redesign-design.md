# CLI Visual Redesign — Foundation, Flow & Voice — Design

## Problem

The interactive CLI (`cli_art.py`, `menu.py`, `picker.py`) works and already
has real infrastructure — a Rich banner, a themed `questionary.Style`, a
colored fit-score table, and the chained "what's next?" flow from
[2026-07-07-menu-flow-and-banner-design.md](2026-07-07-menu-flow-and-banner-design.md).
But it was built incrementally, so:

- Color is defined three different ways across three files: literal hex in
  `picker.py`'s `_RECOMMENDATION_STYLES` (deliberately, per that file's own
  comment — named ANSI colors get remapped by terminal themes), literal
  named colors in `cli_art.py`'s `_RECOMMENDATION_COLORS` (the same
  reasoning never made it back here), and ad hoc inline `[bold cyan]`-style
  markup scattered through both files and `menu.py`.
- Long-running real API calls (`bootstrap_bullet_bank.py`'s pipeline,
  `batch_evaluate.evaluate_all_pending`, `orchestrator.run_pipeline`) print
  nothing while they run — a multi-minute Gemini call looks identical to a
  hang.
- `cli_art.ERROR`/`SUCCESS`/`WARNING`/`HINT` are bare glyphs prepended to
  plain strings — a failure and a passing status read with the same visual
  weight.
- `MAIN_BANNER` is a striking full-width block-letter splash, but nothing
  distinguishes first launch from returning to the menu after every action —
  the same visual weight repeats indefinitely in one session.
- The menu list (`_CHOICES`) is one flat list with a single `Separator()`
  before the last item; nothing visually groups discovery vs. evaluation vs.
  build actions.

Morgan is planning to share this tool with 1-2 other people once it's in
better shape, and wants it to read as a legitimate, high-end, production-
grade CLI with real personality — not just functional.

## Goals

1. One unified visual foundation (`scripts/theme.py`): semantic color
   tokens, an icon set (Nerd Font by default, Unicode fallback), and the
   `questionary.Style`, all built from the same source so every prompt and
   every printed line are provably one palette.
2. Visible progress/motion for every real API call currently silent.
3. A real error/success visual language (bordered panel for failures; a
   consistent glyph+color treatment for success) instead of a bare prefixed
   string.
4. A first-launch splash that's genuinely more polished (an animated
   diagonal-gradient reveal) than a mid-session return-to-menu moment, plus
   a session-end summary instead of a bare "Goodbye!".
5. A live, real-data stats readout (pending JD count, all-time tailored
   count) on the splash — no new persistence, sourced from existing data.
6. Menu items visually grouped by category (icon + labeled separators), and
   a rotating "did you know?" tip line for personality, kept separate from
   the (now purely informative) banner subtitle.
7. Nerd Font icons as the primary experience (Morgan has one active now),
   with a documented, working Unicode fallback and a README/setup note for
   anyone who hasn't enabled one.

## Non-Goals

- No change to the menu's actual actions, labels, merge logic, or chain
  mechanism (`_HANDLERS`, `_CHAIN`, `_run_with_chain`) — that's the prior
  spec's territory and stays as-is.
- No `--quiet`/plain-output scripting mode yet (noted as a future concept
  once `theme.py` exists to gate against — not built now).
- No per-company/archetype accent badges in the fit table — still a
  stretch idea (see below), not part of this pass.
- No historical/cross-session stats beyond what's derivable from existing
  data (`jd_manager.get_pending_jds()`, `jds/completed/` file count) — no
  new tracking file or schema.
- No changes to `cli.py`'s non-interactive commands' actual behavior — only
  their visual output (banners, error/success formatting) where they already
  call into `cli_art.py`.

## Architecture

### 1. `scripts/theme.py` — unified foundation

New module, single source of truth for everything visual:

```python
# Semantic tokens (hex, not named ANSI -- see picker.py's existing
# reasoning: named colors get remapped by terminal themes).
BRAND = "#4dabf7"
BRAND_ACCENT = "#673ab7"      # gradient's second stop; also questionary pointer/qmark
SUCCESS = "#4caf50"
ERROR = "#c96a6a"
WARNING = "#f5c542"
INFO = "#2196f3"
MUTED = "dim"

RECOMMENDATION_COLORS = {
    "Strong pursue": "#4caf50",
    "Selective pursue": "#4dabf7",
    "Low-priority pursue": "#f5c542",
    "Skip": "#c96a6a",
}

# Icon sets: Nerd Font is the default (Morgan's terminal has one active);
# RESUME_BUILDER_ICONS=unicode env var swaps to the plain-Unicode set for
# anyone who hasn't enabled one.
_NERD_ICONS = {"success": "", "error": "", "warning": "", "hint": "", ...}
_UNICODE_ICONS = {"success": "✓", "error": "✗", "warning": "⚠", "hint": "💡", ...}
ICONS = _NERD_ICONS if os.environ.get("RESUME_BUILDER_ICONS") != "unicode" else _UNICODE_ICONS

QUESTIONARY_STYLE = Style([
    ("qmark", f"fg:{BRAND_ACCENT} bold"),
    ("pointer", f"fg:{BRAND_ACCENT} bold"),
    ("answer", f"fg:{INFO} bold"),
    ("selected", f"fg:{SUCCESS}"),
    ...
])
```

`cli_art.py` and `picker.py` import from `theme.py` instead of defining their
own copies; `_RECOMMENDATION_COLORS` (`cli_art.py`) and
`_RECOMMENDATION_STYLES` (`picker.py`) both collapse to
`theme.RECOMMENDATION_COLORS`. `cli_art.SUCCESS`/`ERROR`/`WARNING`/`HINT`
constants become thin wrappers around `theme.ICONS` + the matching color.

**Nerd Font icon set**: exact glyphs to be picked from
[nerdfonts.com/cheat-sheet](https://www.nerdfonts.com/cheat-sheet) during
implementation (this spec fixes the *mechanism* — token name → glyph
mapping, with a working fallback — not the final glyph choices).

### 2. Progress motion for real API calls

Wrap each currently-silent long operation in `rich.status.Status`, using
`theme`'s tokens for consistent spinner coloring:

- `bootstrap_bullet_bank.py`'s pipeline: one status per phase, message drawn
  from a small per-phase phrase list (e.g. "Extracting achievements…",
  "Tagging by skill area…") — this is where transient personality lives.
- `batch_evaluate.evaluate_all_pending`: one status per JD being scored, or
  one aggregate status with a running count ("Evaluating 4/12…").
- `orchestrator.run_pipeline` (batch tailor): same pattern, one status per
  JD.

Rule carried over from the voice discussion: wit lives only in transient
status text, never in data (scores, company names, error detail stay
plain).

### 3. Error/success visual language

- Failures: `cli_art.display_error(message: str)` — a bordered `Panel`
  (`theme.ERROR` border), the error icon, and the message. Replaces bare
  `cli_art.console.print(f"{cli_art.ERROR} ...")` call sites.
- Success: `cli_art.display_success(message: str)` — no border (stays
  lightweight for the common case), just icon + `theme.SUCCESS` color,
  consistent across every call site that currently hand-rolls its own
  `[bold]...[/bold]` success line.
- Warnings/hints keep the existing bare-line treatment (they're advisory,
  not terminal states) but pull their icon/color from `theme.py`.

### 4. Splash, session flow & stats

- **Diagonal-gradient splash with progressive reveal** (first launch only):
  new helper in `cli_art.py`, `_gradient_grid(lines: list[str], start_hex:
  str, end_hex: str) -> list[Text]` — interpolates `theme.BRAND` →
  `theme.BRAND_ACCENT` **per character**, keyed by `(row + col) / (max_row +
  max_col)`, giving a true diagonal sweep from the top-left corner to the
  bottom-right rather than a flat top-to-bottom gradient.
  A second helper, `_reveal_banner(grid: list[Text]) -> None`, drives a
  `rich.live.Live` loop: each frame reveals more of the grid following that
  same diagonal threshold (cells past the threshold render blank/space,
  cells at or before it render their final gradient color) — this is the
  "typing/fade-in" effect, expressed as a diagonal wipe rather than literal
  left-to-right character typing (which reads oddly against solid
  block-letter glyphs) or true alpha-fade (which most terminals can't do).
  Roughly 15-20 frames over ~300-500ms total — enough to register as an
  entrance without slowing down repeat launches.
  **Non-interactive fallback**: gated on `cli_art.console.is_terminal` —
  when `False` (piped output, redirected, running under a test), skip
  `Live` and print the fully-revealed grid in one shot. Keeps this
  invisible to tests and non-interactive use.
- **Stats line**, shown once under the splash on real launch:
  `f"{pending_count} pending · {tailored_count} tailored all-time"`, where
  `pending_count = len(jd_manager.get_pending_jds())` and `tailored_count =
  len(jd_manager.get_completed_jds())` — both existing functions, already
  handle directory-doesn't-exist-yet (fresh install) internally, so no new
  persistence and no new guard logic needed here.
- **Subtitle**: becomes the informative line — left-aligned (matching every
  other panel in the app), e.g. version/tagline text, *not* rotating. The
  rotating-personality role moves entirely to the new tip line (below).
- **Compact return-to-menu**: `run_interactive_menu()`'s loop no longer
  reprints a full banner/panel between actions — a one-line breadcrumb
  (`theme.BRAND`-colored `"› resume-builder"` + a dim rule) replaces it. The
  full `MAIN_BANNER` + gradient splash is reserved for the initial call
  only.
- **"What's next?" prompt**: restyled as a plain `theme`-colored question
  (no bordered panel) — keeps one visual-weight class per moment instead of
  stacking panel-on-panel under an already-lightweight breadcrumb.
- **Session-end summary**: `run_interactive_menu()` tracks a simple
  in-memory counter dict (incremented inside `_run_with_chain` wherever a
  handler returns `True`, keyed by action), printed as one line on exit
  (e.g. `"✓ 3 resumes tailored · 2 cover letters written · Nice work."`).
  Session-scoped only — not persisted.

### 5. Menu grouping & voice

- `_CHOICES` in `menu.py` gets labeled `questionary.Separator("── Discovery ──")`
  -style dividers between category groups (Discovery: Scan/Liveness;
  Evaluation: Evaluate All/Evaluate One; Build: Tailor All/Tailor One/Cover
  Letter/Polish; Utility: View Tracker/Exit), and each `Choice` gets a
  leading icon tied to its category from `theme.ICONS`.
- **"Did you know?" tip rotation**: a `TIPS` list (in `theme.py` or a new
  small `copy.py`) of short usage tips (e.g. mentioning `resume run --pick`,
  `resume test -v`, the bootstrap flow) — one chosen via `random.choice` per
  real launch (not per loop iteration), printed once below the splash/stats
  line, above the first menu prompt.

## Data Flow (launch sequence)

```
resume  (bare invocation)
  -> menu.run_interactive_menu()
       cli_art.display_main_banner()       # gradient splash, once
       cli_art.display_stats_line()        # pending/tailored counts, once
       cli_art.display_tip()               # random tip, once
       session_stats = {}
       while True:
         if first iteration: no breadcrumb (splash already shown)
         else: print compact breadcrumb
         choice = questionary.select(main menu, _CHOICES)  # grouped + iconed
         if choice in (None, "exit"):
           print session summary from session_stats
           break
         _run_with_chain(choice, session_stats)   # existing chain logic,
                                                    # now also tallies session_stats
```

## Error Handling

- Missing `jds/completed/` directory (fresh install, nothing tailored yet):
  already handled — `jd_manager.get_completed_jds()` creates the directory
  if absent and returns `[]`, so `tailored_count` is `0` with no new guard
  needed.
- `RESUME_BUILDER_ICONS` env var: any value other than exactly `"unicode"`
  falls through to the Nerd Font set (fails toward the enhanced default,
  not toward breakage — a typo'd env var doesn't silently degrade the
  experience for someone who *does* have a Nerd Font active).
- Gradient helper receives a `lines` list shorter than expected (e.g. banner
  text edited later without updating the helper call): interpolates over
  whatever line count it's given — no hardcoded row count assumption.

## Testing

- `theme.py`: unit tests — `ICONS` resolves to the Nerd Font set by default
  and to the Unicode set when `RESUME_BUILDER_ICONS=unicode` is set
  (`monkeypatch`/`patch.dict(os.environ, ...)`); `RECOMMENDATION_COLORS`
  keys match the four literal strings `orchestrator.FitEvaluationSchema`
  actually produces (guards against typo drift between the two files).
- `cli_art._gradient_grid()`: unit test — given N lines and two hex colors,
  returns N styled `Text` objects; the top-left cell's style resolves to
  `start_hex`, the bottom-right cell's to `end_hex`.
- `cli_art._reveal_banner()`: unit test with `console.is_terminal` patched
  to `False` — confirms it prints the fully-revealed grid once and never
  touches `Live` (no hang, no delay, in a piped/test context). A patched
  `is_terminal=True` case (with `Live` itself mocked) confirms the frame
  count is > 1 and the final frame matches the fully-revealed grid.
- `cli_art.display_error`/`display_success`: existing convention (per the
  prior spec) is no dedicated test for static rendering — covered by
  whichever call site already has tests mocking `cli_art` (per this
  session's check, `test_menu.py` mocks `cli_art` functions rather than
  asserting on rendered text, so no changes needed there for the restyle
  itself).
- `menu.run_interactive_menu()`'s session-summary tally: unit test — a
  sequence of mocked `_HANDLERS` returns (`True`/`False` across a couple of
  actions) produces the expected counter dict/summary string.
- Live verification: run `resume` bare, confirm the diagonal-gradient splash
  reveals smoothly (no flicker, no misalignment, finishes in well under a
  second) in a real terminal, the stats line shows real pending/tailored
  counts, a tip appears, the menu shows grouped separators + icons, run one
  action and confirm the compact breadcrumb (not a full banner) appears on
  return-to-menu, then `Exit` and confirm the session summary line reflects
  what was actually done. Separately, confirm piping `resume`'s output
  (e.g. `resume | cat`) still shows the static fully-revealed banner with no
  hang or animation artifacts.

## Stretch Ideas (explicitly out of scope for this pass)

- Per-company/archetype accent-colored mini badges in the fit table.
- A `--quiet`/plain-output escape hatch for scripting.
