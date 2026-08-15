# Jobs Screen Action Triggers — Design

## Context: the broader Charmbracelet redesign

This is the third and final piece of sub-project 2 (see
[docs/superpowers/specs/2026-08-08-jobs-screen-design.md](2026-08-08-jobs-screen-design.md)),
which was itself split into three pieces:

1. JD data export bridge — done.
2. Split-pane list + detail screen — done.
3. **Action triggers** (this spec) — Liveness Check, Tailor Resume, Update
   Status, triggered from inside the Jobs screen.

Sub-project 2's own Non-Goals explicitly deferred this piece: "action
triggers... shells back to Python for real work with a spinner, then
reloads the export. That's piece 3, not touched here." This spec covers
all three actions together (not phased further), since their shared
plumbing — the subprocess contract, the reload mechanism, the spinner —
is most of the work, and phasing by action would mean re-deriving that
plumbing context three times.

## Problem

The Jobs screen (piece 2) is read-only: it shows real JD evaluation data,
but nothing in it can change anything. The actions a job seeker actually
wants to take from this view — check whether a posting is still live,
tailor a resume for it, mark it Applied/Interview/etc. — all still require
leaving the dashboard and going back to the interactive Python menu.

The real work behind each action already exists and already supports a
single JD, not just bulk operation: `liveness.verify_jd_paths(paths:
list)`, `orchestrator.run_pipeline(jd_path=...)`,
`jd_manager.save_application_status(jd_path, status)`. What's missing is
a way for the Go dashboard — which owns the terminal for the whole
session, unlike sub-project 1's one-shot prompt binaries — to invoke that
Python logic mid-session and reflect the result.

## Goals

- A new `scripts/dashboard_actions.py` CLI with three subcommands:
  `liveness <jd_path>`, `tailor <jd_path>`, `status <jd_path>
  <new_status>`, each taking a `--jobs-path <path>` option. Each does its
  real work via the existing Python functions above, then overwrites the
  file at `--jobs-path` with a fresh `picker.list_all_evaluated_jds()`
  dump before exiting — reusing the exact export shape piece 1 already
  established, not inventing a second contract.
- `dashboard.py`'s existing `_write_jobs_export()` (piece 1) and this new
  script's refresh both call a shared `_export_jobs_to(path: str) ->
  None` helper, rather than duplicating the dump-to-JSON logic.
- Two new flags Go receives from `dashboard.py`, alongside the existing
  `-path`/`-jobs-path`: `-python-path` (`sys.executable` — avoids
  invoking a bare `python3` that CLAUDE.md warns may resolve to an
  unrelated stray venv) and `-project-root`
  (`profile_paths.PROJECT_ROOT` — Go's own CWD is `dashboard/`, not the
  project root, since `dashboard.py` already launches `go run` with
  `cwd=DASHBOARD_DIR`).
- `JobsModel` gains three key bindings on the currently selected job:
  `l` (Liveness Check), `t` (Tailor Resume — only when `Status ==
  "Pending"`, matching the existing menu convention that tailoring
  targets Pending JDs), `u` (Update Status, opens a picker sub-state over
  `jd_manager.APPLICATION_STATUSES`).
- All three dispatch through one `runAction(action, jdPath string,
  extraArgs ...string) tea.Cmd` — bubbletea already runs `Cmd`s off the
  UI thread, so the blocking subprocess call inside it doesn't freeze
  rendering. A `bubbles/spinner` (already a dependency) renders while an
  action is in flight.
- On completion, `JobsModel` reloads `data.LoadJobs(jobsPath)` and
  re-selects the current job by `Path` (mirroring how
  `PipelineModel.WithReloadedData` already preserves selection across a
  reload).
- A failed action (non-zero exit) surfaces as a dismissible error message
  in the UI, not a crash.

## Non-Goals

- **No streaming progress.** The action subprocess runs to completion as
  one blocking call; Go only inspects its result afterward. A spinner is
  the only in-flight feedback — no live log tail from the subprocess's
  own console output.
- **No new validation logic duplicated in Go.** `status`'s `new_status`
  argument is validated against `jd_manager.APPLICATION_STATUSES` in
  Python (`dashboard_actions.py`), not re-validated in Go — Go's status
  picker only ever offers the real list, so an invalid value shouldn't
  reach the subprocess in practice, but the Python-side check stays as
  the actual guarantee.
- **No explicit `-profile` flag.** `RESUME_PROFILE` propagates through
  the whole process chain via normal OS environment inheritance
  (confirmed: `profile_paths.set_active_profile()` sets a real
  `os.environ` entry, and neither `dashboard.py`'s `subprocess.run()` nor
  Go's own `exec.Command` override `Env`, so the default
  inherit-from-parent behavior carries it all the way through). No new
  plumbing needed.
- **No retry logic.** A failed action can be retried by pressing the same
  key again; there's no automatic retry.

## Architecture

**`scripts/dashboard_actions.py`** (new):

```
python3 scripts/dashboard_actions.py liveness <jd_path> --jobs-path <path>
python3 scripts/dashboard_actions.py tailor <jd_path> --jobs-path <path>
python3 scripts/dashboard_actions.py status <jd_path> <new_status> --jobs-path <path>
```

Uses `argparse` with subparsers. Each subcommand:

- `liveness`: calls `liveness.verify_jd_paths([jd_path])`. Exit 0 unless
  the result dict has a truthy `"error"` key (a check that *ran* and came
  back "expired" is still a successful action — the JD's liveness state
  is a valid outcome, not a failure of the check itself).
- `tailor`: calls `orchestrator.run_pipeline(jd_path=jd_path)`, which
  returns `(completed_count, failed_count)`. Exit 0 only if
  `completed_count > 0`.
- `status`: validates `new_status` is in `jd_manager.APPLICATION_STATUSES`
  (exit non-zero with a clear message if not), then calls
  `jd_manager.save_application_status(jd_path, new_status)`. Always
  succeeds if validation passes (the underlying function has no failure
  return).

All three, on success, call `_export_jobs_to(args.jobs_path)` before
exiting 0. On any failure, print a one-line message to stderr and exit 1
— no export refresh on failure, so Go's reload after a failed action
just re-reads what was already there (nothing changed).

**`scripts/dashboard.py`** gains `_export_jobs_to(path: str) -> None`,
factored out of the existing `_write_jobs_export()`:

```python
def _export_jobs_to(path: str) -> None:
    rows = picker.list_all_evaluated_jds()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)


def _write_jobs_export(profile: str = None) -> str:
    if profile:
        profile_paths.set_active_profile(profile)
    fd, path = tempfile.mkstemp(suffix=".json", prefix="dashboard_jobs_")
    os.close(fd)
    _export_jobs_to(path)
    return path
```

`run()` gains two more `go run` arguments: `-python-path
{sys.executable}` and `-project-root {profile_paths.PROJECT_ROOT}`.

**Go side — `internal/ui/screens/jobs.go`** gains state:

```go
type JobsModel struct {
	// ... existing fields ...
	jobsPath      string
	pythonPath    string
	projectRoot   string
	spinner       spinner.Model
	actionInProgress string // "", "liveness", "tailor", "status"
	actionError   string
	statusPicker  bool
	statusCursor  int
}
```

`runAction` builds and runs the subprocess:

```go
func (m JobsModel) runAction(action, jdPath string, extraArgs ...string) tea.Cmd {
	return func() tea.Msg {
		args := append([]string{
			filepath.Join(m.projectRoot, "scripts", "dashboard_actions.py"),
			action, jdPath, "--jobs-path", m.jobsPath,
		}, extraArgs...)
		cmd := exec.Command(m.pythonPath, args...)
		cmd.Dir = m.projectRoot
		out, err := cmd.CombinedOutput()
		return jobsActionCompleteMsg{action: action, err: err, output: string(out)}
	}
}
```

On `jobsActionCompleteMsg`: clear `actionInProgress`; if `err != nil`, set
`actionError` from `output` (the combined stdout+stderr, matching what a
human running the command directly would see); otherwise reload via
`data.LoadJobs(m.jobsPath)`, reapply the filter, and re-select the
previously-current job by `Path` if it's still present in the reloaded
set.

**Key handling** (in priority order, matching `PipelineModel`'s existing
layered-interception pattern for `statusPicker`/`searchInput`):

1. If `actionInProgress != ""`: ignore all keys except nothing (actions
   aren't cancellable — killing a half-finished tailor/liveness run mid-
   flight risks leaving files partially written).
2. If `actionError != ""`: any key clears it, then that key is otherwise
   swallowed (so a dismiss doesn't also trigger an unrelated action).
3. If `statusPicker`: up/down move `statusCursor` through
   `jd_manager.APPLICATION_STATUSES`, enter dispatches `runAction("status",
   path, chosenStatus)` and sets `actionInProgress = "status"`, esc
   cancels back to the normal view.
4. Otherwise: existing up/down/f/q/esc handling, plus `l` → dispatch
   liveness, `t` → dispatch tailor (no-op if `CurrentJob().Status !=
   "Pending"`), `u` → open `statusPicker`.

## Error Handling

- **Action subprocess fails (non-zero exit):** `actionError` shows the
  captured combined output; the jobs list is *not* reloaded (nothing on
  disk changed, since `dashboard_actions.py` only refreshes the export on
  its own success path).
- **`dashboard_actions.py` itself fails to even start** (e.g.
  `pythonPath` is stale/wrong): `exec.Command(...).CombinedOutput()`
  returns an error with empty/minimal output; `actionError` falls back to
  the Go-side error text (`err.Error()`) when `output` is empty, so the
  user isn't shown a blank message.
- **Reload after success fails** (`LoadJobs` errors on the freshly
  written file — shouldn't happen if `dashboard_actions.py` succeeded,
  but defensively): falls back to keeping the pre-action `rows` in place
  and setting `actionError` to the load error, rather than wiping the
  list to empty.
- **`t` pressed on a Completed job:** no-op, not an error — matches how
  the existing menu's tailor action is simply not offered for Completed
  JDs, rather than offered-then-rejected.

## Testing

- **Python — `tests/test_dashboard_actions.py`:** one test per
  subcommand, each patching the underlying function
  (`liveness.verify_jd_paths`, `orchestrator.run_pipeline`,
  `jd_manager.save_application_status`) and `dashboard_actions._export_jobs_to`
  to assert: the right function is called with the right arguments, exit
  code matches the function's result (success/failure), and the export
  refresh only happens on success. Plus one test for `status`'s
  validation rejecting a value not in `APPLICATION_STATUSES` without
  calling `save_application_status` at all.
- **Python — `tests/test_dashboard.py`:** a test that `_write_jobs_export`
  still produces the same output shape now that it's built on
  `_export_jobs_to` (regression guard for the refactor), and that
  `run()`'s `subprocess.run` call now includes `-python-path` and
  `-project-root`.
- **Go — `internal/ui/screens/jobs_test.go`:** `runAction` isn't directly
  testable without actually spawning a subprocess (no fake-exec harness
  in this codebase), so tests instead cover the parts that don't need a
  real process: key-gating (`t` is a no-op on a Completed job without
  dispatching anything), status-picker cursor movement and cancellation,
  and — feeding a synthetic `jobsActionCompleteMsg` directly into
  `Update()` — that a success message clears `actionError` and triggers
  the reload-and-reselect path, and a failure message sets `actionError`
  without touching `rows`.
