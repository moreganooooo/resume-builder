package prompt

import (
	"os"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/huh/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/colorprofile"
	"github.com/charmbracelet/x/ansi"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// hasHeadings reports whether a select spec carries section headings.
// huh's Select has no non-selectable rows, so a headed menu renders through
// sectionModel instead; a plain one keeps huh.
func hasHeadings(spec Spec) bool {
	for _, o := range spec.Options {
		if o.Heading {
			return true
		}
	}
	return false
}

// runSections renders a single-choice menu grouped under headings, styled
// from the same huh theme as every other prompt so it reads as one family.
// Headings are skipped by the cursor, so they can never be submitted.
func runSections(t theme.Theme, spec Spec) (Result, error) {
	m := newSectionModel(t, spec)
	p := tea.NewProgram(m,
		tea.WithOutput(os.Stderr),
		tea.WithColorProfile(colorprofile.TrueColor),
	)
	final, err := p.Run()
	if err != nil {
		return Result{}, err
	}
	s := final.(sectionModel)
	if s.aborted {
		return Result{}, huh.ErrUserAborted
	}
	return Result{Value: s.opts[s.cursor].Value}, nil
}

type sectionModel struct {
	st       *huh.Styles
	title    string
	opts     []Option
	cursor   int
	offset   int
	width    int
	height   int
	lastMove time.Time
	done     bool
	aborted  bool
}

func newSectionModel(t theme.Theme, spec Spec) sectionModel {
	m := sectionModel{
		st: t.HuhTheme().Theme(true), title: spec.Message, opts: spec.Options,
		width: 100, height: 40, cursor: -1,
	}
	for i, o := range m.opts {
		if o.Heading {
			continue
		}
		if m.cursor < 0 || (spec.DefaultValue != "" && o.Value == spec.DefaultValue) {
			m.cursor = i
		}
	}
	return m
}

func (m sectionModel) Init() tea.Cmd { return nil }

// move steps to the next selectable row in dir, wrapping around.
func (m *sectionModel) move(dir int) {
	n := len(m.opts)
	for i := 1; i <= n; i++ {
		j := ((m.cursor+dir*i)%n + n) % n
		if !m.opts[j].Heading {
			m.cursor = j
			return
		}
	}
}

func (m sectionModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
	case tea.KeyPressMsg:
		switch msg.String() {
		case "up", "k", "shift+tab", "down", "j", "tab":
			if time.Since(m.lastMove) < repeatThrottle {
				break
			}
			m.lastMove = time.Now()
			if s := msg.String(); s == "up" || s == "k" || s == "shift+tab" {
				m.move(-1)
			} else {
				m.move(1)
			}
		case "home", "g":
			m.cursor = len(m.opts) - 1
			m.move(1)
		case "end", "G":
			m.cursor = 0
			m.move(-1)
		case "enter":
			if m.cursor >= 0 {
				m.done = true
				return m, tea.Quit
			}
		case "esc", "q", "ctrl+c":
			m.done, m.aborted = true, true
			return m, tea.Quit
		}
	}
	return m, nil
}

// lines renders every row; cursorLine is the index of the highlighted one.
func (m sectionModel) lines() (out []string, cursorLine int) {
	w := max(20, m.width-4)
	heading := lipgloss.NewStyle().Foreground(m.st.Focused.Title.GetForeground()).Bold(true)
	rule := lipgloss.NewStyle().Foreground(m.st.Focused.Description.GetForeground())
	for i, o := range m.opts {
		if o.Heading {
			if i > 0 {
				out = append(out, "")
			}
			label := strings.ToUpper(strings.TrimSpace(o.Label))
			fill := max(0, min(w, 48)-ansi.StringWidth(label)-1)
			out = append(out, heading.Render(label)+" "+rule.Render(strings.Repeat("─", fill)))
			continue
		}
		label := ansi.Truncate(o.Label, w-2, "…")
		if i == m.cursor {
			cursorLine = len(out)
			out = append(out, m.st.Focused.SelectSelector.Render("> ")+m.st.Focused.SelectedOption.Render(label))
		} else {
			out = append(out, "  "+m.st.Focused.UnselectedOption.Render(label))
		}
	}
	return out, cursorLine
}

func (m sectionModel) View() tea.View {
	if m.done {
		return tea.NewView("")
	}
	rows, cur := m.lines()
	// Window long menus around the cursor, keeping its heading in view.
	avail := max(5, m.height-3)
	start := 0
	if len(rows) > avail {
		start = max(0, min(cur-avail/2, len(rows)-avail))
		rows = rows[start : start+avail]
	}
	var b strings.Builder
	b.WriteString(m.st.Focused.Title.Render(m.title) + "\n")
	b.WriteString(strings.Join(rows, "\n"))
	return tea.NewView(m.st.Focused.Base.Render(b.String()))
}
