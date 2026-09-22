package screens

import (
	"fmt"
	"image/color"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// -- HuhField: the select field --
//
// Huh owns the keyboard and the validation; the spec is the VISUAL contract
// the product holds it to, and it is written for four states and four
// kinds. Only the select kind is built here, because only the select kind
// has a surface: the status picker, shared by Pipeline and Jobs.
//
// The spec's select is a left rail in the state's color, one option per
// row, the row under the cursor carrying a Mauve ┃ and drawn in Text while
// the rest sit in Subtext. That last part is the substance of the change:
// the picker used to draw EVERY option in Blue and mark the current one
// with a "> " and a filled Overlay background, so the eye had to find the
// selection by spotting a background rather than by reading the one row
// that is brighter than its neighbours. The ┃ is also the same cursor
// ClusterTree uses, so "this is the row you are on" looks the same
// wherever it appears.
//
// The other three kinds are deliberately absent rather than written
// speculatively. input/text render a bordered box, and the two places that
// would want one -- Pipeline's and Jobs' search -- are single-row status
// lines whose height is budgeted by a `rows++`; a bordered box costs two
// more rows and would silently eat list rows on both screens. multiselect
// belongs to the FilePicker's multi-file mode, which this huh version does
// not have.

// FieldState is the spec's four-state field model. Error and Complete are
// declared because the contract has four states and a partial enum invites
// a caller to invent a fifth; the status picker only ever uses Focused.
type FieldState int

// The four states, in the spec's own order.
const (
	FieldBlurred FieldState = iota
	FieldFocused
	FieldError
	FieldComplete
)

// fieldAccent is the border/rail and label color for a state.
func fieldAccent(t theme.Theme, state FieldState) (rail, label color.Color) {
	switch state {
	case FieldFocused:
		return t.Mauve, t.Mauve
	case FieldError:
		return t.Red, t.Red
	case FieldComplete, FieldBlurred:
		return t.Overlay, t.Subtext
	}
	return t.Overlay, t.Subtext
}

// RenderSelectField draws a labelled option list, one string per row: the
// label first, then one row per option. Returning LINES rather than a block
// is what lets the two callers splice it into a height they have already
// budgeted, the same reason RenderClusterTree does it.
func RenderSelectField(t theme.Theme, label string, options []string, cursor int, state FieldState, width int) []string {
	if width <= 0 {
		return nil
	}
	rail, labelColor := fieldAccent(t, state)

	var lines []string
	if label != "" {
		style := lipgloss.NewStyle().Foreground(labelColor).
			Bold(state == FieldFocused || state == FieldError).Width(width)
		lines = append(lines, style.Render(ansi.Truncate(label, width, "…")))
	}

	// The rail occupies a fixed two columns on every row -- rail glyph plus
	// a space -- so that the cursor moving cannot shift the labels.
	const railWidth = 2
	textWidth := max(width-railWidth, 4)
	railStyle := lipgloss.NewStyle().Foreground(rail)
	cursorStyle := lipgloss.NewStyle().Foreground(t.Mauve)

	for i, opt := range options {
		glyph := railStyle.Render("│")
		optStyle := lipgloss.NewStyle().Foreground(t.Subtext).Width(textWidth)
		if i == cursor {
			glyph = cursorStyle.Render("┃")
			optStyle = lipgloss.NewStyle().Foreground(t.Text).Bold(true).Width(textWidth)
		}
		lines = append(lines, glyph+" "+optStyle.Render(ansi.Truncate(opt, textWidth, "…")))
	}
	return lines
}

// -- HuhField: the search status line --
//
// Pipeline and Jobs each had their own renderSearchBar, identical apart
// from where the denominator came from -- the duplication bars.go's own
// header warns about, and it had already started to matter: both were
// going to need the same two corrections.
//
// This is NOT the spec's bordered `input` box, deliberately. Both screens
// budget the search bar as a single row (`rows++`), and a bordered field
// costs two more; adopting the box would quietly take two list rows from
// each screen. What it does adopt is the parts that carry meaning: the
// focused accent is MAUVE, the same focus color TuiPanel, the status
// picker's rail and ClusterTree's cursor all use -- it was Blue here, so
// the one surface where the user is actually typing was the one surface
// whose focus color disagreed with everything else -- and an empty query
// renders a PLACEHOLDER in Overlay instead of a bare cursor floating after
// a badge, which reads as a hung screen rather than an invitation.

// SearchBarState is what a screen has to tell the shared renderer.
type SearchBarState struct {
	Query   string
	Typing  bool // the user is editing the query right now
	Matched int
	Total   int
	Width   int
}

// RenderSearchBar draws the one-line search status bar, or "" when there is
// neither an active query nor an in-progress one.
func RenderSearchBar(t theme.Theme, s SearchBarState) string {
	if !s.Typing && s.Query == "" {
		return ""
	}
	style := lipgloss.NewStyle().Foreground(t.Text).Width(s.Width).Padding(0, 2)
	hintStyle := lipgloss.NewStyle().Foreground(t.Subtext)

	prompt := lipgloss.NewStyle().Bold(true).Foreground(t.Mauve).Render("/")
	if s.Typing {
		prompt = lipgloss.NewStyle().Bold(true).Foreground(t.Surface).
			Background(t.Mauve).Padding(0, 1).Render(" SEARCH ")
	}

	display := lipgloss.NewStyle().Foreground(t.Text).Render(s.Query)
	if s.Query == "" && s.Typing {
		display = lipgloss.NewStyle().Foreground(t.Overlay).Render("company or title")
	}
	if s.Typing {
		display += lipgloss.NewStyle().Foreground(t.Mauve).Render("█")
	}

	hint := "   Esc: clear   /: edit"
	if s.Typing {
		hint = "   Enter: keep   Esc: cancel   Ctrl+U: clear"
	}
	matchInfo := hintStyle.Render(fmt.Sprintf("  %d/%d matching", s.Matched, s.Total))
	return style.Render(prompt + " " + display + matchInfo + hintStyle.Render(hint))
}
