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
	msg, ok := cmd().(JobsClosedMsg)
	if !ok {
		t.Fatalf("expected JobsClosedMsg, got %T", cmd())
	}
	if !msg.Quit {
		t.Fatal("expected \"q\" to emit JobsClosedMsg{Quit: true}, got Quit: false")
	}
}

// Esc backs out to the Main Menu rather than quitting the app -- distinct
// from "q", which still exits the whole program.
func TestEscPressEmitsJobsClosedMsgBack(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	_, cmd := m.Update(tea.KeyMsg{Type: tea.KeyEsc})
	if cmd == nil {
		t.Fatal("expected a command from pressing esc")
	}
	msg, ok := cmd().(JobsClosedMsg)
	if !ok {
		t.Fatalf("expected JobsClosedMsg, got %T", cmd())
	}
	if msg.Quit {
		t.Fatal("expected Esc to emit JobsClosedMsg{Quit: false} (back), got Quit: true")
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

// TestRenderJobDetailPaneSurfacesPostingLegitimacyWarning guards a bug
// where Evaluation.PostingLegitimacy/.PostingLegitimacyNotes were decoded
// from the persisted evaluation JSON but never rendered anywhere in this
// screen -- a fake/stale-posting warning had no way to reach the user.
func TestRenderJobDetailPaneSurfacesPostingLegitimacyWarning(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)

	suspicious := model.JobRow{
		Company: "Acme", Title: "Marketing Lead", Status: "Pending",
		Evaluation: model.Evaluation{
			CompositeScore:         4.0,
			PostingLegitimacy:      "Suspicious",
			PostingLegitimacyNotes: "No company website, posted by a personal email address.",
		},
	}
	rendered := ansi.Strip(m.renderJobDetailPane(suspicious, 60, 20))
	for _, want := range []string{"Posting legitimacy: Suspicious", "No company website"} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("expected detail pane to surface the legitimacy warning, want %q, got %q", want, rendered)
		}
	}

	// "High Confidence" is the common case and shouldn't clutter every job's
	// detail pane with a line that says nothing.
	confident := suspicious
	confident.Evaluation.PostingLegitimacy = "High Confidence"
	rendered = ansi.Strip(m.renderJobDetailPane(confident, 60, 20))
	if strings.Contains(rendered, "Posting legitimacy") {
		t.Fatalf("expected no legitimacy line for High Confidence, got %q", rendered)
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

	var cmd tea.Cmd
	m, cmd = m.Update(jobsActionCompleteMsg{action: "liveness"})

	if m.actionInProgress != "" {
		t.Fatalf("expected actionInProgress cleared, got %q", m.actionInProgress)
	}
	if cmd == nil {
		t.Fatal("expected a reloadJobsCmd to be returned")
	}
	// The reload now happens off-thread (see reloadJobsCmd) -- run the
	// returned Cmd and feed its jobsReloadedMsg back in, mirroring what the
	// real bubbletea runtime does.
	m, _ = m.Update(cmd())

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

// manyJobRows returns n jobs -- enough to exceed a small terminal's visible
// sidebar rows, so scroll behavior actually gets exercised.
func manyJobRows(n int) []model.JobRow {
	rows := make([]model.JobRow, n)
	for i := range rows {
		rows[i] = model.JobRow{
			Path:       fmt.Sprintf("job-%02d.json", i),
			Status:     "Pending",
			Company:    fmt.Sprintf("Company %02d", i),
			Title:      fmt.Sprintf("Role %02d", i),
			Evaluation: model.Evaluation{CompositeScore: 4.0},
		}
	}
	return rows
}

// TestScrollFollowsCursorPastVisibleWindow guards the P0 bug where the
// sidebar always rendered from the top of the filtered list regardless of
// cursor position: on a short terminal, moving the cursor past what fits
// on screen left the selection invisible with no way to scroll to it.
func TestScrollFollowsCursorPastVisibleWindow(t *testing.T) {
	// height=12 leaves a handful of visible sidebar rows after chrome (see
	// chromeAvailHeight/sidebarViewportLines) -- comfortably fewer than the
	// 30 rows below, so the cursor is guaranteed to outrun the first screen.
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), manyJobRows(30), 100, 12)

	for range 25 {
		m, _ = m.Update(tea.KeyMsg{Type: tea.KeyDown})
	}
	if m.cursor != 25 {
		t.Fatalf("expected cursor at 25, got %d", m.cursor)
	}

	rendered := ansi.Strip(m.View())
	if !strings.Contains(rendered, "Company 25") {
		t.Fatalf("expected the selected row (Company 25) to be visible after scrolling down, got:\n%s", rendered)
	}
}

// TestScrollJumpsToTopAndBottom guards the g/G keybindings added alongside
// the scroll fix, mirroring pipeline.go's existing g/G behavior.
func TestScrollJumpsToTopAndBottom(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), manyJobRows(30), 100, 12)

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'G'}})
	if m.cursor != 29 {
		t.Fatalf("expected G to move cursor to the last row (29), got %d", m.cursor)
	}
	if rendered := ansi.Strip(m.View()); !strings.Contains(rendered, "Company 29") {
		t.Fatalf("expected the last row (Company 29) to be visible after G, got:\n%s", rendered)
	}

	m, _ = m.Update(tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune{'g'}})
	if m.cursor != 0 {
		t.Fatalf("expected g to move cursor to the first row (0), got %d", m.cursor)
	}
	if rendered := ansi.Strip(m.View()); !strings.Contains(rendered, "Company 00") {
		t.Fatalf("expected the first row (Company 00) to be visible after g, got:\n%s", rendered)
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
