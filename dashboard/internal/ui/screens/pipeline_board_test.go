package screens

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func boardTestModel() PipelineModel {
	apps := []model.CareerApplication{
		{Company: "Acme", Role: "Copywriter", Status: "Evaluated", Score: 4.1, ScoreRaw: "4.10"},
		{Company: "Globex", Role: "Editor", Status: "Applied", Score: 4.2, ScoreRaw: "4.20"},
		{Company: "Initech", Role: "Strategist", Status: "Interview", Score: 4.3, ScoreRaw: "4.30"},
		// Terminal: the board must not show it, but it must not lose it
		// from the list modes either.
		{Company: "Hooli", Role: "Analyst", Status: "Rejected", Score: 4.4, ScoreRaw: "4.40"},
	}
	m := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps, model.PipelineMetrics{}, "", 140, 40)
	m.viewMode = "board"
	m.animDone = true
	m.applyFilterAndSort()
	return m
}

func TestPipelineBoard_ColumnsExcludeTerminalStatuses(t *testing.T) {
	m := boardTestModel()

	cols := m.boardColumns()
	if len(cols) != len(boardStatuses) {
		t.Fatalf("expected %d columns, got %d", len(boardStatuses), len(cols))
	}

	total := 0
	for _, idxs := range cols {
		total += len(idxs)
	}
	if total != 3 {
		t.Errorf("expected the 3 non-terminal applications on the board, got %d", total)
	}

	view := ansi.Strip(m.View())
	if strings.Contains(view, "Hooli") {
		t.Errorf("a Rejected application is on the board; terminal statuses are list-only:\n%s", view)
	}
	for _, want := range []string{"EVALUATED", "APPLIED", "RESPONDED", "INTERVIEW", "OFFER", "Acme", "Globex"} {
		if !strings.Contains(view, want) {
			t.Errorf("expected board view to contain %q:\n%s", want, view)
		}
	}
}

func TestPipelineBoard_NavigationMovesTheSharedCursor(t *testing.T) {
	m := boardTestModel()
	// Not cursor = 0: the default sort is score-descending, so filtered[0]
	// is the Rejected role, which no column holds. Landing the cursor is
	// exactly what the first keypress does.
	m.boardMoveCursor(0, 0)
	if app, _ := m.CurrentApp(); app.Company != "Acme" {
		t.Fatalf("expected the cursor to land on the first card of the first column, got %q", app.Company)
	}

	// Right lands on the next occupied column, and the cursor is the same
	// cursor every other action on this screen reads.
	m, _ = m.handleKey(tea.KeyPressMsg{Code: 'l'})
	app, ok := m.CurrentApp()
	if !ok || app.Company != "Globex" {
		t.Fatalf("expected the cursor on Globex after moving right, got %+v", app)
	}

	// Clamped, not wrapped: past Offer there is nowhere further forward.
	for i := 0; i < 6; i++ {
		m, _ = m.handleKey(tea.KeyPressMsg{Code: 'l'})
	}
	if col, _ := m.boardCursorColumn(); col == 0 {
		t.Errorf("moving right wrapped around to the first column")
	}
}

func TestPipelineBoard_ShiftMoveAsksBeforeCommitting(t *testing.T) {
	m := boardTestModel()
	m.boardMoveCursor(0, 0) // Acme, in Evaluated

	m, cmd := m.handleKey(tea.KeyPressMsg{Code: 'L', Mod: tea.ModShift, Text: "L"})
	if cmd != nil {
		if _, isUpdate := cmd().(PipelineUpdateStatusMsg); isUpdate {
			t.Fatal("L committed a status change on the keypress instead of asking first")
		}
	}
	if !m.statusPicker || !m.statusConfirm {
		t.Fatalf("expected L to open the confirm step, got picker=%v confirm=%v", m.statusPicker, m.statusConfirm)
	}
	if m.pendingStatus != "Applied" {
		t.Errorf("expected the proposed status to be the next column, got %q", m.pendingStatus)
	}

	// The confirm itself is what writes.
	m, cmd = m.Update(tea.KeyPressMsg{Code: 'y', Text: "y"})
	if cmd == nil {
		t.Fatal("expected confirming to produce a status update")
	}
	upd, ok := cmd().(PipelineUpdateStatusMsg)
	if !ok || upd.NewStatus != "Applied" {
		t.Errorf("expected PipelineUpdateStatusMsg to Applied, got %#v", cmd())
	}
}

func TestPipelineBoard_NarrowTerminalExplainsItself(t *testing.T) {
	m := boardTestModel()
	m.Resize(60, 24)

	view := ansi.Strip(m.View())
	if !strings.Contains(view, "columns of terminal width") {
		t.Errorf("expected a width explanation rather than unreadable columns:\n%s", view)
	}
}

func TestPipelineBoard_ViewModeCycleReachesBoardAndReturns(t *testing.T) {
	m := boardTestModel()
	m.viewMode = "grouped"

	m, _ = m.handleKey(tea.KeyPressMsg{Code: 'v', Text: "v"})
	if m.viewMode != "flat" {
		t.Fatalf("expected flat, got %q", m.viewMode)
	}
	m, _ = m.handleKey(tea.KeyPressMsg{Code: 'v', Text: "v"})
	if m.viewMode != "board" {
		t.Fatalf("expected board, got %q", m.viewMode)
	}
	m, _ = m.handleKey(tea.KeyPressMsg{Code: 'v', Text: "v"})
	if m.viewMode != "grouped" {
		t.Fatalf("expected the cycle to return to grouped, got %q", m.viewMode)
	}
}
