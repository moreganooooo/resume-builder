package screens

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func testJobRows() []model.JobRow {
	return []model.JobRow{
		{Path: "a.json", Status: "Pending", Company: "Acme", Title: "Role A", Evaluation: model.Evaluation{CompositeScore: 4.5}},
		{Path: "b.json", Status: "Completed", Company: "Beta", Title: "Role B", Evaluation: model.Evaluation{CompositeScore: 3.0}},
	}
}

func TestNewJobsModelDefaultsToAllFilterShowingEveryRow(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	if m.filter != "all" {
		t.Fatalf("expected default filter %q, got %q", "all", m.filter)
	}
	if len(m.filtered) != 2 {
		t.Fatalf("expected 2 filtered rows, got %d", len(m.filtered))
	}
}

func TestCursorMovementClampsAtBoundaries(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyUp})
	if m.cursor != 0 {
		t.Fatalf("expected cursor clamped to 0, got %d", m.cursor)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	if m.cursor != 1 {
		t.Fatalf("expected cursor at 1, got %d", m.cursor)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	if m.cursor != 1 {
		t.Fatalf("expected cursor clamped to 1 (last row), got %d", m.cursor)
	}
}

func TestFilterCyclesAllPendingCompletedAll(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'f'}})
	if m.filter != "pending" {
		t.Fatalf("expected filter %q, got %q", "pending", m.filter)
	}
	if len(m.filtered) != 1 || m.filtered[0].Status != "Pending" {
		t.Fatalf("expected only Pending rows, got %+v", m.filtered)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'f'}})
	if m.filter != "completed" {
		t.Fatalf("expected filter %q, got %q", "completed", m.filter)
	}
	if len(m.filtered) != 1 || m.filtered[0].Status != "Completed" {
		t.Fatalf("expected only Completed rows, got %+v", m.filtered)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'f'}})
	if m.filter != "all" {
		t.Fatalf("expected filter to cycle back to %q, got %q", "all", m.filter)
	}
}

func TestCurrentJobReturnsFalseWhenEmpty(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), nil, 100, 30)
	if _, ok := m.CurrentJob(); ok {
		t.Fatal("expected CurrentJob to return false for an empty model")
	}
}

func TestQPressEmitsJobsClosedMsg(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	_, cmd := m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'q'}})
	if cmd == nil {
		t.Fatal("expected a command from pressing q")
	}
	if _, ok := cmd().(JobsClosedMsg); !ok {
		t.Fatalf("expected JobsClosedMsg, got %T", cmd())
	}
}

func TestRenderJobDetailPaneShowsKeyFields(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	job := model.JobRow{
		Company: "Acme", Title: "Marketing Lead", Status: "Pending",
		Evaluation: model.Evaluation{
			CompositeScore: 4.66,
			Recommendation: "Strong pursue",
			Why:            "Great fit for the role.",
			RecruiterRead:  "Recruiter will see a match.",
			HardBlockers:   []string{},
			FitSubscores:   map[string]int{"functional_alignment": 5},
		},
	}

	rendered := ansi.Strip(m.renderJobDetailPane(job, 60, 20))

	for _, want := range []string{
		"Acme", "Marketing Lead", "4.7/5", "Strong pursue",
		"Great fit for the role.", "Recruiter will see a match.",
		"functional_alignment: 5",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("expected detail pane to contain %q, got %q", want, rendered)
		}
	}
}

func TestRenderSidebarListShowsEmptyStateWhenNoRows(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), nil, 100, 30)
	rendered := ansi.Strip(m.renderSidebarList(40, 20))
	if !strings.Contains(rendered, "No evaluated jobs match this filter") {
		t.Fatalf("expected empty-state message, got %q", rendered)
	}
}

func TestViewDoesNotPanicAndIncludesTitle(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	rendered := ansi.Strip(m.View())
	if !strings.Contains(rendered, "JOBS") {
		t.Fatalf("expected header to contain %q, got %q", "JOBS", rendered)
	}
}

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
