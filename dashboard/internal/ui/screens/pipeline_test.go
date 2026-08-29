package screens

import (
	"strings"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

func tabIndexForFilter(t *testing.T, filter string) int {
	t.Helper()

	for i, tab := range pipelineTabs {
		if tab.filter == filter {
			return i
		}
	}

	t.Fatalf("expected pipeline tabs to include filter %q", filter)
	return -1
}

func TestWithReloadedDataPreservesStateAndSelection(t *testing.T) {
	initialApps := []model.CareerApplication{
		{
			Company:    "Acme",
			Role:       "Backend Engineer",
			Status:     "Evaluated",
			Score:      4.2,
			ReportPath: "reports/001-acme.md",
		},
		{
			Company:    "Beta",
			Role:       "Platform Engineer",
			Status:     "Applied",
			Score:      4.6,
			ReportPath: "reports/002-beta.md",
		},
	}

	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		initialApps,
		model.PipelineMetrics{Total: len(initialApps)},
		"..",
		120,
		40,
	)
	pm.sortMode = sortCompany
	pm.activeTab = 0
	pm.viewMode = "flat"
	pm.applyFilterAndSort()
	pm.cursor = 1
	pm.reportCache["reports/002-beta.md"] = reportSummary{tldr: "cached"}

	refreshedApps := []model.CareerApplication{
		initialApps[0],
		initialApps[1],
		{
			Company:    "Gamma",
			Role:       "AI Engineer",
			Status:     "Interview",
			Score:      4.8,
			ReportPath: "reports/003-gamma.md",
		},
	}

	reloaded := pm.WithReloadedData(refreshedApps, model.PipelineMetrics{Total: len(refreshedApps)})

	if reloaded.sortMode != sortCompany {
		t.Fatalf("expected sort mode %q, got %q", sortCompany, reloaded.sortMode)
	}
	if reloaded.viewMode != "flat" {
		t.Fatalf("expected view mode to stay flat, got %q", reloaded.viewMode)
	}
	if got := len(reloaded.filtered); got != 3 {
		t.Fatalf("expected 3 filtered apps after refresh, got %d", got)
	}
	if app, ok := reloaded.CurrentApp(); !ok || app.ReportPath != "reports/002-beta.md" {
		t.Fatalf("expected selection to stay on beta app, got %+v (ok=%v)", app, ok)
	}
	if reloaded.reportCache["reports/002-beta.md"].tldr != "cached" {
		t.Fatal("expected cached report summaries to survive refresh")
	}
}

func TestJobDetailPaneIncludesDate(t *testing.T) {
	apps := []model.CareerApplication{{
		Date:    "2026-04-13",
		Company: "Anthropic",
		Role:    "Forward Deployed Engineer",
		Status:  "Applied",
		Score:   4.5,
	}}
	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		apps,
		model.PipelineMetrics{},
		"..",
		120,
		40,
	)

	view := pm.View()

	if !strings.Contains(view, "2026-04-13") {
		t.Fatalf("expected rendered view to include the app's date, got %q", view)
	}
	if !strings.Contains(view, "Anthropic") {
		t.Fatalf("expected rendered view to include the app's company, got %q", view)
	}
}

func TestSearchFiltersByCompanyRoleAndNotes(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Stripe", Role: "Backend Engineer", Status: "Evaluated", Score: 4.6, Notes: "payments infra"},
		{Company: "Anthropic", Role: "AI Safety Engineer", Status: "Applied", Score: 4.8, Notes: "policy work"},
		{Company: "Acme Corp", Role: "Senior PM, Voice AI", Status: "Evaluated", Score: 4.2, Notes: "Series B in Madrid"},
		{Company: "Globex", Role: "Platform Engineer", Status: "Applied", Score: 3.9, Notes: "remote-first"},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)
	pm.activeTab = tabIndexForFilter(t, filterAll)

	// Match by company substring (case-insensitive).
	pm.searchQuery = "stripe"
	pm.applyFilterAndSort()
	if len(pm.filtered) != 1 || pm.filtered[0].Company != "Stripe" {
		t.Fatalf("expected 1 match for 'stripe', got %+v", pm.filtered)
	}

	// Match by role substring.
	pm.searchQuery = "voice ai"
	pm.applyFilterAndSort()
	if len(pm.filtered) != 1 || pm.filtered[0].Company != "Acme Corp" {
		t.Fatalf("expected 1 match for 'voice ai', got %+v", pm.filtered)
	}

	// Match by notes substring.
	pm.searchQuery = "madrid"
	pm.applyFilterAndSort()
	if len(pm.filtered) != 1 || pm.filtered[0].Company != "Acme Corp" {
		t.Fatalf("expected 1 match for notes 'madrid', got %+v", pm.filtered)
	}

	// Empty query restores everything.
	pm.searchQuery = ""
	pm.applyFilterAndSort()
	if len(pm.filtered) != len(apps) {
		t.Fatalf("expected empty query to restore all rows, got %d/%d", len(pm.filtered), len(apps))
	}
}

func TestSearchComposesWithActiveTab(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Stripe", Role: "Backend Engineer", Status: "Evaluated", Score: 4.6},
		{Company: "Stripe", Role: "Frontend Engineer", Status: "Applied", Score: 4.5},
		{Company: "Anthropic", Role: "AI Engineer", Status: "Applied", Score: 4.8},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)
	pm.activeTab = tabIndexForFilter(t, filterApplied)
	pm.searchQuery = "stripe"
	pm.applyFilterAndSort()

	if len(pm.filtered) != 1 || pm.filtered[0].Role != "Frontend Engineer" {
		t.Fatalf("expected applied+stripe to leave only Frontend Engineer, got %+v", pm.filtered)
	}
}

func TestSearchIsCaseInsensitive(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Anthropic", Role: "AI Engineer", Status: "Evaluated", Score: 4.8},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)
	for _, q := range []string{"anthropic", "ANTHROPIC", "AnThRoPiC"} {
		pm.searchQuery = q
		pm.applyFilterAndSort()
		if len(pm.filtered) != 1 {
			t.Fatalf("expected case-insensitive match for %q, got %d rows", q, len(pm.filtered))
		}
	}
}

func TestSearchEnterCommitsAndEscClearsCommittedQuery(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Stripe", Role: "Backend Engineer", Status: "Evaluated", Score: 4.6},
		{Company: "Anthropic", Role: "AI Engineer", Status: "Evaluated", Score: 4.8},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)

	// Open input and type "stripe".
	pm, _ = pm.Update(pressKey("/"))
	if !pm.searchInput {
		t.Fatal("expected `/` to open search input")
	}
	for _, r := range "stripe" {
		pm, _ = pm.Update(pressKey(string(r)))
	}
	if pm.searchQuery != "stripe" {
		t.Fatalf("expected query to live-update to 'stripe', got %q", pm.searchQuery)
	}
	if len(pm.filtered) != 1 || pm.filtered[0].Company != "Stripe" {
		t.Fatalf("expected live filter to leave only Stripe, got %+v", pm.filtered)
	}

	// Enter commits — input closes, query stays.
	pm, _ = pm.Update(pressKey("enter"))
	if pm.searchInput {
		t.Fatal("expected Enter to close input")
	}
	if pm.searchQuery != "stripe" {
		t.Fatalf("expected Enter to keep committed query, got %q", pm.searchQuery)
	}

	// Esc on a committed query clears the search and restores the full list.
	pm, _ = pm.Update(pressKey("esc"))
	if pm.searchQuery != "" {
		t.Fatalf("expected Esc to clear committed query, got %q", pm.searchQuery)
	}
	if len(pm.filtered) != len(apps) {
		t.Fatalf("expected Esc to restore full list, got %d/%d", len(pm.filtered), len(apps))
	}
}

func TestSearchEscInInputCancelsAndClears(t *testing.T) {
	// Use multiple rows so the test catches a regression where Esc clears the query
	// but forgets to re-apply the filter — the visible count would stay at 1
	// otherwise even though the underlying state went stale.
	apps := []model.CareerApplication{
		{Company: "Stripe", Role: "Backend Engineer", Status: "Evaluated", Score: 4.6},
		{Company: "Globex", Role: "Platform Engineer", Status: "Evaluated", Score: 4.0},
		{Company: "Anthropic", Role: "AI Engineer", Status: "Evaluated", Score: 4.8},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)
	pm.searchInput = true
	pm.searchQuery = "stri"
	pm.applyFilterAndSort()
	if len(pm.filtered) != 1 {
		t.Fatalf("setup expected 1 row matching 'stri', got %d", len(pm.filtered))
	}

	pm, _ = pm.Update(pressKey("esc"))
	if pm.searchInput {
		t.Fatal("expected Esc in input mode to close input")
	}
	if pm.searchQuery != "" {
		t.Fatalf("expected Esc in input mode to clear in-progress query, got %q", pm.searchQuery)
	}
	if len(pm.filtered) != len(apps) {
		t.Fatalf("expected Esc to re-expand filtered list to %d rows, got %d", len(apps), len(pm.filtered))
	}
}

func TestSearchResetsCursorOnQueryChange(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Acme", Role: "Backend Engineer", Status: "Evaluated", Score: 4.0},
		{Company: "Beta", Role: "Frontend Engineer", Status: "Evaluated", Score: 4.1},
		{Company: "Gamma", Role: "AI Engineer", Status: "Evaluated", Score: 4.2},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)
	pm.cursor = 2

	pm, _ = pm.Update(pressKey("/"))
	pm, _ = pm.Update(pressKey("a"))

	if pm.cursor != 0 {
		t.Fatalf("expected cursor to reset to 0 on query change, got %d", pm.cursor)
	}
	if pm.scrollOffset != 0 {
		t.Fatalf("expected scrollOffset to reset to 0 on query change, got %d", pm.scrollOffset)
	}
}

func TestSearchStatePreservedAcrossReload(t *testing.T) {
	initial := []model.CareerApplication{
		{Company: "Stripe", Role: "Backend", Status: "Evaluated", Score: 4.6},
		{Company: "Acme", Role: "AI", Status: "Evaluated", Score: 4.0},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), initial, model.PipelineMetrics{Total: len(initial)}, "..", 120, 40)
	pm.searchQuery = "stripe"
	pm.applyFilterAndSort()

	refreshed := append([]model.CareerApplication{}, initial...)
	refreshed = append(refreshed, model.CareerApplication{Company: "Globex", Role: "Platform", Status: "Applied", Score: 4.3})

	reloaded := pm.WithReloadedData(refreshed, model.PipelineMetrics{Total: len(refreshed)})

	if reloaded.searchQuery != "stripe" {
		t.Fatalf("expected refresh to preserve search query, got %q", reloaded.searchQuery)
	}
	if len(reloaded.filtered) != 1 || reloaded.filtered[0].Company != "Stripe" {
		t.Fatalf("expected refresh+search to keep filter applied, got %+v", reloaded.filtered)
	}
}

func TestRejectedAndDiscardedTabsFilterCorrectly(t *testing.T) {
	apps := []model.CareerApplication{
		{
			Company:    "Acme",
			Role:       "Backend Engineer",
			Status:     "Rejected",
			Score:      3.4,
			ReportPath: "reports/001-acme.md",
		},
		{
			Company:    "Beta",
			Role:       "Platform Engineer",
			Status:     "Discarded",
			Score:      2.1,
			ReportPath: "reports/002-beta.md",
		},
		{
			Company:    "Gamma",
			Role:       "AI Engineer",
			Status:     "Applied",
			Score:      4.6,
			ReportPath: "reports/003-gamma.md",
		},
	}

	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		apps,
		model.PipelineMetrics{Total: len(apps)},
		"..",
		120,
		40,
	)

	pm.activeTab = tabIndexForFilter(t, filterRejected)
	pm.applyFilterAndSort()
	if len(pm.filtered) != 1 || pm.filtered[0].Status != "Rejected" {
		t.Fatalf("expected rejected tab to isolate rejected rows, got %+v", pm.filtered)
	}

	pm.activeTab = tabIndexForFilter(t, filterDiscarded)
	pm.applyFilterAndSort()
	if len(pm.filtered) != 1 || pm.filtered[0].Status != "Discarded" {
		t.Fatalf("expected discarded tab to isolate discarded rows, got %+v", pm.filtered)
	}
}

// With no committed search query, Esc backs out to the Main Menu rather
// than quitting the app -- PipelineClosedMsg{Quit: false}, distinct from
// "q"'s PipelineClosedMsg{Quit: true}. This used to be a no-op (see git
// history) specifically to avoid Esc silently exiting the whole app; now
// that "back" and "quit" are different outcomes, Esc can safely mean
// "leave this screen" without reopening that accidental-exit risk.
func TestEscWithoutQueryGoesBack(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Stripe", Role: "Backend Engineer", Status: "Evaluated", Score: 4.6},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)
	if pm.searchQuery != "" {
		t.Fatalf("setup expected empty search query, got %q", pm.searchQuery)
	}

	pm, cmd := pm.Update(pressKey("esc"))
	if cmd == nil {
		t.Fatal("expected Esc with no query to emit PipelineClosedMsg, got nil cmd")
	}
	msg, ok := cmd().(PipelineClosedMsg)
	if !ok {
		t.Fatalf("expected PipelineClosedMsg, got %T", cmd())
	}
	if msg.Quit {
		t.Fatal("expected Esc to emit PipelineClosedMsg{Quit: false} (back), got Quit: true")
	}
	if pm.searchInput {
		t.Fatal("Esc with no query should not toggle searchInput")
	}
}

// "q" always quits the whole app, distinct from Esc's "back to menu".
func TestQAlwaysQuits(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Stripe", Role: "Backend Engineer", Status: "Evaluated", Score: 4.6},
	}
	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)

	_, cmd := pm.Update(pressKey("q"))
	if cmd == nil {
		t.Fatal("expected \"q\" to emit PipelineClosedMsg, got nil cmd")
	}
	msg, ok := cmd().(PipelineClosedMsg)
	if !ok {
		t.Fatalf("expected PipelineClosedMsg, got %T", cmd())
	}
	if !msg.Quit {
		t.Fatal("expected \"q\" to emit PipelineClosedMsg{Quit: true}, got Quit: false")
	}
}

// Regression: typing during search input must not synchronously fan out to
// loadCurrentReport. Reading reports per keystroke caused visible UI lag, so
// the load is deferred to commit (Enter) / cancel (Esc) instead.
func TestSearchTypingDoesNotLoadReports(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Stripe", Role: "Backend Engineer", Status: "Evaluated", Score: 4.6, ReportPath: "reports/001-stripe.md"},
		{Company: "Anthropic", Role: "AI Engineer", Status: "Evaluated", Score: 4.8, ReportPath: "reports/002-anthropic.md"},
	}

	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)

	pm, _ = pm.Update(pressKey("/"))
	if !pm.searchInput {
		t.Fatal("expected `/` to open search input")
	}

	// Typing must not trigger PipelineLoadReportMsg.
	for _, r := range "stri" {
		var cmd tea.Cmd
		pm, cmd = pm.Update(pressKey(string(r)))
		if cmd != nil {
			if msg := cmd(); msg != nil {
				if _, ok := msg.(PipelineLoadReportMsg); ok {
					t.Fatalf("typing rune %q should not emit PipelineLoadReportMsg", string(r))
				}
			}
		}
	}

	// Backspace must not trigger PipelineLoadReportMsg either.
	pm, cmd := pm.Update(pressKey("backspace"))
	if cmd != nil {
		if msg := cmd(); msg != nil {
			if _, ok := msg.(PipelineLoadReportMsg); ok {
				t.Fatal("Backspace during search input should not emit PipelineLoadReportMsg")
			}
		}
	}

	// Ctrl+U must not trigger PipelineLoadReportMsg either.
	pm, cmd = pm.Update(pressKey("ctrl+u"))
	if cmd != nil {
		if msg := cmd(); msg != nil {
			if _, ok := msg.(PipelineLoadReportMsg); ok {
				t.Fatal("Ctrl+U during search input should not emit PipelineLoadReportMsg")
			}
		}
	}
}

func TestPipelineModel_StarfieldTickOnEmptyDetail(t *testing.T) {
	// Empty pipeline: should initialize starfield tick loop
	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		[]model.CareerApplication{},
		model.PipelineMetrics{Total: 0},
		"..",
		120,
		40,
	)

	cmd := pm.Init()
	if cmd == nil {
		t.Fatalf("expected non-nil Init cmd for starfield animation loop on empty model")
	}

	// Update with starfieldTickMsg should schedule next tick when empty
	var tickMsg starfieldTickMsg
	_, nextCmd := pm.Update(tickMsg)
	if nextCmd == nil {
		t.Fatalf("expected next starfield tick cmd when detail pane is empty")
	}
}

func TestPipelineModel_SetNotice(t *testing.T) {
	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		[]model.CareerApplication{},
		model.PipelineMetrics{Total: 0},
		"..",
		120,
		40,
	)

	pm.SetNotice("Status update failed: permission denied")
	if pm.Notice() != "Status update failed: permission denied" {
		t.Fatalf("expected notice %q, got %q", "Status update failed: permission denied", pm.Notice())
	}
	rendered := pm.renderNotice()
	if !strings.Contains(rendered, "permission denied") {
		t.Fatalf("expected rendered notice to contain 'permission denied', got %q", rendered)
	}
}

func TestRenderPipelineDetailPane_ZeroAndNilFields(t *testing.T) {
	// CareerApplication with completely empty fields
	emptyApp := model.CareerApplication{}
	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		[]model.CareerApplication{emptyApp},
		model.PipelineMetrics{},
		"..",
		120,
		40,
	)

	view := pm.View()
	if view == "" {
		t.Fatalf("expected non-empty view for empty CareerApplication")
	}

	detail := pm.renderJobDetailPane(emptyApp, 60, 30)
	if detail == "" {
		t.Fatalf("expected non-empty detail pane for empty CareerApplication")
	}
}

func TestPipeline_UndoStatusChange(t *testing.T) {
	app := model.CareerApplication{
		Company: "Acme",
		Role:    "Engineer",
		Status:  "Evaluated",
	}
	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		[]model.CareerApplication{app},
		model.PipelineMetrics{Total: 1},
		"..",
		120,
		40,
	)
	pm.applyFilterAndSort()

	// Initial undo should notify nothing to undo
	pm, _ = pm.Update(tea.KeyPressMsg(tea.Key{Code: 'u', Text: "u"}))
	if !strings.Contains(pm.Notice(), "Nothing to undo") {
		t.Fatalf("expected notice for empty undo stack, got %q", pm.Notice())
	}
	pm.notice = ""

	// Change status: press 'c' to open picker, move down, press enter to select, press y to confirm
	pm, _ = pm.Update(tea.KeyPressMsg(tea.Key{Code: 'c', Text: "c"}))
	pm, _ = pm.Update(tea.KeyPressMsg(tea.Key{Code: 'j', Text: "j"}))
	pm, _ = pm.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyEnter}))
	var cmd tea.Cmd
	pm, cmd = pm.Update(tea.KeyPressMsg(tea.Key{Code: 'y', Text: "y"}))
	if cmd == nil {
		t.Fatalf("expected status update command")
	}

	// Check undo stack
	if len(pm.undoStack) != 1 {
		t.Fatalf("expected 1 item on undo stack, got %d", len(pm.undoStack))
	}

	// Dismiss any notice if present and press 'u' to undo
	pm.notice = ""
	pm, cmd = pm.Update(tea.KeyPressMsg(tea.Key{Code: 'u', Text: "u"}))
	if cmd == nil {
		t.Fatalf("expected undo command to revert status")
	}
	msg := cmd()
	updateMsg, ok := msg.(PipelineUpdateStatusMsg)
	if !ok {
		t.Fatalf("expected PipelineUpdateStatusMsg, got %T", msg)
	}
	if updateMsg.NewStatus != "Evaluated" {
		t.Fatalf("expected reverted status 'Evaluated', got %q", updateMsg.NewStatus)
	}
}

func TestPipeline_EmptyStateContextual(t *testing.T) {
	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		[]model.CareerApplication{},
		model.PipelineMetrics{Total: 0},
		"..",
		120,
		40,
	)
	pm.applyFilterAndSort()

	view := pm.View()
	if !strings.Contains(view, "No applications") && !strings.Contains(view, "0") {
		t.Fatalf("expected view to reflect zero applications or empty state")
	}
}

func TestPipelineModel_MouseInteractions(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Acme", Role: "Dev", Status: "Evaluated", Score: 4.2},
		{Company: "Beta", Role: "Lead", Status: "Applied", Score: 4.8},
		{Company: "Gamma", Role: "Architect", Status: "Interview", Score: 4.9},
	}
	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		apps,
		model.PipelineMetrics{Total: len(apps)},
		"..",
		120,
		40,
	)
	pm.applyFilterAndSort()

	// Initial cursor is 0
	if pm.cursor != 0 {
		t.Fatalf("expected initial cursor 0, got %d", pm.cursor)
	}

	// Mouse wheel down advances cursor
	pm, _ = pm.Update(tea.MouseWheelMsg{Button: tea.MouseWheelDown})
	if pm.cursor != 1 {
		t.Errorf("expected cursor 1 after wheel down, got %d", pm.cursor)
	}

	// Mouse wheel up retreats cursor
	pm, _ = pm.Update(tea.MouseWheelMsg{Button: tea.MouseWheelUp})
	if pm.cursor != 0 {
		t.Errorf("expected cursor 0 after wheel up, got %d", pm.cursor)
	}

	// Mouse wheel in detail pane scrolls detailScrollOffset without changing cursor
	pm, _ = pm.Update(tea.MouseWheelMsg{X: 100, Button: tea.MouseWheelDown})
	if pm.cursor != 0 {
		t.Errorf("expected cursor to remain 0 when scrolling detail pane, got %d", pm.cursor)
	}
	// This application's detail fits the pane, so there is nothing to
	// scroll and the offset must stay pinned at 0 -- an unclamped counter
	// left the user scrolling back up through dead notches, and once it
	// ran past the end the pane snapped back to the top.
	if pm.detailScrollOffset != 0 {
		t.Errorf("expected detailScrollOffset to stay 0 for content that fits, got %d", pm.detailScrollOffset)
	}

	// In a pane short enough that the detail overflows, the same wheel
	// event does scroll -- and stops at the last page rather than running
	// on forever.
	short := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		apps,
		model.PipelineMetrics{Total: len(apps)},
		"..",
		120,
		14,
	)
	short.applyFilterAndSort()
	short, _ = short.Update(tea.MouseWheelMsg{X: 100, Button: tea.MouseWheelDown})
	if short.detailScrollOffset != 1 {
		t.Errorf("expected detailScrollOffset 1 in a short pane, got %d", short.detailScrollOffset)
	}
	for i := 0; i < 200; i++ {
		short, _ = short.Update(tea.MouseWheelMsg{X: 100, Button: tea.MouseWheelDown})
	}
	app, _ := short.CurrentApp()
	height := short.height - short.chromeRowsFixed()
	if height < 5 {
		height = 5
	}
	lines := short.pipelineDetailContentLines(app, short.width-int(float64(short.width)*pipelineSidebarRatio), height)
	want := detailMaxScrollFor(len(lines), height)
	if short.detailScrollOffset != want {
		t.Errorf("detail scroll ran past the end: got %d, want clamp at %d", short.detailScrollOffset, want)
	}
}

func TestPipelineModel_MouseClick(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Acme Corp", Role: "Engineer", Status: "draft"},
		{Company: "Beta Inc", Role: "Designer", Status: "draft"},
	}
	pm := NewPipelineModel(
		theme.NewTheme("catppuccin-mocha"),
		apps,
		model.PipelineMetrics{Total: len(apps)},
		"..",
		120,
		40,
	)
	pm.applyFilterAndSort()

	_ = zone.Scan(pm.View())

	info := zone.WaitFor("pipeline_row_1", 2*time.Second)
	if info == nil {
		t.Fatalf("zone pipeline_row_1 never registered after Scan -- the click path is untested if this is skipped")
	}
	pm, _ = pm.Update(tea.MouseClickMsg{X: info.StartX + 1, Y: info.StartY})
	if pm.cursor != 1 {
		t.Errorf("expected cursor 1 after clicking pipeline row 1, got %d", pm.cursor)
	}
}
