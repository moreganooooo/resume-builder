# Scan + Verify Progress Consistency

## Problem

Job scanning (`scan.py` running `scan_jobright.py`, `scan_linkedin.py`,
`scan_ats.py`, `scan_boards.py`) and the liveness verify pass that follows it
(`liveness.py` driving `check-liveness.mjs`) are the first thing a user
watches the program do, but the four sources look like four different
programs while they run:

- `scan_jobright.py` / `scan_linkedin.py` narrate sparsely via ad hoc
  `cli_art.cli_info`/`cli_error` calls.
- `scan_ats.py` uses only `logging.info` — invisible to a normal user.
- `scan_boards.py` (and `scan_ats.py`, which reuses it) has its own
  bespoke `ProgressReporter` class — well-designed (running ETA math,
  explicitly built to avoid a "did it hang?" experience), but plain text,
  not themed.
- `liveness.py`'s verify pass streams genuinely live per-item progress from
  a Node subprocess (`check-liveness.mjs`), but as raw unstyled stderr
  lines passed straight through.

The finale is already consistent — every source converges on
`cli_art.render_scan_report()` — so the fracture is entirely in the
**during** experience, not the **after**.

Sequential execution is a hard constraint here, not a stylistic choice:
`scan.py`'s `run_scan()` calls each source's fetcher and blocks until it
returns its complete list (`for source in sources: jobs = fetch()`). True
concurrent multi-source progress would require reworking every fetcher's
internals (thread/async), a separate, larger decision explicitly deferred —
this design's component is built so that decision remains possible later
without a second UI rewrite, but does not implement it now.

## Design

### 1. Shared component: `cli_art.new_scan_activity()`

Added to `cli_art.py`, beside the existing `new_progress()` — not a new
package, so there's exactly one theme/progress system in the codebase.
Built on `rich.progress.Progress`, configured with just `SpinnerColumn` +
one task whose *description* is a live-updating tally (no bar, no
percentage column — most of these sources never know a grand total up
front). `Progress` is built on `rich.live.Live` and exposes `.console`;
printing through `progress.console.print()` while a task is live is
supported Rich behavior — it hoists permanent lines above the live region
instead of conflicting with it. That gives the two-part shape this design
wants: a scrolling, permanent step-log of completed items, with one pinned
line showing "what's happening right now."

```python
class ScanActivity:
    """Context-managed live activity display for a multi-source scan or
    verify pass: a pinned, live-updating tally line plus a permanent,
    themed step-log of completed items underneath it."""

    def step(self, icon_name: str, source: str, message: str) -> None:
        """Print one permanent themed line: icon (via
        theme.colorize_icon), source label, message. Mirrors
        ProgressReporter's per-item line, styled."""

    def tally(self, **counts: int) -> None:
        """Update the pinned line's description from named counts, e.g.
        tally(fetched=12, written=9, skipped=3, errors=0) ->
        'Scanning · Fetched 12 · Written 9 · Skipped 3 · Errors 0'.
        Count names deliberately match scan.py's existing per-source
        result dict keys (fetched/written/skipped) rather than inventing
        synonyms."""


def new_scan_activity(**kwargs) -> ScanActivity: ...
```

Internally reuses `ProgressReporter`'s existing running-average ETA math
(moved into `ScanActivity`, not reimplemented) for sources that do know a
total up front (`scan_ats.py`/`scan_boards.py`, and the liveness verify
pass, which knows candidate count before it starts).

This is purely the **during** experience.  `cli_art.render_scan_report()`
is unchanged and still runs once at the end.

### 2. `scan_jobright.py` / `scan_linkedin.py`

Each `fetch_jobright_jobs()` / `fetch_linkedin_jobs()` gains an optional
`activity: ScanActivity | None = None` parameter. Existing sparse
`cli_art.cli_info(...)` call sites become `activity.step("success",
"JobRight", ...)` (or `"warning"`/`"error"` as appropriate) — one line per
job found (JobRight) or per job found (LinkedIn), same information,
themed and folded into the shared log instead of ad hoc.

`activity=None` (the default) must be a fully valid no-op path — both
scripts are also runnable standalone (see `test_scan_ats.py` etc. and any
direct CLI use), and existing tests call these functions without an
activity object.

### 3. `scan_ats.py` / `scan_boards.py`

Retire the standalone `ProgressReporter` class. `scan_ats.py` already
calls `scan_boards.ProgressReporter(len(companies) + len(queries),
label="Checking")` — a single call site becomes
`activity.step(...)`/`activity.tally(...)` calls instead, reusing the
moved ETA logic from inside `ScanActivity`.

### 4. `scan.py`

`run_scan()` opens one `new_scan_activity()` context around its existing
`for source in sources:` loop and passes the same `activity` object into
every `fetch()` call — one continuous log spanning all four sources in a
single run, not four separate experiences stitched together.

### 5. Liveness verify pass

`check-liveness.mjs` currently writes human-readable lines to stderr
(`console.error(...)`) which `liveness.py` passes straight through via
`cli_art.print_subprocess_output`. Change, **gated behind the existing
`--json-file` flag** (`check-liveness.mjs` is also run standalone per its
own documented `Usage:` lines — that path is untouched): when invoked with
`--json-file`, it *additionally* emits one structured line per completed
check to stderr, e.g.:

```json
{"type": "progress", "index": 3, "total": 25, "result": "active", "company": "Acme", "title": "Data Engineer"}
```

`liveness.py`'s `for line in proc.stderr:` loop tries `json.loads(line)`
first:

- **Success** → format through `activity.step(...)`, mapping `result`
  (`active`/`likely_active`/`expired`/`uncertain`) to the existing
  success/warning/error icon set.
- **Failure** (a line that isn't a structured progress event — a genuine
  unexpected error from the Node side) → fall back to today's raw
  passthrough via `cli_art.print_subprocess_output`, so nothing is ever
  silently swallowed.

The final JSON results blob on stdout (what `liveness.py` actually parses
for outcomes) is unchanged.

### 6. Error handling

No new error-formatting convention. This plugs into what `cli_art.py`
already establishes as house rule: raw exception text never reaches the
user; `friendly_error`/`friendly_warning` give plain English plus a
concrete fix. `scan.py`'s existing `_ScanWarningCollector` /
`_summarize_warnings` grouping (e.g. "workday: posting text fetch failed
(HTTP 404) x44") is untouched — the step-log is additive; the grouped
summary still feeds `render_scan_report()` exactly as it does today.

## Files touched

- `scripts/cli_art.py` — new `ScanActivity` class, `new_scan_activity()`.
- `scripts/scan_jobright.py` — `activity` param, `cli_info`/`cli_error`
  call sites become `activity.step(...)`.
- `scripts/scan_linkedin.py` — same.
- `scripts/scan_boards.py` — `ProgressReporter` retired; ETA math moves
  into `ScanActivity`.
- `scripts/scan_ats.py` — `ProgressReporter` call site becomes
  `activity` calls.
- `scripts/scan.py` — `run_scan()` opens one `new_scan_activity()` around
  the source loop, threads it into each `fetch()`.
- `scripts/liveness.py` — `verify_jd_paths()`'s stderr loop tries
  structured-JSON-first with raw-line fallback.
- `scripts/check-liveness.mjs` — emits structured progress lines to
  stderr, gated behind `--json-file`.
- `tests/test_cli_art.py` — new file; covers `ScanActivity.step()`/
  `.tally()` formatting.
- `tests/test_liveness.py` — new test for the JSON-line-vs-raw-line
  fallback parsing.

No changes to any fetcher's return value or to `run_scan()`'s return
contract — `activity` is optional and additive, so
`test_scan.py`/`test_scan_ats.py`/`test_scan_boards.py`/
`test_scan_linkedin.py` keep passing unmodified.

## Explicitly out of scope

- Concurrent/parallel source fetching. Sequential execution stays exactly
  as it is; `ScanActivity` is shaped so that a later move to concurrency
  is a backend change (threaded fetchers updating the same `activity`)
  rather than a second UI rewrite, but that move itself is not part of
  this design.
- Any change to `render_scan_report()` or the final summary shape.
- Any of the other under-styled scripts identified but not part of the
  scan→verify journey (`situational_roles.py`, `maintenance.py`,
  `batch_evaluate.py`, bullet-bank maintenance scripts, etc.) — those
  belong to the separately-sequenced "other user-facing workflows" pass.
- Bubble Tea/Lip Gloss/Bubbles v2 migration for the Go dashboard —
  unrelated runtime, tracked as its own future item.
