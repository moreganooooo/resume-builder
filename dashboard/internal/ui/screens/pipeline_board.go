package screens

import (
	"fmt"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

// boardStatuses are the board's columns, in pipeline order.
//
// Skip, Rejected and Discarded are deliberately absent. A board reads as a
// path forward, and a terminal status is not a place an application is moving
// through -- putting them here would invite an H/L nudge into a column nothing
// leaves, and would widen every other column for the privilege. They stay
// reachable in the list modes, where they are already grouped and counted.
var boardStatuses = []string{"evaluated", "applied", "responded", "interview", "offer"}

// boardColumnWidth is the narrowest a column can be and still say anything
// useful. Below five columns' worth the board is rendered as a notice instead,
// since a two-character-wide card is not a view.
const boardColumnWidth = 18

// boardCardLines is how many rows each card occupies: company, role, score.
const boardCardLines = 3

// boardColumns buckets the currently filtered applications into the board's
// columns, carrying each one's index in m.filtered along with it.
//
// The index is the point: every other action on this screen -- loading the
// report, opening the URL, changing the status, undo -- goes through
// m.cursor as an index into m.filtered, so the board navigates by moving
// that same cursor rather than keeping a second position of its own that
// the rest of the screen would not know about.
func (m PipelineModel) boardColumns() [][]int {
	cols := make([][]int, len(boardStatuses))
	for i, app := range m.filtered {
		norm := data.NormalizeStatus(app.Status)
		for c, status := range boardStatuses {
			if norm == status {
				cols[c] = append(cols[c], i)
				break
			}
		}
	}
	return cols
}

// boardCursorColumn reports which column the cursor currently sits in, and
// its row within that column. Returns (-1, -1) when the cursor is on an
// application no column holds (a Rejected role, say, reached in list mode
// before switching to the board).
func (m PipelineModel) boardCursorColumn() (col, row int) {
	for c, idxs := range m.boardColumns() {
		for r, idx := range idxs {
			if idx == m.cursor {
				return c, r
			}
		}
	}
	return -1, -1
}

// boardMoveCursor moves the cursor by dCol columns and dRow rows, clamping at
// both edges rather than wrapping -- a board's columns are an ordered funnel,
// so wrapping from Offer back to Evaluated would read as progress lost.
func (m *PipelineModel) boardMoveCursor(dCol, dRow int) bool {
	cols := m.boardColumns()
	col, row := m.boardCursorColumn()
	if col < 0 {
		// Not on the board at all: land on the first column that has
		// anything, so the first keypress does something visible.
		for c, idxs := range cols {
			if len(idxs) > 0 {
				m.cursor = idxs[0]
				m.boardColumn = c
				return true
			}
		}
		return false
	}

	if dCol != 0 {
		target := col + dCol
		if target < 0 || target >= len(cols) {
			return false
		}
		m.boardColumn = target
		if len(cols[target]) == 0 {
			// An empty column still takes focus -- it is where an H/L
			// move would land, so the user has to be able to see it --
			// but there is no card to put the cursor on.
			return true
		}
		if row >= len(cols[target]) {
			row = len(cols[target]) - 1
		}
		m.cursor = cols[target][row]
		return true
	}

	target := row + dRow
	if target < 0 || target >= len(cols[col]) {
		return false
	}
	m.cursor = cols[col][target]
	return true
}

// boardProposeMove opens the existing confirm step for shifting the focused
// card one column left or right.
//
// Deliberately the same two-step confirm the status picker uses, and
// deliberately not a commit on keypress: H and L sit next to h and l, a status
// write goes out to Python and into the tracker, and "I meant to scroll" is
// not something the undo stack should be the first line of defense against.
func (m *PipelineModel) boardProposeMove(delta int) bool {
	col, _ := m.boardCursorColumn()
	if col < 0 {
		return false
	}
	target := col + delta
	if target < 0 || target >= len(boardStatuses) {
		return false
	}
	if _, ok := m.CurrentApp(); !ok {
		return false
	}
	m.pendingStatus = statusLabel(boardStatuses[target])
	m.statusPicker = true
	m.statusConfirm = true
	// Leave statusCursor pointing at the proposed status, so backing out of
	// the confirm with Esc drops into the picker on the same entry rather
	// than on whatever was last highlighted.
	for i, opt := range statusOptions {
		if strings.EqualFold(opt, m.pendingStatus) {
			m.statusCursor = i
			break
		}
	}
	return true
}

// handleBoardKey claims the handful of keys whose meaning changes on the
// board, and reports whether it did. Everything it does not claim -- the
// filters, sort, status picker, search, `o`, `r`, `?` -- falls through to the
// screen's normal handler unchanged, because none of those care which way the
// rows happen to be laid out.
//
// Tab cycling loses its h/l/arrow spelling here, since the board needs those
// for its own columns, but `f` still cycles tabs, so nothing becomes
// unreachable.
func (m PipelineModel) handleBoardKey(msg tea.KeyPressMsg) (bool, PipelineModel, tea.Cmd) {
	switch msg.String() {
	case "down", "j":
		if m.boardMoveCursor(0, 1) {
			return true, m, m.loadCurrentReport()
		}
		return true, m, nil

	case "up", "k":
		if m.boardMoveCursor(0, -1) {
			return true, m, m.loadCurrentReport()
		}
		return true, m, nil

	case "right", "l":
		if m.boardMoveCursor(1, 0) {
			return true, m, m.loadCurrentReport()
		}
		return true, m, nil

	case "left", "h":
		if m.boardMoveCursor(-1, 0) {
			return true, m, m.loadCurrentReport()
		}
		return true, m, nil

	case "L":
		if !m.boardProposeMove(1) {
			m.notice = "No column to the right to move this to."
		}
		return true, m, nil

	case "H":
		if !m.boardProposeMove(-1) {
			m.notice = "No column to the left to move this to."
		}
		return true, m, nil
	}
	return false, m, nil
}

// renderBoard draws the five columns side by side.
func (m PipelineModel) renderBoard(width, height int) string {
	cols := m.boardColumns()

	colWidth := width / len(boardStatuses)
	if colWidth < boardColumnWidth {
		return lipgloss.NewStyle().
			Foreground(m.theme.Subtext).
			Width(width).
			Height(height).
			Padding(1, 2).
			Render(fmt.Sprintf(
				"The board needs about %d columns of terminal width; this one has %d.\n\nPress [ v ] to switch back to the list.",
				boardColumnWidth*len(boardStatuses), width))
	}

	focused, _ := m.boardCursorColumn()
	if focused < 0 {
		focused = m.boardColumn
	}

	rendered := make([]string, len(boardStatuses))
	for c, status := range boardStatuses {
		rendered[c] = m.renderBoardColumn(status, cols[c], colWidth, height, c == focused)
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, rendered...)
}

func (m PipelineModel) renderBoardColumn(status string, idxs []int, width, height int, focused bool) string {
	inner := width - 4
	if inner < 1 {
		inner = 1
	}

	header := lipgloss.NewStyle().
		Bold(true).
		Foreground(m.statusColorMap()[status]).
		Render(ansi.Truncate(fmt.Sprintf("%s (%d)", strings.ToUpper(statusLabel(status)), len(idxs)), inner, "…"))

	lines := []string{header, ""}

	// Two rows of chrome (the header and its blank line) plus the border
	// come out of the card budget before anything is drawn.
	capacity := (height - 4) / boardCardLines
	if capacity < 1 {
		capacity = 1
	}

	if len(idxs) == 0 {
		lines = append(lines, lipgloss.NewStyle().Foreground(m.theme.Subtext).Render("—"))
	}

	// Scroll the column so the cursor's own card stays visible; each column
	// scrolls independently, since they hold unrelated numbers of cards.
	start := 0
	for r, idx := range idxs {
		if idx == m.cursor && r >= capacity {
			start = r - capacity + 1
		}
	}

	for r := start; r < len(idxs) && r-start < capacity; r++ {
		lines = append(lines, m.renderBoardCard(m.filtered[idxs[r]], idxs[r], inner, idxs[r] == m.cursor)...)
	}

	if hidden := len(idxs) - start - capacity; hidden > 0 {
		lines = append(lines, lipgloss.NewStyle().
			Foreground(m.theme.Subtext).
			Render(fmt.Sprintf("+%d more", hidden)))
	}

	borderColor := m.theme.Overlay
	if focused {
		borderColor = m.theme.Blue
	}

	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(borderColor).
		Width(width-2).
		Height(height-2).
		Padding(0, 1).
		Render(strings.Join(lines, "\n"))
}

// renderBoardCard renders one application as exactly boardCardLines rows, so
// a column's capacity arithmetic stays honest.
func (m PipelineModel) renderBoardCard(app model.CareerApplication, index, width int, selected bool) []string {
	rt := rowTheme(m.theme, selected)

	company := lipgloss.NewStyle().Bold(true).Foreground(rt.Text).
		Render(ansi.Truncate(app.Company, width-2, "…"))
	role := lipgloss.NewStyle().Foreground(rt.Subtext).
		Render(ansi.Truncate(app.Role, width-2, "…"))

	// ScoreRaw, not Score: JobRowsToApplications leaves it empty for a role
	// that was never evaluated, which is the one place the two disagree --
	// and "—" is the honest rendering of that, not "0.00".
	score := app.ScoreRaw
	if score == "" {
		score = "—"
	}
	meta := lipgloss.NewStyle().Foreground(rt.Subtext).Render(score)

	marker := "  "
	if selected {
		marker = lipgloss.NewStyle().Foreground(m.theme.Mauve).Render("┃ ")
	}

	card := []string{marker + company, marker + role, marker + meta}
	for i := range card {
		card[i] = zone.Mark(fmt.Sprintf("pipeline_board_%d_%d", index, i), card[i])
	}
	return card
}
