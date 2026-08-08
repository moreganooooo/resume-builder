package screens

import (
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
