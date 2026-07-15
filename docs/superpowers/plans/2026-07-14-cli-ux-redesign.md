# CLI Visual Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give resume-builder's interactive CLI one unified color/icon/style
system, visible motion where an API call is genuinely silent, a real error/
success visual language, and a more polished (animated, data-backed, grouped)
launch/session experience — without touching any menu action's actual
behavior.

**Architecture:** A new `scripts/theme.py` becomes the single source of
truth for colors, icons, and the shared `questionary.Style`; `cli_art.py`
and `picker.py` are refactored to build their constants from it instead of
duplicating them. `cli_art.py` gains new display functions (gradient splash
reveal, stats line, tip line, breadcrumb, error/success panels) that
`menu.py` and `cli.py` call at the appropriate points. `menu.py`'s
`run_interactive_menu()`/`_run_with_chain()` gain a `session_stats` dict
threaded through for the exit-time summary, and `_CHOICES` gains grouped
`Separator`s + icons. No changes to `_HANDLERS`/`_CHAIN` routing logic, no
changes to any pipeline module's actual behavior — only their visual output.

**Tech Stack:** Python 3.10+, `rich` (Console, Panel, Live, Text, Status,
box), `questionary` (Style, Separator, Choice), stdlib `unittest`
(`python -m unittest discover -s tests`, run from project root with
`.venv/` activated).

## Global Constraints

- Every new/changed module lives under `scripts/` and is imported the way
  existing sibling modules are (`sys.path.insert(0, SCRIPTS_DIR)` in each
  test file — see any existing `tests/test_*.py` header).
- No named ANSI color strings (`"cyan"`, `"green"`, etc.) anywhere in
  `theme.py`, `cli_art.py`, or `picker.py` — hex only, per the project's
  existing (documented) reasoning that named colors get remapped by
  terminal themes.
- Nerd Font icons are the default; `RESUME_BUILDER_ICONS=unicode` (exact
  match, case-sensitive) is the only way to opt into the plain-Unicode
  fallback set. Any other/unset value resolves to Nerd Font icons.
- No change to `menu._HANDLERS`, `menu._CHAIN`, or the order/conditions
  under which `_run_with_chain` recurses — those stay exactly as the prior
  `2026-07-07-menu-flow-and-banner-design.md` spec left them.
- No change to any pipeline module's (`orchestrator.py`, `batch_evaluate.py`,
  `bootstrap_bullet_bank.py`) actual return values, side effects, or
  existing `print()` calls — only new, additive wrapping around specific
  already-identified silent call sites.
- Run `python -m unittest discover -s tests` (or `resume test -v`) after
  every task and confirm the full suite passes, not just the new file —
  several tasks intentionally modify existing test files.

---

## File Structure

| File | Responsibility |
|---|---|
| `scripts/theme.py` (new) | Color tokens, Nerd Font/Unicode icon sets + env var switch, `RECOMMENDATION_COLORS`/`RECOMMENDATION_STYLES`, shared `QUESTIONARY_STYLE`. |
| `scripts/cli_art.py` (modified) | Imports constants from `theme.py`; gains `display_error`, `display_success`, gradient/reveal helpers, `display_main_banner` rewrite, `display_stats_line`, `display_tip`, `display_breadcrumb`; `display_whats_next_panel` restyled. |
| `scripts/picker.py` (modified) | `_RECOMMENDATION_STYLES` now sourced from `theme.RECOMMENDATION_STYLES`. |
| `scripts/menu.py` (modified) | `_CHOICES` gains grouped `Separator`s + icons; `run_interactive_menu`/`_run_with_chain` gain `session_stats` threading and a session-end summary; breadcrumb on loop-back. |
| `scripts/batch_evaluate.py` (modified) | Wraps the one genuinely-silent `engine.evaluate_fit(path)` call in a status spinner. |
| `scripts/cli.py` (modified) | `evaluate` command's single-JD branch wraps its `evaluate_fit` call in a status spinner; error/warning lines switch to `cli_art.display_error`/`display_success`. |
| `tests/test_theme.py` (new) | Icon env-var switch, `RECOMMENDATION_COLORS` keys match `orchestrator.FitEvaluationSchema`'s literal. |
| `tests/test_cli_art.py` (new) | Gradient grid math, reveal fallback behavior, stats line, tip line, error/success panels. |
| `tests/test_cli_art_bootstrap.py` (modified) | `test_hint_constant_exists_and_is_styled` rewritten for the new theme-driven `HINT`. |
| `tests/test_menu.py` (modified) | `TestChoicesAndHandlers` label assertions relaxed to `assertIn` (icon prefix); `TestRunWithChain` calls updated for `_run_with_chain`'s new `session_stats` parameter; new tests for the session-summary tally. |
| `tests/test_picker.py` (modified, if needed) | Confirm `_RECOMMENDATION_STYLES` still resolves correctly after sourcing from `theme.py` (existing tests, if any touch this, continue passing — see Task 3). |
| `README.md` (modified) | Setup section gains a Nerd Font note; "Colors" paragraph updated; Interactive menu section documents the splash/stats/tip/breadcrumb/summary. |
| `CLAUDE.md` (modified) | One-line Setup addition pointing at the Nerd Font note. |

---

### Task 1: `scripts/theme.py` — unified color/icon/style foundation

**Files:**
- Create: `scripts/theme.py`
- Test: `tests/test_theme.py`

**Interfaces:**
- Produces: `theme.BRAND`, `theme.BRAND_ACCENT`, `theme.SUCCESS`,
  `theme.ERROR`, `theme.WARNING`, `theme.INFO` (all `"#rrggbb"` strings);
  `theme.RECOMMENDATION_COLORS: dict[str, str]`;
  `theme.RECOMMENDATION_STYLES: dict[str, str]`; `theme.ICONS: dict[str, str]`
  (keys: `success`, `error`, `warning`, `hint`, `discovery`, `evaluate`,
  `build`, `utility`); `theme.QUESTIONARY_STYLE: questionary.Style`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_theme.py
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import importlib

import theme  # noqa: E402
import orchestrator  # noqa: E402


class TestIconSwitch(unittest.TestCase):

    def test_defaults_to_nerd_font_icons(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RESUME_BUILDER_ICONS", None)
            reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "")

    def test_unicode_env_var_switches_to_unicode_icons(self):
        with patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "unicode"}):
            reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "✓")
        importlib.reload(theme)  # restore default for subsequent tests

    def test_unrecognized_value_falls_back_to_nerd_font(self):
        with patch.dict(os.environ, {"RESUME_BUILDER_ICONS": "banana"}):
            reloaded = importlib.reload(theme)
        self.assertEqual(reloaded.ICONS["success"], "")
        importlib.reload(theme)


class TestRecommendationColors(unittest.TestCase):

    def test_keys_match_fit_evaluation_schema_literal(self):
        schema_values = orchestrator.FitEvaluationSchema.__fields__["recommendation"].annotation.__args__
        self.assertEqual(set(theme.RECOMMENDATION_COLORS.keys()), set(schema_values))
        self.assertEqual(set(theme.RECOMMENDATION_STYLES.keys()), set(schema_values))

    def test_skip_style_is_not_bold_others_are(self):
        self.assertNotIn("bold", theme.RECOMMENDATION_STYLES["Skip"])
        self.assertIn("bold", theme.RECOMMENDATION_STYLES["Strong pursue"])


class TestQuestionaryStyle(unittest.TestCase):

    def test_new_user_token_is_success_colored(self):
        style_rules = dict(theme.QUESTIONARY_STYLE.style_rules)
        self.assertIn("new_user", style_rules)
        self.assertIn(theme.SUCCESS, style_rules["new_user"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/morganescott/resume-builder && source .venv/bin/activate && python -m unittest tests.test_theme -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'theme'`

- [ ] **Step 3: Write `scripts/theme.py`**

```python
"""theme.py -- single source of truth for resume-builder's CLI visual
system: color tokens, icon glyphs (Nerd Font by default, plain Unicode
fallback), and the shared questionary.Style. cli_art.py and picker.py both
build their own constants from this module instead of defining their own
copies -- see docs/superpowers/specs/2026-07-14-cli-ux-redesign-design.md.
"""

import os

from questionary import Style

# Semantic color tokens -- hex, not named ANSI colors. Named colors get
# remapped by whatever terminal theme is active; this project has already
# hit that in practice (see README's "Colors" section: `cyan` washed out
# to near-invisible gray on a dark-teal theme).
BRAND = "#4dabf7"
BRAND_ACCENT = "#673ab7"
SUCCESS = "#4caf50"
ERROR = "#c96a6a"
WARNING = "#f5c542"
INFO = "#2196f3"

# Values match orchestrator.FitEvaluationSchema's `recommendation` Literal
# exactly: "Strong pursue", "Selective pursue", "Low-priority pursue", "Skip".
RECOMMENDATION_COLORS = {
    "Strong pursue": SUCCESS,
    "Selective pursue": BRAND,
    "Low-priority pursue": WARNING,
    "Skip": ERROR,
}

# questionary Choice-title style strings for the same four tiers. "Skip"
# stays unbolded (deliberately de-emphasized); the other three are bold.
RECOMMENDATION_STYLES = {
    "Strong pursue": f"fg:{SUCCESS} bold",
    "Selective pursue": f"fg:{BRAND} bold",
    "Low-priority pursue": f"fg:{WARNING} bold",
    "Skip": f"fg:{ERROR}",
}

# Font Awesome glyphs (Private Use Area code points Nerd Fonts patch in
# verbatim under the nf-fa-* names) -- this is the default experience.
_NERD_ICONS = {
    "success": "",     # nf-fa-check
    "error": "",       # nf-fa-times
    "warning": "",     # nf-fa-exclamation_triangle
    "hint": "",        # nf-fa-lightbulb_o
    "discovery": "",   # nf-fa-search
    "evaluate": "",    # nf-fa-bar_chart
    "build": "",       # nf-fa-wrench
    "utility": "",     # nf-fa-cog
}

# Plain Unicode fallback -- renders correctly with no special font. See
# README's "Fonts"/Setup notes for how to opt in via RESUME_BUILDER_ICONS.
_UNICODE_ICONS = {
    "success": "✓",     # ✓
    "error": "✗",       # ✗
    "warning": "⚠",     # ⚠
    "hint": "\U0001F4A1",    # 💡
    "discovery": "\U0001F50D",  # 🔍
    "evaluate": "\U0001F4CA",   # 📊
    "build": "\U0001F6E0",      # 🛠
    "utility": "⚙",         # ⚙
}

# Nerd Font is the default -- set RESUME_BUILDER_ICONS=unicode (exact,
# case-sensitive match) to fall back to the plain-Unicode set. Any other
# or unset value fails toward the enhanced default, not toward breakage --
# a typo'd env var shouldn't silently degrade someone who does have a
# Nerd Font active.
ICONS = _UNICODE_ICONS if os.environ.get("RESUME_BUILDER_ICONS") == "unicode" else _NERD_ICONS

QUESTIONARY_STYLE = Style([
    ("qmark", f"fg:{BRAND_ACCENT} bold"),
    ("question", "bold"),
    ("answer", f"fg:{INFO} bold"),
    ("pointer", f"fg:{BRAND_ACCENT} bold"),
    ("highlighted", f"fg:{BRAND_ACCENT} bold"),
    ("selected", f"fg:{SUCCESS}"),
    ("separator", "fg:#cc5454"),
    ("new_user", f"fg:{SUCCESS} bold"),
    ("instruction", ""),
    ("text", ""),
])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_theme -v`
Expected: all tests PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/theme.py tests/test_theme.py
git commit -m "$(cat <<'EOF'
Add theme.py: unified color/icon/questionary-style tokens

Single source of truth replacing the hex/named-color/inline-markup mix
scattered across cli_art.py and picker.py. Nerd Font icons default on,
with a RESUME_BUILDER_ICONS=unicode fallback for anyone without one.
EOF
)"
```

---

### Task 2: Refactor `cli_art.py`'s constants onto `theme.py`

**Files:**
- Modify: `scripts/cli_art.py:1-33` (imports, `SUCCESS`/`ERROR`/`WARNING`/`HINT`, `QUESTIONARY_STYLE`), `scripts/cli_art.py:83-89` (`_RECOMMENDATION_COLORS`)
- Test: `tests/test_cli_art_bootstrap.py:11-23`

**Interfaces:**
- Consumes: `theme.SUCCESS/ERROR/WARNING/INFO`, `theme.ICONS`,
  `theme.QUESTIONARY_STYLE`, `theme.RECOMMENDATION_COLORS` (Task 1).
- Produces: `cli_art.SUCCESS/ERROR/WARNING/HINT` (Rich markup strings,
  theme-driven), `cli_art.QUESTIONARY_STYLE` (re-export of
  `theme.QUESTIONARY_STYLE`, so `menu.py`/`picker.py` need no import
  changes), `cli_art._RECOMMENDATION_COLORS` now sourced from
  `theme.RECOMMENDATION_COLORS`.

- [ ] **Step 1: Update the failing test for the new HINT behavior**

Replace the existing test in `tests/test_cli_art_bootstrap.py` (lines 11-16)
— it currently asserts the literal Unicode lightbulb and `"cyan"`, which no
longer match the theme-driven default:

```python
# tests/test_cli_art_bootstrap.py -- replace TestHintConstant with:
class TestHintConstant(unittest.TestCase):

    def test_hint_uses_theme_icon_and_color_by_default(self):
        self.assertIn(cli_art.theme.ICONS["hint"], cli_art.HINT)
        self.assertIn(cli_art.theme.INFO, cli_art.HINT)
```

Leave `TestNewUserStyleToken` and `TestDisplayBootstrapIntro` unchanged —
`TestNewUserStyleToken` already asserts `"#4caf50"` (that's
`theme.SUCCESS`), which Task 1 already preserves via `theme.QUESTIONARY_STYLE`.

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `python -m unittest tests.test_cli_art_bootstrap -v`
Expected: `test_hint_uses_theme_icon_and_color_by_default` FAILS —
`AttributeError: module 'cli_art' has no attribute 'theme'` (not imported
yet)

- [ ] **Step 3: Refactor `cli_art.py`'s constants**

Replace `scripts/cli_art.py` lines 1-33 (imports through the end of
`QUESTIONARY_STYLE`) with:

```python
"""Lightweight banner/symbols for resume-builder's CLI, in job_automater's
cli_art.py style (rich Console/Panel) but trimmed down -- no hand-drawn ASCII
block art, just a clean styled banner."""

import random
import time

from rich import box
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import jd_manager
import theme

console = Console()

SUCCESS = f"[bold {theme.SUCCESS}]{theme.ICONS['success']}[/bold {theme.SUCCESS}]"
ERROR = f"[bold {theme.ERROR}]{theme.ICONS['error']}[/bold {theme.ERROR}]"
WARNING = f"[bold {theme.WARNING}]{theme.ICONS['warning']}[/bold {theme.WARNING}]"
HINT = f"[bold {theme.INFO}]{theme.ICONS['hint']}[/bold {theme.INFO}]"

# Re-exported so menu.py/picker.py's existing `cli_art.QUESTIONARY_STYLE`
# references keep working unchanged.
QUESTIONARY_STYLE = theme.QUESTIONARY_STYLE
```

Then replace the `_RECOMMENDATION_COLORS` dict (originally lines 83-89)
with:

```python
# Same four tiers as orchestrator.FitEvaluationSchema's `recommendation`
# Literal -- sourced from theme.py so this table and picker.py's checkbox
# list are provably one palette, not two hand-maintained copies. "Skip"
# is intentionally not dimmed here (it was previously "red dim" in this
# file only) -- unified to match picker.py's plain-hex treatment.
_RECOMMENDATION_COLORS = theme.RECOMMENDATION_COLORS
```

(Leave every other function in `cli_art.py` — `display_main_banner`,
`display_whats_next_panel`, `display_bootstrap_intro`, `display_banner`,
`render_fit_table`, `display_applications_tracker` — untouched in this
task; `display_main_banner` is rewritten in Task 5.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cli_art_bootstrap -v`
Expected: all 3 tests PASS

Then run the full suite to confirm nothing else broke:
Run: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cli_art.py tests/test_cli_art_bootstrap.py
git commit -m "$(cat <<'EOF'
Refactor cli_art.py's color/icon/style constants onto theme.py

SUCCESS/ERROR/WARNING/HINT and _RECOMMENDATION_COLORS now build from
theme.py's tokens instead of hardcoding named colors and an emoji.
EOF
)"
```

---

### Task 3: Refactor `picker.py`'s `_RECOMMENDATION_STYLES` onto `theme.py`

**Files:**
- Modify: `scripts/picker.py:17-26`
- Test: `tests/test_picker.py` (verify existing tests still pass; no new
  test needed — `theme.RECOMMENDATION_STYLES`'s content is already covered
  by `tests/test_theme.py`'s `TestRecommendationColors`)

**Interfaces:**
- Consumes: `theme.RECOMMENDATION_STYLES` (Task 1).
- Produces: `picker._RECOMMENDATION_STYLES` (re-export, same dict).

- [ ] **Step 1: Confirm current behavior with the existing test suite**

Run: `python -m unittest tests.test_picker -v`
Expected: all PASS (baseline, before this task's change)

- [ ] **Step 2: N/A — no new failing test for this task**

This task is a pure refactor with no new observable behavior (Task 1's
`test_skip_style_is_not_bold_others_are` and
`test_keys_match_fit_evaluation_schema_literal` already pin the values this
dict must have). Proceed directly to the implementation.

- [ ] **Step 3: Refactor `picker.py`**

Replace `scripts/picker.py` lines 17-26 with:

```python
import theme

# Sourced from theme.py so picker.py's checkbox list and cli_art.py's fit
# table are provably one palette -- see theme.RECOMMENDATION_STYLES for
# the exact values ("Skip" stays unbolded, deliberately de-emphasized).
_RECOMMENDATION_STYLES = theme.RECOMMENDATION_STYLES
```

(This replaces the previous inline dict and its explanatory comment —
`theme.py`'s own module docstring/comments now carry that reasoning.)

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `python -m unittest tests.test_picker tests.test_theme -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/picker.py
git commit -m "$(cat <<'EOF'
Refactor picker.py's recommendation-tier styles onto theme.py

Same dict, now sourced from the single theme.py definition instead of
a second hardcoded copy.
EOF
)"
```

---

### Task 4: `cli_art.display_error`/`display_success` + call-site updates

**Files:**
- Modify: `scripts/cli_art.py` (add two functions after the `HINT`/
  `QUESTIONARY_STYLE` block)
- Modify: `scripts/cli.py:81,84,145,159` (call-site swaps)
- Modify: `scripts/menu.py:130` (call-site swap)
- Test: `tests/test_cli_art.py` (new file)

**Interfaces:**
- Consumes: `theme.ERROR`, `theme.SUCCESS`, `theme.ICONS` (Task 1).
- Produces: `cli_art.display_error(message: str) -> None`,
  `cli_art.display_success(message: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_art.py
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from rich.console import Console

import cli_art  # noqa: E402


def _rendered(fn, *args, **kwargs):
    console = Console(record=True, width=100)
    original = cli_art.console
    cli_art.console = console
    try:
        fn(*args, **kwargs)
    finally:
        cli_art.console = original
    return console.export_text()


class TestDisplayError(unittest.TestCase):

    def test_renders_message_in_a_bordered_panel(self):
        output = _rendered(cli_art.display_error, "Evaluation failed.")
        self.assertIn("Evaluation failed.", output)
        self.assertIn(cli_art.theme.ICONS["error"], output)


class TestDisplaySuccess(unittest.TestCase):

    def test_renders_message_with_icon_no_border(self):
        output = _rendered(cli_art.display_success, "Resume built.")
        self.assertIn("Resume built.", output)
        self.assertIn(cli_art.theme.ICONS["success"], output)
        # No panel border characters -- success stays lightweight.
        self.assertNotIn("╭", output)  # ╭ (rounded-panel corner)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_cli_art -v`
Expected: FAIL — `AttributeError: module 'cli_art' has no attribute 'display_error'`

- [ ] **Step 3: Implement the two functions**

Add to `scripts/cli_art.py`, directly after the `QUESTIONARY_STYLE = theme.QUESTIONARY_STYLE` line:

```python
def display_error(message: str) -> None:
    """A failure reads with real visual weight -- a bordered panel, not a
    bare icon-prefixed line."""
    body = f"[bold {theme.ERROR}]{theme.ICONS['error']}[/bold {theme.ERROR}] {message}"
    console.print(Panel(body, border_style=theme.ERROR, box=box.ROUNDED, padding=(0, 2)))


def display_success(message: str) -> None:
    """Stays lightweight (no border) -- this is the common case and a
    bordered panel for every success would get old fast."""
    console.print(f"[bold {theme.SUCCESS}]{theme.ICONS['success']}[/bold {theme.SUCCESS}] {message}")
```

Then update the four call sites in `scripts/cli.py`:

- Line 81: replace
  `cli_art.console.print(f"{cli_art.ERROR} Pass a JD file OR --pick, not both.")`
  with
  `cli_art.display_error("Pass a JD file OR --pick, not both.")`
- Line 84: replace
  `cli_art.console.print(f"{cli_art.ERROR} Pass a JD file, or use --pick to select interactively.")`
  with
  `cli_art.display_error("Pass a JD file, or use --pick to select interactively.")`
- Line 145: replace
  `cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")`
  with
  `cli_art.display_error("Evaluation failed -- no parseable result.")`
- Line 159: leave `WARNING` as-is (advisory, not a terminal state — see
  spec's Architecture section 3).

And in `scripts/menu.py` line 130, replace
`cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")`
with `cli_art.display_error("Evaluation failed -- no parseable result.")`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cli_art -v`
Expected: both tests PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS (confirms the `cli.py`/`menu.py` call-site swaps didn't
break `tests/test_cli_evaluate.py`/`tests/test_menu.py`, which mock
`cli_art`/assert on return values, not printed text)

- [ ] **Step 5: Commit**

```bash
git add scripts/cli_art.py scripts/cli.py scripts/menu.py tests/test_cli_art.py
git commit -m "$(cat <<'EOF'
Add cli_art.display_error/display_success, adopt at existing call sites

Failures now render as a bordered panel instead of a bare icon-prefixed
line; success stays lightweight (no border) since it's the common case.
EOF
)"
```

---

### Task 5: Diagonal-gradient splash with progressive reveal

**Files:**
- Modify: `scripts/cli_art.py` (replace `MAIN_BANNER`/`display_main_banner`, lines 35-60 of the original file)
- Test: `tests/test_cli_art.py` (add classes)

**Interfaces:**
- Consumes: `theme.BRAND`, `theme.BRAND_ACCENT`, `theme.SUCCESS` (Task 1).
- Produces: `cli_art.MAIN_BANNER_LINES: list[str]`,
  `cli_art._lerp_hex(start_hex: str, end_hex: str, t: float) -> str`,
  `cli_art._gradient_grid(lines: list, start_hex: str, end_hex: str) -> list`,
  `cli_art._render_grid(lines: list, grid: list, threshold: int = None) -> Text`,
  `cli_art._reveal_banner(lines: list, grid: list, render_frame) -> None`,
  `cli_art.display_main_banner() -> None` (rewritten).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_art.py -- add these classes

from unittest.mock import patch


class TestLerpHex(unittest.TestCase):

    def test_t_zero_returns_start(self):
        self.assertEqual(cli_art._lerp_hex("#000000", "#ffffff", 0.0), "#000000")

    def test_t_one_returns_end(self):
        self.assertEqual(cli_art._lerp_hex("#000000", "#ffffff", 1.0), "#ffffff")

    def test_t_half_returns_midpoint(self):
        self.assertEqual(cli_art._lerp_hex("#000000", "#ffffff", 0.5), "#7f7f7f")


class TestGradientGrid(unittest.TestCase):

    def test_top_left_is_start_color(self):
        grid = cli_art._gradient_grid(["AB", "CD"], "#000000", "#ffffff")
        self.assertEqual(grid[0][0], "#000000")

    def test_bottom_right_is_end_color(self):
        grid = cli_art._gradient_grid(["AB", "CD"], "#000000", "#ffffff")
        self.assertEqual(grid[-1][-1], "#ffffff")

    def test_handles_empty_lines_without_crashing(self):
        grid = cli_art._gradient_grid(["AB", "", "CD"], "#000000", "#ffffff")
        self.assertEqual(grid[1], [])


class TestRevealBanner(unittest.TestCase):

    def test_non_terminal_prints_once_fully_revealed(self):
        console = cli_art.Console(record=True, width=100, force_terminal=False)
        original = cli_art.console
        cli_art.console = console
        calls = []

        def render_frame(threshold):
            calls.append(threshold)
            return cli_art.Text(f"threshold={threshold}")

        try:
            cli_art._reveal_banner(["AB"], [["#000000", "#111111"]], render_frame)
        finally:
            cli_art.console = original

        self.assertEqual(calls, [None])
        self.assertIn("threshold=None", console.export_text())

    @patch("cli_art.Live")
    def test_terminal_drives_multiple_frames(self, mock_live_cls):
        console = cli_art.Console(record=True, width=100, force_terminal=True)
        original = cli_art.console
        cli_art.console = console
        mock_live = mock_live_cls.return_value.__enter__.return_value

        def render_frame(threshold):
            return cli_art.Text(f"threshold={threshold}")

        try:
            with patch("cli_art.time.sleep"):
                cli_art._reveal_banner(["AB", "CD"], [["#000000", "#111111"], ["#222222", "#ffffff"]], render_frame)
        finally:
            cli_art.console = original

        self.assertGreater(mock_live.update.call_count, 1)


class TestDisplayMainBanner(unittest.TestCase):

    def test_runs_without_error_in_non_terminal_mode(self):
        console = cli_art.Console(record=True, width=100, force_terminal=False)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_main_banner()
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("BUILDER", output.replace("█", "").replace(" ", "").upper() + output)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_cli_art -v`
Expected: FAIL — `AttributeError: module 'cli_art' has no attribute '_lerp_hex'`

- [ ] **Step 3: Implement**

Replace `MAIN_BANNER` and `display_main_banner()` in `scripts/cli_art.py`
with:

```python
# Raw block-letter lines, no markup -- color now comes from the diagonal
# gradient applied per-character in display_main_banner(), not a blanket
# style wrapper.
MAIN_BANNER_LINES = [
    "██████╗ ███████╗███████╗██╗   ██╗███╗   ███╗███████╗",
    "██╔══██╗██╔════╝██╔════╝██║   ██║████╗ ████║██╔════╝",
    "██████╔╝█████╗  ███████╗██║   ██║██╔████╔██║█████╗  ",
    "██╔══██╗██╔══╝  ╚════██║██║   ██║██║╚██╔╝██║██╔══╝  ",
    "██║  ██║███████╗███████║╚██████╔╝██║ ╚═╝ ██║███████╗",
    "╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚══════╝",
    "",
    "██████╗ ██╗   ██╗██╗██╗     ██████╗ ███████╗██████╗ ",
    "██╔══██╗██║   ██║██║██║     ██╔══██╗██╔════╝██╔══██╗",
    "██████╔╝██║   ██║██║██║     ██║  ██║█████╗  ██████╔╝",
    "██╔══██╗██║   ██║██║██║     ██║  ██║██╔══╝  ██╔══██╗",
    "██████╔╝╚██████╔╝██║███████╗██████╔╝███████╗██║  ██║",
    "╚═════╝  ╚═════╝ ╚═╝╚══════╝╚═════╝ ╚══════╝╚═╝  ╚═╝",
]

SUBTITLE = "Tailored resumes & cover letters, powered by Gemini"


def _lerp_hex(start_hex: str, end_hex: str, t: float) -> str:
    """Linearly interpolates between two '#rrggbb' colors at t in [0, 1]."""
    start_rgb = tuple(int(start_hex[i:i + 2], 16) for i in (1, 3, 5))
    end_rgb = tuple(int(end_hex[i:i + 2], 16) for i in (1, 3, 5))
    mixed = tuple(round(start_rgb[c] + (end_rgb[c] - start_rgb[c]) * t) for c in range(3))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def _gradient_grid(lines: list, start_hex: str, end_hex: str) -> list:
    """Returns a per-character color grid (list of list of hex strings,
    parallel to `lines`) -- a diagonal sweep from start_hex (top-left) to
    end_hex (bottom-right), keyed by (row + col) / (max_row + max_col)."""
    max_row = max(len(lines) - 1, 1)
    max_col = max((len(line) for line in lines), default=1)
    max_col = max(max_col - 1, 1)
    denom = max_row + max_col

    grid = []
    for row, line in enumerate(lines):
        grid.append([_lerp_hex(start_hex, end_hex, (row + col) / denom) for col in range(len(line))])
    return grid


def _render_grid(lines: list, grid: list, threshold: int = None) -> Text:
    """Builds one multi-line Rich Text from lines/grid. threshold is the
    max (row + col) diagonal index to reveal; None reveals everything."""
    text = Text()
    for row, line in enumerate(lines):
        for col, ch in enumerate(line):
            if threshold is not None and (row + col) > threshold:
                text.append(" ")
            else:
                text.append(ch, style=grid[row][col])
        text.append("\n")
    return text


def _reveal_banner(lines: list, grid: list, render_frame) -> None:
    """Drives a rich.live.Live diagonal-wipe reveal. render_frame(threshold)
    returns the Rich renderable for a given frame (threshold=None means
    fully revealed). Falls back to a single fully-revealed print when
    stdout isn't a real terminal (piped output, non-interactive contexts,
    tests) -- Live's redraws don't compose safely with non-TTY output."""
    if not console.is_terminal:
        console.print(render_frame(None))
        return

    max_row = max(len(lines) - 1, 1)
    max_col = max((len(line) for line in lines), default=1)
    max_col = max(max_col - 1, 1)
    max_threshold = max_row + max_col

    frame_count = 18
    with Live(console=console, refresh_per_second=30, transient=False) as live:
        for frame in range(frame_count + 1):
            threshold = round(max_threshold * frame / frame_count)
            live.update(render_frame(threshold))
            time.sleep(0.5 / frame_count)


def display_main_banner() -> None:
    grid = _gradient_grid(MAIN_BANNER_LINES, theme.BRAND, theme.BRAND_ACCENT)

    def render_frame(threshold):
        return Panel(
            _render_grid(MAIN_BANNER_LINES, grid, threshold=threshold),
            border_style=theme.SUCCESS, box=box.DOUBLE, padding=(1, 2),
        )

    _reveal_banner(MAIN_BANNER_LINES, grid, render_frame)
    console.print(SUBTITLE, style="dim")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cli_art -v`
Expected: all PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cli_art.py tests/test_cli_art.py
git commit -m "$(cat <<'EOF'
Add diagonal-gradient splash with progressive Live reveal

display_main_banner() now sweeps the block-letter title from brand blue
to brand purple diagonally, revealed over ~18 frames via rich.live.Live.
Falls back to a single fully-revealed print when stdout isn't a real
terminal (piped output, tests) since Live doesn't compose with that.
EOF
)"
```

- [ ] **Step 6: Live verification**

Run: `resume` (bare invocation) in a real terminal
Expected: the banner sweeps in diagonally from blue to purple over well
under a second, with no misalignment or flicker; the subtitle line appears
left-aligned beneath it. Then run `resume | cat` and confirm the banner
appears instantly, fully revealed, with no hang or animation artifacts.

---

### Task 6: Stats line + "did you know?" tip rotation

**Files:**
- Modify: `scripts/cli_art.py` (add after `display_main_banner`)
- Test: `tests/test_cli_art.py` (add classes)

**Interfaces:**
- Consumes: `jd_manager.get_pending_jds()`, `jd_manager.get_completed_jds()`
  (existing, `scripts/jd_manager.py:398,426`); `theme.INFO`, `theme.ICONS`
  (Task 1).
- Produces: `cli_art.display_stats_line() -> None`,
  `cli_art.TIPS: list[str]`, `cli_art.display_tip() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_art.py -- add these classes

from unittest.mock import patch


class TestDisplayStatsLine(unittest.TestCase):

    @patch("cli_art.jd_manager.get_completed_jds", return_value=["a.json", "b.json"])
    @patch("cli_art.jd_manager.get_pending_jds", return_value=["c.json"])
    def test_prints_real_pending_and_tailored_counts(self, mock_pending, mock_completed):
        console = cli_art.Console(record=True, width=100)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_stats_line()
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("1 pending", output)
        self.assertIn("2 tailored all-time", output)


class TestDisplayTip(unittest.TestCase):

    def test_prints_one_of_the_known_tips(self):
        console = cli_art.Console(record=True, width=200)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_tip()
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertTrue(any(tip in output for tip in cli_art.TIPS))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_cli_art -v`
Expected: FAIL — `AttributeError: module 'cli_art' has no attribute 'display_stats_line'`

- [ ] **Step 3: Implement**

Add to `scripts/cli_art.py`, after `display_main_banner()`:

```python
def display_stats_line() -> None:
    """Real, live data -- no new persistence. pending count comes from
    jd_manager.get_pending_jds(); tailored count is jds/completed/'s file
    count (both already create their directory if missing)."""
    pending = len(jd_manager.get_pending_jds())
    tailored = len(jd_manager.get_completed_jds())
    console.print(f"{pending} pending · {tailored} tailored all-time", style=theme.INFO)


TIPS = [
    "resume run --pick lets you interactively choose which pending JDs to tailor, instead of the whole batch.",
    "resume test -v lists every test by name instead of just dots.",
    "New here? The menu's top \"New User? Start Here!\" option bootstraps a bullet bank from your existing resume or LinkedIn export.",
    "resume polish lets you conversationally tweak an already-generated resume or cover letter.",
    "Evaluating a JD persists its score onto the file itself, so \"Customize Resume for a Specific JD\" never re-scores it.",
]


def display_tip() -> None:
    tip = random.choice(TIPS)
    console.print(f"{theme.ICONS['hint']}  Did you know? {tip}", style="dim")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cli_art -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cli_art.py tests/test_cli_art.py
git commit -m "$(cat <<'EOF'
Add live stats line and "did you know?" tip rotation to the splash

Stats are real data (pending/tailored counts), no new persistence. Tips
carry the rotating-personality role, separated from the now purely
informative subtitle.
EOF
)"
```

---

### Task 7: Breadcrumb + restyled "what's next" prompt

**Files:**
- Modify: `scripts/cli_art.py` (add `display_breadcrumb`, rewrite `display_whats_next_panel`)
- Test: `tests/test_cli_art.py` (add class)

**Interfaces:**
- Consumes: `theme.BRAND` (Task 1).
- Produces: `cli_art.display_breadcrumb() -> None`;
  `cli_art.display_whats_next_panel()` (same name, rewritten body — no
  signature change, so `menu.py` needs no edit for this task).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_art.py -- add this class

class TestDisplayBreadcrumb(unittest.TestCase):

    def test_prints_a_one_line_rule_not_a_full_panel(self):
        console = cli_art.Console(record=True, width=100)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.display_breadcrumb()
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("resume-builder", output)
        # A breadcrumb rule is one line of dashes + text -- a full banner
        # box would include multiple '=' or '═' (double-line) rows.
        self.assertNotIn("═", output)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_art -v`
Expected: FAIL — `AttributeError: module 'cli_art' has no attribute 'display_breadcrumb'`

- [ ] **Step 3: Implement**

Add to `scripts/cli_art.py`:

```python
def display_breadcrumb() -> None:
    """Replaces a full banner repaint on menu loop-back -- one line, not
    another full-width panel every time an action finishes."""
    console.rule(f"[bold {theme.BRAND}]›[/bold {theme.BRAND}] resume-builder", style="dim", align="left")
```

Replace `display_whats_next_panel()`'s body (previously a bordered
`Panel`) with a plain styled line, keeping the function name unchanged so
`menu.py`'s existing call site needs no edit:

```python
def display_whats_next_panel() -> None:
    console.print(f"\n[bold {theme.BRAND}]What's next?[/bold {theme.BRAND}]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cli_art -v`
Expected: all PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cli_art.py tests/test_cli_art.py
git commit -m "$(cat <<'EOF'
Add compact breadcrumb, restyle "what's next" as a plain line

One visual-weight class per moment: a one-line rule on menu loop-back
instead of a full banner repaint, and a plain styled question instead
of a bordered panel under an already-lightweight breadcrumb.
EOF
)"
```

---

### Task 8: Session-end summary tally in `menu.py`

**Files:**
- Modify: `scripts/menu.py:199-242` (`_run_with_chain`, `run_interactive_menu`)
- Test: `tests/test_menu.py:258-314` (`TestRunWithChain` — update existing calls), new `TestSessionSummary` class

**Interfaces:**
- Consumes: `cli_art.display_breadcrumb`, `cli_art.display_stats_line`,
  `cli_art.display_tip`, `cli_art.SUCCESS` (Tasks 6-7).
- Produces: `menu._run_with_chain(value: str, session_stats: dict) -> None`
  (signature change — was `(value: str) -> None`);
  `menu._session_summary(session_stats: dict) -> str`;
  `menu._SESSION_LABELS: dict[str, str]`.

- [ ] **Step 1: Update `TestRunWithChain`'s existing calls and add summary tests**

Every existing call to `menu._run_with_chain("fake")` in
`tests/test_menu.py`'s `TestRunWithChain` class (6 call sites, currently
single-argument) needs a second `{}` (or a populated dict where the test
checks tallying) argument. Replace the entire `TestRunWithChain` class
(lines 258-314) with:

```python
class TestRunWithChain(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_no_op_handler_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: False}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_handler_with_no_chain_entry_skips_the_prompt(self, mock_select):
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False):
            menu._run_with_chain("fake", {})
        mock_select.assert_not_called()

    @patch("menu.questionary.select")
    def test_chain_prompt_appends_back_to_menu_choice(self, mock_select):
        mock_select.return_value.ask.return_value = "__back__"
        with patch.dict(menu._HANDLERS, {"fake": lambda: True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual([c.title for c in choices], ["Next", "Back to Menu"])
        self.assertEqual([c.value for c in choices], ["somewhere", "__back__"])

    @patch("menu.questionary.select")
    def test_back_to_menu_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = "__back__"
        with patch.dict(menu._HANDLERS, {"fake": lambda: calls.append("fake") or True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
        self.assertEqual(calls, ["fake"])

    @patch("menu.questionary.select")
    def test_cancelled_prompt_stops_recursion(self, mock_select):
        calls = []
        mock_select.return_value.ask.return_value = None
        with patch.dict(menu._HANDLERS, {"fake": lambda: calls.append("fake") or True}, clear=False), \
             patch.dict(menu._CHAIN, {"fake": [("Next", "somewhere")]}, clear=False):
            menu._run_with_chain("fake", {})
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
            menu._run_with_chain("first", {})
        self.assertEqual(calls, ["first", "second"])


class TestSessionSummary(unittest.TestCase):

    @patch("menu.questionary.select")
    def test_successful_action_increments_its_labeled_count(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"tailor_all": lambda: True}, clear=False), \
             patch.dict(menu._CHAIN, {}, clear=True):
            menu._run_with_chain("tailor_all", session_stats)
        self.assertEqual(session_stats, {"resumes tailored": 1})

    @patch("menu.questionary.select")
    def test_no_op_action_does_not_increment(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"tailor_all": lambda: False}, clear=False):
            menu._run_with_chain("tailor_all", session_stats)
        self.assertEqual(session_stats, {})

    @patch("menu.questionary.select")
    def test_unlabeled_action_does_not_increment(self, mock_select):
        session_stats = {}
        with patch.dict(menu._HANDLERS, {"polish": lambda: True}, clear=False):
            menu._run_with_chain("polish", session_stats)
        self.assertEqual(session_stats, {})

    def test_empty_summary_string(self):
        self.assertEqual(menu._session_summary({}), "No actions taken this session.")

    def test_summary_joins_multiple_labels(self):
        summary = menu._session_summary({"resumes tailored": 3, "cover letters written": 2})
        self.assertIn("3 resumes tailored", summary)
        self.assertIn("2 cover letters written", summary)
        self.assertIn("Nice work.", summary)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_menu -v`
Expected: FAIL — `TypeError: _run_with_chain() takes 1 positional argument but 2 were given`

- [ ] **Step 3: Implement**

Replace `scripts/menu.py` lines 199-242 (`_CHAIN` dict through
`run_interactive_menu`) with:

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

# Labels for the session-end summary -- only actions worth reporting on
# exit get an entry; anything absent here (e.g. "polish", "scan",
# "liveness") just isn't tallied.
_SESSION_LABELS = {
    "tailor_all": "resumes tailored",
    "tailor_one": "resumes tailored",
    "coverletter_one": "cover letters written",
}


def _run_with_chain(value: str, session_stats: dict) -> None:
    did_something = _HANDLERS[value]()
    if did_something:
        label = _SESSION_LABELS.get(value)
        if label:
            session_stats[label] = session_stats.get(label, 0) + 1

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
    _run_with_chain(choice, session_stats)


def _session_summary(session_stats: dict) -> str:
    if not session_stats:
        return "No actions taken this session."
    parts = [f"{count} {label}" for label, count in session_stats.items()]
    return f"{cli_art.SUCCESS} " + " · ".join(parts) + " · Nice work."


def run_interactive_menu() -> None:
    cli_art.display_main_banner()
    cli_art.display_stats_line()
    cli_art.display_tip()

    session_stats = {}
    first_loop = True

    while True:
        if first_loop:
            first_loop = False
        else:
            cli_art.display_breadcrumb()
        cli_art.console.print()
        choice = questionary.select(
            "What would you like to do?", choices=_CHOICES, style=cli_art.QUESTIONARY_STYLE,
        ).ask()

        if choice == "exit" or not choice:
            cli_art.console.print(f"\n{_session_summary(session_stats)}\n")
            break

        _run_with_chain(choice, session_stats)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_menu -v`
Expected: all PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "$(cat <<'EOF'
Add session-end summary tally; breadcrumb replaces full-banner loop-back

_run_with_chain gains an additive session_stats parameter (routing logic
unchanged) to tally tailor/cover-letter actions for a one-line exit
summary. run_interactive_menu shows the splash/stats/tip once, then a
compact breadcrumb on every return to the main menu instead of repainting
the full banner.
EOF
)"
```

---

### Task 9: Menu grouping — labeled separators + category icons

**Files:**
- Modify: `scripts/menu.py:32-45` (`_CHOICES`)
- Test: `tests/test_menu.py:14-30` (`TestChoicesAndHandlers` — relax label assertions)

**Interfaces:**
- Consumes: `theme.ICONS` (Task 1).
- Produces: `menu._CHOICES` (same list of values/handlers — only `title`
  strings and `Separator` entries change).

- [ ] **Step 1: Relax the label assertions to tolerate an icon prefix**

Replace `tests/test_menu.py`'s `test_choices_have_the_renamed_labels`
(lines 21-30) — exact-match `assertEqual` would break once titles gain an
icon prefix; switch to `assertIn` so the test still pins the meaningful
text without coupling to the exact glyph (which differs between the
Nerd Font default and the Unicode fallback):

```python
    def test_choices_have_the_renamed_labels(self):
        labels = {c.value: c.title for c in menu._CHOICES}
        self.assertIn("Scan for New Postings", labels["scan"])
        self.assertIn("Check Posting Liveness", labels["liveness"])
        self.assertIn("Evaluate ALL Pending JDs", labels["evaluate_all"])
        self.assertIn("Evaluate a Specific JD", labels["evaluate_one"])
        self.assertIn("Customize Resume for ALL Pending JDs (batch)", labels["tailor_all"])
        self.assertIn("Customize Resume for a Specific JD", labels["tailor_one"])
        self.assertIn("Write cover letter for a Specific JD", labels["coverletter_one"])
        self.assertIn("Polish a resume or cover letter", labels["polish"])

    def test_choices_are_grouped_with_labeled_separators(self):
        separator_lines = [c.line for c in menu._CHOICES if isinstance(c, questionary.Separator)]
        self.assertTrue(any("Discovery" in line for line in separator_lines))
        self.assertTrue(any("Evaluation" in line for line in separator_lines))
        self.assertTrue(any("Build" in line for line in separator_lines))
```

(`test_pick_from_list_entries_are_gone`, lines 14-19, needs no change —
it only checks `.value`, not `.title`.)

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `python -m unittest tests.test_menu -v`
Expected: `test_choices_are_grouped_with_labeled_separators` FAILS (no
grouped separators exist yet)

- [ ] **Step 3: Implement**

Replace `scripts/menu.py` lines 32-45 (`_CHOICES`) with:

```python
_CHOICES = [
    questionary.Choice(title=[("class:new_user", "--> New User? Start Here!")], value="bootstrap"),
    questionary.Separator("── Discovery ──"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Scan for New Postings", value="scan"),
    questionary.Choice(title=f"{theme.ICONS['discovery']}  Check Posting Liveness", value="liveness"),
    questionary.Separator("── Evaluation ──"),
    questionary.Choice(title=f"{theme.ICONS['evaluate']}  Evaluate ALL Pending JDs", value="evaluate_all"),
    questionary.Choice(title=f"{theme.ICONS['evaluate']}  Evaluate a Specific JD", value="evaluate_one"),
    questionary.Separator("── Build ──"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Customize Resume for ALL Pending JDs (batch)", value="tailor_all"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Customize Resume for a Specific JD", value="tailor_one"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Write cover letter for a Specific JD", value="coverletter_one"),
    questionary.Choice(title=f"{theme.ICONS['build']}  Polish a resume or cover letter", value="polish"),
    questionary.Separator("── Utility ──"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  View Application Tracker", value="view_applications"),
    questionary.Choice(title=f"{theme.ICONS['utility']}  Exit", value="exit"),
]
```

Add `import theme` near the top of `scripts/menu.py` (alongside the
existing `import cli_art` line).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_menu -v`
Expected: all PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/menu.py tests/test_menu.py
git commit -m "$(cat <<'EOF'
Group main menu with labeled separators and category icons

Discovery/Evaluation/Build/Utility groups replace the single flat list
+ one bare separator, each item prefixed with its category's theme icon.
EOF
)"
```

- [ ] **Step 6: Live verification**

Run: `resume` in a real terminal, confirm the menu shows four labeled
groups with a distinct icon per category, and that the icons render as
real glyphs (not tofu boxes) given the Nerd Font active in this terminal.

---

### Task 10: Progress motion for `evaluate_fit`'s three real call sites

**Files:**
- Modify: `scripts/batch_evaluate.py:1-17,63-68` (add `cli_art` import, wrap the call)
- Modify: `scripts/menu.py:123-136` (`_handle_evaluate_one`)
- Modify: `scripts/cli.py:141-147` (`evaluate` command's single-JD branch)
- Test: `tests/test_menu.py` (existing `TestHandleEvaluateOne` already
  mocks `menu.orchestrator.ResumeEngine`, so no change needed there — see
  Step 1)

**Interfaces:**
- Consumes: `cli_art.console.status` (Rich's existing `Console.status()`
  context manager — no new `cli_art` function needed for this task).

- [ ] **Step 1: Confirm existing tests already tolerate this change**

`tests/test_menu.py`'s `TestHandleEvaluateOne` mocks
`menu.orchestrator.ResumeEngine` entirely (the whole class, not just
`evaluate_fit`), so wrapping the call in a `with` block inside
`_handle_evaluate_one` doesn't change what's observable to those tests.
Run the baseline first to confirm:

Run: `python -m unittest tests.test_menu -v`
Expected: all PASS (baseline, before this task's change)

- [ ] **Step 2: N/A — no new failing test**

This task wraps an existing call in a spinner context manager; the
behavior change (spinner text appears during the call) isn't meaningfully
assertable without capturing terminal control codes, which none of this
project's existing tests do (see `test_cli_art_bootstrap.py`'s convention
of only testing *content*, never animation/spinner frames). Proceed
directly to implementation, then confirm the full suite still passes in
Step 4.

- [ ] **Step 3: Implement**

In `scripts/batch_evaluate.py`, add `import cli_art` to the imports (after
`import jd_manager`), then replace line 68
(`evaluation = engine.evaluate_fit(path)`) with:

```python
        with cli_art.console.status(f"Weighing the fit for {company_name or os.path.basename(path)}...", spinner="dots"):
            evaluation = engine.evaluate_fit(path)
```

In `scripts/menu.py`'s `_handle_evaluate_one()` (line 127-128), replace:

```python
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
```

with:

```python
    engine = orchestrator.ResumeEngine()
    with cli_art.console.status("Weighing the fit...", spinner="dots"):
        result = engine.evaluate_fit(path)
```

In `scripts/cli.py`'s `evaluate` command (line 142-143), replace:

```python
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(jd_file)
```

with:

```python
    engine = orchestrator.ResumeEngine()
    with cli_art.console.status("Weighing the fit...", spinner="dots"):
        result = engine.evaluate_fit(jd_file)
```

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/batch_evaluate.py scripts/menu.py scripts/cli.py
git commit -m "$(cat <<'EOF'
Add a spinner around evaluate_fit()'s three call sites

evaluate_fit() is the one pipeline call that's genuinely silent for its
whole duration on the success path (verified against the code -- the
other pipeline entry points already print their own step-by-step
progress, so they're deliberately left alone; wrapping them in a
competing Live spinner would corrupt output that already works).
EOF
)"
```

- [ ] **Step 6: Live verification**

Run `resume evaluate jds/<some_pending_file>` (or the menu's "Evaluate a
Specific JD") against a real pending JD and confirm a spinner with
"Weighing the fit..." text appears and animates for the duration of the
Gemini call, then clears cleanly once the result prints.

---

### Task 11: Fit table polish — bordered panel + color-key legend

**Files:**
- Modify: `scripts/cli_art.py` (`render_fit_table`, originally lines 98-123)
- Test: `tests/test_cli_art.py` (add class)

**Interfaces:**
- Consumes: `theme.ERROR`, `theme.RECOMMENDATION_COLORS` (Task 1, already
  used by `_RECOMMENDATION_COLORS` via Task 2).
- Produces: `cli_art.render_fit_table(results: list) -> None` (same
  signature — visual output only changes).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_art.py -- add this class

class TestRenderFitTable(unittest.TestCase):

    def test_shows_count_title_and_recommendation_legend(self):
        results = [
            {"error": False, "composite_score": 4.5, "recommendation": "Strong pursue",
             "company_name": "Acme", "job_title": "Writer"},
            {"error": True, "composite_score": None, "recommendation": None,
             "company_name": "Bad Co", "job_title": "Unknown"},
        ]
        console = cli_art.Console(record=True, width=120)
        original = cli_art.console
        cli_art.console = console
        try:
            cli_art.render_fit_table(results)
        finally:
            cli_art.console = original
        output = console.export_text()
        self.assertIn("2 JD(s) evaluated", output)
        self.assertIn("Strong pursue", output)
        self.assertIn("ERROR", output)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli_art -v`
Expected: FAIL — `AssertionError: '2 JD(s) evaluated' not found in output`

- [ ] **Step 3: Implement**

Replace `render_fit_table` in `scripts/cli_art.py` with:

```python
def render_fit_table(results: list) -> None:
    """Renders batch_evaluate.evaluate_all_pending()'s result list as a
    Rich Table, colored by recommendation tier (modeled on job_automater's
    display_job_table(), cli.py:73-142). results is expected pre-sorted
    (evaluate_all_pending() already sorts best-first, errors-last)."""
    table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style="bold magenta")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Score", justify="right")
    table.add_column("Recommendation")
    table.add_column("Company")
    table.add_column("Title")

    for i, r in enumerate(results, 1):
        if r["error"]:
            table.add_row(str(i), f"[{theme.ERROR}]ERROR[/{theme.ERROR}]", "-", r["company_name"], r["job_title"])
            continue
        color = _RECOMMENDATION_COLORS.get(r["recommendation"], "white")
        table.add_row(
            str(i),
            f"[{color}]{r['composite_score']:.2f}/5[/{color}]",
            f"[{color}]{r['recommendation']}[/{color}]",
            r["company_name"],
            r["job_title"],
        )

    legend = "  ".join(f"[{color}]■[/{color}] {tier}" for tier, color in _RECOMMENDATION_COLORS.items())
    console.print(Panel(
        table, title=f"{len(results)} JD(s) evaluated", subtitle=legend,
        border_style=theme.BRAND, box=box.ROUNDED,
    ))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cli_art -v`
Expected: all PASS

Then: `python -m unittest discover -s tests`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/cli_art.py tests/test_cli_art.py
git commit -m "$(cat <<'EOF'
Polish the fit table: bordered panel + recommendation color-key legend

render_fit_table's box=None table gains real framing and a title showing
the result count; a compact legend maps each color to its recommendation
tier. Also fixes the one remaining named-color holdout ("red" on error
rows), now theme.ERROR.
EOF
)"
```

---

### Task 12: Documentation — Nerd Font setup note + README updates

**Files:**
- Modify: `CLAUDE.md` (Setup section)
- Modify: `README.md` (Setup section, "Colors" paragraph, "Interactive menu" section)

**Interfaces:** None (documentation only).

- [ ] **Step 1: N/A — documentation task, no test**

- [ ] **Step 2: N/A**

- [ ] **Step 3: Update `CLAUDE.md`'s Setup section**

Add one bullet to the `## Setup` section, after the existing "Bare
`python3`..." bullet:

```markdown
- The interactive menu's icons default to Nerd Font glyphs — if your
  terminal doesn't have one active, set `RESUME_BUILDER_ICONS=unicode` in
  your shell profile (or before invoking `resume`) to fall back to plain
  Unicode symbols. See README's "Colors" section for how to enable a
  Nerd Font instead.
```

- [ ] **Step 4: Update `README.md`**

In the `## Setup` numbered list (after item 5, the JobRight/LinkedIn
cookie note), add:

```markdown
6. Optional, for the best icon experience: enable a [Nerd Font](https://www.nerdfonts.com/)
   in your terminal profile (iTerm2: Preferences → Profiles → Text → Font;
   Terminal.app: Preferences → Profiles → Text → Font). The menu's icons
   default to Nerd Font glyphs; without one active they'll render as
   blank boxes in that terminal window. No Nerd Font handy? Set
   `RESUME_BUILDER_ICONS=unicode` to use plain Unicode symbols instead —
   works everywhere, no special font required.
```

Replace the `**Colors:**` paragraph (lines 137-143) with:

```markdown
**Colors & icons:** every color and icon in the interactive menu is
sourced from one place, `scripts/theme.py` — explicit hex colors (blue
`#4dabf7`, purple `#673ab7`, green `#4caf50`, etc.) rather than named ANSI
colors like `cyan`, since named colors get remapped by whatever terminal
theme is active (on a dark-teal theme, `cyan` used to render as a washed-
out, nearly invisible gray). Icons default to Nerd Font glyphs (see
Setup above); set `RESUME_BUILDER_ICONS=unicode` to use plain Unicode
symbols instead if you haven't enabled one.
```

In the `## Interactive menu` section, after the first paragraph (ending
"...named after the pipeline stage they support:"), add a short paragraph
describing the launch/session experience:

```markdown
On launch, the title banner sweeps in with a diagonal blue-to-purple
gradient, followed by a live stats line (how many JDs are pending, how
many have been tailored all-time) and a rotating "did you know?" tip.
Returning to this menu after an action shows a compact one-line breadcrumb
instead of repainting the full banner. Choosing Exit prints a one-line
summary of what you actually did that session (e.g. "3 resumes tailored ·
2 cover letters written").
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "$(cat <<'EOF'
Document Nerd Font setup, theme.py, and the new launch/session experience

Setup notes for enabling a Nerd Font (or falling back to
RESUME_BUILDER_ICONS=unicode), and README updates describing the
gradient splash, stats line, tip rotation, breadcrumb, and session
summary.
EOF
)"
```

## Final Verification

- [ ] Run the full suite one more time: `python -m unittest discover -s tests -v`
  Expected: all tests PASS.
- [ ] Run `resume` bare in a real terminal and walk through: splash reveal
  → stats/tip lines → grouped menu with icons → pick one no-op-safe action
  (e.g. "Check Posting Liveness" with nothing pending) → confirm breadcrumb
  appears on return → Exit → confirm the session summary line reflects
  what was actually done (or "No actions taken this session." if nothing
  did).
- [ ] Run `resume | cat` and confirm no hang, no animation artifacts, no
  corrupted output — the splash prints once, fully revealed.
