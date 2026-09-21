package screens

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/answers"
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

func TestAnswersScrollback(t *testing.T) {
	m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{Path: "job"}, "python3", ".", 40, 12)
	for _, word := range []string{"FIRST", "SECOND", "THIRD"} {
		m.turns = append(m.turns, answerTurn{
			Question: word, Answer: strings.Repeat("filler words here ", 8) + word + "END",
		})
	}
	if !strings.Contains(m.View(), "THIRDEND") || strings.Contains(ansi.Strip(m.View()), "You: FIRST") {
		t.Fatalf("default view should follow the newest answer:\n%s", m.View())
	}
	pgUp := tea.KeyPressMsg(tea.Key{Code: tea.KeyPgUp})
	for i := 0; i < 20; i++ { // well past the top; must clamp
		m, _ = m.Update(pgUp)
	}
	if !strings.Contains(ansi.Strip(m.View()), "You: FIRST") {
		t.Fatalf("PgUp should reach the oldest turn:\n%s", m.View())
	}
	if len(strings.Split(m.View(), "\n")) > 12 {
		t.Fatal("scrolled view exceeds terminal height")
	}
	for i := 0; i < 20; i++ {
		m, _ = m.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyPgDown}))
	}
	if m.scroll != 0 || !strings.Contains(m.View(), "THIRDEND") {
		t.Fatalf("PgDn should return to the newest line (scroll=%d)", m.scroll)
	}
	m, _ = m.Update(tea.MouseWheelMsg(tea.Mouse{Button: tea.MouseWheelUp}))
	if m.scroll == 0 {
		t.Fatal("mouse wheel up should scroll back")
	}
	m, _ = m.Update(answers.AnswerMsg{Answer: "fresh"})
	if m.scroll != 0 {
		t.Fatal("a new answer should snap back to the newest line")
	}
}

func TestAnswersQTypesUnlessInputEmpty(t *testing.T) {
	m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{Path: "job"}, "python3", ".", 80, 24)
	press := func(r rune) tea.Cmd {
		var cmd tea.Cmd
		m, cmd = m.Update(tea.KeyPressMsg(tea.Key{Code: r, Text: string(r)}))
		return cmd
	}
	press('W')
	if cmd := press('q'); cmd != nil {
		if _, quit := cmd().(AnswersClosedMsg); quit {
			t.Fatal("q while typing a question must not quit")
		}
	}
	if m.input.Value() != "Wq" {
		t.Fatalf("q should be typed into the input, got %q", m.input.Value())
	}
	m.input.Reset()
	cmd := press('q')
	if cmd == nil {
		t.Fatal("q on an empty input should quit")
	}
	if msg, ok := cmd().(AnswersClosedMsg); !ok || !msg.Quit {
		t.Fatal("q on an empty input should send a quit message")
	}
}
