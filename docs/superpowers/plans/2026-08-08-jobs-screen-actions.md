# Jobs Screen Action Triggers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the Jobs screen trigger real work (Liveness Check, Tailor Resume, Update Status) on the selected job, via a new Python CLI the Go dashboard shells out to mid-session, then reload fresh data afterward.

**Architecture:** A new `scripts/dashboard_actions.py` CLI (`liveness`/`tailor`/`status` subcommands) does the real work via existing Python functions, then refreshes the same `--jobs-path` file the dashboard is reading from. `JobsModel` gains `l`/`t`/`u` key bindings that dispatch a blocking subprocess call as a `tea.Cmd` (bubbletea already runs these off the UI thread), show a `bubbles/spinner` while in flight, and reload+reselect on completion.

**Tech Stack:** Go 1.24 (`bubbles/spinner`, already a dependency), Python 3.10+ (`argparse`, stdlib `unittest`).

## Global Constraints

- `go run` only — never `go build`.
- No streaming progress from the action subprocess — a spinner is the only in-flight feedback; Go only inspects the result after the subprocess exits.
- `status`'s validation against `jd_manager.APPLICATION_STATUSES` lives in Python (`dashboard_actions.py`), not duplicated in Go.
- No `-profile` flag — `RESUME_PROFILE` propagates through the process chain via normal OS environment inheritance (verified: `set_active_profile()` sets a real `os.environ` entry; neither `dashboard.py`'s `subprocess.run()` nor Go's `exec.Command` override `Env`).
- `NewJobsModel`'s existing signature is not changed — action config (`jobsPath`/`pythonPath`/`projectRoot`) is set via a new `WithActionConfig()` fluent setter, so none of the 5 existing `NewJobsModel(...)` call sites in `jobs_test.go` (from the prior plan) need editing.

---

### Task 1: `_export_jobs_to` refactor

**Files:**
- Modify: `scripts/dashboard.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Produces: `dashboard._export_jobs_to(path: str) -> None` — consumed by Task 2's `dashboard_actions.py` and by this task's own refactored `_write_jobs_export()`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_dashboard.py` (add `import tempfile` to the top alongside the existing imports):

```python
class TestExportJobsTo(unittest.TestCase):

    @patch("dashboard.picker.list_all_evaluated_jds")
    def test_writes_rows_to_the_given_path(self, mock_list):
        rows = [{"path": "a.json", "status": "Pending"}]
        mock_list.return_value = rows
        path = os.path.join(tempfile.gettempdir(), "test_export_jobs_to.json")
        try:
            dashboard._export_jobs_to(path)
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(json.load(f), rows)
        finally:
            os.remove(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_dashboard -v -k TestExportJobsTo`
Expected: FAIL — `AttributeError: module 'dashboard' has no attribute '_export_jobs_to'`.

- [ ] **Step 3: Refactor `_write_jobs_export` to build on the new helper**

In `scripts/dashboard.py`, replace:

```python
def _write_jobs_export(profile: str = None) -> str:
    """Writes picker.list_all_evaluated_jds() to a fresh temp JSON file
    and returns its path, for the Go dashboard's -jobs-path flag. Always
    a fresh snapshot, never cached -- evaluation/liveness/application
    data changes between dashboard launches via the Python menu, so a
    stale export would be actively misleading. Only touches the active
    profile when an explicit one is given (mirrors _handle_bootstrap()'s
    own pattern in menu.py) -- the real call site (run(), with
    profile=None) never needs the reload."""
    if profile:
        profile_paths.set_active_profile(profile)
    rows = picker.list_all_evaluated_jds()
    fd, path = tempfile.mkstemp(suffix=".json", prefix="dashboard_jobs_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return path
```

with:

```python
def _export_jobs_to(path: str) -> None:
    """Writes picker.list_all_evaluated_jds() to path, overwriting
    whatever's there. Shared by _write_jobs_export() (a fresh temp file
    per dashboard launch) and dashboard_actions.py (which refreshes the
    same file an already-running dashboard session is reading from,
    after a real action changes the underlying JD data)."""
    rows = picker.list_all_evaluated_jds()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f)


def _write_jobs_export(profile: str = None) -> str:
    """Writes picker.list_all_evaluated_jds() to a fresh temp JSON file
    and returns its path, for the Go dashboard's -jobs-path flag. Always
    a fresh snapshot, never cached -- evaluation/liveness/application
    data changes between dashboard launches via the Python menu, so a
    stale export would be actively misleading. Only touches the active
    profile when an explicit one is given (mirrors _handle_bootstrap()'s
    own pattern in menu.py) -- the real call site (run(), with
    profile=None) never needs the reload."""
    if profile:
        profile_paths.set_active_profile(profile)
    fd, path = tempfile.mkstemp(suffix=".json", prefix="dashboard_jobs_")
    os.close(fd)
    _export_jobs_to(path)
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_dashboard -v`
Expected: PASS (all tests in the file, including the pre-existing `TestWriteJobsExport` class — the refactor preserves `_write_jobs_export`'s exact public behavior).

- [ ] **Step 5: Commit**

```bash
git add scripts/dashboard.py tests/test_dashboard.py
git commit -m "refactor: extract _export_jobs_to from _write_jobs_export"
```

---

### Task 2: `dashboard_actions.py` CLI

**Files:**
- Create: `scripts/dashboard_actions.py`
- Test: `tests/test_dashboard_actions.py`

**Interfaces:**
- Consumes: `dashboard._export_jobs_to` (Task 1), `liveness.verify_jd_paths` (existing), `orchestrator.run_pipeline` (existing), `jd_manager.APPLICATION_STATUSES`/`save_application_status` (existing).
- Produces: `dashboard_actions._liveness(jd_path, jobs_path) -> int`, `dashboard_actions._tailor(jd_path, jobs_path) -> int`, `dashboard_actions._status(jd_path, new_status, jobs_path) -> int` — consumed by Task 2's own `main()`, invoked by Go via subprocess in Task 4.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dashboard_actions.py`:

```python
import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import dashboard_actions  # noqa: E402


class TestLiveness(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_success_refreshes_export_and_returns_zero(self, mock_verify, mock_export):
        mock_verify.return_value = {"active": 1, "likely_active": 0, "expired": 0, "uncertain": 0, "moved": 0}
        code = dashboard_actions._liveness("jds/morgan/a.json", "/tmp/jobs.json")
        mock_verify.assert_called_once_with(["jds/morgan/a.json"])
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.liveness.verify_jd_paths")
    def test_error_result_returns_nonzero_without_refreshing(self, mock_verify, mock_export):
        mock_verify.return_value = {"error": True}
        code = dashboard_actions._liveness("jds/morgan/a.json", "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestTailor(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_success_refreshes_export_and_returns_zero(self, mock_run, mock_export):
        mock_run.return_value = (1, 0)
        code = dashboard_actions._tailor("jds/morgan/a.json", "/tmp/jobs.json")
        mock_run.assert_called_once_with(jd_path="jds/morgan/a.json")
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.orchestrator.run_pipeline")
    def test_zero_completed_returns_nonzero_without_refreshing(self, mock_run, mock_export):
        mock_run.return_value = (0, 1)
        code = dashboard_actions._tailor("jds/morgan/a.json", "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_export.assert_not_called()


class TestStatus(unittest.TestCase):

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.save_application_status")
    def test_valid_status_refreshes_export_and_returns_zero(self, mock_save, mock_export):
        code = dashboard_actions._status("jds/morgan/a.json", "Applied", "/tmp/jobs.json")
        mock_save.assert_called_once_with("jds/morgan/a.json", "Applied")
        mock_export.assert_called_once_with("/tmp/jobs.json")
        self.assertEqual(code, 0)

    @patch("dashboard_actions.dashboard._export_jobs_to")
    @patch("dashboard_actions.jd_manager.save_application_status")
    def test_invalid_status_rejected_without_saving(self, mock_save, mock_export):
        code = dashboard_actions._status("jds/morgan/a.json", "NotARealStatus", "/tmp/jobs.json")
        self.assertEqual(code, 1)
        mock_save.assert_not_called()
        mock_export.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m unittest tests.test_dashboard_actions -v`
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'dashboard_actions'`.

- [ ] **Step 3: Write the implementation**

Create `scripts/dashboard_actions.py`:

```python
"""dashboard_actions.py -- CLI the Go dashboard shells out to mid-session
to trigger real work (Liveness Check, Tailor Resume, Update Status) on a
single JD, from inside the Jobs screen (dashboard/internal/ui/screens/
jobs.go). Each subcommand does its real work via the existing Python
functions, then refreshes the same --jobs-path file the dashboard is
reading from (via dashboard._export_jobs_to()) so the Go side can reload
fresh state after the subprocess returns.

See docs/superpowers/specs/2026-08-08-jobs-screen-actions-design.md.
"""

import argparse
import sys

import dashboard
import jd_manager
import liveness
import orchestrator


def _liveness(jd_path: str, jobs_path: str) -> int:
    result = liveness.verify_jd_paths([jd_path])
    if result.get("error"):
        print(f"liveness check failed for {jd_path}", file=sys.stderr)
        return 1
    dashboard._export_jobs_to(jobs_path)
    return 0


def _tailor(jd_path: str, jobs_path: str) -> int:
    completed, _failed = orchestrator.run_pipeline(jd_path=jd_path)
    if completed == 0:
        print(f"tailoring failed for {jd_path}", file=sys.stderr)
        return 1
    dashboard._export_jobs_to(jobs_path)
    return 0


def _status(jd_path: str, new_status: str, jobs_path: str) -> int:
    if new_status not in jd_manager.APPLICATION_STATUSES:
        print(
            f"invalid status {new_status!r} -- must be one of {jd_manager.APPLICATION_STATUSES}",
            file=sys.stderr,
        )
        return 1
    jd_manager.save_application_status(jd_path, new_status)
    dashboard._export_jobs_to(jobs_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    liveness_parser = subparsers.add_parser("liveness")
    liveness_parser.add_argument("jd_path")
    liveness_parser.add_argument("--jobs-path", required=True)

    tailor_parser = subparsers.add_parser("tailor")
    tailor_parser.add_argument("jd_path")
    tailor_parser.add_argument("--jobs-path", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("jd_path")
    status_parser.add_argument("new_status")
    status_parser.add_argument("--jobs-path", required=True)

    args = parser.parse_args()

    if args.command == "liveness":
        return _liveness(args.jd_path, args.jobs_path)
    if args.command == "tailor":
        return _tailor(args.jd_path, args.jobs_path)
    if args.command == "status":
        return _status(args.jd_path, args.new_status, args.jobs_path)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_dashboard_actions -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/dashboard_actions.py tests/test_dashboard_actions.py
git commit -m "feat: add dashboard_actions.py CLI for liveness/tailor/status actions"
```

---

### Task 3: `dashboard.py` gains `-python-path`/`-project-root`

**Files:**
- Modify: `scripts/dashboard.py`
- Modify: `tests/test_dashboard.py`

**Interfaces:**
- Produces: `run()`'s `go run` invocation now includes `-python-path {sys.executable}` and `-project-root {profile_paths.PROJECT_ROOT}` — consumed by Task 7's `main.go` flags.

- [ ] **Step 1: Update the failing test**

In `tests/test_dashboard.py`'s `TestRun.test_launches_go_run_with_the_profile_data_dir`, extend the assertions:

```python
    @patch("dashboard.picker.list_all_evaluated_jds", return_value=[])
    @patch("dashboard.subprocess.run")
    @patch("dashboard.os.path.exists", return_value=True)
    @patch("dashboard.go_available", return_value=True)
    def test_launches_go_run_with_the_profile_data_dir(self, mock_go, mock_exists, mock_subproc, mock_list):
        mock_subproc.return_value = MagicMock(returncode=0)
        success, message = dashboard.run("morgan")
        self.assertTrue(success)
        expected_data_dir = dashboard.profile_paths.data_dir("morgan")
        args = mock_subproc.call_args[0][0]
        self.assertEqual(args[0], "go")
        self.assertEqual(args[1], "run")
        self.assertEqual(args[2], ".")
        self.assertEqual(args[3], "-path")
        self.assertEqual(args[4], expected_data_dir)
        self.assertEqual(args[5], "-jobs-path")
        self.assertTrue(args[6])  # a real temp path was generated; cleanup itself is TestRunCleansUpJobsExport's job
        self.assertEqual(args[7], "-python-path")
        self.assertEqual(args[8], dashboard.sys.executable)
        self.assertEqual(args[9], "-project-root")
        self.assertEqual(args[10], dashboard.profile_paths.PROJECT_ROOT)
        self.assertEqual(mock_subproc.call_args[1], {"cwd": dashboard.DASHBOARD_DIR})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && python -m unittest tests.test_dashboard -v -k test_launches_go_run_with_the_profile_data_dir`
Expected: FAIL — `IndexError: list index out of range` (args only has 7 elements today).

- [ ] **Step 3: Add the new flags**

In `scripts/dashboard.py`, add `import sys` to the top imports, and update `run()`:

```python
import json
import os
import shutil
import subprocess
import sys
import tempfile

import picker
import profile_paths
```

```python
    jobs_path = _write_jobs_export(profile)
    try:
        result = subprocess.run(
            [
                "go", "run", ".",
                "-path", data_dir,
                "-jobs-path", jobs_path,
                "-python-path", sys.executable,
                "-project-root", profile_paths.PROJECT_ROOT,
            ],
            cwd=DASHBOARD_DIR,
        )
    finally:
        os.remove(jobs_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && python -m unittest tests.test_dashboard -v`
Expected: PASS (all tests in the file — the two other `subprocess.run`-invoking tests, `test_returns_false_when_dashboard_process_exits_nonzero` and the `TestRunCleansUpJobsExport` class, don't assert on the full args list, only index 6 or general call presence, so they're unaffected by the new trailing args).

- [ ] **Step 5: Commit**

```bash
git add scripts/dashboard.py tests/test_dashboard.py
git commit -m "feat: pass python interpreter and project root to the Go dashboard"
```

---

### Task 4: Go — action dispatch infrastructure (Liveness Check, Tailor Resume)

**Files:**
- Modify: `dashboard/internal/ui/screens/jobs.go`
- Modify: `dashboard/internal/ui/screens/jobs_test.go`

**Interfaces:**
- Consumes: `data.LoadJobs` (existing, from the prior plan).
- Produces: `(m JobsModel) WithActionConfig(jobsPath, pythonPath, projectRoot string) JobsModel`, `jobsActionCompleteMsg{action string, err error, output string}` — consumed by Task 5 (status picker dispatches through the same `runAction`) and Task 6 (rendering reads `actionInProgress`/`actionError`).

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/internal/ui/screens/jobs_test.go` (add `"fmt"`, `"os"`, `"path/filepath"` to the import block):

```go
func TestWithActionConfigSetsFields(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m = m.WithActionConfig("/tmp/jobs.json", "/tmp/python3", "/tmp/project")

	if m.jobsPath != "/tmp/jobs.json" || m.pythonPath != "/tmp/python3" || m.projectRoot != "/tmp/project" {
		t.Fatalf("expected action config fields set, got jobsPath=%q pythonPath=%q projectRoot=%q", m.jobsPath, m.pythonPath, m.projectRoot)
	}
}

func TestLPressDispatchesLivenessAction(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m = m.WithActionConfig("/tmp/jobs.json", "python3", "/tmp")

	m, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'l'}})

	if m.actionInProgress != "liveness" {
		t.Fatalf("expected actionInProgress %q, got %q", "liveness", m.actionInProgress)
	}
	if cmd == nil {
		t.Fatal("expected a command to be dispatched")
	}
}

func TestTPressNoOpOnCompletedJob(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown}) // select the Completed row (Beta)
	if job, _ := m.CurrentJob(); job.Status != "Completed" {
		t.Fatalf("test setup: expected cursor on a Completed job, got %+v", job)
	}

	m, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'t'}})

	if m.actionInProgress != "" {
		t.Fatalf("expected no action dispatched for a Completed job, got %q", m.actionInProgress)
	}
	if cmd != nil {
		t.Fatal("expected no command dispatched")
	}
}

func TestKeysIgnoredWhileActionInProgress(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m.actionInProgress = "tailor"

	m, cmd := m.Update(tea.KeyMsg{Type: tea.KeyDown})

	if m.cursor != 0 {
		t.Fatalf("expected cursor unchanged while action in progress, got %d", m.cursor)
	}
	if cmd != nil {
		t.Fatal("expected no command while an action is in progress")
	}
}

func TestKeyPressDismissesActionError(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m.actionError = "something failed"

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})

	if m.actionError != "" {
		t.Fatal("expected actionError cleared by keypress")
	}
	if m.cursor != 0 {
		t.Fatalf("expected the dismissing keypress itself to be swallowed, cursor should stay 0, got %d", m.cursor)
	}
}

func TestActionCompleteMsgSuccessReloadsAndReselects(t *testing.T) {
	dir := t.TempDir()
	jobsPath := filepath.Join(dir, "jobs.json")
	initial := `[{"path":"a.json","status":"Pending","company":"Acme","title":"Role A","evaluation":{"composite_score":4.5}}]`
	if err := os.WriteFile(jobsPath, []byte(initial), 0o644); err != nil {
		t.Fatalf("failed to seed jobs file: %v", err)
	}

	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m = m.WithActionConfig(jobsPath, "python3", dir)
	m.actionInProgress = "liveness"

	// Simulate the export having been refreshed with different data by the
	// time the action completes.
	refreshed := `[{"path":"a.json","status":"Pending","company":"Acme Updated","title":"Role A","evaluation":{"composite_score":4.9}}]`
	if err := os.WriteFile(jobsPath, []byte(refreshed), 0o644); err != nil {
		t.Fatalf("failed to update jobs file: %v", err)
	}

	m, _ = m.Update(jobsActionCompleteMsg{action: "liveness"})

	if m.actionInProgress != "" {
		t.Fatalf("expected actionInProgress cleared, got %q", m.actionInProgress)
	}
	if len(m.rows) != 1 || m.rows[0].Company != "Acme Updated" {
		t.Fatalf("expected reloaded rows to reflect the refreshed export, got %+v", m.rows)
	}
}

func TestActionCompleteMsgFailureSetsErrorWithoutReloading(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m = m.WithActionConfig("/does/not/matter.json", "python3", "/tmp")
	m.actionInProgress = "tailor"

	m, _ = m.Update(jobsActionCompleteMsg{action: "tailor", err: fmt.Errorf("boom"), output: "tailoring failed: rate limited"})

	if m.actionInProgress != "" {
		t.Fatalf("expected actionInProgress cleared, got %q", m.actionInProgress)
	}
	if m.actionError != "tailoring failed: rate limited" {
		t.Fatalf("expected actionError from output, got %q", m.actionError)
	}
	if len(m.rows) != 2 {
		t.Fatalf("expected rows untouched on failure, got %d", len(m.rows))
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && go test ./internal/ui/screens/... -run "TestWithActionConfig|TestLPressDispatches|TestTPressNoOp|TestKeysIgnored|TestKeyPressDismisses|TestActionCompleteMsg" -v`
Expected: FAIL to compile — `undefined: JobsModel.WithActionConfig`, `undefined: jobsActionCompleteMsg`, `m.jobsPath`/`m.actionInProgress`/`m.actionError` undefined fields.

- [ ] **Step 3: Write the implementation**

In `dashboard/internal/ui/screens/jobs.go`, update the import block:

```go
import (
	"fmt"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)
```

Add fields to `JobsModel`:

```go
type JobsModel struct {
	rows          []model.JobRow
	filtered      []model.JobRow
	cursor        int
	filter        string // "all", "pending", "completed"
	width, height int
	theme         theme.Theme

	jobsPath      string
	pythonPath    string
	projectRoot   string
	actionInProgress string // "", "liveness", "tailor", "status"
	actionError   string
}

// jobsActionCompleteMsg is emitted when a dashboard_actions.py subprocess
// finishes. output is stdout+stderr combined, used as the error message
// on failure (matches what a human running the command directly sees).
type jobsActionCompleteMsg struct {
	action string
	err    error
	output string
}

// WithActionConfig sets the fields needed to dispatch actions
// (liveness/tailor/status via dashboard_actions.py). Separate from
// NewJobsModel so existing callers/tests that don't exercise actions
// don't need updating.
func (m JobsModel) WithActionConfig(jobsPath, pythonPath, projectRoot string) JobsModel {
	m.jobsPath = jobsPath
	m.pythonPath = pythonPath
	m.projectRoot = projectRoot
	return m
}
```

Add `runAction` and `reloadAfterAction`:

```go
// runAction builds and runs a dashboard_actions.py subprocess. Bubbletea
// runs the returned Cmd off the UI thread, so this blocking call doesn't
// freeze rendering.
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

// reloadAfterAction re-reads m.jobsPath (freshly written by a successful
// dashboard_actions.py run) and re-selects the previously-current job by
// Path, mirroring PipelineModel.WithReloadedData's selection-preserving
// reload.
func (m JobsModel) reloadAfterAction() JobsModel {
	rows, err := data.LoadJobs(m.jobsPath)
	if err != nil {
		m.actionError = err.Error()
		return m
	}
	var currentPath string
	if job, ok := m.CurrentJob(); ok {
		currentPath = job.Path
	}
	m.rows = rows
	m.applyFilter()
	if currentPath != "" {
		for i, r := range m.filtered {
			if r.Path == currentPath {
				m.cursor = i
				break
			}
		}
	}
	return m
}
```

Replace `Update`:

```go
// Update handles input for the jobs screen.
func (m JobsModel) Update(msg tea.Msg) (JobsModel, tea.Cmd) {
	switch msg := msg.(type) {
	case jobsActionCompleteMsg:
		m.actionInProgress = ""
		if msg.err != nil {
			m.actionError = strings.TrimSpace(msg.output)
			if m.actionError == "" {
				m.actionError = msg.err.Error()
			}
			return m, nil
		}
		return m.reloadAfterAction(), nil

	case tea.KeyMsg:
		if m.actionInProgress != "" {
			return m, nil
		}
		if m.actionError != "" {
			m.actionError = ""
			return m, nil
		}
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.filtered)-1 {
				m.cursor++
			}
		case "f":
			m.filter = nextJobsFilter(m.filter)
			m.applyFilter()
		case "l":
			if job, ok := m.CurrentJob(); ok {
				m.actionInProgress = "liveness"
				return m, m.runAction("liveness", job.Path)
			}
		case "t":
			if job, ok := m.CurrentJob(); ok && job.Status == "Pending" {
				m.actionInProgress = "tailor"
				return m, m.runAction("tailor", job.Path)
			}
		case "q", "esc":
			return m, func() tea.Msg { return JobsClosedMsg{} }
		}
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
	}
	return m, nil
}
```

Note: this replaces the `Update` method entirely — the `statusPicker`/spinner branches come in Tasks 5-6; this step deliberately omits them so Task 4's tests (which don't touch `u` or the spinner) pass on their own first.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && go test ./internal/ui/screens/... -v`
Expected: PASS — every test in the package (including all pre-existing ones from the prior plan; this task must not regress `TestFilterCyclesAllPendingCompletedAll`, `TestQPressEmitsJobsClosedMsg`, etc.).

- [ ] **Step 5: Commit**

```bash
git add dashboard/internal/ui/screens/jobs.go dashboard/internal/ui/screens/jobs_test.go
git commit -m "feat(dashboard): add liveness/tailor action dispatch to JobsModel"
```

---

### Task 5: Go — status picker sub-state (Update Status)

**Files:**
- Modify: `dashboard/internal/ui/screens/jobs.go`
- Modify: `dashboard/internal/ui/screens/jobs_test.go`

**Interfaces:**
- Consumes: `runAction` (Task 4).
- Produces: `jobsApplicationStatuses []string`, `(m JobsModel) handleStatusPickerKey(msg tea.KeyMsg) (JobsModel, tea.Cmd)` — consumed by Task 6's rendering (`overlayStatusPicker`).

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/internal/ui/screens/jobs_test.go`:

```go
func TestUOpensStatusPicker(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'u'}})
	if !m.statusPicker {
		t.Fatal("expected statusPicker to open")
	}
	if m.statusCursor != 0 {
		t.Fatalf("expected statusCursor reset to 0, got %d", m.statusCursor)
	}
}

func TestStatusPickerCursorClampsAtBoundaries(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'u'}})

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyUp})
	if m.statusCursor != 0 {
		t.Fatalf("expected statusCursor clamped to 0, got %d", m.statusCursor)
	}

	for range jobsApplicationStatuses {
		m, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	}
	if m.statusCursor != len(jobsApplicationStatuses)-1 {
		t.Fatalf("expected statusCursor clamped to %d, got %d", len(jobsApplicationStatuses)-1, m.statusCursor)
	}
}

func TestStatusPickerEscCancels(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'u'}})
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	if m.statusPicker {
		t.Fatal("expected statusPicker to close on esc")
	}
	if m.actionInProgress != "" {
		t.Fatal("expected no action dispatched on cancel")
	}
}

func TestStatusPickerEnterDispatchesStatusAction(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m = m.WithActionConfig("/tmp/jobs.json", "python3", "/tmp")
	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'u'}})

	m, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEnter})

	if m.statusPicker {
		t.Fatal("expected statusPicker closed after enter")
	}
	if m.actionInProgress != "status" {
		t.Fatalf("expected actionInProgress %q, got %q", "status", m.actionInProgress)
	}
	if cmd == nil {
		t.Fatal("expected a command to be dispatched")
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && go test ./internal/ui/screens/... -run "TestUOpensStatusPicker|TestStatusPickerCursor|TestStatusPickerEsc|TestStatusPickerEnter" -v`
Expected: FAIL to compile — `m.statusPicker`/`m.statusCursor` undefined fields, `undefined: jobsApplicationStatuses`.

- [ ] **Step 3: Write the implementation**

In `dashboard/internal/ui/screens/jobs.go`, add fields to `JobsModel`:

```go
	statusPicker bool
	statusCursor int
```

Add the status list and picker key handler:

```go
// jobsApplicationStatuses must match jd_manager.APPLICATION_STATUSES
// exactly (scripts/jd_manager.py) -- Python is the real validator
// (dashboard_actions.py's status subcommand rejects anything else), this
// is just what the picker offers.
var jobsApplicationStatuses = []string{"Applied", "Responded", "Interview", "Offer", "Rejected", "Withdrawn"}

func (m JobsModel) handleStatusPickerKey(msg tea.KeyMsg) (JobsModel, tea.Cmd) {
	switch msg.String() {
	case "esc":
		m.statusPicker = false
		return m, nil
	case "up", "k":
		if m.statusCursor > 0 {
			m.statusCursor--
		}
	case "down", "j":
		if m.statusCursor < len(jobsApplicationStatuses)-1 {
			m.statusCursor++
		}
	case "enter":
		m.statusPicker = false
		if job, ok := m.CurrentJob(); ok {
			chosen := jobsApplicationStatuses[m.statusCursor]
			m.actionInProgress = "status"
			return m, m.runAction("status", job.Path, chosen)
		}
	}
	return m, nil
}
```

In `Update`, insert the `statusPicker` interception and the `u` key, matching where Task 4 left the `tea.KeyMsg` case:

```go
	case tea.KeyMsg:
		if m.actionInProgress != "" {
			return m, nil
		}
		if m.actionError != "" {
			m.actionError = ""
			return m, nil
		}
		if m.statusPicker {
			return m.handleStatusPickerKey(msg)
		}
		switch msg.String() {
		case "up", "k":
			if m.cursor > 0 {
				m.cursor--
			}
		case "down", "j":
			if m.cursor < len(m.filtered)-1 {
				m.cursor++
			}
		case "f":
			m.filter = nextJobsFilter(m.filter)
			m.applyFilter()
		case "l":
			if job, ok := m.CurrentJob(); ok {
				m.actionInProgress = "liveness"
				return m, m.runAction("liveness", job.Path)
			}
		case "t":
			if job, ok := m.CurrentJob(); ok && job.Status == "Pending" {
				m.actionInProgress = "tailor"
				return m, m.runAction("tailor", job.Path)
			}
		case "u":
			if _, ok := m.CurrentJob(); ok {
				m.statusPicker = true
				m.statusCursor = 0
			}
		case "q", "esc":
			return m, func() tea.Msg { return JobsClosedMsg{} }
		}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && go test ./internal/ui/screens/... -v`
Expected: PASS — every test in the package.

- [ ] **Step 5: Commit**

```bash
git add dashboard/internal/ui/screens/jobs.go dashboard/internal/ui/screens/jobs_test.go
git commit -m "feat(dashboard): add status picker sub-state to JobsModel"
```

---

### Task 6: Go — spinner, error bar, status picker rendering

**Files:**
- Modify: `dashboard/internal/ui/screens/jobs.go`
- Modify: `dashboard/internal/ui/screens/jobs_test.go`

**Interfaces:**
- Consumes: `actionInProgress`/`actionError`/`statusPicker`/`statusCursor`/`jobsApplicationStatuses` (Tasks 4-5).
- Produces: updated `View()` showing a spinner during an action, an error bar on failure, and the status picker overlaid on the sidebar list.

- [ ] **Step 1: Write the failing tests**

Append to `dashboard/internal/ui/screens/jobs_test.go`:

```go
func TestViewShowsSpinnerWhileActionInProgress(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m.actionInProgress = "tailor"
	rendered := ansi.Strip(m.View())
	if !strings.Contains(rendered, "Tailoring resume") {
		t.Fatalf("expected action status line, got %q", rendered)
	}
}

func TestViewShowsActionError(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m.actionError = "network timeout"
	rendered := ansi.Strip(m.View())
	if !strings.Contains(rendered, "network timeout") {
		t.Fatalf("expected error message rendered, got %q", rendered)
	}
}

func TestRenderSidebarListOverlaysStatusPickerWhenOpen(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m.statusPicker = true
	rendered := ansi.Strip(m.renderSidebarList(40, 25))
	if !strings.Contains(rendered, "Set status:") {
		t.Fatalf("expected status picker overlay, got %q", rendered)
	}
	for _, want := range jobsApplicationStatuses {
		if !strings.Contains(rendered, want) {
			t.Fatalf("expected status option %q in overlay, got %q", want, rendered)
		}
	}
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd dashboard && go test ./internal/ui/screens/... -run "TestViewShowsSpinner|TestViewShowsActionError|TestRenderSidebarListOverlaysStatusPicker" -v`
Expected: FAIL — "Tailoring resume"/error text/"Set status:" not found in output (the current `View()`/`renderSidebarList` don't render any of this yet).

- [ ] **Step 3: Write the implementation**

In `dashboard/internal/ui/screens/jobs.go`, add `"github.com/charmbracelet/bubbles/spinner"` to the import block, add a `spinner spinner.Model` field to `JobsModel`, and initialize it in `NewJobsModel`:

```go
type JobsModel struct {
	// ... existing fields from Tasks 4-5 ...
	spinner spinner.Model
}

func NewJobsModel(t theme.Theme, rows []model.JobRow, width, height int) JobsModel {
	m := JobsModel{
		rows:    rows,
		filter:  "all",
		width:   width,
		height:  height,
		theme:   t,
		spinner: spinner.New(spinner.WithSpinner(spinner.Dot)),
	}
	m.applyFilter()
	return m
}
```

Replace `View()`:

```go
// View renders the jobs screen.
func (m JobsModel) View() string {
	header := m.renderHeader()
	var extra string
	if m.actionInProgress != "" {
		extra = m.renderActionStatus()
	} else if m.actionError != "" {
		extra = m.renderActionError()
	}
	help := m.renderHelp()

	leftWidth := int(float64(m.width) * 0.35)
	rightWidth := m.width - leftWidth
	availHeight := m.chromeAvailHeight()

	leftPane := m.renderSidebarList(leftWidth, availHeight)
	var rightPane string
	if job, ok := m.CurrentJob(); ok {
		rightPane = m.renderJobDetailPane(job, rightWidth, availHeight)
	} else {
		rightPane = m.renderEmptyDetailPane(rightWidth, availHeight)
	}

	splitView := lipgloss.JoinHorizontal(lipgloss.Top, leftPane, rightPane)
	if extra != "" {
		return lipgloss.JoinVertical(lipgloss.Left, header, extra, splitView, help)
	}
	return lipgloss.JoinVertical(lipgloss.Left, header, splitView, help)
}

func actionLabel(action string) string {
	switch action {
	case "liveness":
		return "Checking liveness"
	case "tailor":
		return "Tailoring resume"
	case "status":
		return "Updating status"
	default:
		return "Working"
	}
}

func (m JobsModel) renderActionStatus() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Yellow).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)
	return style.Render(m.spinner.View() + " " + actionLabel(m.actionInProgress) + "...")
}

func (m JobsModel) renderActionError() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Red).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 2)
	return style.Render("Error: " + truncateRunes(m.actionError, m.width-12) + " (press any key to dismiss)")
}
```

Update `renderSidebarList` to overlay the status picker (add right before the `return borderStyle.Render(content)` line):

```go
	if m.statusPicker {
		content = m.overlayStatusPicker(content)
	}

	borderStyle := lipgloss.NewStyle().
```

(i.e. the `if m.statusPicker` block goes immediately above the existing `borderStyle := ...` line, before the final `return borderStyle.Render(content)`.)

Add `overlayStatusPicker`:

```go
func (m JobsModel) overlayStatusPicker(body string) string {
	bodyLines := strings.Split(body, "\n")

	pickerWidth := 30
	padStyle := theme.PadHorizontal(lipgloss.NewStyle())
	borderStyle := lipgloss.NewStyle().Foreground(m.theme.Blue).Bold(true)

	var picker []string
	picker = append(picker, padStyle.Render(borderStyle.Render("Set status:")))
	for i, opt := range jobsApplicationStatuses {
		style := lipgloss.NewStyle().Foreground(m.theme.Blue).Width(pickerWidth)
		if i == m.statusCursor {
			style = style.Background(m.theme.Overlay).Bold(true)
		}
		prefix := "  "
		if i == m.statusCursor {
			prefix = "> "
		}
		picker = append(picker, padStyle.Render(style.Render(prefix+opt)))
	}

	bodyLines = append(bodyLines, picker...)
	return strings.Join(bodyLines, "\n")
}
```

Update `renderHelp` to mention the new keys:

```go
func (m JobsModel) renderHelp() string {
	style := lipgloss.NewStyle().
		Foreground(m.theme.Blue).
		Background(m.theme.Surface).
		Width(m.width).
		Padding(0, 1)

	keyStyle := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Text)
	descStyle := lipgloss.NewStyle().Foreground(m.theme.Blue)

	return style.Render(
		keyStyle.Render("↑↓/jk") + descStyle.Render(" nav  ") +
			keyStyle.Render("f") + descStyle.Render(" filter  ") +
			keyStyle.Render("l") + descStyle.Render(" liveness  ") +
			keyStyle.Render("t") + descStyle.Render(" tailor  ") +
			keyStyle.Render("u") + descStyle.Render(" status  ") +
			keyStyle.Render("q") + descStyle.Render(" quit"))
}
```

Finally, wire the spinner's ticking into `Update` (add this case to the existing `switch msg := msg.(type)` in `Update`, alongside `jobsActionCompleteMsg`/`tea.KeyMsg`/`tea.WindowSizeMsg`):

```go
	case spinner.TickMsg:
		if m.actionInProgress == "" {
			return m, nil
		}
		var cmd tea.Cmd
		m.spinner, cmd = m.spinner.Update(msg)
		return m, cmd
```

And start the spinner ticking whenever an action is dispatched — update the three dispatch sites (`l`, `t`, and `handleStatusPickerKey`'s `enter`) to batch in `m.spinner.Tick`:

```go
		case "l":
			if job, ok := m.CurrentJob(); ok {
				m.actionInProgress = "liveness"
				return m, tea.Batch(m.runAction("liveness", job.Path), m.spinner.Tick)
			}
		case "t":
			if job, ok := m.CurrentJob(); ok && job.Status == "Pending" {
				m.actionInProgress = "tailor"
				return m, tea.Batch(m.runAction("tailor", job.Path), m.spinner.Tick)
			}
```

```go
	case "enter":
		m.statusPicker = false
		if job, ok := m.CurrentJob(); ok {
			chosen := jobsApplicationStatuses[m.statusCursor]
			m.actionInProgress = "status"
			return m, tea.Batch(m.runAction("status", job.Path, chosen), m.spinner.Tick)
		}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd dashboard && go test ./internal/ui/screens/... -v`
Expected: PASS — every test in the package.

- [ ] **Step 5: Commit**

```bash
git add dashboard/internal/ui/screens/jobs.go dashboard/internal/ui/screens/jobs_test.go
git commit -m "feat(dashboard): render spinner/error/status-picker in JobsModel"
```

---

### Task 7: Wire the new flags into `main.go`

**Files:**
- Modify: `dashboard/main.go`

**Interfaces:**
- Consumes: `screens.JobsModel.WithActionConfig` (Task 4).

No new test file (package `main` has none) — verified via build.

- [ ] **Step 1: Add the flags and pass them to `WithActionConfig`**

In `dashboard/main.go`'s `main()`:

```go
	pathFlag := flag.String("path", ".", "Path to career-ops directory")
	jobsPathFlag := flag.String("jobs-path", "", "Path to the JD evaluation export JSON (see scripts/dashboard.py)")
	pythonPathFlag := flag.String("python-path", "python3", "Path to the Python interpreter for dashboard actions (see scripts/dashboard.py)")
	projectRootFlag := flag.String("project-root", ".", "Path to the resume-builder project root (for locating scripts/dashboard_actions.py)")
	themeFlag := flag.String("theme", "resume-builder", "Theme name: resume-builder, catppuccin-mocha, catppuccin-latte, or auto")
```

```go
	jm := screens.NewJobsModel(t, jobRows, 120, 40).WithActionConfig(*jobsPathFlag, *pythonPathFlag, *projectRootFlag)
```

- [ ] **Step 2: Verify it builds**

Run: `cd dashboard && go build ./cmd/prompt/... ./internal/ui/prompt/... ./internal/ui/screens/... ./internal/data/... ./internal/theme/... ./internal/ui/menu/... .`
Expected: builds clean.

- [ ] **Step 3: Commit**

```bash
git add dashboard/main.go
git commit -m "feat(dashboard): pass python-path/project-root into JobsModel action config"
```

---

### Task 8: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full Python test suite**

Run: `source .venv/bin/activate && python -m unittest discover -s tests 2>&1 | tail -20`
Expected: the same pre-existing, unrelated failures as before this plan (`test_audit_keepers`, `test_cli_art.TestRenderDoctorReport`, `test_orchestrator_main_batch` — 3 failures, 5 errors), plus all new tests (`test_dashboard_actions.py`, updated `test_dashboard.py`) passing. No new failures.

- [ ] **Step 2: Run the full Go test suite**

Run: `cd dashboard && go test ./... 2>&1`
Expected: the same pre-existing, out-of-scope failure in `internal/ui/bootstrap` (`ShowIf` build error) and its `cmd/bootstrap` dependent, plus every other package — including `internal/ui/screens` with all the new action tests — passing.

- [ ] **Step 3: Confirm the new key bindings are wired**

Run: `grep -n '"l", "t", "u"\|case "l":\|case "t":\|case "u":' dashboard/internal/ui/screens/jobs.go`
Expected: matches for all three key cases inside `Update`.

No commit for this task — it's verification only.
