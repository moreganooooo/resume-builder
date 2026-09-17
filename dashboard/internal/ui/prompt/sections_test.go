package prompt

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func testSections() sectionModel {
	return newSectionModel(theme.NewTheme("resume-builder"), Spec{
		Message: "Menu",
		Options: []Option{
			{Label: "Health", Heading: true},
			{Label: "Doctor", Value: "doctor"},
			{Label: "Skills", Heading: true},
			{Label: "Manage", Value: "manage"},
			{Label: "Back", Value: "back"},
		},
	})
}

func TestSectionsCursorSkipsHeadings(t *testing.T) {
	m := testSections()
	if m.cursor != 1 {
		t.Fatalf("cursor starts on first option, got %d", m.cursor)
	}
	down := tea.KeyPressMsg{Code: tea.KeyDown}
	next, _ := m.Update(down)
	m = next.(sectionModel)
	if m.opts[m.cursor].Value != "manage" {
		t.Fatalf("down should skip the heading, landed on %q", m.opts[m.cursor].Label)
	}
	m.lastMove = m.lastMove.Add(-repeatThrottle * 2)
	next, _ = m.Update(tea.KeyPressMsg{Code: tea.KeyUp})
	m = next.(sectionModel)
	m.lastMove = m.lastMove.Add(-repeatThrottle * 2)
	next, _ = m.Update(tea.KeyPressMsg{Code: tea.KeyUp})
	m = next.(sectionModel)
	if m.opts[m.cursor].Value != "back" {
		t.Fatalf("up from the first option wraps to the last, got %q", m.opts[m.cursor].Label)
	}
}

func TestSectionsRenderHeadingsAndDefault(t *testing.T) {
	m := testSections()
	out := m.View().Content
	for _, want := range []string{"HEALTH", "SKILLS", "Doctor"} {
		if !strings.Contains(out, want) {
			t.Errorf("view missing %q", want)
		}
	}
	m = newSectionModel(theme.NewTheme("resume-builder"), Spec{Options: m.opts, DefaultValue: "manage"})
	if m.opts[m.cursor].Value != "manage" {
		t.Errorf("default value not honored")
	}
}
