# Bullet-Bank Family Themed Output + Markup-Safety Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix a real markup-swallowing bug in `cli_art`'s message helpers, then
route all 103 `console.print(..., markup=False)` call sites across 11
bullet-bank maintenance scripts through the now-safe themed helpers.

**Architecture:** `rich.markup.escape()` applied at the boundary of
`cli_art.py`'s message-taking functions makes markup-enabled output safe for
arbitrary dynamic text (bullet content, company names, provider IDs). Every
`console.print(..., markup=False)` call site in scope then becomes a call to
one of those now-safe helpers, chosen by what the line communicates. Two
files get one exception each: `triage_needs_review.py`'s five-line routing
summary and `audit_keepers.py`'s columnar Top-10 rows both become themed
tables instead of icon+sentence lines, since they're tabular data, not
prose.

**Tech Stack:** Python (`rich`).

**Spec:** `docs/superpowers/specs/2026-08-12-bullet-bank-family-progress-consistency-design.md`

## Global Constraints

- `bullet_bank_menu.py` is out of scope entirely (zero `markup=False` calls,
  already fine).
- No change to any script's return value, persisted data, or CSV schema —
  only terminal output changes.
- Line-choice rule, applied consistently across every task: a line
  confirming something completed successfully → `cli_art.cli_success`; a
  line surfacing a real problem the user should know about (thin data,
  missing file, degraded input) → `cli_art.cli_warning`; a genuine failure
  → `cli_art.cli_error`; ordinary progress narration → `cli_art.cli_info`;
  quantitative/config-echo lines mainly useful for debugging →
  `cli_art.detail(..., level=cli_art.VERBOSE)`; a manual `"─" * N` or
  `"\n" + "─" * N` divider line → `cli_art.console.rule(style="dim")`
  (already an established pattern in these same files); a multi-column
  aligned data row → a themed table, never an icon+sentence line.
- Every replacement drops the `markup=False, soft_wrap=True` kwargs (the
  helper functions already apply their own consistent formatting) and
  drops any manual `f"  "`/`f"   "` leading-space indentation (the helpers'
  icon prefix already provides visual structure — preserving hand-rolled
  indentation on top of an icon reads as double-indented).

---

### Task 1: `cli_art.py` — escape fix + new table renderer

**Files:**
- Modify: `scripts/cli_art.py` — `cli_info`, `cli_warning`, `cli_error`,
  `cli_success`, `display_error`, `display_success` (all currently near
  lines 44-54 and 905-918), `ScanActivity.step()` (from the scan+verify
  work); append a new `render_rewrite_queue_table()`.
- Test: `tests/test_cli_art.py` (append)

**Interfaces:**
- Consumes: `rich.markup.escape` (new import).
- Produces: all six message-helper functions and `ScanActivity.step()`
  keep their existing signatures — this is a behavior-only change, no
  signature changes. New: `cli_art.render_rewrite_queue_table(rows: list, title: str) -> None`
  where each row is `{"rank": int, "source": str, "composite": float, "manager_test": str, "bullet": str}`.

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_cli_art.py`:

  ```python
  class TestMarkupEscaping(unittest.TestCase):

      def test_cli_warning_does_not_swallow_bracketed_dynamic_text(self):
          output = _rendered(cli_art.cli_warning, "[NEEDS_REWRITE] Led team to grow revenue")
          self.assertIn("[NEEDS_REWRITE]", output)

      def test_cli_error_does_not_swallow_bracketed_dynamic_text(self):
          output = _rendered(cli_art.cli_error, "[LinkedIn ON_ERROR] timeout")
          self.assertIn("[LinkedIn ON_ERROR]", output)

      def test_cli_info_does_not_swallow_bracketed_dynamic_text(self):
          output = _rendered(cli_art.cli_info, "Loaded [workday] 42 bullets")
          self.assertIn("[workday]", output)

      def test_cli_success_does_not_swallow_bracketed_dynamic_text(self):
          output = _rendered(cli_art.cli_success, "Wrote [42] rows")
          self.assertIn("[42]", output)


  class TestScanActivityMarkupEscaping(unittest.TestCase):

      def test_step_message_with_brackets_is_not_swallowed(self):
          activity = cli_art.new_scan_activity()
          with activity:
              with patch("cli_art.console.print") as mock_print:
                  activity.step("success", "ATS", "Found [Series B startup] listing")
          printed = mock_print.call_args[0][0]
          self.assertIn("[Series B startup]", printed)


  class TestRenderRewriteQueueTable(unittest.TestCase):

      def test_renders_rank_source_composite_manager_test_and_bullet(self):
          rows = [
              {"rank": 1, "source": "keeper_audit", "composite": 42.0, "manager_test": "FAIL", "bullet": "Led [Series B] growth"},
          ]
          output = _rendered(cli_art.render_rewrite_queue_table, rows, "Top 10 Worst")
          self.assertIn("keeper_audit", output)
          self.assertIn("FAIL", output)
          self.assertIn("Led [Series B] growth", output)
          self.assertIn("Top 10 Worst", output)
  ```

- [ ] **Step 2: Run tests, verify they fail**

  Run: `python -m unittest tests.test_cli_art.TestMarkupEscaping tests.test_cli_art.TestScanActivityMarkupEscaping tests.test_cli_art.TestRenderRewriteQueueTable -v`
  Expected: FAIL — `TestMarkupEscaping`/`TestScanActivityMarkupEscaping` fail
  with the bracketed text missing from output (reproducing the swallowing
  bug); `TestRenderRewriteQueueTable` fails with `AttributeError`.

- [ ] **Step 3: Add the import and escape the six message helpers**

  In `scripts/cli_art.py`, add near the top (alongside the other `rich`
  imports):

  ```python
  from rich.markup import escape as _escape_markup
  ```

  Change `display_error`, `display_success`, `cli_info`, `cli_warning`,
  `cli_error`, `cli_success` (current lines ~44-54 and ~905-918):

  ```python
  def display_error(message: str) -> None:
      """A failure reads with real visual weight -- a bordered panel, not a
      bare icon-prefixed line. message is escaped before interpolation --
      Rich's markup parser silently drops bracketed content that happens
      to look like a style tag (e.g. a company name in brackets), rather
      than raising or rendering it literally, so caller-supplied text must
      never reach console.print unescaped."""
      body = f"[bold {theme.ERROR}]{theme.colorize_icon('error')}[/bold {theme.ERROR}] {_escape_markup(message)}"
      console.print(Panel(body, border_style=theme.ERROR, box=box.ROUNDED, padding=(0, 2)))


  def display_success(message: str) -> None:
      """Stays lightweight (no border) -- this is the common case and a
      bordered panel for every success would get old fast. message is
      escaped -- see display_error()'s docstring."""
      console.print(f"[bold {theme.SUCCESS}]{theme.colorize_icon('success')}[/bold {theme.SUCCESS}] {_escape_markup(message)}")
  ```

  ```python
  def cli_info(message: str) -> None:
      """Print an informational message with hint icon. message is
      escaped -- see display_error()'s docstring."""
      console.print(f"{HINT} {_escape_markup(message)}", soft_wrap=True)

  def cli_warning(message: str) -> None:
      """Print a warning message with warning icon. message is escaped --
      see display_error()'s docstring."""
      console.print(f"{WARNING} {_escape_markup(message)}", soft_wrap=True)

  def cli_error(message: str) -> None:
      """Print an error message using display_error for consistency."""
      display_error(message)

  def cli_success(message: str) -> None:
      """Print a success message with success icon. message is escaped --
      see display_error()'s docstring."""
      console.print(f"{SUCCESS} {_escape_markup(message)}", soft_wrap=True)
  ```

- [ ] **Step 4: Escape `ScanActivity.step()`'s dynamic params**

  In `ScanActivity.step()` (added earlier this session, currently reads):

  ```python
      def step(self, icon_name: str, source: str, message: str) -> None:
          """Print one permanent themed line: icon, source label,
          message, plus a running ETA suffix once start_source() has
          been called and at least one prior step() has run."""
          eta = ""
          if self._eta_total is not None:
              self._eta_done += 1
              if self._eta_done > 1:
                  avg = (time.time() - self._eta_start) / self._eta_done
                  remaining = avg * (self._eta_total - self._eta_done)
                  eta = f" (~{_format_scan_eta(remaining)} remaining)"
          icon = theme.colorize_icon(icon_name)
          self._progress.console.print(
              f"  {icon} [bold]{source}[/bold] {message}{eta}", soft_wrap=True,
          )
  ```

  Change the final two lines to escape `source` and `message`:

  ```python
          icon = theme.colorize_icon(icon_name)
          self._progress.console.print(
              f"  {icon} [bold]{_escape_markup(source)}[/bold] {_escape_markup(message)}{eta}", soft_wrap=True,
          )
  ```

- [ ] **Step 5: Add `render_rewrite_queue_table()`**

  Append to `scripts/cli_art.py`, after `render_comparison_table()`:

  ```python
  def render_rewrite_queue_table(rows: list, title: str) -> None:
      """Themed table for a ranked list of queued-for-rewrite bullets --
      audit_keepers.py's Top-10-worst preview. Each row:
      {"rank", "source", "composite", "manager_test", "bullet"}. Bullet
      text and source are escaped (see display_error()'s docstring) since
      Table cells parse markup exactly like console.print does -- a
      bullet or provider-id containing a stray "[" would otherwise be
      silently dropped the same way a plain console.print call would."""
      table = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=TABLE_HEADER_STYLE)
      table.add_column("#", justify="right")
      table.add_column("Source")
      table.add_column("Composite", justify="right")
      table.add_column("Manager Test")
      table.add_column("Bullet")
      for row in rows:
          table.add_row(
              str(row["rank"]),
              _escape_markup(str(row["source"])),
              f"{row['composite']:.0f}",
              str(row["manager_test"]),
              f"{_escape_markup(row['bullet'])}...",
          )
      console.print(Panel(table, title=title, border_style=theme.BRAND, box=box.ROUNDED, padding=(0, 1)))
  ```

- [ ] **Step 6: Run tests, verify they pass**

  Run: `python -m unittest tests.test_cli_art.TestMarkupEscaping tests.test_cli_art.TestScanActivityMarkupEscaping tests.test_cli_art.TestRenderRewriteQueueTable -v`
  Expected: PASS (6 tests)

- [ ] **Step 7: Run the full test suite**

  Run: `python -m unittest discover -s tests 2>&1 | tail -15`
  Expected: PASS (no regressions in any existing `cli_info`/`cli_warning`/
  `cli_error`/`cli_success`/`ScanActivity` caller — none of them currently
  depend on real markup inside their message)

- [ ] **Step 8: Commit**

  ```bash
  git add scripts/cli_art.py tests/test_cli_art.py
  git commit -m "fix(cli_art): escape dynamic text in message helpers to stop Rich from silently swallowing bracketed content"
  ```

---

### Task 2: `audit_bullet_bank.py` (1 call site)

**Files:** Modify `scripts/audit_bullet_bank.py:87`. No existing test
exercises this print line directly (`test_audit_bullet_bank.py`, if it
exists, doesn't assert on it) — no test changes needed; the file's
existing tests continue to exercise the surrounding logic unchanged.

- [ ] **Step 1:** Change line 87 from:

  ```python
      cli_art.console.print(f"  [{i+1}/{total}] {bullet[:60]}...", markup=False, soft_wrap=True)
  ```

  to:

  ```python
      cli_art.cli_info(f"[{i+1}/{total}] {bullet[:60]}...")
  ```

- [ ] **Step 2:** No dedicated test file exists for this script
  (`tests/test_audit_bullet_bank.py` does not exist). Verify with a
  syntax/import check instead:

  Run: `python -c "import ast; ast.parse(open('scripts/audit_bullet_bank.py').read())" && python -c "import sys; sys.path.insert(0, 'scripts'); import audit_bullet_bank"`
  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/audit_bullet_bank.py
  git commit -m "style(audit_bullet_bank): route progress line through themed cli_info"
  ```

---

### Task 3: `trim_detective_findings.py` (1 call site)

**Files:** Modify `scripts/trim_detective_findings.py:53`.

- [ ] **Step 1:** Change:

  ```python
      cli_art.console.print(f"Wrote {OUTPUT_CSV} ({len(trimmed_rows)} rows)", markup=False, soft_wrap=True)
  ```

  to:

  ```python
      cli_art.cli_success(f"Wrote {OUTPUT_CSV} ({len(trimmed_rows)} rows)")
  ```

  (`cli_success`, not `cli_info` — this line reports the script's one and
  only real output artifact being written, i.e. successful completion.)

- [ ] **Step 2:** Run: `python -m unittest tests.test_trim_detective_findings -v`
  Expected: PASS (no regressions)

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/trim_detective_findings.py
  git commit -m "style(trim_detective_findings): route completion line through themed cli_success"
  ```

---

### Task 4: `score_keeper_gems.py` (2 call sites)

**Files:** Modify `scripts/score_keeper_gems.py:192,219`.

- [ ] **Step 1:** Change line 192:

  ```python
              cli_art.console.print(f"  [{i}] {rows[i].get(bullet_col, '')[:100]}", markup=False, soft_wrap=True)
  ```

  to:

  ```python
              cli_art.cli_info(f"[{i}] {rows[i].get(bullet_col, '')[:100]}")
  ```

  Change line 219:

  ```python
          cli_art.console.print(f"  [{n}/{len(to_score_idx)}] Scoring: {bullet[:80]}...", markup=False, soft_wrap=True)
  ```

  to:

  ```python
          cli_art.cli_info(f"[{n}/{len(to_score_idx)}] Scoring: {bullet[:80]}...")
  ```

- [x] **Step 2:** No dedicated test file exists for this script. Verify
  with a syntax/import check:

  Run: `python -c "import ast; ast.parse(open('scripts/score_keeper_gems.py').read())" && python -c "import sys; sys.path.insert(0, 'scripts'); import score_keeper_gems"`
  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/score_keeper_gems.py
  git commit -m "style(score_keeper_gems): route progress lines through themed cli_info"
  ```

---

### Task 5: `detect_blank_scores.py` (5 call sites)

**Files:** Modify `scripts/detect_blank_scores.py:146,147,153,156,204`.

- [ ] **Step 1:** Replace each of the following exactly:

  Line 146-147:

  ```python
      cli_art.console.print(f"   Total rows:           {report['total_rows']}", markup=False, soft_wrap=True)
      cli_art.console.print(f"   Fully unscored rows:  {report['fully_unscored_rows']}", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_info(f"Total rows: {report['total_rows']}")
      cli_art.cli_info(f"Fully unscored rows: {report['fully_unscored_rows']}")
  ```

  Line 153:

  ```python
          cli_art.console.print("   Blank counts per score column:", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
          cli_art.cli_info("Blank counts per score column:")
  ```

  Line 156 (already builds its own `status` icon via `theme.colorize_icon`
  — this one is a per-column data row, not a plain sentence; keep its
  existing icon logic, just drop `markup=False` so that icon actually
  renders, and escape the dynamic `col` name since it's untrusted):

  ```python
              status = theme.colorize_icon('success') if count == 0 else theme.colorize_icon('warning')
              cli_art.console.print(f"   {status} {col}: {count} blank", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
              status = theme.colorize_icon('success') if count == 0 else theme.colorize_icon('warning')
              cli_art.console.print(f"   {status} {escape(str(col))}: {count} blank", soft_wrap=True)
  ```

  This requires a new import at the top of `scripts/detect_blank_scores.py`,
  alongside its existing imports:

  ```python
  from rich.markup import escape
  ```

  Line 204:

  ```python
      cli_art.console.print(f"Total unscored rows across all files: {total_unscored}", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_info(f"Total unscored rows across all files: {total_unscored}")
  ```

- [x] **Step 2:** No dedicated test file exists for this script. Verify
  with a syntax/import check:

  Run: `python -c "import ast; ast.parse(open('scripts/detect_blank_scores.py').read())" && python -c "import sys; sys.path.insert(0, 'scripts'); import detect_blank_scores"`
  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/detect_blank_scores.py
  git commit -m "style(detect_blank_scores): route lines through themed cli_info, escape dynamic column name"
  ```

---

### Task 6: `retire_rewrite_queue.py` (5 call sites)

**Files:** Modify `scripts/retire_rewrite_queue.py:49,70,71,79,85`.

- [ ] **Step 1:** Replace each:

  Line 49 (a real problem — the input file is missing, script exits):

  ```python
          cli_art.console.print("rewrite-queue.csv not found. Exiting.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
          cli_art.cli_warning("rewrite-queue.csv not found. Exiting.")
  ```

  Lines 70-71:

  ```python
      cli_art.console.print(f"Retiring {len(retire_rows)} non-representative rows.", markup=False, soft_wrap=True)
      cli_art.console.print(f"Keeping {len(keep_rows)} rows in rewrite-queue.", markup=False, soft_wrap=True)
  ```

  become:

  ```python
      cli_art.cli_info(f"Retiring {len(retire_rows)} non-representative rows.")
      cli_art.cli_info(f"Keeping {len(keep_rows)} rows in rewrite-queue.")
  ```

  Line 79:

  ```python
      cli_art.console.print(f"  Appended {len(retire_rows)} rows to {RETIRED_PATH}.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_success(f"Appended {len(retire_rows)} rows to {RETIRED_PATH}.")
  ```

  Line 85:

  ```python
      cli_art.console.print(f"  Rewrote {REWRITE_QUEUE} with {len(keep_rows)} active rows.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_success(f"Rewrote {REWRITE_QUEUE} with {len(keep_rows)} active rows.")
  ```

- [x] **Step 2:** No dedicated test file exists for this script. Verify
  with a syntax/import check:

  Run: `python -c "import ast; ast.parse(open('scripts/retire_rewrite_queue.py').read())" && python -c "import sys; sys.path.insert(0, 'scripts'); import retire_rewrite_queue"`
  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/retire_rewrite_queue.py
  git commit -m "style(retire_rewrite_queue): route lines through themed cli_info/success/warning"
  ```

---

### Task 7: `embed_bullet_bank.py` (6 call sites)

**Files:** Modify `scripts/embed_bullet_bank.py:96,152,182,183,191-193,223`.
(Lines 127, 133, 173, 181, 207, 219, 225 already use `theme.colorize_icon()`
with markup enabled — leave those untouched, they're already correct.)

- [ ] **Step 1:** Replace each:

  Line 96 (a real, recoverable problem — hit a rate limit, retrying):

  ```python
              cli_art.console.print(f"    ⏳ Rate limited. Waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})...", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
              cli_art.cli_warning(f"Rate limited. Waiting {wait}s (attempt {attempt+1}/{MAX_RETRIES})...")
  ```

  (drop the hand-rolled `⏳` — `cli_warning`'s own icon replaces it)

  Line 152:

  ```python
      cli_art.console.print("   Using API key from environment (value redacted).", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.detail("Using API key from environment (value redacted).", level=cli_art.VERBOSE)
  ```

  Lines 182-183:

  ```python
      cli_art.console.print(f"Batch size: {BATCH_SIZE} bullets/call → {n_batches} API calls remaining", markup=False, soft_wrap=True)
      cli_art.console.print(f"Estimated time: ~{est_secs // 60}m {est_secs % 60}s\n", markup=False, soft_wrap=True)
  ```

  become:

  ```python
      cli_art.cli_info(f"Batch size: {BATCH_SIZE} bullets/call → {n_batches} API calls remaining")
      cli_art.cli_info(f"Estimated time: ~{est_secs // 60}m {est_secs % 60}s")
  ```

  Lines 191-193 (per-batch progress row):

  ```python
          cli_art.console.print(f"   Batch {batch_num}/{n_batches}  "
                f"[bullets {batch_start+1}–{batch_end}/{total}]  "
                f"{batch[0][:60]}{'...' if len(batch[0]) > 60 else ''}", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
          cli_art.cli_info(
              f"Batch {batch_num}/{n_batches}  [bullets {batch_start+1}–{batch_end}/{total}]  "
              f"{batch[0][:60]}{'...' if len(batch[0]) > 60 else ''}"
          )
  ```

  Line 223:

  ```python
          cli_art.console.print(f"Checkpoint file removed.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
          cli_art.cli_info("Checkpoint file removed.")
  ```

- [ ] **Step 2:** Run: `python -m unittest tests.test_embed_bullet_bank -v`
  Expected: PASS (no regressions)

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/embed_bullet_bank.py
  git commit -m "style(embed_bullet_bank): route lines through themed helpers, move API-key note to verbose detail"
  ```

---

### Task 8: `tag_bullet_bank.py` (6 call sites)

**Files:** Modify `scripts/tag_bullet_bank.py:177-183`.

- [ ] **Step 1:** Replace:

  ```python
      cli_art.console.print(f"{args.input_csv}: {len(rows)} rows", markup=False, soft_wrap=True)
      cli_art.console.print(f"  Already tagged (left alone): {skipped_existing}", markup=False, soft_wrap=True)
      cli_art.console.print(f"  Newly tagged: {tagged}  (of which {fell_back} fell back to {fallback})", markup=False, soft_wrap=True)
      cli_art.console.print(f"  Weak match, no unique keyword hit (flagged for review): {len(review_rows)}", markup=False, soft_wrap=True)
      cli_art.console.print(f"  Wrote: {out_path}", markup=False, soft_wrap=True)
      if review_rows:
          cli_art.console.print(f"  Wrote: {review_path}", markup=False, soft_wrap=True)
  ```

  with:

  ```python
      cli_art.cli_info(f"{args.input_csv}: {len(rows)} rows")
      cli_art.cli_info(f"Already tagged (left alone): {skipped_existing}")
      cli_art.cli_success(f"Newly tagged: {tagged}  (of which {fell_back} fell back to {fallback})")
      if review_rows:
          cli_art.cli_warning(f"Weak match, no unique keyword hit (flagged for review): {len(review_rows)}")
      cli_art.cli_success(f"Wrote: {out_path}")
      if review_rows:
          cli_art.cli_success(f"Wrote: {review_path}")
  ```

  (Note: the "weak match" line is now conditionally shown only when
  `review_rows` is non-empty and routed through `cli_warning`, since a
  zero count is not itself worth a warning-styled line — this is a small,
  deliberate behavior improvement consistent with §2 of the spec's
  line-choice rule, not a regression: previously it always printed "…: 0".)

- [ ] **Step 2:** Run: `python -m unittest tests.test_tag_bullet_bank -v`
  Expected: PASS (no regressions)

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/tag_bullet_bank.py
  git commit -m "style(tag_bullet_bank): route summary lines through themed helpers"
  ```

---

### Task 9: `detect_hidden_gems.py` (10 call sites)

**Files:** Modify `scripts/detect_hidden_gems.py:66,70,96-98,108-109,119,124,126,128`.

- [x] **Step 1:** Replace each:

  Line 66 (real problem — pipeline prerequisite missing):

  ```python
          cli_art.console.print("  Run the audit + rewrite pipeline first to produce keepers.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
          cli_art.cli_warning("Run the audit + rewrite pipeline first to produce keepers.")
  ```

  Line 70:

  ```python
      cli_art.console.print(f"  Loaded {len(df)} bullets from {KEEPERS_CSV}", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_info(f"Loaded {len(df)} bullets from {KEEPERS_CSV}")
  ```

  Lines 96-98:

  ```python
          cli_art.console.print("  No Hidden Gems found with current thresholds.", markup=False, soft_wrap=True)
          cli_art.console.print(f"  Thresholds: hidden_gem_score>={GEM_SCORE_MIN}, "
                f"accuracy>={ACCURACY_MIN} + believability>={BELIEVABILITY_MIN}", markup=False, soft_wrap=True)
  ```

  become:

  ```python
          cli_art.cli_info("No Hidden Gems found with current thresholds.")
          cli_art.detail(
              f"Thresholds: hidden_gem_score>={GEM_SCORE_MIN}, "
              f"accuracy>={ACCURACY_MIN} + believability>={BELIEVABILITY_MIN}",
              level=cli_art.NORMAL,
          )
  ```

  Lines 107-109:

  ```python
      cli_art.console.print(f"  Found {len(gems)} Hidden Gems out of {len(df)} keeper bullets "
            f"({len(gems)/len(df)*100:.1f}%).", markup=False, soft_wrap=True)
      cli_art.console.print(f"  Wrote {GEMS_CSV}", markup=False, soft_wrap=True)
  ```

  become:

  ```python
      cli_art.cli_success(
          f"Found {len(gems)} Hidden Gems out of {len(df)} keeper bullets "
          f"({len(gems)/len(df)*100:.1f}%)."
      )
      cli_art.cli_success(f"Wrote {GEMS_CSV}")
  ```

  Line 119:

  ```python
      cli_art.console.print("\n  Top Hidden Gems:", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_info("Top Hidden Gems:")
  ```

  Lines 124, 126:

  ```python
          cli_art.console.print(f"  {i}. [score={gem_score}] {text}", markup=False, soft_wrap=True)
          if gem_reason:
              cli_art.console.print(f"     Reason: {gem_reason}", markup=False, soft_wrap=True)
  ```

  become:

  ```python
          cli_art.cli_info(f"{i}. [score={gem_score}] {text}")
          if gem_reason:
              cli_art.detail(f"Reason: {gem_reason}", level=cli_art.NORMAL)
  ```

  Line 128:

  ```python
      cli_art.console.print("\n  Done.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_success("Done.")
  ```

- [x] **Step 2:** No dedicated test file exists for this script. Verify
  with a syntax/import check:

  Run: `python -c "import ast; ast.parse(open('scripts/detect_hidden_gems.py').read())" && python -c "import sys; sys.path.insert(0, 'scripts'); import detect_hidden_gems"`
  Expected: no errors.

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/detect_hidden_gems.py
  git commit -m "style(detect_hidden_gems): route lines through themed helpers"
  ```

---

### Task 10: `triage_needs_review.py` (14 call sites + summary table)

**Files:** Modify `scripts/triage_needs_review.py:128,153,159,205-209,213,217,221,230,233,235`.
Test: `tests/test_triage_needs_review.py` already exists — no new file
needed, its existing tests assert on CSV routing outcomes, not exact
print text, so they should keep passing unmodified.

**Interfaces:**
- Consumes: `cli_art.render_rewrite_queue_table` is *not* reused here (its
  columns don't match) — this task adds a small new table renderer
  instead, `cli_art.render_triage_summary_table(counts: dict) -> None`,
  where `counts` has keys `keep`/`rewrite`/`retire`/`duplicate`/`leftover`.

- [x] **Step 1: Write a failing test for the new table renderer**

  Append to `tests/test_cli_art.py` (this renderer belongs there, same as
  `render_rewrite_queue_table`, even though its only caller is
  `triage_needs_review.py`):

  ```python
  class TestRenderTriageSummaryTable(unittest.TestCase):

      def test_renders_all_five_counts(self):
          output = _rendered(cli_art.render_triage_summary_table, {
              "keep": 3, "rewrite": 1, "retire": 0, "duplicate": 2, "leftover": 5,
          })
          self.assertIn("3", output)
          self.assertIn("KEEP", output)
          self.assertIn("REWRITE", output)
          self.assertIn("RETIRE", output)
          self.assertIn("DUPLICATE", output)
          self.assertIn("Leftover", output)
  ```

- [x] **Step 2:** Run `python -m unittest tests.test_cli_art.TestRenderTriageSummaryTable -v`
  Expected: FAIL (`AttributeError`)

- [x] **Step 3:** Add `render_triage_summary_table()` to `scripts/cli_art.py`,
  after `render_rewrite_queue_table()`:

  ```python
  def render_triage_summary_table(counts: dict) -> None:
      """Themed summary for triage_needs_review.py's routing pass --
      replaces five flat 'KEEP -> N' lines with one small table matching
      render_bullet_bank_status()'s visual language."""
      table = Table(box=box.SIMPLE_HEAD, show_header=False)
      table.add_column("Outcome")
      table.add_column("Count", justify="right")
      table.add_row(f"[{theme.SUCCESS}]KEEP[/{theme.SUCCESS}]", str(counts.get("keep", 0)))
      table.add_row(f"[{theme.WARNING}]REWRITE[/{theme.WARNING}]", str(counts.get("rewrite", 0)))
      table.add_row(f"[{theme.ERROR}]RETIRE[/{theme.ERROR}]", str(counts.get("retire", 0)))
      table.add_row("DUPLICATE (already in keeper bank, skipped)", str(counts.get("duplicate", 0)))
      table.add_row("Leftover (needs human)", str(counts.get("leftover", 0)))
      console.print(Panel(table, title="Triage Results", border_style=theme.BRAND, box=box.ROUNDED, padding=(0, 1)))
  ```

- [x] **Step 4:** Run `python -m unittest tests.test_cli_art.TestRenderTriageSummaryTable -v`
  Expected: PASS

- [x] **Step 5:** In `scripts/triage_needs_review.py`, replace the five
  count-summary lines (current lines 205-209):

  ```python
      cli_art.console.print(f"  KEEP    → {len(keep_rows)}", markup=False, soft_wrap=True)
      cli_art.console.print(f"  REWRITE → {len(rewrite_rows)}", markup=False, soft_wrap=True)
      cli_art.console.print(f"  RETIRE  → {len(retire_rows)}", markup=False, soft_wrap=True)
      cli_art.console.print(f"  DUPLICATE (already in keeper bank, skipped): {n_duplicate}", markup=False, soft_wrap=True)
      cli_art.console.print(f"  Leftover (needs human): {len(leftover)}", markup=False, soft_wrap=True)
  ```

  with:

  ```python
      cli_art.render_triage_summary_table({
          "keep": len(keep_rows), "rewrite": len(rewrite_rows), "retire": len(retire_rows),
          "duplicate": n_duplicate, "leftover": len(leftover),
      })
  ```

  Replace the remaining lines:

  Line 128 (inside `append_rows()` — a real data-shape warning):

  ```python
          cli_art.console.print(f"  Note: {os.path.basename(path)} has no column for {dropped} -- not written.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
          cli_art.cli_warning(f"{os.path.basename(path)} has no column for {dropped} -- not written.")
  ```

  Line 153 (no work to do — informational, not an error):

  ```python
          cli_art.console.print("needs-review.csv not found. Nothing to triage.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
          cli_art.cli_info("needs-review.csv not found. Nothing to triage.")
  ```

  Line 159:

  ```python
      cli_art.console.print(f"Triaging {len(all_rows)} rows from needs-review.csv...", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_info(f"Triaging {len(all_rows)} rows from needs-review.csv...")
  ```

  Lines 213, 217, 221 (each "Appended N rows to X" after the table now
  prints):

  ```python
          cli_art.console.print(f"  Appended {len(keep_rows)} rows to {KEEPERS_CSV}", markup=False, soft_wrap=True)
  ...
          cli_art.console.print(f"  Appended {len(rewrite_rows)} rows to {REWRITE_QUEUE}", markup=False, soft_wrap=True)
  ...
          cli_art.console.print(f"  Appended {len(retire_rows)} rows to {RETIRED_PATH}", markup=False, soft_wrap=True)
  ```

  each become (respectively):

  ```python
          cli_art.cli_success(f"Appended {len(keep_rows)} rows to {KEEPERS_CSV}")
  ...
          cli_art.cli_success(f"Appended {len(rewrite_rows)} rows to {REWRITE_QUEUE}")
  ...
          cli_art.cli_success(f"Appended {len(retire_rows)} rows to {RETIRED_PATH}")
  ```

  Lines 230, 233:

  ```python
          cli_art.console.print(f"  {len(leftover)} rows remain in {NEEDS_REVIEW} for manual review.", markup=False, soft_wrap=True)
      else:
          os.remove(NEEDS_REVIEW)
          cli_art.console.print(f"  All rows routed. Deleted {NEEDS_REVIEW}.", markup=False, soft_wrap=True)
  ```

  become:

  ```python
          cli_art.cli_info(f"{len(leftover)} rows remain in {NEEDS_REVIEW} for manual review.")
      else:
          os.remove(NEEDS_REVIEW)
          cli_art.cli_success(f"All rows routed. Deleted {NEEDS_REVIEW}.")
  ```

  Line 235:

  ```python
      cli_art.console.print("\n  Done.", markup=False, soft_wrap=True)
  ```

  becomes:

  ```python
      cli_art.cli_success("Done.")
  ```

- [x] **Step 6:** Run `python -m unittest tests.test_triage_needs_review -v`
  Expected: PASS. If any existing test does assert on exact print text
  (verify by reading the file if a failure occurs here), update that
  assertion to match the new themed output rather than reverting the
  themed line.

- [x] **Step 7:** Run the full test suite: `python -m unittest discover -s tests 2>&1 | tail -15`
  Expected: PASS

- [x] **Step 8: Commit**

  ```bash
  git add scripts/cli_art.py scripts/triage_needs_review.py tests/test_cli_art.py
  git commit -m "feat(triage_needs_review): themed routing summary table + themed status lines"
  ```

---

### Task 11: `cluster_bullet_bank.py` (23 call sites)

**Files:** Modify `scripts/cluster_bullet_bank.py:131,167-168,173,206,209,211,215,220,231,431-432,436,445,447,471,489,490,497,512,535,537,540,542`.

- [x] **Step 1:** Replace each, in file order:

  ```python
  # L131 (recoverable problem, retrying)
  cli_art.console.print(f"    Rate limited. Waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_warning(f"Rate limited. Waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
  ```

  ```python
  # L167-168 (stale checkpoint discarded -- worth flagging)
  cli_art.console.print("  Bullet bank changed since this checkpoint was saved -- "
        "discarding stale progress and starting over.", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_warning("Bullet bank changed since this checkpoint was saved -- discarding stale progress and starting over.")
  ```

  ```python
  # L173
  cli_art.console.print(f"  Resuming from checkpoint: {next_index} bullets already embedded.", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Resuming from checkpoint: {next_index} bullets already embedded.")
  ```

  ```python
  # L206
  cli_art.console.print(f"  Loaded {len(bullets)} cached vectors from {VECTOR_CACHE}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Loaded {len(bullets)} cached vectors from {VECTOR_CACHE}")
  ```

  ```python
  # L209
  cli_art.console.print(f"  Cache shape mismatch ({cached.shape} vs expected ({len(bullets)}, {EMBED_DIM})). Re-embedding...", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_warning(f"Cache shape mismatch ({cached.shape} vs expected ({len(bullets)}, {EMBED_DIM})). Re-embedding...")
  ```

  ```python
  # L211
  cli_art.console.print("  Cache is stale (bullet bank content changed since it was built). Re-embedding...", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_warning("Cache is stale (bullet bank content changed since it was built). Re-embedding...")
  ```

  ```python
  # L215
  cli_art.console.print(f"  Embedding {total} bullets via {EMBED_MODEL} (batches of {BATCH_SIZE}, starting at {start_index})...", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Embedding {total} bullets via {EMBED_MODEL} (batches of {BATCH_SIZE}, starting at {start_index})...")
  ```

  ```python
  # L220
  cli_art.console.print(f"    {batch_end}/{total}...", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.detail(f"{batch_end}/{total}...", level=cli_art.NORMAL)
  ```

  ```python
  # L231
  cli_art.console.print(f"  Saved {total} vectors to {VECTOR_CACHE}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_success(f"Saved {total} vectors to {VECTOR_CACHE}")
  ```

  ```python
  # L431-432 (prerequisite missing)
  cli_art.console.print("  Run audit_bullet_bank.py first to score every bullet — this", markup=False, soft_wrap=True)
  cli_art.console.print("  script needs those scores to assign next_action.", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_warning("Run audit_bullet_bank.py first to score every bullet -- this script needs those scores to assign next_action.")
  ```

  ```python
  # L436
  cli_art.console.print(f"  Loaded {len(df)} bullets from {RAW_CSV}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Loaded {len(df)} bullets from {RAW_CSV}")
  ```

  ```python
  # L445
  cli_art.console.print(f"  Computing cosine similarity matrix ({len(bullets)}x{len(bullets)})...", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Computing cosine similarity matrix ({len(bullets)}x{len(bullets)})...")
  ```

  ```python
  # L447
  cli_art.console.print(f"  Clustering at threshold={SIMILARITY_THRESHOLD}...", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Clustering at threshold={SIMILARITY_THRESHOLD}...")
  ```

  ```python
  # L471
  cli_art.console.print(f"  Audit join: manager_test normalized: {n_pass} PASS / {n_fail} FAIL", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Audit join: manager_test normalized: {n_pass} PASS / {n_fail} FAIL")
  ```

  ```python
  # L489-490
  cli_art.console.print(f"  Clusters: {n_clusters}  |  Singletons: {n_singletons}  |  Non-representative: {n_dupes}", markup=False, soft_wrap=True)
  cli_art.console.print(f"  next_action breakdown:\n{df['next_action'].value_counts().to_string()}", markup=False, soft_wrap=True)
  ```
  become
  ```python
  cli_art.cli_info(f"Clusters: {n_clusters}  |  Singletons: {n_singletons}  |  Non-representative: {n_dupes}")
  cli_art.detail(f"next_action breakdown:\n{df['next_action'].value_counts().to_string()}", level=cli_art.NORMAL)
  ```

  ```python
  # L497
  cli_art.console.print(f"  Wrote {len(df)} rows to {CLUSTER_MAP_CSV}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_success(f"Wrote {len(df)} rows to {CLUSTER_MAP_CSV}")
  ```

  ```python
  # L512
  cli_art.console.print(f"  Wrote cluster map to {CLUSTER_MAP}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_success(f"Wrote cluster map to {CLUSTER_MAP}")
  ```

  ```python
  # L535
  cli_art.console.print(f"  Appended {len(new_rows)} new rows to existing {REWRITE_QUEUE} ({len(combined)} total)", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_success(f"Appended {len(new_rows)} new rows to existing {REWRITE_QUEUE} ({len(combined)} total)")
  ```

  ```python
  # L537
  cli_art.console.print(f"  No new rows to append — {REWRITE_QUEUE} already up to date.", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"No new rows to append -- {REWRITE_QUEUE} already up to date.")
  ```

  ```python
  # L540
  cli_art.console.print(f"  Wrote {len(non_rep)} rows to {REWRITE_QUEUE}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_success(f"Wrote {len(non_rep)} rows to {REWRITE_QUEUE}")
  ```

  ```python
  # L542
  cli_art.console.print("\n  Done.", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_success("Done.")
  ```

- [x] **Step 2:** Run `grep -n "markup=False" scripts/cluster_bullet_bank.py`
  Expected: no matches remain.

- [x] **Step 3:** Run `python -m unittest tests.test_cluster_bullet_bank -v`
  Expected: PASS. If any existing test asserts on exact print text
  (verify by reading the file if a failure occurs here), update that
  assertion to match the new themed output.

- [x] **Step 4:** Run the full test suite: `python -m unittest discover -s tests 2>&1 | tail -15`
  Expected: PASS

- [x] **Step 5: Commit**

  ```bash
  git add scripts/cluster_bullet_bank.py
  git commit -m "style(cluster_bullet_bank): route all lines through themed helpers"
  ```

---

### Task 12: `audit_keepers.py` (remaining `markup=False` call sites + Top-10 table)

**Files:** Modify `scripts/audit_keepers.py`.

**Interfaces:**
- Consumes: `cli_art.render_rewrite_queue_table` (Task 1).

This is the largest and last file. Apply the Global Constraints line-choice
rule to every remaining `console.print(..., markup=False)` call site in the
file. The verified call sites and their exact treatment:

- [x] **Step 1:** Replace the confirmed call sites, in file order:

  ```python
  # ~L811-812
  cli_art.console.print(f"   Excluded {excluded_a} already-attempted MANUAL bullet(s) from keeper audit "
        f"(pass --retry-manual to include them again)", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Excluded {excluded_a} already-attempted MANUAL bullet(s) from keeper audit (pass --retry-manual to include them again)")
  ```

  ```python
  # ~L815
  cli_art.console.print(f"   From keeper audit (NEEDS_REWRITE + MANUAL): {len(df_keeper_bad)}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"From keeper audit (NEEDS_REWRITE + MANUAL): {len(df_keeper_bad)}")
  ```

  ```python
  # ~L823-824
  cli_art.console.print("   Source B (cluster-map MANUAL): SKIPPED — loading from keepers-audited.csv.", markup=False, soft_wrap=True)
  cli_art.console.print("   Only retrying MANUAL/NEEDS_REWRITE rows from keepers-audited.csv.", markup=False, soft_wrap=True)
  ```
  become
  ```python
  cli_art.cli_info("Source B (cluster-map MANUAL): SKIPPED -- loading from keepers-audited.csv.")
  cli_art.detail("Only retrying MANUAL/NEEDS_REWRITE rows from keepers-audited.csv.", level=cli_art.NORMAL)
  ```

  ```python
  # ~L867
  cli_art.console.print(f"   Excluded {excluded} already-processed bullets (kept, or previously MANUAL){suffix}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Excluded {excluded} already-processed bullets (kept, or previously MANUAL){suffix}")
  ```

  ```python
  # ~L876
  cli_art.console.print(f"   From cluster map MANUAL (not in keepers): {len(df_map_manual)}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"From cluster map MANUAL (not in keepers): {len(df_map_manual)}")
  ```

  ```python
  # ~L900
  cli_art.console.print(f"   Deduplicated: {before_dedup} → {len(df_queue)} unique bullets", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Deduplicated: {before_dedup} -> {len(df_queue)} unique bullets")
  ```

  ```python
  # ~L915
  cli_art.console.print(f"   Lowest composite: {df_queue['composite_score'].min():.0f}  "
        f"Highest: {df_queue['composite_score'].max():.0f}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"Lowest composite: {df_queue['composite_score'].min():.0f}  Highest: {df_queue['composite_score'].max():.0f}")
  ```

  ```python
  # ~L976
  cli_art.console.print(f"   --limit set: processing {limit} of {len(df_queue)} queued bullets.", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"--limit set: processing {limit} of {len(df_queue)} queued bullets.")
  ```

  ```python
  # ~L985 -- ad hoc divider, replace with the console.rule() this file already uses elsewhere (see e.g. "STAGE 4 — Auto-Rewrite")
  cli_art.console.print(f"\n{'─' * 60}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.console.rule(style="dim")
  ```

  ```python
  # ~L986
  cli_art.console.print(f"[{i}/{total}] {bullet_preview}...", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"[{i}/{total}] {bullet_preview}...")
  ```

  ```python
  # ~L988
  cli_art.console.print(f"   Source: {row.get('queue_source', '')}  "
        f"Composite: {row.get('composite_score', '?')}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.detail(f"Source: {row.get('queue_source', '')}  Composite: {row.get('composite_score', '?')}", level=cli_art.NORMAL)
  ```

  ```python
  # ~L1079
  cli_art.console.print(f"\n   Stage 4 complete → KEEP: {n_keep} | MANUAL: {n_manual}", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_success(f"Stage 4 complete -> KEEP: {n_keep} | MANUAL: {n_manual}")
  ```

  ```python
  # ~L1117-1119 -- three-line manual banner, collapse to one console.rule() call
  cli_art.console.print("\n" + "─" * 60, markup=False, soft_wrap=True)
  cli_art.console.print("  audit_keepers.py  —  Keeper Audit Pipeline", markup=False, soft_wrap=True)
  cli_art.console.print("─" * 60, markup=False, soft_wrap=True)
  ```
  become
  ```python
  cli_art.console.rule(f"[bold {theme.BRAND}]audit_keepers.py -- Keeper Audit Pipeline[/bold {theme.BRAND}]", style="dim")
  ```

  ```python
  # ~L1120-1125 -- six config-echo lines, all become verbose detail
  cli_art.console.print(f"  dry_run:             {args.dry_run}", markup=False, soft_wrap=True)
  cli_art.console.print(f"  skip_rescore:        {args.skip_rescore}", markup=False, soft_wrap=True)
  cli_art.console.print(f"  auto_rewrite:        {args.auto_rewrite}", markup=False, soft_wrap=True)
  cli_art.console.print(f"  rebuild_from_keepers: {args.rebuild_from_keepers}", markup=False, soft_wrap=True)
  cli_art.console.print(f"  retry_manual:        {args.retry_manual}", markup=False, soft_wrap=True)
  cli_art.console.print(f"  limit:               {args.limit}", markup=False, soft_wrap=True)
  ```
  become
  ```python
  cli_art.detail(f"dry_run: {args.dry_run}  skip_rescore: {args.skip_rescore}  auto_rewrite: {args.auto_rewrite}  "
                 f"rebuild_from_keepers: {args.rebuild_from_keepers}  retry_manual: {args.retry_manual}  limit: {args.limit}",
                 level=cli_art.VERBOSE)
  ```

  ```python
  # ~L1209
  cli_art.console.print("\n   STAGE 4 skipped — queue is empty.", markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info("STAGE 4 skipped -- queue is empty.")
  ```

  ```python
  # ~L1225-ish
  cli_art.console.print(
      f"\n   {len(df_queue)} bullets queued. "
      f"Run with --auto-rewrite to process them."
  , markup=False, soft_wrap=True)
  ```
  becomes
  ```python
  cli_art.cli_info(f"{len(df_queue)} bullets queued. Run with --auto-rewrite to process them.")
  ```

  ```python
  # ~L1237-1239
  cli_art.console.print(f"     Audited keepers  → {os.path.basename(KEEPERS_AUDITED)}", markup=False, soft_wrap=True)
  cli_art.console.print(f"     Discrepancies    → {os.path.basename(DISCREPANCIES_OUT)}", markup=False, soft_wrap=True)
  cli_art.console.print(f"     Rewrite queue    → {os.path.basename(REWRITE_QUEUE_OUT)}", markup=False, soft_wrap=True)
  ```
  become
  ```python
  cli_art.cli_success(f"Audited keepers  -> {os.path.basename(KEEPERS_AUDITED)}")
  cli_art.cli_success(f"Discrepancies    -> {os.path.basename(DISCREPANCIES_OUT)}")
  cli_art.cli_success(f"Rewrite queue    -> {os.path.basename(REWRITE_QUEUE_OUT)}")
  ```

- [x] **Step 2: Sweep for anything not covered above**

  Run: `grep -n "markup=False" scripts/audit_keepers.py`

  For any remaining match not listed in Step 1 (the extraction above,
  done via multiple targeted reads of a 1,245-line file, covers every
  site found during planning, but re-verify against the live file rather
  than trust that count): apply the same Global Constraints line-choice
  rule (success/info/warning/error/detail/rule, matching what the
  specific line communicates), following the pattern of the examples
  above.

- [x] **Step 3: Convert the Top-10 columnar block to the table renderer**

  Replace (current, inside `stage3_build_rewrite_queue()`):

  ```python
      cli_art.console.print("\n   Top 10 worst (will be rewritten first if --auto-rewrite):", markup=False, soft_wrap=True)
      for _, row in df_queue.head(10).iterrows():
          bp  = str(row.get("Bullet Point", ""))[:65]
          src = row.get("queue_source", "")
          cmp = row.get("composite_score", 0)
          mgr = str(row.get("manager_test", "")).upper()
          cli_art.console.print(f"      #{int(row['queue_rank']):>3}  [{src:<20}]  cmp={cmp:>5.0f}  mgr={mgr:<4}  {bp}...", markup=False, soft_wrap=True)
  ```

  with:

  ```python
      rows = []
      for _, row in df_queue.head(10).iterrows():
          rows.append({
              "rank": int(row["queue_rank"]),
              "source": row.get("queue_source", ""),
              "composite": row.get("composite_score", 0),
              "manager_test": str(row.get("manager_test", "")).upper(),
              "bullet": str(row.get("Bullet Point", ""))[:65],
          })
      cli_art.render_rewrite_queue_table(rows, "Top 10 Worst (will be rewritten first if --auto-rewrite)")
  ```

- [x] **Step 4: Run**

  Run: `grep -n "markup=False" scripts/audit_keepers.py`
  Expected: no matches remain.

- [x] **Step 5:** Run `python -m unittest tests.test_audit_keepers -v`
  Expected: PASS. If any existing test asserts on exact print text
  (verify by reading the file if a failure occurs here), update that
  assertion to match the new themed output.

- [x] **Step 6:** Run the full test suite: `python -m unittest discover -s tests 2>&1 | tail -15`
  Expected: PASS

- [x] **Step 7: Commit**

  ```bash
  git add scripts/audit_keepers.py
  git commit -m "style(audit_keepers): route all lines through themed helpers, Top-10 preview becomes a table"
  ```

---

## Manual verification (after all tasks)

- [ ] Run at least one of the smaller scripts directly (e.g.
  `python scripts/tag_bullet_bank.py <sample.csv>`) against real or
  sandboxed data and visually confirm themed icons/color now appear where
  the output used to be flat text, and that no dynamic content (a company
  name, a bullet containing a stray `[`) is silently missing.
- [ ] Run `audit_keepers.py --dry-run` (if a dry-run/mock path is
  available) and confirm the Top-10 preview now renders as a bordered
  table, and the multi-line banner at startup now renders as one
  `console.rule()` instead of three separate lines.
