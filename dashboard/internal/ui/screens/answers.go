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
	theme         theme.Theme
	pythonPath    string
	projectRoot   string
	cancel        context.CancelFunc
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
	case tea.KeyPressMsg:
		switch msg.String() {
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
	var body []string
	for _, turn := range m.turns {
		body = append(body, lipgloss.NewStyle().Foreground(m.theme.Blue).Render("You: ")+turn.Question)
		body = append(body, lipgloss.NewStyle().Foreground(m.theme.Green).Render("Answer: ")+turn.Answer)
		if turn.Limit > 0 {
			body = append(body, fmt.Sprintf("%s · chars %d/%d", turn.Kind, len([]rune(turn.Answer)), turn.Limit))
		}
		for _, warning := range turn.Warnings {
			body = append(body, lipgloss.NewStyle().Foreground(m.theme.Peach).Render("⚠ "+warning))
		}
	}
	if len(body) == 0 {
		body = append(body, lipgloss.NewStyle().Foreground(m.theme.Subtext).
			Render("Paste an application question and press Enter."))
	}
	footer := lipgloss.NewStyle().Foreground(m.theme.Subtext).
		Render(fmt.Sprintf("%s · Enter send · Esc back · q quit", m.status))
	lines := strings.Split(strings.Join([]string{header, "", strings.Join(body, "\n"), "", m.input.View(), footer}, "\n"), "\n")
	for i, line := range lines {
		lines[i] = ansi.Truncate(line, max(1, m.width), "…")
	}
	return strings.Join(lines, "\n")
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
