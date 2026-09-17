package prompt

import (
	"fmt"
	"image/color"
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
// time. Options labeled "[Category] Name" are grouped into one section per
// category (in the order the caller sent them), and each section fills
// top-to-bottom, then left-to-right, so an alphabetical list reads like a
// newspaper. It fills the terminal, reflows on resize, toggles on mouse
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
	gridMaxColW    = 40
)

// gridLine is one rendered row of the body: a section header, a spacer, or
// a row of cells (option indices, -1 for an empty slot in a short column).
type gridLine struct {
	header string
	count  int
	cells  []int
}

type gridModel struct {
	t         theme.Theme
	title     string
	opts      []Option
	cats      []string // parsed category per option ("" when unlabeled)
	names     []string // label without the "[Category] " prefix
	checked   []bool
	visible   []int // option indices matching the filter, in caller order
	lines     []gridLine
	cursor    int // option index under the cursor, -1 when nothing visible
	offset    int // first body line shown
	filter    string
	filtering bool
	width     int
	height    int
	lastMove  time.Time
	aborted   bool
}

func splitCategory(label string) (string, string) {
	if strings.HasPrefix(label, "[") {
		if end := strings.Index(label, "] "); end > 0 {
			return label[1:end], label[end+2:]
		}
	}
	return "", label
}

func newGridModel(t theme.Theme, spec Spec) gridModel {
	m := gridModel{
		t: t, title: spec.Message, opts: spec.Options,
		checked: make([]bool, len(spec.Options)),
		width:   100, height: 30,
	}
	for _, o := range spec.Options {
		c, n := splitCategory(o.Label)
		m.cats = append(m.cats, c)
		m.names = append(m.names, n)
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
	m.cursor, m.offset = -1, 0
	if len(m.visible) > 0 {
		m.cursor = m.visible[0]
	}
	m.layout()
}

func (m gridModel) colWidth() int {
	longest := 0
	for _, n := range m.names {
		longest = max(longest, ansi.StringWidth(n))
	}
	return max(gridMinColW, min(gridMaxColW, longest+5)) // "✓ " + gap
}

func (m gridModel) cols() int {
	return max(1, (m.width-2)/m.colWidth())
}

func (m gridModel) pageRows() int {
	return max(1, m.height-gridHeaderRows-gridFooterRows)
}

// layout rebuilds the body lines: one section per category run, each laid
// out column-major (down, then across) with balanced column heights.
func (m *gridModel) layout() {
	m.lines = m.lines[:0]
	cols := m.cols()
	for start := 0; start < len(m.visible); {
		cat := m.cats[m.visible[start]]
		end := start
		for end < len(m.visible) && m.cats[m.visible[end]] == cat {
			end++
		}
		section := m.visible[start:end]
		if len(m.lines) > 0 {
			m.lines = append(m.lines, gridLine{})
		}
		if cat != "" {
			m.lines = append(m.lines, gridLine{header: cat, count: len(section)})
		}
		rows := (len(section) + cols - 1) / cols
		for r := 0; r < rows; r++ {
			line := gridLine{cells: make([]int, cols)}
			for c := 0; c < cols; c++ {
				line.cells[c] = -1
				if i := c*rows + r; i < len(section) {
					line.cells[c] = section[i]
				}
			}
			m.lines = append(m.lines, line)
		}
		start = end
	}
	m.scrollToCursor()
}

// cursorPos finds the body line and column of the cursor.
func (m gridModel) cursorPos() (int, int) {
	for li, l := range m.lines {
		for c, o := range l.cells {
			if o == m.cursor && o >= 0 {
				return li, c
			}
		}
	}
	return -1, -1
}

// moveVert steps to the nearest cell line above/below (crossing section
// headers), staying in the same column or the closest filled one to its left.
func (m *gridModel) moveVert(dir int) {
	li, col := m.cursorPos()
	if li < 0 {
		return
	}
	for l := li + dir; l >= 0 && l < len(m.lines); l += dir {
		cells := m.lines[l].cells
		for c := min(col, len(cells)-1); c >= 0; c-- {
			if cells[c] >= 0 {
				m.cursor = cells[c]
				m.scrollToCursor()
				return
			}
		}
	}
}

// moveHoriz steps to the neighboring column on the same row, skipping the
// empty slots a short final column leaves.
func (m *gridModel) moveHoriz(dir int) {
	li, col := m.cursorPos()
	if li < 0 {
		return
	}
	cells := m.lines[li].cells
	for c := col + dir; c >= 0 && c < len(cells); c += dir {
		if cells[c] >= 0 {
			m.cursor = cells[c]
			return
		}
	}
}

func (m *gridModel) scrollToCursor() {
	li, _ := m.cursorPos()
	if li < 0 {
		return
	}
	// Keep a section's header in view when its first row is focused.
	top := li
	if li > 0 && m.lines[li-1].header != "" {
		top = li - 1
	}
	rows := m.pageRows()
	if top < m.offset {
		m.offset = top
	} else if li >= m.offset+rows {
		m.offset = li - rows + 1
	}
	m.clampOffset()
}

func (m *gridModel) clampOffset() {
	m.offset = max(0, min(m.offset, len(m.lines)-m.pageRows()))
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
		m.layout()

	case tea.MouseClickMsg:
		if msg.Button != tea.MouseLeft {
			break
		}
		li := m.offset + msg.Y - gridHeaderRows
		col := (msg.X - 1) / m.colWidth()
		if msg.Y >= gridHeaderRows && li < len(m.lines) && li < m.offset+m.pageRows() && msg.X >= 1 {
			if cells := m.lines[li].cells; col < len(cells) && cells[col] >= 0 {
				m.cursor = cells[col]
				m.checked[m.cursor] = !m.checked[m.cursor]
			}
		}

	case tea.MouseWheelMsg:
		if msg.Button == tea.MouseWheelUp {
			m.offset--
		} else if msg.Button == tea.MouseWheelDown {
			m.offset++
		}
		m.clampOffset()

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

		moves := map[string]func(){
			"up": func() { m.moveVert(-1) }, "k": func() { m.moveVert(-1) },
			"down": func() { m.moveVert(1) }, "j": func() { m.moveVert(1) },
			"left": func() { m.moveHoriz(-1) }, "h": func() { m.moveHoriz(-1) },
			"right": func() { m.moveHoriz(1) }, "l": func() { m.moveHoriz(1) },
			"pgup":   func() { m.page(-1) },
			"pgdown": func() { m.page(1) },
		}
		if mv, ok := moves[key]; ok {
			if now := time.Now(); now.Sub(m.lastMove) >= repeatThrottle {
				m.lastMove = now
				mv()
			}
			return m, nil
		}
		switch key {
		case "home", "g":
			if len(m.visible) > 0 {
				m.cursor, m.offset = m.visible[0], 0
			}
		case "end", "G":
			if len(m.visible) > 0 {
				m.cursor = m.visible[len(m.visible)-1]
				m.scrollToCursor()
			}
		case "space", "x":
			if m.cursor >= 0 {
				m.checked[m.cursor] = !m.checked[m.cursor]
			}
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

func (m *gridModel) page(dir int) {
	for i := 0; i < m.pageRows(); i++ {
		m.moveVert(dir)
	}
}

// categoryColor gives each section its own accent; unknown categories
// take a stable color from the rest of the palette.
func (m gridModel) categoryColor(cat string) lipgloss.Style {
	palette := []color.Color{m.t.Blue, m.t.Peach, m.t.Mauve, m.t.Yellow, m.t.Sky, m.t.Pink}
	known := map[string]int{"tool": 0, "hard skill": 1, "core function": 2, "skill": 3}
	idx, ok := known[strings.ToLower(cat)]
	if !ok {
		sum := 0
		for _, r := range cat {
			sum += int(r)
		}
		idx = 4 + sum%2
	}
	return lipgloss.NewStyle().Foreground(palette[idx])
}

func pluralize(cat string) string {
	if strings.HasSuffix(cat, "s") {
		return cat
	}
	return cat + "s"
}

func (m gridModel) renderCell(o, w int) string {
	if o < 0 {
		return strings.Repeat(" ", w)
	}
	mark := lipgloss.NewStyle().Foreground(m.t.Overlay).Render("○")
	nameStyle := lipgloss.NewStyle().Foreground(m.t.Text)
	if m.checked[o] {
		mark = lipgloss.NewStyle().Foreground(m.t.Green).Bold(true).Render("✓")
		nameStyle = nameStyle.Foreground(m.t.Green)
	}
	name := nameStyle.Render(ansi.Truncate(m.names[o], w-4, "…"))
	style := lipgloss.NewStyle().Width(w - 1)
	if o == m.cursor {
		style = style.Background(m.t.Surface).Bold(true)
	}
	return style.Render(mark+" "+name) + " "
}

func (m gridModel) renderHeader(l gridLine) string {
	accent := m.categoryColor(l.header)
	selected := 0
	for _, o := range m.visible {
		if m.cats[o] == l.header && m.checked[o] {
			selected++
		}
	}
	dim := lipgloss.NewStyle().Foreground(m.t.Subtext)
	title := accent.Bold(true).Render("▍" + strings.ToUpper(pluralize(l.header)))
	meta := fmt.Sprintf(" %d", l.count)
	if selected > 0 {
		meta += fmt.Sprintf(" · %d selected", selected)
	}
	used := ansi.StringWidth(pluralize(l.header)) + 1 + len(meta) + 2
	rule := strings.Repeat("─", max(0, m.cols()*m.colWidth()-used))
	return title + dim.Render(meta+" ") + lipgloss.NewStyle().Foreground(m.t.Overlay).Render(rule)
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
		b.WriteString(" " + accent.Render("/ ") + m.filter + accent.Render("█") + "\n\n")
	case m.filter != "":
		b.WriteString(" " + dim.Render("filter: ") + m.filter + dim.Render("  (esc to clear)") + "\n\n")
	default:
		b.WriteString("\n\n")
	}

	w, rows := m.colWidth(), m.pageRows()
	for li := m.offset; li < m.offset+rows; li++ {
		if li < len(m.lines) {
			l := m.lines[li]
			b.WriteString(" ")
			if l.header != "" {
				b.WriteString(m.renderHeader(l))
			}
			for _, o := range l.cells {
				b.WriteString(m.renderCell(o, w))
			}
		}
		b.WriteString("\n")
	}

	if len(m.visible) == 0 {
		b.WriteString(dim.Render(" no matches"))
	}
	pos := ""
	if len(m.lines) > rows {
		pct := 100 * (m.offset + rows) / len(m.lines)
		pos = fmt.Sprintf("%d%%  ·  ", min(100, pct))
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
