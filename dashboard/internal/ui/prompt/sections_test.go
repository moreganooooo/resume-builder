package prompt

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
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

// TestDescriptionsRenderOnTheirOwnLine pins the two halves of the second-line
// menu description: a spec carrying descriptions must reach this renderer at
// all (huh's own Select cannot draw them), and the description must land on a
// line of its own rather than beside the label.
func TestDescriptionsRenderOnTheirOwnLine(t *testing.T) {
	spec := Spec{
		Message: "Main Menu",
		Options: []Option{
			{Label: "Find Jobs", Value: "find_jobs",
				Description: "Search job boards or paste a job link"},
			{Label: "Exit", Value: "exit"},
		},
	}
	out := ansi.Strip(newSectionModel(theme.NewTheme("resume-builder"), spec).View().Content)
	var labelLine, descLine = -1, -1
	for i, line := range strings.Split(out, "\n") {
		if strings.Contains(line, "Find Jobs") {
			labelLine = i
		}
		if strings.Contains(line, "Search job boards") {
			descLine = i
		}
	}
	if labelLine < 0 || descLine < 0 {
		t.Fatalf("expected both the label and its description in:\n%s", out)
	}
	if descLine != labelLine+1 {
		t.Errorf("description should sit on the line under its label, got %d and %d:\n%s",
			labelLine, descLine, out)
	}
}

// TestSelectedRowCarriesOnlyTheBar pins the design system's selection
// language (States / Selection & dimming): the Mauve bar and colour mark the
// focused row, and no "> " cursor is drawn beside it.
func TestSelectedRowCarriesOnlyTheBar(t *testing.T) {
	rows, cur := testSections().lines()
	got := ansi.Strip(rows[cur])
	if !strings.HasPrefix(got, theme.SelectionBar) {
		t.Fatalf("focused row should open with the bar, got %q", got)
	}
	if strings.Contains(got, ">") {
		t.Fatalf("focused row still draws a > cursor: %q", got)
	}
}

// TestSpacersSeparateGroupsWithOneBlankLine: a spacer is one empty,
// unselectable line -- never doubled beside a heading, never at the ends.
func TestSpacersSeparateGroupsWithOneBlankLine(t *testing.T) {
	m := newSectionModel(theme.NewTheme("resume-builder"), Spec{
		Options: []Option{
			{Spacer: true},
			{Label: "Find", Value: "find"},
			{Spacer: true},
			{Label: "Group", Heading: true},
			{Label: "Help", Value: "help"},
			{Spacer: true},
		},
	})
	if m.opts[m.cursor].Value != "find" {
		t.Fatalf("cursor should start on the first real option, got %q", m.opts[m.cursor].Label)
	}
	rows, _ := m.lines()
	var plain []string
	for _, r := range rows {
		plain = append(plain, strings.TrimSpace(ansi.Strip(r)))
	}
	if len(plain) != 4 || plain[1] != "" || plain[0] == "" || plain[3] == "" {
		t.Fatalf("want [Find, blank, GROUP, Help], got %q", plain)
	}
	m.move(1)
	if m.opts[m.cursor].Value != "help" {
		t.Fatalf("down should skip spacer and heading, got %q", m.opts[m.cursor].Label)
	}
}
