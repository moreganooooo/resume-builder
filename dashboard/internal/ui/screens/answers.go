package screens

import (
	"context"
	"fmt"
	"strconv"
	"strings"

	"charm.land/bubbles/v2/textarea"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/answers"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

type AnswersClosedMsg struct{ Quit bool }
type OpenAnswersMsg struct{ Job model.JobRow }

type answerTurn struct {
	Question string
	Answer   string
	Kind     string
	Limit    int
	Warnings []string
}

type AnswersModel struct {
	job           model.JobRow
	turns         []answerTurn
	input         textarea.Model
	busy          bool
	status        string
	charLimit     int
	width, height int
	// scroll is how many conversation lines the view sits above the newest
	// one; 0 follows the latest answer.
	scroll      int
	theme       theme.Theme
	pythonPath  string
	projectRoot string
	cancel      context.CancelFunc
}

func NewAnswersModel(t theme.Theme, job model.JobRow, pythonPath, projectRoot string, width, height int) AnswersModel {
	input := textarea.New()
	input.Placeholder = "Paste an application question…"
	input.SetHeight(3)
	input.SetWidth(max(20, width-6))
	input.Focus()
	return AnswersModel{
		job: job, input: input, width: width, height: height,
		theme: t, pythonPath: pythonPath, projectRoot: projectRoot,
		status: "Ready",
	}
}

func (m *AnswersModel) Resize(width, height int) {
	m.width, m.height = width, height
	m.input.SetWidth(max(20, width-6))
}

func (m AnswersModel) Init() tea.Cmd { return textarea.Blink }

func (m AnswersModel) Update(msg tea.Msg) (AnswersModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.Resize(msg.Width, msg.Height)
	case answers.AnswerMsg:
		m.busy = false
		m.status = "Answer ready"
		m.scroll = 0
		newTurn := answerTurn{
			Question: m.input.Value(), Answer: msg.Answer, Kind: msg.Kind,
			Limit: msg.CharLimit, Warnings: msg.Warnings,
		}
		if msg.Action == "regenerate" || msg.Action == "shorten" {
			if len(m.turns) > 0 {
				newTurn.Question = m.turns[len(m.turns)-1].Question
				m.turns[len(m.turns)-1] = newTurn
			}
		} else {
			m.turns = append(m.turns, newTurn)
			m.input.Reset()
		}
		if m.cancel != nil {
			m.cancel()
			m.cancel = nil
		}
		return m, nil
	case answers.ErrorMsg:
		m.busy = false
		m.status = "Error: " + msg.Err.Error()
		if m.cancel != nil {
			m.cancel()
			m.cancel = nil
		}
		return m, nil
	case tea.MouseWheelMsg:
		// Button, not Y, gives the wheel direction (see kb.go).
		switch msg.Button {
		case tea.MouseWheelUp:
			m.scrollBy(3)
		case tea.MouseWheelDown:
			m.scrollBy(-3)
		}
		return m, nil
	case tea.KeyPressMsg:
		switch msg.String() {
		// Page keys only: the arrow keys belong to the multi-line input.
		case "pgup", "ctrl+u":
			m.scrollBy(max(1, m.bodyHeight()/2))
			return m, nil
		case "pgdown", "ctrl+d":
			m.scrollBy(-max(1, m.bodyHeight()/2))
			return m, nil
		case "esc":
			if m.busy && m.cancel != nil {
				m.cancel()
				m.busy = false
				m.status = "Cancelled"
				return m, nil
			}
			return m, func() tea.Msg { return AnswersClosedMsg{} }
		case "ctrl+c", "q":
			return m, func() tea.Msg { return AnswersClosedMsg{Quit: true} }
		case "enter":
			if m.busy || strings.TrimSpace(m.input.Value()) == "" {
				return m, nil
			}
			question := strings.TrimSpace(m.input.Value())
			if strings.HasPrefix(question, "/limit ") {
				parts := strings.Fields(question)
				if len(parts) == 2 {
					if limit, err := strconv.Atoi(parts[1]); err == nil && limit > 0 {
						m.charLimit = limit
						m.status = fmt.Sprintf("Character limit set to %d", limit)
						m.input.Reset()
					} else {
						m.status = "Usage: /limit N"
					}
				} else {
					m.status = "Usage: /limit N"
				}
				return m, nil
			}
			ctx, cancel := context.WithCancel(context.Background())
			m.cancel, m.busy, m.status = cancel, true, "Thinking…"
			return m, answers.Turn(ctx, m.pythonPath, m.projectRoot, answers.TurnRequest{
				Job: m.job.Path, Question: question, CharLimit: m.charLimit,
			})
		case "alt+enter":
			m.input.InsertRune('\n')
			return m, nil
		case "ctrl+r", "ctrl+s":
			if m.busy || len(m.turns) == 0 {
				return m, nil
			}
			action := "regenerate"
			if msg.String() == "ctrl+s" {
				action = "shorten"
			}
			last := m.turns[len(m.turns)-1]
			ctx, cancel := context.WithCancel(context.Background())
			m.cancel, m.busy, m.status = cancel, true, "Thinking…"
			return m, answers.Turn(ctx, m.pythonPath, m.projectRoot, answers.TurnRequest{
				Job: m.job.Path, Question: last.Question, CharLimit: last.Limit, Action: action,
			})
		}
	}
	var cmd tea.Cmd
	m.input, cmd = m.input.Update(msg)
	return m, cmd
}

func (m AnswersModel) View() string {
	header := lipgloss.NewStyle().Bold(true).Foreground(m.theme.Mauve).
		Render(ansi.Truncate(fmt.Sprintf("Application Answers · %s · %s", m.job.Title, m.job.Company), max(1, m.width), "…"))
	bodyLines := m.conversationLines()
	inputLines := strings.Split(m.input.View(), "\n")
	hint := ""
	// Header, input and footer stay put; the conversation scrolls between
	// them, following the newest line unless the user has paged back.
	if avail := m.bodyHeight(); avail > 0 && len(bodyLines) > avail {
		scroll := min(m.scroll, len(bodyLines)-avail)
		endLine := len(bodyLines) - scroll
		bodyLines = bodyLines[endLine-avail : endLine]
		if scroll > 0 {
			hint = fmt.Sprintf(" · ↑%d PgUp/PgDn", scroll)
		} else {
			hint = " · PgUp older"
		}
	}
	footer := lipgloss.NewStyle().Foreground(m.theme.Subtext).
		Render(fmt.Sprintf("%s · Enter send · Esc back · q quit%s", m.status, hint))
	lines := []string{header, ""}
	lines = append(lines, bodyLines...)
	lines = append(lines, "")
	lines = append(lines, inputLines...)
	lines = append(lines, footer)
	for i, line := range lines {
		lines[i] = ansi.Truncate(line, max(1, m.width), "…")
	}
	return strings.Join(lines, "\n")
}

// conversationLines renders every turn, word-wrapped to the terminal width --
// per-line truncation used to cut every answer after its first line.
func (m AnswersModel) conversationLines() []string {
	wrap := func(s string) string { return ansi.Wrap(s, max(1, m.width), "") }
	var body []string
	for _, turn := range m.turns {
		body = append(body, wrap(lipgloss.NewStyle().Foreground(m.theme.Blue).Render("You: ")+turn.Question))
		body = append(body, wrap(lipgloss.NewStyle().Foreground(m.theme.Green).Render("Answer: ")+turn.Answer))
		if turn.Limit > 0 {
			body = append(body, fmt.Sprintf("%s · chars %d/%d", turn.Kind, len([]rune(turn.Answer)), turn.Limit))
		}
		for _, warning := range turn.Warnings {
			body = append(body, wrap(lipgloss.NewStyle().Foreground(m.theme.Peach).Render("⚠ "+warning)))
		}
	}
	if len(body) == 0 {
		body = append(body, wrap(lipgloss.NewStyle().Foreground(m.theme.Subtext).
			Render("Paste an application question and press Enter.")))
	}
	return strings.Split(strings.Join(body, "\n"), "\n")
}

// bodyHeight is the number of conversation rows that fit between the header
// and the input, or 0 when the height is unknown (render everything).
func (m AnswersModel) bodyHeight() int {
	if m.height <= 0 {
		return 0
	}
	return max(1, m.height-len(strings.Split(m.input.View(), "\n"))-4) // header, two blanks, footer
}

// scrollBy moves the view delta lines toward older turns (negative: newer),
// clamped so it can neither pass the first line nor sink below the newest.
func (m *AnswersModel) scrollBy(delta int) {
	top := 0
	if avail := m.bodyHeight(); avail > 0 {
		top = max(0, len(m.conversationLines())-avail)
	}
	m.scroll = min(max(0, m.scroll+delta), top)
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
