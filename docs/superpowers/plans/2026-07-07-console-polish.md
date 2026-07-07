# Console Output Polish & Color System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the three biggest sources of console noise (repeated PDF blocks in the trim loop, raw JSON keyword dumps, no visual separation between Step headers and their sub-output) and fix the interactive menu's banner from being invisible against Morgan's actual terminal by moving off theme-dependent named colors onto explicit hex colors, matching a scheme confirmed by direct visual comparison.

**Architecture:** Two small, independently-testable pure functions extracted into `orchestrator.py` (`_parse_pdf_result`, `_summarize_keywords`) replace inline regex/JSON-dump logic at their call sites; a plain-text divider already used by the bullet-audit loop gets extended to 8 more call sites; `cli_art.py` gains one new bordered-panel function and an existing one changes color; `menu.py` gets a one-line wiring change to use it.

**Tech Stack:** Python 3.10+, `rich` (Panel/box, already a dependency), `unittest` (stdlib, project's only test framework).

## Global Constraints

- Python 3.10+ syntax (`str | None`, etc.) — matches the rest of `scripts/`.
- No new `cli_art`/Rich dependency inside `orchestrator.py` — Step header dividers stay plain-text, matching the bullet-audit loop's existing `print(f"\n{'─'*60}")` convention exactly, not colorized.
- Color palette is fixed by the approved design: blue `#4dabf7` (banner text), green `#4caf50` (panel borders — already the hex behind `QUESTIONARY_STYLE`'s `selected` and the existing `✓` success symbol), purple `#673ab7` unchanged (questionary's existing pointer/qmark). No other named-color usage in `cli_art.py` (`SUCCESS`/`ERROR`/`WARNING`, `display_banner`, `render_fit_table`) changes.
- No bordered panel around the main recurring "What would you like to do?" menu prompt — only the once-per-launch banner and the after-action "What's next?" chain prompt get panels.
- The "Warming segment cache" per-(company, tag) listing is explicitly out of scope — leave untouched.
- Tests: stdlib `unittest`, `tests/test_*.py` naming (auto-discovered), `sys.path.insert(0, SCRIPTS_DIR)` + plain `import <module>`.
- Run the suite with `python -m unittest discover -s tests -v` from the project root with `.venv/` activated (or `resume test -v`).

---

### Task 1: `_parse_pdf_result()` + trim loop PDF-block collapse

**Files:**
- Modify: `scripts/orchestrator.py`
- Test: `tests/test_orchestrator_console_output.py` (new)

**Interfaces:**
- Produces: `_parse_pdf_result(stdout: str) -> tuple` (returns `(page_count: int | None, size_str: str)`). Used only within `build_tailored_resume()`'s Step 7 trim loop — no other task depends on it.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_orchestrator_console_output.py`:

```python
import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402


class TestParsePdfResult(unittest.TestCase):

    def test_extracts_page_count_and_size(self):
        stdout = (
            "📄 Input:  /x/y.html\n"
            "📁 Output: /x/y.pdf\n"
            "📏 Format: LETTER\n"
            "✅ PDF generated: /x/y.pdf\n"
            "📊 Pages: 3\n"
            "📦 Size: 69.2 KB\n"
        )
        page_count, size_str = orchestrator._parse_pdf_result(stdout)
        self.assertEqual(page_count, 3)
        self.assertEqual(size_str, "69.2 KB")

    def test_missing_pages_line_returns_none(self):
        page_count, size_str = orchestrator._parse_pdf_result("no pages line here\n📦 Size: 10.0 KB")
        self.assertIsNone(page_count)
        self.assertEqual(size_str, "10.0 KB")

    def test_missing_size_line_returns_unknown_size(self):
        page_count, size_str = orchestrator._parse_pdf_result("📊 Pages: 2\nno size line here")
        self.assertEqual(page_count, 2)
        self.assertEqual(size_str, "unknown size")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_orchestrator_console_output -v`
Expected: FAIL — `AttributeError: module 'orchestrator' has no attribute '_parse_pdf_result'`.

- [ ] **Step 3: Add `_parse_pdf_result()` to `scripts/orchestrator.py`**

Add it right after `_widow_trim_instruction()` (the most recently defined module-level helper):

```python
def _parse_pdf_result(stdout: str) -> tuple:
    """Extracts (page_count, size_str) from generate-pdf.mjs's stdout --
    page_count is None and size_str is "unknown size" if either line
    isn't found."""
    page_count_match = re.search(r"Pages:\s*(\d+)", stdout)
    page_count = int(page_count_match.group(1)) if page_count_match else None
    size_match = re.search(r"Size:\s*([\d.]+\s*\w+)", stdout)
    size_str = size_match.group(1) if size_match else "unknown size"
    return page_count, size_str
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_orchestrator_console_output -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire it into the Step 7 trim loop**

Find this exact block inside `build_tailored_resume()`:

```python
        while True:
            pdf_result = subprocess.run(
                ["node", pdf_script, html_out, pdf_out, "--format=letter"],
                capture_output=True, text=True
            )
            if pdf_result.returncode != 0:
                print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
                return {}

            print(pdf_result.stdout)
            page_count_match = re.search(r"Pages:\s*(\d+)", pdf_result.stdout)
            page_count = int(page_count_match.group(1)) if page_count_match else None

            if page_count is None or page_count <= 2 or trim_attempt >= max_trim_attempts:
                break

            if not dropped_optional_clients:
                dropped_optional_clients = True
                has_optional_clients = any(
                    fixed_content.CLIENTS.get(job.get("company"), {}).get("essential") is False
                    and job.get("clients")
                    for job in resume_data.get("EXPERIENCE", [])
                )
                if has_optional_clients:
                    # Free, non-LLM trim step: drop the Inside Sales Team
                    # client roster (fixed_content.CLIENTS marks it
                    # non-essential) before spending an LLM-driven
                    # trim_instructions attempt.
                    print(f"  PDF is {page_count} pages, dropping optional client rosters...")
                    resume_data = normalize_resume.normalize(resume_data, include_optional_clients=False)
                    render_html(resume_data, html_out)
                    continue

            print(f"  PDF is {page_count} pages, applying trim step {trim_attempt + 1}/{max_trim_attempts}...")
```

Replace with:

```python
        while True:
            pdf_result = subprocess.run(
                ["node", pdf_script, html_out, pdf_out, "--format=letter"],
                capture_output=True, text=True
            )
            if pdf_result.returncode != 0:
                print(f"  ⚠️  PDF generation failed:\n{pdf_result.stderr}")
                return {}

            page_count, size_str = _parse_pdf_result(pdf_result.stdout)
            is_final = page_count is None or page_count <= 2 or trim_attempt >= max_trim_attempts
            if is_final:
                print(pdf_result.stdout)
                break

            if not dropped_optional_clients:
                dropped_optional_clients = True
                has_optional_clients = any(
                    fixed_content.CLIENTS.get(job.get("company"), {}).get("essential") is False
                    and job.get("clients")
                    for job in resume_data.get("EXPERIENCE", [])
                )
                if has_optional_clients:
                    # Free, non-LLM trim step: drop the Inside Sales Team
                    # client roster (fixed_content.CLIENTS marks it
                    # non-essential) before spending an LLM-driven
                    # trim_instructions attempt.
                    print(f"  PDF is {page_count} pages ({size_str}), dropping optional client rosters...")
                    resume_data = normalize_resume.normalize(resume_data, include_optional_clients=False)
                    render_html(resume_data, html_out)
                    continue

            print(f"  PDF is {page_count} pages ({size_str}), applying trim step {trim_attempt + 1}/{max_trim_attempts}...")
```

- [ ] **Step 6: Run the existing trim-loop tests to confirm the behavior change is purely cosmetic**

Run: `python -m unittest tests.test_orchestrator_build_checkpoint -v`
Expected: PASS (all tests, including
`test_trim_loop_survives_one_unparseable_attempt_and_still_succeeds`,
`test_page_count_trim_loop_retries_then_succeeds`,
`test_page_count_trim_loop_exhausts_and_returns_empty`,
`test_trim_loop_after_checkpoint_resumed_resume_data_does_not_raise` —
these assert on `resume_data`/return values, not console text, so passing
unchanged confirms this was a display-only change).

- [ ] **Step 7: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test).

- [ ] **Step 8: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_console_output.py
git commit -m "feat: collapse trim loop's repeated PDF block to one line per intermediate attempt"
```

---

### Task 2: `_summarize_keywords()` + Step 1 wiring

**Files:**
- Modify: `scripts/orchestrator.py`
- Test: `tests/test_orchestrator_console_output.py`

**Interfaces:**
- Produces: `_summarize_keywords(jd_keywords: dict) -> str`. Used only at Step 1's keyword-extraction print site.

- [ ] **Step 1: Write the failing tests**

In `tests/test_orchestrator_console_output.py`, find the trailing block
Task 1 left at the end of the file:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with the new test class plus the same trailing block moved
after it (so there's still exactly one `if __name__` block, now at the
true end of the file):

```python
class TestSummarizeKeywords(unittest.TestCase):

    def test_summarizes_three_categories(self):
        result = orchestrator._summarize_keywords({
            "tools": ["LinkedIn", "Figma", "Adobe Creative Cloud"],
            "hard_skills": ["A", "B", "C", "D", "E", "F", "G", "H"],
            "core_functions": ["X", "Y", "Z"],
        })
        self.assertEqual(result, "3 tools, 8 hard skills, 3 core functions")

    def test_omits_empty_categories(self):
        result = orchestrator._summarize_keywords({
            "tools": ["LinkedIn"],
            "hard_skills": [],
            "core_functions": ["X"],
        })
        self.assertEqual(result, "1 tools, 1 core functions")

    def test_all_empty_returns_none_found(self):
        result = orchestrator._summarize_keywords({"tools": [], "hard_skills": [], "core_functions": []})
        self.assertEqual(result, "none found")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_orchestrator_console_output -v`
Expected: FAIL — `AttributeError: module 'orchestrator' has no attribute '_summarize_keywords'`.

- [ ] **Step 3: Add `_summarize_keywords()` to `scripts/orchestrator.py`**

Add it right after `_parse_pdf_result()` (Task 1):

```python
def _summarize_keywords(jd_keywords: dict) -> str:
    """One-line count summary of a JDKeywordSchema-shaped dict (tools,
    hard_skills, core_functions today, but iterates generically over
    whatever keys are present). Full values remain in the checkpoint JSON
    for anyone who needs them."""
    parts = [f"{len(v)} {k.replace('_', ' ')}" for k, v in jd_keywords.items() if v]
    return ", ".join(parts) if parts else "none found"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_orchestrator_console_output -v`
Expected: PASS (6 tests total: 3 from Task 1 + 3 new).

- [ ] **Step 5: Wire it into Step 1**

Find:

```python
        print(f"  Keywords extracted: {json.dumps(jd_keywords, indent=2)[:400]}")
```

Replace with:

```python
        print(f"  Keywords extracted: {_summarize_keywords(jd_keywords)}")
```

- [ ] **Step 6: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test).

- [ ] **Step 7: Commit**

```bash
git add scripts/orchestrator.py tests/test_orchestrator_console_output.py
git commit -m "feat: replace keyword-extraction JSON dump with a one-line summary"
```

---

### Task 3: Step header dividers

**Files:**
- Modify: `scripts/orchestrator.py`

**Interfaces:** None — pure cosmetic print-statement changes, no new functions.

This task has no test-first cycle (matches the spec's Testing section: no
dedicated tests for cosmetic print output) — apply all 8 edits, then
verify via the full suite (confirms nothing else broke) and live
verification (Task 5).

- [ ] **Step 1: Add the divider before each of the 8 Step header print sites**

Each edit follows the same pattern: prepend `print(f"\n{'─'*60}")` (the
exact convention already used at `orchestrator.py:1311` in the
bullet-audit loop) and drop the leading `\n` from the existing header
string, so there's exactly one blank line of separation, matching the
bullet loop's own spacing.

Find:
```python
        print("\nStep 1: Extracting JD keywords...")
```
Replace with:
```python
        print(f"\n{'─'*60}")
        print("Step 1: Extracting JD keywords...")
```

Find:
```python
        print("\nStep 2: Mining bullet bank...")
```
Replace with:
```python
        print(f"\n{'─'*60}")
        print("Step 2: Mining bullet bank...")
```

Find:
```python
        print("\nStep 3: Auditing bullets...")
```
Replace with:
```python
        print(f"\n{'─'*60}")
        print("Step 3: Auditing bullets...")
```

Find:
```python
        print("\nStep 4: Building resume...")
```
Replace with:
```python
        print(f"\n{'─'*60}")
        print("Step 4: Building resume...")
```

Find:
```python
        print("\nStep 5: Running holistic resume critique...")
```
Replace with:
```python
        print(f"\n{'─'*60}")
        print("Step 5: Running holistic resume critique...")
```

Find:
```python
                print("\nStep 5.5: Resuming: recommendation pass already complete from checkpoint.")
```
Replace with:
```python
                print(f"\n{'─'*60}")
                print("Step 5.5: Resuming: recommendation pass already complete from checkpoint.")
```

Find:
```python
                print(f"\nStep 5.5: Applying actionable recommendations one at a time "
                      f"({start_index}/{len(recs)} already done)...")
```
Replace with:
```python
                print(f"\n{'─'*60}")
                print(f"Step 5.5: Applying actionable recommendations one at a time "
                      f"({start_index}/{len(recs)} already done)...")
```

Find:
```python
        print("\nStep 7: Rendering HTML and generating PDF...")
```
Replace with:
```python
        print(f"\n{'─'*60}")
        print("Step 7: Rendering HTML and generating PDF...")
```

- [ ] **Step 2: Run the full suite to confirm nothing broke**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test — none of these test files assert on exact
console text at these print sites).

- [ ] **Step 3: Commit**

```bash
git add scripts/orchestrator.py
git commit -m "feat: add divider convention to top-level Step headers"
```

---

### Task 4: Blue/green color system — banner panel, chain-prompt panel

**Files:**
- Modify: `scripts/cli_art.py`
- Modify: `scripts/menu.py`

**Interfaces:**
- Produces: `cli_art.display_whats_next_panel() -> None` (new). `cli_art.display_main_banner()`'s visible output changes (bordered, blue text) but its signature is unchanged.
- Consumes (in `menu.py`): `cli_art.display_whats_next_panel`.

No test-first cycle for this task (matches the spec's Testing section:
no dedicated tests for banners/panels, same convention as the existing
`display_banner`/`render_fit_table`) — implement, verify by rendering
directly, then confirm the existing test suite (which doesn't assert on
this console output) still passes.

- [ ] **Step 1: Add the `box` import to `scripts/cli_art.py`**

Find:
```python
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
```
Replace with:
```python
from questionary import Style
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
```

- [ ] **Step 2: Change `MAIN_BANNER`'s color and wrap `display_main_banner()` in a panel**

Find:
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

Replace with:
```python
MAIN_BANNER = """
[bold #4dabf7]
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
[/bold #4dabf7]
[dim]          Tailored resumes & cover letters, powered by Gemini[/dim]
"""


def display_main_banner() -> None:
    console.print(Panel(MAIN_BANNER, border_style="#4caf50", box=box.DOUBLE, padding=(1, 2)))


def display_whats_next_panel() -> None:
    console.print(Panel("What's next?", border_style="#4caf50", box=box.ROUNDED, padding=(0, 2)))
```

- [ ] **Step 3: Verify both render cleanly**

Run:
```bash
source .venv/bin/activate && python3 -c "
import sys; sys.path.insert(0, 'scripts')
import cli_art
cli_art.display_main_banner()
cli_art.display_whats_next_panel()
"
```
Expected: the "RESUME"/"BUILDER" block art prints in blue inside a
double-lined green-bordered box with the dim tagline beneath it, followed
by a smaller rounded green-bordered box containing "What's next?" — no
Rich markup errors, no misaligned/wrapped lines.

- [ ] **Step 4: Wire the new panel into `menu.py`'s chain prompt**

Find:
```python
    choices = [questionary.Choice(title=label, value=v) for label, v in next_options]
    choices.append(questionary.Choice(title="Back to Menu", value="__back__"))
    choice = questionary.select(
        "What's next?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```
Replace with:
```python
    choices = [questionary.Choice(title=label, value=v) for label, v in next_options]
    choices.append(questionary.Choice(title="Back to Menu", value="__back__"))
    cli_art.display_whats_next_panel()
    choice = questionary.select(
        "Choose one:", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

- [ ] **Step 5: Run the menu test suite to confirm nothing broke**

Run: `python -m unittest tests.test_menu -v`
Expected: PASS (all tests — none assert on the literal "What's next?"
prompt-text argument, only on the `choices` kwarg, so this text change is
safe).

- [ ] **Step 6: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test).

- [ ] **Step 7: Commit**

```bash
git add scripts/cli_art.py scripts/menu.py
git commit -m "feat: fix banner color for theme-dependent terminals, add bordered panels to banner and chain prompt"
```

---

### Task 5: Full-suite confirmation + live verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite one more time**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test, all four prior tasks combined).

- [ ] **Step 2: Live-verify the banner and chain prompt**

Run `resume` (bare invocation). Confirm:
1. The title banner renders in blue block-letter text inside a
   double-lined green-bordered panel, clearly legible against your actual
   terminal background (not blending into it the way the old plain cyan
   text did).
2. Pick any action that does something (e.g. Scan, or Customize Resume
   for a Specific JD), and confirm the "What's next?" panel appears
   (rounded, green border) immediately before the follow-up choice list.
3. The main "What would you like to do?" prompt itself stays unboxed,
   exactly as before.

- [ ] **Step 3: Live-verify the trim loop and keyword summary**

Run `resume tailor <a real pending JD file>` against one that needs at
least one trim attempt. Confirm:
1. Step 1 prints a single-line keyword summary ("Keywords extracted: N
   tools, N hard skills, N core functions"), not a multi-line JSON dump.
2. Each Step header (1 through 7, including 5.5) is preceded by a plain
   `────` divider line, visually separating it from the sub-output above.
3. Only the *final* trim attempt's PDF generation prints the full
   6-line block (Input/Output/Format/ATS normalization/Pages/Size) —
   every intermediate attempt shows one line ("PDF is N pages (X KB),
   applying trim step Y/Z...") instead.

- [ ] **Step 4: Report back**

No commit for this task — it's verification only. If either live check
surfaces a real problem (a color that still doesn't read well, a Rich
markup error, a missing divider), stop and report it rather than
declaring the polish pass done.

---

## Self-Review Notes

- **Spec coverage:** Goal 1 (trim-loop collapse) -> Task 1. Goal 2
  (keyword one-liner) -> Task 2. Goal 3 (Step dividers) -> Task 3. Goal 4
  (banner color/border fix) -> Task 4. Goal 5 (chain-prompt panel) ->
  Task 4. All five spec goals have a task.
- **Placeholder scan:** No TBD/TODO markers; every step has complete,
  runnable code or an exact command.
- **Type consistency:** `_parse_pdf_result(stdout: str) -> tuple` (Task
  1) and `_summarize_keywords(jd_keywords: dict) -> str` (Task 2) are
  each used identically at their one call site — no cross-task signature
  reuse to drift. `cli_art.display_whats_next_panel()` (Task 4) is
  defined and consumed within the same task, one call site in `menu.py`.
- **Scope check confirmed against Non-Goals:** no changes made to
  `SUCCESS`/`ERROR`/`WARNING`, `display_banner()`, `render_fit_table()`,
  the "Warming segment cache" listing, or the main recurring menu prompt
  — verified none of Tasks 1-4 touch those.
