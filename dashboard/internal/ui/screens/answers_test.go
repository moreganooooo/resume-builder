package screens

import (
	"strings"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/answers"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
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
	// Stripped, and lowercase: the footer is a HelpBar now, which prints the
	// key itself rather than a prose label ("enter" is what a person types)
	// and styles the key and its description separately -- so the two are
	// adjacent on screen but not adjacent in the raw string.
	if !strings.Contains(ansi.Strip(view), "enter send") {
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

func TestAnswersHelpOverlayOnlyOpensOnAnEmptyBox(t *testing.T) {
	// A question mark is punctuation on this screen far more often than it
	// is a command, so the overlay must lose the key while the user is
	// mid-question -- the same rule `q` already follows.
	m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{Path: "job"}, "python3", ".", 80, 24)
	m, _ = m.Update(tea.KeyPressMsg(tea.Key{Code: '?', Text: "?"}))
	if !m.showHelp {
		t.Fatal("? on an empty box should open the reference")
	}
	m, _ = m.Update(tea.KeyPressMsg(tea.Key{Code: tea.KeyEscape}))
	if m.showHelp {
		t.Fatal("esc should dismiss the reference")
	}

	m.input.SetValue("Why do you want to work here")
	m, _ = m.Update(tea.KeyPressMsg(tea.Key{Code: '?', Text: "?"}))
	if m.showHelp {
		t.Fatal("? mid-question is punctuation, not a command")
	}
	if !strings.Contains(m.input.Value(), "?") {
		t.Fatal("the question mark should have reached the input")
	}
}

func TestAnswersHelpOverlaySwallowsEveryKey(t *testing.T) {
	// The box is hidden behind the modal; typing into what you cannot see is
	// how a reference screen silently corrupts a half-written question.
	m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{Path: "job"}, "python3", ".", 80, 24)
	m, _ = m.Update(tea.KeyPressMsg(tea.Key{Code: '?', Text: "?"}))
	m, cmd := m.Update(tea.KeyPressMsg(tea.Key{Code: 'x', Text: "x"}))
	if m.input.Value() != "" {
		t.Fatalf("key reached the hidden input: %q", m.input.Value())
	}
	if cmd != nil {
		t.Fatal("a key consumed by the overlay should issue no command")
	}
}

func TestAnswersFooterHintsAreClickable(t *testing.T) {
	// The footer is a real HelpBar now, so a click on "esc back" has to
	// produce exactly what typing esc produces.
	m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{Path: "job"}, "python3", ".", 80, 24)
	_ = zone.Scan(m.View())
	var escIndex = -1
	for i, b := range answersHelpBindings {
		if b.Key == "esc" {
			escIndex = i
		}
	}
	if escIndex < 0 {
		t.Fatal("expected an esc hint in the footer")
	}
	info := zone.WaitFor(helpBarZoneID(answersHelpZone, escIndex), time.Second)
	if info == nil {
		t.Fatal("the esc hint published no zone bounds")
	}
	_, cmd := m.Update(tea.MouseClickMsg{X: info.StartX, Y: info.StartY, Button: tea.MouseLeft})
	if cmd == nil {
		t.Fatal("clicking the esc hint should close the screen")
	}
	if _, ok := cmd().(AnswersClosedMsg); !ok {
		t.Fatal("clicking esc produced a different message than pressing it")
	}
}

func TestAnswersClickOutsideTheFooterReachesTheInput(t *testing.T) {
	// Swallowing every click would leave the one box on this screen
	// unreachable by mouse.
	m := NewAnswersModel(theme.NewTheme("resume-builder"), model.JobRow{Path: "job"}, "python3", ".", 80, 24)
	_ = zone.Scan(m.View())
	if _, ok := HelpBarClicked(answersHelpZone, answersHelpBindings, tea.MouseClickMsg{X: 2, Y: 1, Button: tea.MouseLeft}); ok {
		t.Fatal("a click in the header should not resolve to a footer hint")
	}
}
