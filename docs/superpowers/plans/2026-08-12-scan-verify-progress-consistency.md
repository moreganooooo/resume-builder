# Scan + Verify Progress Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four inconsistent progress patterns across job scanning
(JobRight/LinkedIn/ATS/boards) and the liveness verify pass with one shared,
themed, live-updating step-log component.

**Architecture:** A new `cli_art.ScanActivity` class (built on `rich.progress.Progress`,
using its documented support for printing permanent lines while a live task is
active) provides `step()` (a themed, permanent per-item line) and `tally()` (a
pinned, live-updating summary line). `scan.py`'s `run_scan()` opens one
`ScanActivity` and threads it, as an optional keyword argument, through every
fetcher and into the liveness verify pass, so one continuous log spans the
whole scan-to-verify journey.

**Tech Stack:** Python (`rich`), Node.js (`node:test`, Playwright — unchanged).

**Spec:** `docs/superpowers/specs/2026-08-12-scan-verify-progress-consistency-design.md`

## Global Constraints

- Sequential execution stays exactly as it is — no threading/asyncio. `ScanActivity`
  must not assume or require concurrent callers.
- No new Python package — `ScanActivity` lives inside `scripts/cli_art.py`, beside
  the existing `new_progress()`.
- Every new `activity` parameter is optional (`activity=None` default) and a full
  no-op when absent — no existing caller or test may break.
- No change to any fetcher's return value shape or to `run_scan()`'s return
  contract.
- `check-liveness.mjs`'s standalone (non-`--json-file`) usage is untouched.
- `render_scan_report()` and its data (`source_results`, `written` count) are
  unchanged — this plan only touches the *during* experience.
- Reuse `scan_boards.ProgressReporter`'s existing running-ETA-average math
  (moved, not reimplemented) and `theme.colorize_icon()` for icons (existing
  keys: `success`, `warning`, `error`, `skip`, `discovery`).

---

### Task 1: `cli_art.ScanActivity` + `new_scan_activity()`

**Files:**
- Modify: `scripts/cli_art.py` (append after `new_progress()`, which currently
  ends at line 1312 — new code becomes the new end of the file)
- Test: `tests/test_cli_art.py` (append; file already exists, do not create it)

**Interfaces:**
- Produces: `cli_art.new_scan_activity(**kwargs) -> ScanActivity`;
  `ScanActivity` usable as `with ... as activity:`; `activity.start_source(total: int, label: str = "Checking") -> None`;
  `activity.step(icon_name: str, source: str, message: str) -> None`;
  `activity.tally(**counts: int) -> None`.
- Consumes: `cli_art.console` (module global), `theme.colorize_icon`,
  `theme.BRAND`, already-imported `Progress`/`SpinnerColumn`/`TextColumn`/`time`
  (all present at the top of `cli_art.py` already — no new imports needed).

- [ ] **Step 1: Write failing tests**

  Append to `tests/test_cli_art.py`:

  ```python
  class TestScanActivity(unittest.TestCase):

      def test_step_prints_themed_line_with_icon_and_source(self):
          activity = cli_art.new_scan_activity()
          with activity:
              with patch("cli_art.console.print") as mock_print:
                  activity.step("success", "JobRight", "Found Senior Data Engineer @ Acme")
          mock_print.assert_called_once_with(
              f"  {cli_art.theme.colorize_icon('success')} [bold]JobRight[/bold] "
              "Found Senior Data Engineer @ Acme",
              soft_wrap=True,
          )

      def test_step_has_no_eta_before_start_source(self):
          activity = cli_art.new_scan_activity()
          with activity:
              with patch("cli_art.console.print") as mock_print:
                  activity.step("success", "Boards", "checked remoteok")
          printed = mock_print.call_args[0][0]
          self.assertNotIn("remaining)", printed)

      def test_step_shows_eta_from_second_call_after_start_source(self):
          activity = cli_art.new_scan_activity()
          with activity:
              activity.start_source(3, label="Checking")
              with patch("cli_art.console.print") as mock_print:
                  activity.step("success", "ATS", "first item")
                  activity.step("success", "ATS", "second item")
          first_printed = mock_print.call_args_list[0].args[0]
          second_printed = mock_print.call_args_list[1].args[0]
          self.assertNotIn("remaining)", first_printed)
          self.assertIn("remaining)", second_printed)

      def test_tally_updates_pinned_task_description(self):
          activity = cli_art.new_scan_activity()
          with activity:
              activity.tally(fetched=12, written=9, skipped=3, errors=0)
              task = next(t for t in activity._progress.tasks if t.id == activity._task_id)
          self.assertIn("Fetched 12", task.description)
          self.assertIn("Written 9", task.description)
          self.assertIn("Skipped 3", task.description)
          self.assertIn("Errors 0", task.description)

      def test_tally_is_cumulative_across_calls(self):
          activity = cli_art.new_scan_activity()
          with activity:
              activity.tally(fetched=5)
              activity.tally(written=2)
              task = next(t for t in activity._progress.tasks if t.id == activity._task_id)
          self.assertIn("Fetched 5", task.description)
          self.assertIn("Written 2", task.description)
  ```

- [ ] **Step 2: Run tests, verify they fail**

  Run: `python -m unittest tests.test_cli_art.TestScanActivity -v`
  Expected: FAIL with `AttributeError: module 'cli_art' has no attribute 'new_scan_activity'`

- [ ] **Step 3: Implement `ScanActivity` and `new_scan_activity()`**

  Append to `scripts/cli_art.py`, after the existing `new_progress()` function:

  ```python
  class ScanActivity:
      """Context-managed live activity display for a multi-source scan or
      verify pass: one pinned, live-updating tally line (a themed
      rich.Progress spinner task) plus a permanent, themed step-log of
      completed items printed above it. Progress is built on Live and
      supports printing permanent lines through its own .console while a
      task stays live -- that's what gives this its two-part shape,
      matching Crush's step-log-plus-status-line pattern rather than an
      animated percentage bar (most of these sources never know a grand
      total up front). See new_scan_activity()."""

      def __init__(self, **progress_kwargs):
          self._progress = Progress(
              SpinnerColumn(),
              TextColumn("[progress.description]{task.description}"),
              console=console,
              **progress_kwargs,
          )
          self._task_id = None
          self._counts: dict = {}
          self._eta_total = None
          self._eta_done = 0
          self._eta_start = None

      def __enter__(self) -> "ScanActivity":
          self._progress.__enter__()
          self._task_id = self._progress.add_task(
              f"[bold {theme.BRAND}]Scanning[/bold {theme.BRAND}]", total=None,
          )
          return self

      def __exit__(self, *exc_info) -> None:
          self._progress.__exit__(*exc_info)

      def start_source(self, total: int, label: str = "Checking") -> None:
          """Resets the running ETA tracker for the next source's items --
          same averaging math scan_boards.ProgressReporter used to own.
          A source with no known total up front (e.g. JobRight's
          open-ended pagination) simply never calls this, and step()
          prints with no ETA suffix."""
          self._eta_total = total
          self._eta_done = 0
          self._eta_start = time.time()

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

      def tally(self, **counts: int) -> None:
          """Update the pinned line's description from named counts,
          cumulative across calls, e.g. tally(fetched=12) then
          tally(written=9) -> 'Scanning · Fetched 12 · Written 9'. Count
          names deliberately match scan.py's existing per-source result
          dict keys (fetched/written/skipped) rather than inventing
          synonyms."""
          self._counts.update(counts)
          description = f"[bold {theme.BRAND}]Scanning[/bold {theme.BRAND}]"
          if self._counts:
              parts = " · ".join(f"{key.capitalize()} {value}" for key, value in self._counts.items())
              description += f" · {parts}"
          self._progress.update(self._task_id, description=description)


  def _format_scan_eta(seconds: float) -> str:
      """Same duration formatting scan_boards._format_duration used to
      own (Ns / NmNNs / NhNNm) -- moved here since ETA math now lives on
      ScanActivity instead of the retired ProgressReporter."""
      seconds = max(int(seconds), 0)
      if seconds < 60:
          return f"{seconds}s"
      minutes, seconds = divmod(seconds, 60)
      if minutes < 60:
          return f"{minutes}m{seconds:02d}s"
      hours, minutes = divmod(minutes, 60)
      return f"{hours}h{minutes:02d}m"


  def new_scan_activity(**kwargs) -> ScanActivity:
      """Themed live activity display for a multi-source scan or verify
      pass: a pinned, live-updating tally line plus a permanent step-log
      of completed items underneath it. Usage:

          with cli_art.new_scan_activity() as activity:
              activity.start_source(len(jobs), label="Checking")
              for job in jobs:
                  activity.step("success", "ATS", f"{job['title']} @ {job['company']}")
              activity.tally(fetched=len(jobs))
      """
      return ScanActivity(**kwargs)
  ```

- [ ] **Step 4: Run tests, verify they pass**

  Run: `python -m unittest tests.test_cli_art.TestScanActivity -v`
  Expected: PASS (5 tests)

- [ ] **Step 5: Run the full existing test_cli_art.py suite, verify no regressions**

  Run: `python -m unittest tests.test_cli_art -v`
  Expected: PASS (all existing tests plus the 5 new ones)

- [ ] **Step 6: Commit**

  ```bash
  git add scripts/cli_art.py tests/test_cli_art.py
  git commit -m "feat(cli_art): add ScanActivity themed step-log/tally component"
  ```

---

### Task 2: `scan_boards.py` — retire `ProgressReporter`, use `ScanActivity`

**Files:**
- Modify: `scripts/scan_boards.py:96-128` (delete `_format_duration` and
  `ProgressReporter`), `scripts/scan_boards.py:320-330` (`fetch_board_jobs`
  signature and loop body)
- Test: `tests/test_scan_boards.py:27-59` (delete `TestFormatDuration` and
  `TestProgressReporter`)

**Interfaces:**
- Consumes: `cli_art.ScanActivity.start_source()`/`.step()` from Task 1.
- Produces: `scan_boards.fetch_board_jobs(sources: list = None, search_term: str = None, activity=None) -> list`
  (new `activity` param; return shape unchanged).

- [ ] **Step 1: Update `test_scan_boards.py`**

  Delete the `TestFormatDuration` class (lines 27-40) and the
  `TestProgressReporter` class (lines 42-59) entirely — equivalent coverage
  now lives in `tests/test_cli_art.py::TestScanActivity` (Task 1). No new
  test needed here: every existing `TestFetchBoardJobs` test calls
  `fetch_board_jobs()` without an `activity` argument and asserts only on
  the returned job list, which is unaffected by an optional, unused
  parameter.

- [ ] **Step 2: Run the suite, verify it fails only on the deleted symbols'
  removal (sanity check nothing else references them)**

  Run: `grep -rn "ProgressReporter\|_format_duration" scripts/ tests/`
  Expected: no matches outside `scripts/scan_boards.py` and
  `scripts/scan_ats.py` (handled in Task 3) before Step 3 below runs.

- [ ] **Step 3: Delete `_format_duration`/`ProgressReporter`, update `fetch_board_jobs`**

  In `scripts/scan_boards.py`, delete the `_format_duration` function and
  `ProgressReporter` class (current lines 96-128).

  Change the `fetch_board_jobs` signature and loop (current lines 320-330):

  ```python
  def fetch_board_jobs(sources: list = None, search_term: str = None, activity=None) -> list:
      """Runs each requested board provider (default: all of BOARD_PROVIDERS),
      applies the title/location prefilter, fetches each surviving posting's
      full text, and returns a list of job dicts in the same shape
      scan_jobright.py/scan_linkedin.py already produce. `activity` (a
      cli_art.ScanActivity) is optional -- when given, announces each
      provider as it's checked through the shared themed step-log instead
      of nothing at all."""
      sources = sources or BOARD_PROVIDERS

      jobs = []
      if activity is not None:
          activity.start_source(len(sources), label="Fetching")
      for provider_id in sources:
          if activity is not None:
              activity.step("discovery", "Boards", f"Checking {provider_id}")
          # `entry.name` is what a provider falls back to for `company` when
  ```

  (The rest of the function body — from `entry = {"name": provider_id}`
  onward — is unchanged.)

- [ ] **Step 4: Run tests, verify pass**

  Run: `python -m unittest tests.test_scan_boards -v`
  Expected: PASS (all remaining tests; `TestFormatDuration`/`TestProgressReporter`
  no longer exist)

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/scan_boards.py tests/test_scan_boards.py
  git commit -m "refactor(scan_boards): replace ProgressReporter with shared ScanActivity"
  ```

---

### Task 3: `scan_ats.py` — use `ScanActivity` instead of `ProgressReporter`

**Files:**
- Modify: `scripts/scan_ats.py:139-217` (`fetch_ats_jobs` signature and both
  loop bodies)
- Test: `tests/test_scan_ats.py` (no structural change needed — see Step 1)

**Interfaces:**
- Consumes: `cli_art.ScanActivity` (Task 1); `scan_boards.fetch_board_jobs`'s
  updated signature is irrelevant here (`scan_ats.py` calls
  `scan_boards._run_node_provider`/`_passes_title_filter`/etc. directly, not
  `fetch_board_jobs`).
- Produces: `scan_ats.fetch_ats_jobs(sources: list = None, activity=None) -> list`.

- [ ] **Step 1: Confirm no test changes are needed**

  Run: `grep -n "ProgressReporter" tests/test_scan_ats.py`
  Expected: no matches — `test_scan_ats.py` never references
  `ProgressReporter` directly (only `fetch_ats_jobs()`'s return value), so
  no test edits are required before implementing.

- [ ] **Step 2: Update `fetch_ats_jobs`**

  In `scripts/scan_ats.py`, change the signature and both `progress.step(...)`
  call sites (current lines 139-217):

  ```python
  def fetch_ats_jobs(sources: list = None, activity=None) -> list:
      """Runs every enabled tracked_companies.yml entry through its
      resolved provider, plus every enabled search_queries.yml sweep query
      through websearch.mjs. `sources` is accepted for SOURCE_FETCHERS
      signature-compatibility with scan.py but unused -- there's no
      meaningful per-call subset the way scan_boards.py has per-provider
      sources; the whole point here is per-company targeting, already
      expressed in tracked_companies.yml itself (its own `enabled` field).

      Skips any entry resolving to an aggregator provider (not one of the
      7 real ATS providers) -- found live, 2026-07-27: 34 tracked_companies
      entries explicitly pin `provider: remoteok`/`jobspresso`/etc. (career-
      ops's own design, each run twice with search_term "marketing"/
      "enablement"), but scan_boards.py's "boards" source already fetches
      those exact same feeds in full and unfiltered. Since "marketing"/
      "enablement" results are necessarily a subset of the full feed, every
      posting these entries could return is already covered by "boards" --
      running them here only re-fetches the same postings under a
      different company label (the pinned entry's own display name, e.g.
      "Jobspresso — Marketing" vs. "boards"'s "jobspresso"), which defeats
      job_key_known()'s source_url+company_name dedup match and produces
      real duplicate JD files (confirmed live: 31 duplicate-URL groups,
      62 files, before this fix). `activity` (a cli_art.ScanActivity) is
      optional -- when given, announces each company/sweep as it's
      checked through the shared themed step-log; ~400 sequential
      subprocess calls with zero feedback otherwise reads as a hang on a
      real run."""
      jobs = []
      companies = [c for c in _load_tracked_companies() if c.get("enabled") is not False]
      queries = [q for q in _load_search_queries() if q.get("enabled") is not False]
      if activity is not None:
          activity.start_source(len(companies) + len(queries), label="Checking")

      for company in companies:
          if activity is not None:
              activity.step("discovery", "ATS", f"Checking {company.get('name') or '?'}")
          provider_id = _resolve_provider_id(company)
  ```

  (Body from `if not provider_id or provider_id not in _ATS_PROVIDER_IDS:`
  onward is unchanged.)

  Then, in the second loop (the `for query in queries:` block), replace
  `progress.step(query.get("name") or "websearch sweep")` with:

  ```python
          if activity is not None:
              activity.step("discovery", "ATS", f"Checking {query.get('name') or 'websearch sweep'}")
  ```

  Remove the now-unused `progress = scan_boards.ProgressReporter(...)` line
  entirely (it's replaced by the `activity.start_source(...)` call above).

- [ ] **Step 3: Run tests, verify pass**

  Run: `python -m unittest tests.test_scan_ats -v`
  Expected: PASS (unmodified — `activity` defaults to `None`, a full no-op)

- [ ] **Step 4: Commit**

  ```bash
  git add scripts/scan_ats.py
  git commit -m "refactor(scan_ats): route progress through shared ScanActivity"
  ```

---

### Task 4: `scan_jobright.py` — thread `ScanActivity` through fetching

**Files:**
- Modify: `scripts/scan_jobright.py:36-144` (`fetch_jobright_jobs`)
- Test: Create `tests/test_scan_jobright.py` (no test file exists for this
  script today)

**Interfaces:**
- Consumes: `cli_art.ScanActivity` (Task 1).
- Produces: `scan_jobright.fetch_jobright_jobs(max_position: int = None, activity=None) -> list`.

- [ ] **Step 1: Write a failing test**

  Create `tests/test_scan_jobright.py`:

  ```python
  import os
  import sys
  import unittest
  from unittest.mock import MagicMock, patch

  SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
  sys.path.insert(0, SCRIPTS_DIR)

  import scan_jobright  # noqa: E402


  class TestFetchJobrightJobsActivity(unittest.TestCase):

      @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
      @patch("scan_jobright.requests.get")
      def test_steps_through_activity_when_given(self, mock_get):
          response = MagicMock()
          response.status_code = 200
          response.json.return_value = {"result": {"jobList": [
              {"jobResult": {"jobId": "1", "jobTitle": "Data Engineer", "originalUrl": "https://x.com/1"},
               "companyResult": {"companyName": "Acme"}, "displayScore": 80},
          ]}}
          mock_get.return_value = response

          activity = MagicMock()
          jobs = scan_jobright.fetch_jobright_jobs(max_position=0, activity=activity)

          self.assertEqual(len(jobs), 1)
          activity.step.assert_called_with(
              "success", "JobRight", 'Found "Data Engineer" @ Acme',
          )

      @patch.dict(os.environ, {"JOBRIGHT_COOKIE_STRING": "fake-cookie"})
      @patch("scan_jobright.requests.get")
      def test_works_with_no_activity_given(self, mock_get):
          response = MagicMock()
          response.status_code = 200
          response.json.return_value = {"result": {"jobList": []}}
          mock_get.return_value = response

          jobs = scan_jobright.fetch_jobright_jobs(max_position=0)
          self.assertEqual(jobs, [])
  ```

- [ ] **Step 2: Run test, verify it fails**

  Run: `python -m unittest tests.test_scan_jobright -v`
  Expected: FAIL with `TypeError: fetch_jobright_jobs() got an unexpected keyword argument 'activity'`

- [ ] **Step 3: Implement**

  In `scripts/scan_jobright.py`, change the signature (current line 36) and
  the two relevant call sites:

  ```python
  def fetch_jobright_jobs(max_position: int = None, activity=None) -> list:
  ```

  Replace the per-page announcement (current lines 54-58):

  ```python
          # Up to 11 paginated requests with a 2s backoff on a 500 -- without
          # a visible line per page, `resume scan --source jobright` looks
          # hung for 20+ seconds with logging.info's output invisible by
          # default.
          if activity is not None:
              activity.step("discovery", "JobRight", f"Fetching page (position {position}/{end_position})")
          else:
              cli_art.cli_info(f"Fetching JobRight jobs (position {position}/{end_position})...")
          logging.info(f"Fetching JobRight data for position {position}...")
  ```

  Inside the `for item in job_list:` loop, after a job is appended to
  `jobs` (immediately after the closing `})` of the `jobs.append({...})`
  call, current line 128), add:

  ```python
              if activity is not None:
                  activity.step("success", "JobRight", f'Found "{job_title}" @ {company_name}')
  ```

  Leave every existing `cli_art.cli_error(...)` call site unchanged — those
  are genuine error conditions and stay routed through the existing error
  path regardless of `activity`.

- [ ] **Step 4: Run tests, verify pass**

  Run: `python -m unittest tests.test_scan_jobright -v`
  Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/scan_jobright.py tests/test_scan_jobright.py
  git commit -m "feat(scan_jobright): thread ScanActivity through fetch_jobright_jobs"
  ```

---

### Task 5: `scan_linkedin.py` — thread `ScanActivity` through fetching

**Files:**
- Modify: `scripts/scan_linkedin.py:145-274` (`fetch_linkedin_jobs`)
- Test: `tests/test_scan_linkedin.py` (append)

**Interfaces:**
- Consumes: `cli_art.ScanActivity` (Task 1).
- Produces: `scan_linkedin.fetch_linkedin_jobs(limit: int = None, activity=None) -> list`.

- [ ] **Step 1: Write a failing test**

  Append to `tests/test_scan_linkedin.py`:

  ```python
  class TestFetchLinkedinJobsActivity(unittest.TestCase):

      @patch("scan_linkedin._fetch_personalized_extras", return_value={"is_top_applicant": False, "backup_description": None})
      @patch("scan_linkedin.get_li_at_cookie", return_value="fake-li-at")
      @patch("scan_linkedin.profile_paths.profile_yaml", return_value={"target_roles": {"primary": ["Data Engineer"]}})
      @patch("scan_linkedin.LinkedinScraper")
      def test_steps_through_activity_on_each_result(self, mock_scraper_cls, mock_profile, mock_cookie, mock_extras):
          mock_scraper = mock_scraper_cls.return_value
          registered = {}

          def fake_on(event, handler):
              registered[event] = handler

          mock_scraper.on.side_effect = fake_on

          def fake_run(queries):
              data = MagicMock(title="Data Engineer", company="Acme", link="https://linkedin.com/jobs/view/1",
                                apply_link=None, place="Remote", date=None, date_text=None,
                                employment_type=None, seniority_level=None, description="desc",
                                description_html=None, skills=None, job_id="1", company_link=None)
              registered[scan_linkedin.Events.DATA](data)

          mock_scraper.run.side_effect = fake_run

          activity = MagicMock()
          jobs = scan_linkedin.fetch_linkedin_jobs(activity=activity)

          self.assertEqual(len(jobs), 1)
          activity.step.assert_called_with("success", "LinkedIn", "Found Data Engineer at Acme")
  ```

- [ ] **Step 2: Run test, verify it fails**

  Run: `python -m unittest tests.test_scan_linkedin.TestFetchLinkedinJobsActivity -v`
  Expected: FAIL with `TypeError: fetch_linkedin_jobs() got an unexpected keyword argument 'activity'`

- [ ] **Step 3: Implement**

  In `scripts/scan_linkedin.py`, change the signature (current line 145):

  ```python
  def fetch_linkedin_jobs(limit: int = None, activity=None) -> list:
  ```

  Replace the `on_data` per-result line (current line 190):

  ```python
          if activity is not None:
              activity.step("success", "LinkedIn", f"Found {getattr(data, 'title', '?')} at {getattr(data, 'company', '?')}")
          else:
              cli_art.cli_info(f"Found: {getattr(data, 'title', '?')} at {getattr(data, 'company', '?')}")
  ```

  Leave `on_error`'s `cli_art.cli_error(...)` call unchanged.

- [ ] **Step 4: Run tests, verify pass**

  Run: `python -m unittest tests.test_scan_linkedin -v`
  Expected: PASS (all existing tests plus the new one)

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/scan_linkedin.py tests/test_scan_linkedin.py
  git commit -m "feat(scan_linkedin): thread ScanActivity through fetch_linkedin_jobs"
  ```

---

### Task 6: `scan.py` — open one `ScanActivity` spanning the whole run

**Files:**
- Modify: `scripts/scan.py:1-30` (imports), `scripts/scan.py:139-198`
  (`run_scan`)
- Test: `tests/test_scan.py:65,84,105,115,129,211` (fetcher-double lambdas)

**Interfaces:**
- Consumes: `cli_art.new_scan_activity()` (Task 1); all four fetchers now
  accept `activity=` (Tasks 2-5).
- Produces: no change to `run_scan()`'s public signature or return value
  (still `run_scan(sources: list = None, verify: bool = True) -> int`).

- [ ] **Step 1: Update the six existing fetcher-double lambdas in `test_scan.py`**

  Every `SOURCE_FETCHERS` test double is currently a zero-argument lambda
  (e.g. `lambda: [job]`), which will break once `run_scan()` calls
  `fetch(activity=activity)`. Update all six occurrences to accept (and
  ignore) keyword arguments:

  Using the Edit tool with `replace_all=True`, make these three literal
  replacements in `tests/test_scan.py`:
  - `lambda: [job]` → `lambda **kwargs: [job]` (4 occurrences: lines 65, 84,
    105, 115)
  - `lambda: jobs` → `lambda **kwargs: jobs` (1 occurrence: line 129)
  - `lambda: []` → `lambda **kwargs: []` (1 occurrence: line 211)

- [ ] **Step 2: Run the suite, verify it fails for the right reason**

  Run: `python -m unittest tests.test_scan -v`
  Expected: PASS still (this step alone doesn't change `scan.py`, so
  nothing should break yet — this just confirms the lambda edits didn't
  typo anything before Step 3 changes the calling convention).

- [ ] **Step 3: Implement — thread `activity` through `run_scan()`**

  In `scripts/scan.py`, change the fetch loop (current lines 154-198). The
  current code:

  ```python
      collector = _ScanWarningCollector()
      root_logger = logging.getLogger()
      root_logger.addHandler(collector)
      try:
          for source in sources:
              fetch = SOURCE_FETCHERS.get(source)
              if fetch is None:
                  source_results.append({"source": source, "error": f"unknown source (known: {', '.join(SOURCE_FETCHERS)})"})
                  continue

              warnings_before = len(collector.records)
              jobs = fetch()
  ```

  becomes:

  ```python
      collector = _ScanWarningCollector()
      root_logger = logging.getLogger()
      root_logger.addHandler(collector)
      try:
          with cli_art.new_scan_activity() as activity:
              for source in sources:
                  fetch = SOURCE_FETCHERS.get(source)
                  if fetch is None:
                      source_results.append({"source": source, "error": f"unknown source (known: {', '.join(SOURCE_FETCHERS)})"})
                      continue

                  warnings_before = len(collector.records)
                  jobs = fetch(activity=activity)
      # (rest of the loop body indented one level deeper to stay inside
      # the `with` block, through the end of the existing `for source in
      # sources:` loop -- no other logic changes)
  ```

  After each source's `result` dict is fully built and appended to
  `source_results` (i.e. right after the existing
  `source_results.append(result)` line, still inside the `with`/`for`
  block), add:

  ```python
              activity.tally(fetched=sum(r.get("fetched", 0) for r in source_results),
                             written=sum(r.get("written", 0) for r in source_results),
                             skipped=sum(r.get("skipped", 0) for r in source_results))
  ```

  The `finally: root_logger.removeHandler(collector)` block, and everything
  from `if verify and written_paths:` onward, stay outside the `with
  cli_art.new_scan_activity()` block at their current indentation (the
  activity's job is done once fetching finishes; Task 8 gives the verify
  pass its own activity-threading, opened separately inside
  `liveness.verify_jd_paths`).

  Add `import cli_art` near the top of `scripts/scan.py` if not already
  present (check current imports first — `cli_art` is already imported,
  per the existing `cli_art.render_scan_report(...)` call at the end of
  `run_scan()`, so no import change is actually needed here).

- [ ] **Step 4: Run tests, verify pass**

  Run: `python -m unittest tests.test_scan -v`
  Expected: PASS (all tests, including the six updated lambdas)

- [ ] **Step 5: Run the full test suite to catch any cross-file regression**

  Run: `python -m unittest discover -s tests -v 2>&1 | tail -30`
  Expected: PASS (or a list of failures to fix before continuing — do not
  proceed to Task 7 with a red suite)

- [ ] **Step 6: Commit**

  ```bash
  git add scripts/scan.py tests/test_scan.py
  git commit -m "feat(scan): open one ScanActivity spanning the whole source loop"
  ```

---

### Task 7: `check-liveness.mjs` — structured progress events in `--json-file` mode

**Files:**
- Modify: `scripts/check-liveness.mjs:39-72` (`runJsonMode`)
- Test: Create `scripts/check-liveness.test.mjs`

**Interfaces:**
- Produces: exported `buildProgressEvent(index, total, candidate, result, code, reason) -> object`;
  `runJsonMode` now writes one `JSON.stringify(buildProgressEvent(...))` line
  to stderr per candidate instead of the current two human-readable
  `console.error` lines. `runTextMode` (standalone CLI usage) is completely
  untouched.

- [ ] **Step 1: Write a failing test**

  Create `scripts/check-liveness.test.mjs`:

  ```js
  // Unit tests for check-liveness.mjs's buildProgressEvent() -- the
  // structured per-item progress line liveness.py's _verify_candidates()
  // parses to drive the shared themed ScanActivity step-log instead of
  // passing raw stderr text through.
  //
  // Run: node --test scripts/check-liveness.test.mjs

  import { test } from 'node:test';
  import assert from 'node:assert/strict';
  import { buildProgressEvent } from './check-liveness.mjs';

  test('buildProgressEvent: 1-indexes the position and carries result/code/reason/source_file', () => {
    const event = buildProgressEvent(
      0, 25, { source_file: '/jds/acme.json', url: 'https://acme.com/job/1' },
      'active', 'apply_control_visible', 'visible apply control detected',
    );
    assert.deepEqual(event, {
      type: 'progress',
      index: 1,
      total: 25,
      result: 'active',
      code: 'apply_control_visible',
      reason: 'visible apply control detected',
      source_file: '/jds/acme.json',
    });
  });

  test('buildProgressEvent: null reason becomes JSON null, not undefined', () => {
    const event = buildProgressEvent(
      4, 25, { source_file: '/jds/widgets.json' }, 'active', 'apply_control_visible', undefined,
    );
    assert.equal(event.reason, null);
    assert.equal(JSON.stringify(event).includes('undefined'), false);
  });
  ```

- [ ] **Step 2: Run test, verify it fails**

  Run: `node --test scripts/check-liveness.test.mjs`
  Expected: FAIL — `check-liveness.mjs` has no exported `buildProgressEvent`

- [ ] **Step 3: Implement**

  In `scripts/check-liveness.mjs`, add this exported function above
  `runJsonMode` (after the `UNKNOWN_ICON` constant, before
  `async function runJsonMode`):

  ```js
  export function buildProgressEvent(index, total, candidate, result, code, reason) {
    return {
      type: 'progress',
      index: index + 1,
      total,
      result,
      code,
      reason: reason || null,
      source_file: candidate.source_file,
    };
  }
  ```

  Replace the progress-printing block inside `runJsonMode`'s loop (current
  lines 53-59):

  ```js
      // Progress indicator: [i/total] + status + reason if applicable
      const icon = RESULT_ICONS[result] || UNKNOWN_ICON;
      const progress = `[${i + 1}/${candidates.length}]`;
      console.error(`${progress} ${icon} ${result.padEnd(14)} ${candidate.source_file}`);
      if (reason && result !== 'active' && result !== 'likely_active') {
        console.error(`         → ${reason}`);
      }
  ```

  with:

  ```js
      console.error(JSON.stringify(buildProgressEvent(i, candidates.length, candidate, result, code, reason)));
  ```

  `RESULT_ICONS`/`UNKNOWN_ICON` stay exactly as they are — `runTextMode`
  still uses them (lines 93-94), untouched by this change.

- [ ] **Step 4: Run tests, verify pass**

  Run: `node --test scripts/check-liveness.test.mjs`
  Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/check-liveness.mjs scripts/check-liveness.test.mjs
  git commit -m "feat(check-liveness): emit structured progress events in --json-file mode"
  ```

---

### Task 8: `liveness.py` — consume structured events through `ScanActivity`

**Files:**
- Modify: `scripts/liveness.py:1-35` (imports), `scripts/liveness.py:117-262`
  (`_verify_candidates`, `verify_jd_paths`)
- Test: `tests/test_liveness.py` (append, using the existing `_mock_popen`
  helper)

**Interfaces:**
- Consumes: `cli_art.new_scan_activity()` (Task 1); `check-liveness.mjs`'s new
  structured stderr events (Task 7).
- Produces: `liveness.verify_jd_paths(paths: list, activity=None) -> dict`
  (new optional param; return shape unchanged).

- [ ] **Step 1: Write a failing test**

  Append to `tests/test_liveness.py`:

  ```python
  class TestVerifyCandidatesActivity(unittest.TestCase):

      def setUp(self):
          self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_liveness_activity")
          os.makedirs(self.tmp_dir, exist_ok=True)
          self._real_expired_dir = jd_manager.EXPIRED_DIR
          jd_manager.EXPIRED_DIR = os.path.join(self.tmp_dir, "expired")
          self.jd_path = os.path.join(self.tmp_dir, "acme.json")
          with open(self.jd_path, "w", encoding="utf-8") as f:
              json.dump({"source_url": "https://acme.com/job/1", "job_title": "Test"}, f)

      def tearDown(self):
          jd_manager.EXPIRED_DIR = self._real_expired_dir
          for root, dirs, files in os.walk(self.tmp_dir, topdown=False):
              for name in files:
                  os.remove(os.path.join(root, name))
              for name in dirs:
                  os.rmdir(os.path.join(root, name))
          if os.path.exists(self.tmp_dir):
              os.rmdir(self.tmp_dir)

      @patch("liveness.subprocess.Popen")
      def test_structured_progress_line_routes_through_activity_step(self, mock_popen):
          progress_line = json.dumps({
              "type": "progress", "index": 1, "total": 1, "result": "active",
              "code": "apply_control_visible", "reason": None, "source_file": self.jd_path,
          }) + "\n"
          mock_popen.side_effect = _mock_popen(returncode=0, stdout=json.dumps([
              {"job_key": "abc", "source_file": self.jd_path, "url": "https://acme.com/job/1",
               "result": "active", "code": "apply_control_visible", "reason": None},
          ]), stderr_lines=[progress_line])

          activity = MagicMock()
          liveness.verify_jd_paths([self.jd_path], activity=activity)

          activity.step.assert_called_once()
          args = activity.step.call_args.args
          self.assertEqual(args[0], "success")
          self.assertEqual(args[1], "Verify")

      @patch("liveness.subprocess.Popen")
      @patch("liveness.cli_art.print_subprocess_output")
      def test_non_json_stderr_line_falls_back_to_raw_passthrough(self, mock_print_raw, mock_popen):
          mock_popen.side_effect = _mock_popen(returncode=0, stdout=json.dumps([
              {"job_key": "abc", "source_file": self.jd_path, "url": "https://acme.com/job/1",
               "result": "active", "code": "apply_control_visible", "reason": None},
          ]), stderr_lines=["Fatal: something unexpected\n"])

          activity = MagicMock()
          liveness.verify_jd_paths([self.jd_path], activity=activity)

          activity.step.assert_not_called()
          mock_print_raw.assert_called_once()
  ```

- [ ] **Step 2: Run test, verify it fails**

  Run: `python -m unittest tests.test_liveness.TestVerifyCandidatesActivity -v`
  Expected: FAIL with `TypeError: verify_jd_paths() got an unexpected keyword argument 'activity'`

- [ ] **Step 3: Implement**

  In `scripts/liveness.py`, add `import contextlib` and `import json` near
  the top if not already present (`json` is already imported; add
  `contextlib` alongside the existing `import datetime` /
  `import shutil` / `import subprocess` block).

  Add this module-level mapping near `SCRIPT_DIR` (current line 35):

  ```python
  # Maps check-liveness.mjs's structured progress-event `result` field to
  # this codebase's existing theme.py icon keys (success/warning/error --
  # there's no "likely_active"-specific icon, so it shares "warning" with
  # "uncertain").
  _LIVENESS_ICON_BY_RESULT = {
      "active": "success", "likely_active": "warning",
      "expired": "error", "uncertain": "warning",
  }


  @contextlib.contextmanager
  def _resolve_activity(activity):
      """Reuses a shared activity when the caller (scan.py's run_scan())
      already has one open; otherwise opens a fresh, self-contained one so
      the standalone `resume liveness` entry point (run_liveness_check(),
      with no scan preceding it) also gets the themed step-log rather than
      only benefiting when chained after a scan."""
      if activity is not None:
          yield activity
      else:
          with cli_art.new_scan_activity() as local_activity:
              yield local_activity
  ```

  In `_verify_candidates`, change the signature (current line 117) to
  `def _verify_candidates(candidates: list, activity=None) -> dict:`.

  Replace the stderr-reading loop (current lines 168-177):

  ```python
              try:
                  # Stream progress as the Node child writes it, instead of
                  # subprocess.run()'s communicate(), which buffers the
                  # entire stream and only hands it back after the process
                  # has already exited -- the progress "indicator" was
                  # replaying a finished transcript, not showing live
                  # progress (B21).
                  with _resolve_activity(activity) as resolved_activity:
                      resolved_activity.start_source(len(candidates), label="Checking")
                      for line in proc.stderr:
                          stripped = line.rstrip()
                          event = None
                          try:
                              event = json.loads(stripped)
                          except json.JSONDecodeError:
                              pass
                          if isinstance(event, dict) and event.get("type") == "progress":
                              icon_name = _LIVENESS_ICON_BY_RESULT.get(event.get("result"), "warning")
                              resolved_activity.step(icon_name, "Verify", _jd_label(event.get("source_file")))
                          else:
                              cli_art.print_subprocess_output(f"  {stripped}")
                  proc.wait(timeout=timeout_s)
  ```

  (The `except subprocess.TimeoutExpired:`/`finally:` blocks immediately
  below stay exactly as they are.)

  Update `verify_jd_paths` (current line 252) to accept and forward
  `activity`:

  ```python
  def verify_jd_paths(paths: list, activity=None) -> dict:
  ```

  ...and its body (current line 262) to `return _verify_candidates(_gather_candidates(paths), activity=activity)`.

- [ ] **Step 4: Run tests, verify pass**

  Run: `python -m unittest tests.test_liveness -v`
  Expected: PASS (all existing tests plus the 2 new ones)

- [ ] **Step 5: Thread `activity` from `scan.py` into the verify call**

  In `scripts/scan.py`, inside `run_scan()`'s `if verify and written_paths:`
  block (this is *outside* the `with cli_art.new_scan_activity()` block from
  Task 6, Step 3 — that's intentional, since fetching has already finished
  by this point). Open a second, separate activity here for the verify
  phase:

  ```python
      if verify and written_paths:
          paths_to_verify = list(written_paths.keys())
          if len(paths_to_verify) > VERIFY_CONFIRM_THRESHOLD:
              proceed = True
              if cli_art.console.is_terminal:
                  proceed = questionary.confirm(
                      f"{len(paths_to_verify)} new postings found -- verify all of them with a "
                      f"real browser check (~{len(paths_to_verify) * 16 // 60} min)? "
                      f"(No verifies just the first {VERIFY_CONFIRM_THRESHOLD}.)",
                      default=False, style=cli_art.QUESTIONARY_STYLE,
                  ).ask()
              if not proceed:
                  paths_to_verify = paths_to_verify[:VERIFY_CONFIRM_THRESHOLD]
          with cli_art.new_scan_activity() as verify_activity:
              verify_result = liveness.verify_jd_paths(paths_to_verify, activity=verify_activity)
  ```

  (Everything below `verify_result = ...` in this block stays at its
  current indentation and logic, just now inside the `with`.)

- [ ] **Step 6: Run the full test suite**

  Run: `python -m unittest discover -s tests -v 2>&1 | tail -30`
  Expected: PASS

- [ ] **Step 7: Commit**

  ```bash
  git add scripts/liveness.py scripts/scan.py tests/test_liveness.py
  git commit -m "feat(liveness): consume structured verify-pass events through ScanActivity"
  ```

---

## Manual verification (after all tasks)

- [ ] Run `resume scan` (or `python scripts/cli.py scan`) against a real or
  sandboxed profile and visually confirm: one continuous themed log across
  all four sources, a live-updating tally line, and (if any postings are
  written) a themed step-log during the verify pass — not the old mix of
  silent `logging.info`, bare `[i/N]` text, and raw Node stderr passthrough.
- [ ] Run `python scripts/cli.py liveness` (the standalone entry point, not
  chained after a scan) and confirm it also shows the themed step-log via
  `_resolve_activity`'s self-contained fallback.
