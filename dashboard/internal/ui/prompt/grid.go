package prompt

import (
	"fmt"
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

// runGrid renders a full-screen, multi-column checkbox ("grid" spec type)
// for long lists -- skill_gap_scan.py's pending-pipeline skill list can run
// into the hundreds, and huh's single-column MultiSelect showed ~24 at a
// time. The grid fills the terminal, reflows on resize, toggles on mouse
// click, and throttles held arrow keys so a key-repeat burst doesn't sail
// past the intended item.
func runGrid(t theme.Theme, spec Spec) (Result, error) {
	m := newGridModel(t, spec)
	p := tea.NewProgram(m,
		tea.WithOutput(os.Stderr),
		tea.WithColorProfile(colorprofile.TrueColor),
	)
	final, err := p.Run()
	if err != nil {
		return Result{}, err
	}
	g := final.(gridModel)
	if g.aborted {
		return Result{}, huh.ErrUserAborted
	}
	values := []string{}
	for i, o := range g.opts {
		if g.checked[i] {
			values = append(values, o.Value)
		}
	}
	return Result{Values: values}, nil
}

// repeatThrottle drops movement keys arriving faster than this after the
// previous accepted move. A deliberate tap is never this fast; macOS key
// repeat at its fastest setting is ~30ms, so holding an arrow moves at
// roughly half speed instead of overshooting.
const repeatThrottle = 65 * time.Millisecond

const (
	gridHeaderRows = 4 // title, status, filter, blank
	gridFooterRows = 2 // blank, help
	gridMinColW    = 22
	gridMaxColW    = 44
)

type gridModel struct {
	t         theme.Theme
	title     string
	opts      []Option
	checked   []bool
	visible   []int // indices into opts matching the filter
	cursor    int   // index into visible
	offset    int   // first visible ROW
	filter    string
	filtering bool
	width     int
	height    int
	lastMove  time.Time
	aborted   bool
}

func newGridModel(t theme.Theme, spec Spec) gridModel {
	m := gridModel{
		t: t, title: spec.Message, opts: spec.Options,
		checked: make([]bool, len(spec.Options)),
		width:   100, height: 30,
	}
	m.applyFilter()
	return m
}

func (m *gridModel) applyFilter() {
	m.visible = m.visible[:0]
	q := strings.ToLower(m.filter)
	for i, o := range m.opts {
		if q == "" || strings.Contains(strings.ToLower(o.Label), q) {
			m.visible = append(m.visible, i)
		}
	}
	m.cursor, m.offset = 0, 0
}

func (m gridModel) colWidth() int {
	longest := 0
	for _, o := range m.opts {
		if w := ansi.StringWidth(o.Label); w > longest {
			longest = w
		}
	}
	w := longest + 5 // "✓ " marker + gap
	return max(gridMinColW, min(gridMaxColW, w))
}

func (m gridModel) cols() int {
	return max(1, (m.width-2)/m.colWidth())
}

func (m gridModel) pageRows() int {
	return max(1, m.height-gridHeaderRows-gridFooterRows)
}

func (m *gridModel) move(d int) {
	n := len(m.visible)
	if n == 0 {
		return
	}
	m.cursor = max(0, min(n-1, m.cursor+d))
	m.scrollToCursor()
}

func (m *gridModel) scrollToCursor() {
	row, rows := m.cursor/m.cols(), m.pageRows()
	if row < m.offset {
		m.offset = row
	} else if row >= m.offset+rows {
		m.offset = row - rows + 1
	}
}

func (m *gridModel) toggle(vi int) {
	if vi >= 0 && vi < len(m.visible) {
		i := m.visible[vi]
		m.checked[i] = !m.checked[i]
	}
}

func (m gridModel) selectedCount() int {
	n := 0
	for _, c := range m.checked {
		if c {
			n++
		}
	}
	return n
}

func (m gridModel) Init() tea.Cmd { return nil }

func (m gridModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width, m.height = msg.Width, msg.Height
		m.scrollToCursor()

	case tea.MouseClickMsg:
		if msg.Button != tea.MouseLeft {
			break
		}
		row := msg.Y - gridHeaderRows
		col := (msg.X - 1) / m.colWidth()
		if row >= 0 && row < m.pageRows() && msg.X >= 1 && col < m.cols() {
			vi := (m.offset+row)*m.cols() + col
			if vi < len(m.visible) {
				m.cursor = vi
				m.toggle(vi)
			}
		}

	case tea.MouseWheelMsg:
		maxOff := max(0, (len(m.visible)+m.cols()-1)/m.cols()-m.pageRows())
		if msg.Button == tea.MouseWheelUp {
			m.offset = max(0, m.offset-1)
		} else if msg.Button == tea.MouseWheelDown {
			m.offset = min(maxOff, m.offset+1)
		}

	case tea.KeyPressMsg:
		key := msg.String()
		if m.filtering {
			switch key {
			case "esc":
				m.filtering, m.filter = false, ""
				m.applyFilter()
			case "enter":
				m.filtering = false
			case "backspace":
				if m.filter != "" {
					r := []rune(m.filter)
					m.filter = string(r[:len(r)-1])
					m.applyFilter()
				}
			default:
				if msg.Text != "" {
					m.filter += msg.Text
					m.applyFilter()
				}
			}
			return m, nil
		}

		moves := map[string]int{
			"left": -1, "h": -1, "right": 1, "l": 1,
			"up": -m.cols(), "k": -m.cols(), "down": m.cols(), "j": m.cols(),
			"pgup": -m.cols() * m.pageRows(), "pgdown": m.cols() * m.pageRows(),
		}
		if d, ok := moves[key]; ok {
			if now := time.Now(); now.Sub(m.lastMove) >= repeatThrottle {
				m.lastMove = now
				m.move(d)
			}
			return m, nil
		}
		switch key {
		case "home", "g":
			m.cursor, m.offset = 0, 0
		case "end", "G":
			m.move(len(m.visible))
		case "space", "x":
			m.toggle(m.cursor)
		case "ctrl+a", "a":
			// Toggle every item currently shown (respects the filter).
			allOn := true
			for _, i := range m.visible {
				allOn = allOn && m.checked[i]
			}
			for _, i := range m.visible {
				m.checked[i] = !allOn
			}
		case "/":
			m.filtering = true
		case "enter":
			return m, tea.Quit
		case "esc":
			if m.filter != "" {
				m.filter = ""
				m.applyFilter()
				return m, nil
			}
			m.aborted = true
			return m, tea.Quit
		case "ctrl+c", "q":
			m.aborted = true
			return m, tea.Quit
		}
	}
	return m, nil
}

// categoryColor tints the "[Category]" prefix skill_gap_scan.py puts on
// each label, so groups read at a glance in a dense grid.
func (m gridModel) categoryColor(cat string) lipgloss.Style {
	c := m.t.Sky
	switch strings.ToLower(cat) {
	case "tool":
		c = m.t.Blue
	case "platform":
		c = m.t.Mauve
	case "skill":
		c = m.t.Peach
	case "certification":
		c = m.t.Yellow
	}
	return lipgloss.NewStyle().Foreground(c)
}

func (m gridModel) renderCell(vi, w int) string {
	i := m.visible[vi]
	o := m.opts[i]
	focused := vi == m.cursor

	mark := lipgloss.NewStyle().Foreground(m.t.Overlay).Render("○")
	if m.checked[i] {
		mark = lipgloss.NewStyle().Foreground(m.t.Green).Bold(true).Render("✓")
	}

	label := o.Label
	textW := w - 3
	var body string
	if strings.HasPrefix(label, "[") {
		if end := strings.Index(label, "] "); end > 0 {
			cat := label[1:end]
			name := ansi.Truncate(label[end+2:], max(1, textW-2), "…")
			nameStyle := lipgloss.NewStyle().Foreground(m.t.Text)
			if m.checked[i] {
				nameStyle = nameStyle.Foreground(m.t.Green)
			}
			body = m.categoryColor(cat).Render("▍") + " " + nameStyle.Render(name)
		}
	}
	if body == "" {
		body = lipgloss.NewStyle().Foreground(m.t.Text).Render(ansi.Truncate(label, textW, "…"))
	}

	cell := lipgloss.NewStyle().Width(w - 1).Render(mark + " " + body)
	if focused {
		cell = lipgloss.NewStyle().Width(w - 1).Background(m.t.Surface).Bold(true).Render(mark + " " + body)
	}
	return cell + " "
}

func (m gridModel) View() tea.View {
	var b strings.Builder
	accent := lipgloss.NewStyle().Foreground(m.t.Mauve).Bold(true)
	dim := lipgloss.NewStyle().Foreground(m.t.Subtext)

	b.WriteString(" " + accent.Render(m.title) + "\n")
	b.WriteString(" " + lipgloss.NewStyle().Foreground(m.t.Green).Bold(true).
		Render(fmt.Sprintf("%d selected", m.selectedCount())) +
		dim.Render(fmt.Sprintf("  ·  %d shown of %d", len(m.visible), len(m.opts))) + "\n")
	switch {
	case m.filtering:
		b.WriteString(" " + accent.Render("/ ") + m.filter + lipgloss.NewStyle().Foreground(m.t.Mauve).Render("█") + "\n\n")
	case m.filter != "":
		b.WriteString(" " + dim.Render("filter: ") + m.filter + dim.Render("  (esc to clear)") + "\n\n")
	default:
		b.WriteString("\n\n")
	}

	cols, w, rows := m.cols(), m.colWidth(), m.pageRows()
	totalRows := (len(m.visible) + cols - 1) / cols
	for r := m.offset; r < m.offset+rows; r++ {
		if r < totalRows {
			b.WriteString(" ")
			for c := 0; c < cols; c++ {
				if vi := r*cols + c; vi < len(m.visible) {
					b.WriteString(m.renderCell(vi, w))
				}
			}
		}
		b.WriteString("\n")
	}

	if len(m.visible) == 0 {
		b.WriteString(dim.Render(" no matches"))
	}
	pos := ""
	if totalRows > rows {
		pos = fmt.Sprintf("rows %d–%d of %d  ·  ", m.offset+1, min(totalRows, m.offset+rows), totalRows)
	}
	key := lipgloss.NewStyle().Foreground(m.t.Blue).Bold(true)
	help := []string{
		key.Render("click/space") + dim.Render(" toggle"),
		key.Render("←↑↓→") + dim.Render(" move"),
		key.Render("a") + dim.Render(" all"),
		key.Render("/") + dim.Render(" filter"),
		key.Render("enter") + dim.Render(" confirm"),
		key.Render("esc") + dim.Render(" cancel"),
	}
	b.WriteString("\n " + dim.Render(pos) + strings.Join(help, dim.Render("  ·  ")))

	v := tea.NewView(b.String())
	v.AltScreen = true
	v.MouseMode = tea.MouseModeCellMotion
	return v
}
