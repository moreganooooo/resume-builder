package screens

import (
	"fmt"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"
	"github.com/sahilm/fuzzy"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// -- CommandPalette --
//
// Nine screens and roughly forty bindings: remembering WHICH key is the
// bottleneck, not moving between screens. The palette turns "which key was
// that" into "type what you want", on ctrl+k or `:`.
//
// Two rules from the spec do the actual work:
//   - matched characters render Mauve and bold inside an otherwise plain
//     label, so a person can see WHY a row matched. That is the difference
//     between fzf-style matching feeling intelligent and feeling arbitrary.
//   - every row carries the keybinding it stands for, on the right. The
//     palette teaches the shortcut it is replacing, and so works to make
//     itself progressively unnecessary -- which is the point of a palette in
//     a keyboard-driven tool, as opposed to a menu.
//
// Commands are DERIVED from the screens' own help categories rather than
// listed here a second time (see PaletteCommandsFor). A palette that keeps
// its own copy of the bindings is a palette that will eventually teach a key
// the screen no longer has.

// PaletteCommand is one row. Key is the binding this command stands for, and
// is what gets dispatched -- a command with no Key is navigation, carried by
// Nav instead.
type PaletteCommand struct {
	Group string
	Label string
	Key   string
	Nav   string // menu command to route to, for cross-screen navigation
}

// paletteResult pairs a command with the character positions that matched,
// which is what lets the renderer highlight them.
type paletteResult struct {
	cmd     PaletteCommand
	matched []int
}

// PaletteModel is the palette's own state. The zero value is closed.
type PaletteModel struct {
	Open     bool
	query    string
	cursor   int
	commands []PaletteCommand
	results  []paletteResult
}

// NewPalette opens a palette over the given commands.
func NewPalette(commands []PaletteCommand) PaletteModel {
	m := PaletteModel{Open: true, commands: commands}
	m.refilter()
	return m
}

// Close hides the palette and forgets the query, so reopening it starts
// clean -- a palette that reopens on the last search is answering a question
// the user already finished asking.
func (m *PaletteModel) Close() {
	m.Open = false
	m.query = ""
	m.cursor = 0
	m.results = nil
}

// Query is the text typed so far.
func (m PaletteModel) Query() string { return m.query }

// Selected is the highlighted command, if any.
func (m PaletteModel) Selected() (PaletteCommand, bool) {
	if m.cursor < 0 || m.cursor >= len(m.results) {
		return PaletteCommand{}, false
	}
	return m.results[m.cursor].cmd, true
}

// HandleKey applies one keypress. It reports whether the palette consumed
// it (it consumes everything while open, including plain letters -- those
// are the query) and whether the press CHOSE a command, which the caller
// then dispatches. Esc closes.
func (m *PaletteModel) HandleKey(key string) (consumed, chosen bool) {
	if !m.Open {
		return false, false
	}
	switch key {
	case "esc", "ctrl+c":
		m.Close()
		return true, false
	case "enter":
		if _, ok := m.Selected(); ok {
			return true, true
		}
		return true, false
	case "up", "ctrl+p":
		if m.cursor > 0 {
			m.cursor--
		}
		return true, false
	case "down", "ctrl+n":
		if m.cursor < len(m.results)-1 {
			m.cursor++
		}
		return true, false
	case "backspace":
		if r := []rune(m.query); len(r) > 0 {
			m.query = string(r[:len(r)-1])
			m.refilter()
		}
		return true, false
	case "ctrl+u":
		m.query = ""
		m.refilter()
		return true, false
	}
	// Single printable runes are query text. Anything longer is a named key
	// (tab, pgdown, f1...) the palette has no use for; swallowing it anyway
	// keeps the screen underneath from acting on a keypress the user aimed
	// at the palette.
	if r := []rune(key); len(r) == 1 {
		m.query += key
		m.refilter()
	}
	return true, false
}

// refilter re-runs the match. An empty query lists everything in its
// original order, which is what makes the palette browsable as well as
// searchable -- opening it should not require knowing what to type.
func (m *PaletteModel) refilter() {
	m.results = m.results[:0]
	if m.query == "" {
		for _, c := range m.commands {
			m.results = append(m.results, paletteResult{cmd: c})
		}
		m.cursor = 0
		return
	}

	// Matched against the LABEL alone, not "group label": a query typed to
	// find an action would otherwise be satisfied by the screen name every
	// one of that screen's rows already carries, which ranks whole groups
	// ahead of the row actually wanted.
	labels := make([]string, len(m.commands))
	for i, c := range m.commands {
		labels[i] = c.Label
	}
	for _, match := range fuzzy.Find(m.query, labels) {
		m.results = append(m.results, paletteResult{
			cmd:     m.commands[match.Index],
			matched: match.MatchedIndexes,
		})
	}
	m.cursor = 0
}

// ResultCount is how many commands currently match.
func (m PaletteModel) ResultCount() int { return len(m.results) }

// PaletteNavTargets is the set of screens the palette can navigate to, in
// menu order. The strings are menu.MenuSelectMsg commands, which is what
// makes the palette reuse the existing navigation dispatch rather than
// grow a second one.
var PaletteNavTargets = []string{
	"Pipeline", "Jobs", "Knowledge Base", "Progress", "Insights", "Documents",
}

// PaletteCommandsForScreen builds the palette's command list for whichever
// screen is showing. It reads the screens' OWN help categories, so a
// binding that is renamed or removed changes here with it -- a palette that
// kept its own copy would eventually teach a key the screen no longer has.
func PaletteCommandsForScreen(screen string) []PaletteCommand {
	var cats []helpCategory
	switch screen {
	case "Pipeline":
		cats = pipelineHelpCategories
	case "Jobs":
		cats = jobsHelpCategories
	case "Progress", "Insights":
		cats = progressHelpCategories
	}
	return paletteCommandsFor(screen, cats, PaletteNavTargets)
}

// paletteCommandsFor builds the command list: navigation to every other
// screen, then the CURRENT screen's own single-key actions. Scoping actions
// to the current screen is deliberate -- a key is dispatched to whatever
// screen is showing, so offering another screen's `b` would either do
// nothing or do the wrong thing.
//
// Bindings whose key is not a single token ("↑ ↓ / j k", "PgUp / PgDn") are
// skipped: they are movement, which a palette is a poor way to perform, and
// there is no one key to dispatch for them.
func paletteCommandsFor(screen string, categories []helpCategory, navTargets []string) []PaletteCommand {
	var cmds []PaletteCommand
	for _, target := range navTargets {
		if target == screen {
			continue
		}
		cmds = append(cmds, PaletteCommand{
			Group: "Go to",
			Label: target,
			Nav:   target,
		})
	}
	for _, cat := range categories {
		for _, b := range cat.bindings {
			if !dispatchableKey(b.key) {
				continue
			}
			cmds = append(cmds, PaletteCommand{
				Group: screen,
				Label: b.desc,
				Key:   b.key,
			})
		}
	}
	return cmds
}

// dispatchableKey reports whether a help bar's key string names exactly one
// key the palette can send on the user's behalf.
func dispatchableKey(key string) bool {
	if key == "" {
		return false
	}
	return !strings.ContainsAny(key, " /")
}

// paletteWidth keeps the palette a dialog rather than a full-width banner,
// while still fitting the longest real label at the mobile floor.
func paletteWidth(termWidth int) int {
	w := termWidth - 8
	if w > 64 {
		w = 64
	}
	return w
}

// Render draws the palette as a bordered box: prompt line, results, footer.
// maxRows caps the result list so the box cannot outgrow the terminal.
func (m PaletteModel) Render(t theme.Theme, termWidth, maxRows int) string {
	if !m.Open {
		return ""
	}
	width := paletteWidth(termWidth)
	if width < 20 || maxRows < 1 {
		return ""
	}
	inner := width - 4 // border + padding

	subtext := lipgloss.NewStyle().Foreground(t.Subtext)
	divider := lipgloss.NewStyle().Foreground(t.Overlay).Render(strings.Repeat("─", inner))

	queryText := m.query
	queryStyle := lipgloss.NewStyle().Foreground(t.Text)
	if queryText == "" {
		queryText = "Search screens and actions"
		queryStyle = lipgloss.NewStyle().Foreground(t.Overlay)
	}
	prompt := lipgloss.NewStyle().Foreground(t.Mauve).Bold(true).Render("❯") + " " +
		queryStyle.Render(ansi.Truncate(queryText, inner-4, "…")) +
		lipgloss.NewStyle().Foreground(t.Mauve).Render("█")

	lines := []string{prompt, divider}

	if len(m.results) == 0 {
		lines = append(lines, subtext.Render(
			ansi.Truncate(fmt.Sprintf("No match for %q", m.query), inner, "…")))
	} else {
		// Keep the cursor visible when the match list is taller than the
		// box: scroll the window rather than clipping it at the top, or a
		// selection made below the fold is invisible while it is acted on.
		start := 0
		if m.cursor >= maxRows {
			start = m.cursor - maxRows + 1
		}
		end := start + maxRows
		if end > len(m.results) {
			end = len(m.results)
		}
		for i := start; i < end; i++ {
			lines = append(lines, m.renderRow(t, m.results[i], i == m.cursor, inner))
		}
	}

	lines = append(lines, divider, subtext.Render("↑↓ move · enter run · esc close"))

	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Mauve).
		Background(t.Base).
		Padding(0, 1).
		Width(width - 2).
		Render(strings.Join(lines, "\n"))
}

// OverlayCentered splices an already-rendered block into the middle of a
// view without changing its line count, the same no-reflow rule
// OverlayBottomRight follows: a palette that pushed the screen around
// would lose the user's place the moment it opened.
//
// It composites rather than replacing the view so the screen stays visible
// around the box -- the palette is a thing on top of your work, not a
// detour away from it.
func OverlayCentered(view, block string, width, height int) string {
	if block == "" {
		return view
	}
	viewLines := strings.Split(view, "\n")
	blockLines := strings.Split(block, "\n")
	if len(blockLines) >= len(viewLines) {
		return block
	}

	top := (len(viewLines) - len(blockLines)) / 2
	blockW := lipgloss.Width(blockLines[0])
	left := (width - blockW) / 2
	if left < 0 {
		left = 0
	}

	for i, bl := range blockLines {
		row := top + i
		if row < 0 || row >= len(viewLines) {
			continue
		}
		prefix := ansi.Truncate(viewLines[row], left, "")
		if w := lipgloss.Width(prefix); w < left {
			prefix += strings.Repeat(" ", left-w)
		}
		viewLines[row] = prefix + bl
	}
	return strings.Join(viewLines, "\n")
}

// paletteGroupWidth is the fixed left column. Fixed rather than measured so
// the labels line up across groups, which is what makes the list scannable.
const paletteGroupWidth = 10

func (m PaletteModel) renderRow(t theme.Theme, r paletteResult, selected bool, inner int) string {
	marker := "  "
	if selected {
		marker = lipgloss.NewStyle().Foreground(t.Mauve).Render("▌ ")
	}

	group := lipgloss.NewStyle().Foreground(t.Subtext).Width(paletteGroupWidth).
		Render(ansi.Truncate(r.cmd.Group, paletteGroupWidth-1, "…"))

	keyText := ""
	if r.cmd.Key != "" {
		keyText = lipgloss.NewStyle().Foreground(t.Blue).Render(r.cmd.Key)
	}

	labelRoom := inner - lipgloss.Width(marker) - paletteGroupWidth - lipgloss.Width(keyText) - 1
	if labelRoom < 6 {
		labelRoom = 6
	}
	label := highlightMatch(t, r.cmd.Label, r.matched, labelRoom, selected)

	row := marker + group + label
	if keyText != "" {
		if pad := inner - lipgloss.Width(row) - lipgloss.Width(keyText); pad > 0 {
			row += strings.Repeat(" ", pad)
		}
		row += keyText
	}
	return row
}

// highlightMatch renders label with the matched character positions in Mauve
// bold. Truncation happens by RUNE here rather than through ansi.Truncate,
// because each rune is styled separately and the match indices are rune
// positions in the original string -- truncating the styled result would cut
// inside an escape sequence.
func highlightMatch(t theme.Theme, label string, matched []int, width int, selected bool) string {
	plain := lipgloss.NewStyle().Foreground(t.Text)
	if selected {
		plain = plain.Bold(true)
	}
	hit := lipgloss.NewStyle().Foreground(t.Mauve).Bold(true)

	isMatch := make(map[int]bool, len(matched))
	for _, i := range matched {
		isMatch[i] = true
	}

	runes := []rune(label)
	truncated := false
	if len(runes) > width {
		runes = runes[:width-1]
		truncated = true
	}

	var b strings.Builder
	for i, ch := range runes {
		if isMatch[i] {
			b.WriteString(hit.Render(string(ch)))
		} else {
			b.WriteString(plain.Render(string(ch)))
		}
	}
	if truncated {
		b.WriteString(plain.Render("…"))
	} else if pad := width - len(runes); pad > 0 {
		b.WriteString(strings.Repeat(" ", pad))
	}
	return b.String()
}
