package screens

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)


func pressKey(s string) tea.KeyPressMsg {
	if len(s) == 1 {
		return tea.KeyPressMsg(tea.Key{Code: rune(s[0]), Text: s})
	}
	switch s {
	case "up":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyUp})
	case "down":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyDown})
	case "esc":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyEsc})
	case "enter":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyEnter})
	case "backspace":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyBackspace})
	case "ctrl+u":
		return tea.KeyPressMsg(tea.Key{Code: 'u', Mod: tea.ModCtrl})
	case "pgdown":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyPgDown})
	case "pgup":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyPgUp})
	default:
		return tea.KeyPressMsg(tea.Key{Text: s})
	}
}

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

	m, _ = m.Update(pressKey("up"))
	if m.cursor != 0 {
		t.Fatalf("expected cursor clamped to 0, got %d", m.cursor)
	}

	m, _ = m.Update(pressKey("down"))
	if m.cursor != 1 {
		t.Fatalf("expected cursor at 1, got %d", m.cursor)
	}

	m, _ = m.Update(pressKey("down"))
	if m.cursor != 1 {
		t.Fatalf("expected cursor clamped to 1 (last row), got %d", m.cursor)
	}
}

func TestFilterCyclesAllPendingCompletedAll(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)

	m, _ = m.Update(pressKey("f"))
	if m.filter != "pending" {
		t.Fatalf("expected filter %q, got %q", "pending", m.filter)
	}
	if len(m.filtered) != 1 || m.filtered[0].Status != "Pending" {
		t.Fatalf("expected only Pending rows, got %+v", m.filtered)
	}

	m, _ = m.Update(pressKey("f"))
	if m.filter != "completed" {
		t.Fatalf("expected filter %q, got %q", "completed", m.filter)
	}
	if len(m.filtered) != 1 || m.filtered[0].Status != "Completed" {
		t.Fatalf("expected only Completed rows, got %+v", m.filtered)
	}

	m, _ = m.Update(pressKey("f"))
	if m.filter != "high_fit" {
		t.Fatalf("expected filter to cycle to %q, got %q", "high_fit", m.filter)
	}
	// Continue cycling through remaining filters
	m, _ = m.Update(pressKey("f"))
	if m.filter != "good_fit" {
		t.Fatalf("expected filter to cycle to %q, got %q", "good_fit", m.filter)
	}
	m, _ = m.Update(pressKey("f"))
	if m.filter != "recent" {
		t.Fatalf("expected filter to cycle to %q, got %q", "recent", m.filter)
	}
	m, _ = m.Update(pressKey("f"))
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
	_, cmd := m.Update(pressKey("q"))
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
	_, cmd := m.Update(pressKey("esc"))
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

	rendered := ansi.Strip(m.renderJobDetailPane(job, 60, 100))

	for _, want := range []string{
		"Acme", "Marketing Lead", "4.7/5", "Strong pursue",
		"Great fit for the role.", "Recruiter will see a match.",
		// Human label (theme.SubscoreLabels["functional_alignment"]), not
		// the raw snake_case schema key -- guards the P1 fix for internal-
		// jargon leakage in formatSubscores.
		"Functional: 5",
	} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("expected detail pane to contain %q, got %q", want, rendered)
		}
	}
	if strings.Contains(rendered, "functional_alignment") {
		t.Fatalf("expected raw schema key not to leak into the detail pane, got %q", rendered)
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
	rendered := ansi.Strip(m.renderJobDetailPane(suspicious, 60, 100))
	for _, want := range []string{"Posting legitimacy: Suspicious", "No company website"} {
		if !strings.Contains(rendered, want) {
			t.Fatalf("expected detail pane to surface the legitimacy warning, want %q, got %q", want, rendered)
		}
	}

	// "High Confidence" is the common case and shouldn't clutter every job's
	// detail pane with a line that says nothing.
	confident := suspicious
	confident.Evaluation.PostingLegitimacy = "High Confidence"
	rendered = ansi.Strip(m.renderJobDetailPane(confident, 60, 100))
	if strings.Contains(rendered, "Posting legitimacy") {
		t.Fatalf("expected no legitimacy line for High Confidence, got %q", rendered)
	}
}

func TestRenderSidebarListShowsEmptyStateWhenNoRows(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), nil, 100, 30)
	rendered := ansi.Strip(m.renderSidebarList(40, 20))
	if !strings.Contains(rendered, "No evaluated jobs match") {
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

	m, cmd := m.Update(pressKey("l"))

	if m.actionInProgress != "liveness" {
		t.Fatalf("expected actionInProgress %q, got %q", "liveness", m.actionInProgress)
	}
	if cmd == nil {
		t.Fatal("expected a command to be dispatched")
	}
}

func TestTPressNoOpOnCompletedJob(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m, _ = m.Update(pressKey("down")) // select the Completed row (Beta)
	if job, _ := m.CurrentJob(); job.Status != "Completed" {
		t.Fatalf("test setup: expected cursor on a Completed job, got %+v", job)
	}

	m, cmd := m.Update(pressKey("t"))

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

	m, cmd := m.Update(pressKey("down"))

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

	m, _ = m.Update(pressKey("down"))

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
	m, _ = m.Update(pressKey("u"))
	if !m.statusPicker {
		t.Fatal("expected statusPicker to open")
	}
	if m.statusCursor != 0 {
		t.Fatalf("expected statusCursor reset to 0, got %d", m.statusCursor)
	}
}

func TestStatusPickerCursorClampsAtBoundaries(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m, _ = m.Update(pressKey("u"))

	m, _ = m.Update(pressKey("up"))
	if m.statusCursor != 0 {
		t.Fatalf("expected statusCursor clamped to 0, got %d", m.statusCursor)
	}

	for range jobsApplicationStatuses {
		m, _ = m.Update(pressKey("down"))
	}
	if m.statusCursor != len(jobsApplicationStatuses)-1 {
		t.Fatalf("expected statusCursor clamped to %d, got %d", len(jobsApplicationStatuses)-1, m.statusCursor)
	}
}

func TestStatusPickerEscCancels(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m, _ = m.Update(pressKey("u"))
	m, _ = m.Update(pressKey("esc"))
	if m.statusPicker {
		t.Fatal("expected statusPicker to close on esc")
	}
	if m.actionInProgress != "" {
		t.Fatal("expected no action dispatched on cancel")
	}
}

// TestStatusPickerEnterRequiresConfirmation guards the P2 fix: application-
// status changes are destructive-but-free (see renderStatusPickerOverlay's
// doc comment in bars.go, which points at cli_art.py's confirm_destructive
// -- the CLI-side fix for the identical bug class), so a stray Enter must
// not silently commit a status change on the first keypress.
func TestStatusPickerEnterRequiresConfirmation(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m = m.WithActionConfig("/tmp/jobs.json", "python3", "/tmp")
	m, _ = m.Update(pressKey("u"))

	m, cmd := m.Update(pressKey("enter"))
	if !m.statusPicker || !m.statusConfirm {
		t.Fatal("expected an inline confirm step before the status picker closes")
	}
	if m.actionInProgress != "" {
		t.Fatalf("expected no action dispatched before confirmation, got %q", m.actionInProgress)
	}
	if cmd != nil {
		t.Fatal("expected no command before confirmation")
	}

	m, cmd = m.Update(pressKey("enter"))
	if m.statusPicker {
		t.Fatal("expected statusPicker closed after confirmation")
	}
	if m.actionInProgress != "status" {
		t.Fatalf("expected actionInProgress %q, got %q", "status", m.actionInProgress)
	}
	if cmd == nil {
		t.Fatal("expected a command to be dispatched after confirmation")
	}
}

// TestStatusPickerConfirmEscCancelsBackToPicker guards that backing out of
// the confirm step returns to the picker (so a misclick doesn't force
// redoing the "u" keypress) rather than dispatching or fully closing.
func TestStatusPickerConfirmEscCancelsBackToPicker(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)
	m = m.WithActionConfig("/tmp/jobs.json", "python3", "/tmp")
	m, _ = m.Update(pressKey("u"))
	m, _ = m.Update(pressKey("enter"))
	if !m.statusConfirm {
		t.Fatal("expected confirm state after first enter")
	}

	m, _ = m.Update(pressKey("esc"))
	if m.statusConfirm {
		t.Fatal("expected confirm state cancelled by esc")
	}
	if !m.statusPicker {
		t.Fatal("expected the picker to remain open after cancelling a confirm")
	}
	if m.actionInProgress != "" {
		t.Fatal("expected no action dispatched on cancel")
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

	for i := 0; i < 25; i++ {
		m, _ = m.Update(pressKey("down"))
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

	m, _ = m.Update(pressKey("G"))
	if m.cursor != 29 {
		t.Fatalf("expected G to move cursor to the last row (29), got %d", m.cursor)
	}
	if rendered := ansi.Strip(m.View()); !strings.Contains(rendered, "Company 29") {
		t.Fatalf("expected the last row (Company 29) to be visible after G, got:\n%s", rendered)
	}

	m, _ = m.Update(pressKey("g"))
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

// -- Search (mirrors pipeline_test.go's TestSearch* suite) --

func searchTestJobRows() []model.JobRow {
	return []model.JobRow{
		{Path: "a.json", Status: "Pending", Company: "Stripe", Title: "Backend Engineer"},
		{Path: "b.json", Status: "Completed", Company: "Anthropic", Title: "AI Safety Engineer"},
		{Path: "c.json", Status: "Pending", Company: "Acme Corp", Title: "Senior PM, Voice AI"},
		{Path: "d.json", Status: "Completed", Company: "Globex", Title: "Platform Engineer"},
	}
}

func TestJobsSearchFiltersByCompanyAndTitle(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), searchTestJobRows(), 100, 30)

	// Match by company substring (case-insensitive).
	m.searchQuery = "stripe"
	m.applyFilter()
	if len(m.filtered) != 1 || m.filtered[0].Company != "Stripe" {
		t.Fatalf("expected 1 match for 'stripe', got %+v", m.filtered)
	}

	// Match by title substring.
	m.searchQuery = "voice ai"
	m.applyFilter()
	if len(m.filtered) != 1 || m.filtered[0].Company != "Acme Corp" {
		t.Fatalf("expected 1 match for 'voice ai', got %+v", m.filtered)
	}

	// Empty query restores everything.
	m.searchQuery = ""
	m.applyFilter()
	if len(m.filtered) != len(searchTestJobRows()) {
		t.Fatalf("expected empty query to restore all rows, got %d/%d", len(m.filtered), len(searchTestJobRows()))
	}
}

func TestJobsSearchIsCaseInsensitive(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), searchTestJobRows(), 100, 30)
	for _, q := range []string{"anthropic", "ANTHROPIC", "AnThRoPiC"} {
		m.searchQuery = q
		m.applyFilter()
		if len(m.filtered) != 1 {
			t.Fatalf("expected case-insensitive match for %q, got %d rows", q, len(m.filtered))
		}
	}
}

// TestJobsSearchComposesWithActiveFilter guards the documented composition
// rule in applyFilter's doc comment: search narrows *within* the active
// 3-way status filter rather than resetting it, mirroring pipeline.go's
// search-within-active-tab behavior.
func TestJobsSearchComposesWithActiveFilter(t *testing.T) {
	rows := []model.JobRow{
		{Path: "a.json", Status: "Pending", Company: "Stripe", Title: "Backend Engineer"},
		{Path: "b.json", Status: "Completed", Company: "Stripe", Title: "Frontend Engineer"},
		{Path: "c.json", Status: "Completed", Company: "Anthropic", Title: "AI Engineer"},
	}
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), rows, 100, 30)

	m.filter = "completed"
	m.searchQuery = "stripe"
	m.applyFilter()

	if len(m.filtered) != 1 || m.filtered[0].Title != "Frontend Engineer" {
		t.Fatalf("expected completed+stripe to leave only Frontend Engineer, got %+v", m.filtered)
	}
}

// TestSlashOpensJobsSearchAndTypingDoesNotTriggerShortcuts is the explicit
// regression guard for the most likely bug in adding search to a screen
// that already has single-letter shortcuts (f/l/t/u): once `/` opens the
// search input, every keystroke -- including letters that are normally
// shortcuts -- must go into the query instead of firing an action.
func TestSlashOpensJobsSearchAndTypingDoesNotTriggerShortcuts(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), searchTestJobRows(), 100, 30)

	m, _ = m.Update(pressKey("/"))
	if !m.searchInput {
		t.Fatal("expected `/` to open search input")
	}

	// "f" and "u" are Jobs shortcuts (cycle filter, open status picker) --
	// typed while search is focused, they must become query characters
	// instead of firing those actions.
	for _, r := range "fu" {
		m, _ = m.Update(pressKey(string(r)))
	}
	if m.searchQuery != "fu" {
		t.Fatalf("expected typed letters to become the search query, got %q", m.searchQuery)
	}
	if m.filter != "all" {
		t.Fatalf("expected filter cycle NOT to fire while typing 'f', got filter=%q", m.filter)
	}
	if m.statusPicker {
		t.Fatal("expected status picker NOT to open while typing 'u'")
	}
}

func TestJobsSearchEnterCommitsAndEscClearsCommittedQuery(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), searchTestJobRows(), 100, 30)

	m, _ = m.Update(pressKey("/"))
	for _, r := range "stripe" {
		m, _ = m.Update(pressKey(string(r)))
	}
	if len(m.filtered) != 1 || m.filtered[0].Company != "Stripe" {
		t.Fatalf("expected live filter to leave only Stripe, got %+v", m.filtered)
	}

	m, _ = m.Update(pressKey("enter"))
	if m.searchInput {
		t.Fatal("expected Enter to close input")
	}
	if m.searchQuery != "stripe" {
		t.Fatalf("expected Enter to keep committed query, got %q", m.searchQuery)
	}

	m, _ = m.Update(pressKey("esc"))
	if m.searchQuery != "" {
		t.Fatalf("expected Esc to clear committed query, got %q", m.searchQuery)
	}
	if len(m.filtered) != len(searchTestJobRows()) {
		t.Fatalf("expected Esc to restore full list, got %d/%d", len(m.filtered), len(searchTestJobRows()))
	}
}

// TestJobsSearchEmptyResultsShowsPlainLanguageEmptyState guards the empty
// state a zero-match search must show instead of a blank pane.
func TestJobsSearchEmptyResultsShowsPlainLanguageEmptyState(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), searchTestJobRows(), 100, 30)
	m.searchQuery = "nonexistent-company-xyz"
	m.applyFilter()

	if len(m.filtered) != 0 {
		t.Fatalf("setup expected zero matches, got %+v", m.filtered)
	}
	// Wide enough that the message doesn't word-wrap mid-query, which would
	// otherwise break a naive Contains check on the query substring.
	rendered := ansi.Strip(m.renderSidebarList(80, 20))
	if !strings.Contains(rendered, "No jobs match") || !strings.Contains(rendered, "nonexistent-company-xyz") {
		t.Fatalf("expected plain-language empty state naming the query, got %q", rendered)
	}
}

func TestJobsSearchBarRendersMatchCountAndAppearsInHelpOverlay(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), searchTestJobRows(), 100, 30)
	m.searchQuery = "stripe"
	m.applyFilter()

	bar := ansi.Strip(m.renderSearchBar())
	if !strings.Contains(bar, "1/4 matching") {
		t.Fatalf("expected search bar to show match count '1/4 matching', got %q", bar)
	}

	rendered := ansi.Strip(m.View())
	if !strings.Contains(rendered, "stripe") {
		t.Fatalf("expected View() to render the active search bar, got %q", rendered)
	}

	overlay := ansi.Strip(renderHelpOverlay(theme.NewTheme("catppuccin-mocha"), "Jobs", jobsHelpCategories, 100, 30))
	if !strings.Contains(overlay, "/") || !strings.Contains(overlay, "Search company/title") {
		t.Fatalf("expected `/` search binding documented in the help overlay, got %q", overlay)
	}
}

// The Fit/Odds suffix is additive detail and must yield before the job
// title does. The Python side shipped this wrong first -- adding the two
// columns unconditionally pushed pre-existing content off the edge -- so
// the drop path is pinned here rather than left to a visual check.
func TestJobSubtitleScoresDropBeforeTitleOnNarrowSidebars(t *testing.T) {
	th := theme.NewTheme("resume-builder")
	job := model.JobRow{
		Title: "Revenue Operations Lead",
		Evaluation: model.Evaluation{
			CompositeScore: 4.2, FitScore: 4.5, InterviewOddsScore: 3.9,
		},
	}

	wide := jobSubtitleWithScores(th, job, 60)
	if !strings.Contains(wide, "4.5") || !strings.Contains(wide, "3.9") {
		t.Errorf("wide sidebar should carry both layer scores, got %q", wide)
	}
	if !strings.Contains(wide, "Revenue Operations Lead") {
		t.Errorf("wide sidebar dropped the title, got %q", wide)
	}

	narrow := jobSubtitleWithScores(th, job, jobsScoreDetailMinWidth-1)
	if strings.Contains(narrow, "4.5") || strings.Contains(narrow, "3.9") {
		t.Errorf("narrow sidebar should drop the scores, got %q", narrow)
	}
	if narrow != job.Title {
		t.Errorf("narrow sidebar must keep the title intact, got %q", narrow)
	}
}

// A zero score means "not recorded" -- these fields postdate some saved
// evaluations, and the scale starts at 1, so 0.0 would be a lie.
func TestLayerScoreRendersMissingAsDash(t *testing.T) {
	if got := layerScore(0); got != "-" {
		t.Errorf("layerScore(0) = %q, want %q", got, "-")
	}
	if got := layerScore(4.5); got != "4.5" {
		t.Errorf("layerScore(4.5) = %q, want %q", got, "4.5")
	}

	job := model.JobRow{Title: "Analyst", Evaluation: model.Evaluation{CompositeScore: 3.1}}
	if got := jobSubtitleWithScores(theme.NewTheme("resume-builder"), job, 60); got != job.Title {
		t.Errorf("a job with no layer scores should render just its title, got %q", got)
	}
}

// A hung subprocess and a slow one look identical on an indeterminate
// spinner. These thresholds are deliberately generous -- orchestrator.py
// allows 180s for a PDF render alone -- so the hint means "something is
// wrong", not "this is taking a while".
func TestStalledHintOnlyFiresPastTheThreshold(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("resume-builder"), testJobRows(), 100, 30)

	if got := m.stalledHint(); got != "" {
		t.Errorf("no action in flight should give no hint, got %q", got)
	}

	m.actionInProgress = "tailor"
	m.actionStartedAt = time.Now().Add(-2 * time.Minute)
	if got := m.stalledHint(); got != "" {
		t.Errorf("a 2-minute tailor is normal, want no hint, got %q", got)
	}

	m.actionStartedAt = time.Now().Add(-stalledTailorAfter - time.Minute)
	if !strings.Contains(m.stalledHint(), "longer than usual") {
		t.Errorf("an over-threshold tailor should warn, got %q", m.stalledHint())
	}

	// Liveness is a bounded network call and gets a much shorter leash,
	// so the same elapsed time that's fine for a tailor is not fine here.
	m.actionInProgress = "liveness"
	m.actionStartedAt = time.Now().Add(-2 * time.Minute)
	if !strings.Contains(m.stalledHint(), "longer than usual") {
		t.Errorf("a 2-minute liveness check should warn, got %q", m.stalledHint())
	}
}

func TestMatchesJobSearchIncludesDescription(t *testing.T) {
	job := model.JobRow{
		Company: "Acme", Title: "Marketing Lead", Description: "Requires expert knowledge of Cobol and Fortran",
	}

	if !matchesJobSearch(job, "Cobol") {
		t.Errorf("expected search query 'Cobol' to match against the description")
	}

	if !matchesJobSearch(job, "FORTRAN") {
		t.Errorf("expected search query to be case-insensitive, but 'FORTRAN' did not match description")
	}

	if matchesJobSearch(job, "Python") {
		t.Errorf("expected query 'Python' not to match job with unrelated description")
	}
}

func TestDetailScrollOffsetResetAndClamping(t *testing.T) {
	m := NewJobsModel(theme.NewTheme("catppuccin-mocha"), testJobRows(), 100, 30)

	// Scroll down detail scroll offset
	m.detailScrollOffset = 5

	// Cursor movement down should reset detailScrollOffset to 0
	m, _ = m.Update(pressKey("j"))
	if m.detailScrollOffset != 0 {
		t.Errorf("expected detailScrollOffset to reset to 0 on cursor down, got %d", m.detailScrollOffset)
	}

	m.detailScrollOffset = 10
	// Cursor movement up should reset detailScrollOffset to 0
	m, _ = m.Update(pressKey("k"))
	if m.detailScrollOffset != 0 {
		t.Errorf("expected detailScrollOffset to reset to 0 on cursor up, got %d", m.detailScrollOffset)
	}

	m.detailScrollOffset = 8
	// Movement with pgdown should reset detailScrollOffset to 0
	m, _ = m.Update(pressKey("pgdown"))
	if m.detailScrollOffset != 0 {
		t.Errorf("expected detailScrollOffset to reset on page down, got %d", m.detailScrollOffset)
	}
}
