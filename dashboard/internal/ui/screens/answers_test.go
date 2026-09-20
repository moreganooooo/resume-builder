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
