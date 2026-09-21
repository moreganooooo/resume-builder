package screens

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func TestAnswersViewFitsSmallTerminal(t *testing.T) {
	for _, size := range [][2]int{{80, 24}, {35, 12}} {
		m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{
			Path: "job", Title: "Content Strategist", Company: "Acme",
		}, "python3", ".", size[0], size[1])
		for _, line := range strings.Split(m.View(), "\n") {
			if ansi.StringWidth(line) > size[0] {
				t.Fatalf("line exceeds width %d: %q", size[0], line)
			}
		}
	}
}

func TestAnswersEscClosesAndEnterRequiresQuestion(t *testing.T) {
	m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{Path: "job"}, "python3", ".", 80, 24)
	var cmd tea.Cmd
	m, cmd = m.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyEnter}))
	if cmd != nil || m.busy {
		t.Fatal("empty question should not submit")
	}
	m, cmd = m.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyEscape}))
	if cmd == nil {
		t.Fatal("escape should return a close command")
	}
	if _, ok := cmd().(AnswersClosedMsg); !ok {
		t.Fatal("escape returned the wrong message")
	}
}

func TestAnswersWrapsLongAnswerAndKeepsInputVisible(t *testing.T) {
	m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{Path: "job"}, "python3", ".", 40, 12)
	long := strings.Repeat("alpha beta gamma delta ", 12) + "OMEGA"
	m.turns = append(m.turns, answerTurn{Question: "Why?", Answer: long})
	view := m.View()
	if !strings.Contains(view, "OMEGA") {
		t.Fatalf("end of the answer is missing:\n%s", view)
	}
	lines := strings.Split(view, "\n")
	if len(lines) > 12 {
		t.Fatalf("view has %d lines, exceeds height 12", len(lines))
	}
	for _, line := range lines {
		if ansi.StringWidth(line) > 40 {
			t.Fatalf("line exceeds width 40: %q", line)
		}
	}
	if !strings.Contains(view, "Enter send") {
		t.Fatalf("footer pushed off-screen:\n%s", view)
	}
}
