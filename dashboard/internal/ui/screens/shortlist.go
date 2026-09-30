package screens

import (
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/anim"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// Shortlist ("favorite") display primitives, shared by the Pipeline and
// Browse & Manage Jobs screens so the two cannot drift on what a
// shortlisted role looks like.
//
// The mark itself is persisted by Python (jd_manager.save_favorite, under
// the JD's own _favorite key); nothing here writes state. These helpers
// only decide how it is drawn and how the save is celebrated.

// Star glyphs. The hollow star is drawn only on the cursor's own row, so
// the affordance is discoverable without pebbling every unshortlisted row
// with an empty marker.
const (
	starFilled = "★"
	starHollow = "☆"
)

// bloomFrames is the save animation: a star growing into place. Four
// frames at bloomFrameInterval is ~240ms -- long enough to register as a
// deliberate flourish, short enough that holding [*] down never feels
// blocked on it.
var bloomFrames = []string{"·", "✦", "✧", starFilled}

const bloomFrameInterval = 60 * time.Millisecond

// ShortlistBloomMsg advances the star bloom by one frame.
type ShortlistBloomMsg struct{}

// shortlistBloom is the in-flight save animation for a single row.
//
// It is keyed by row identity rather than by index because the list
// re-sorts underneath it: shortlisting a role can move it (a SHORTLIST tab
// is one keypress away, and the actionable-bar exemption can surface a row
// that was hidden a moment ago), and an index-keyed animation would then
// bloom on whichever unrelated role slid into that slot.
type shortlistBloom struct {
	key    string
	frame  int
	active bool
}

// ShortlistKey identifies a row for bloom purposes. Company+role rather
// than path, since a database-only job's "path" is a job id and a file's
// path changes the moment it is archived or completed.
func ShortlistKey(company, role string) string {
	return strings.ToLower(strings.TrimSpace(company)) + "\x00" + strings.ToLower(strings.TrimSpace(role))
}

// Start begins a bloom for the given row, or snaps straight to the final
// frame under reduced motion. Returns the tick command to run, which is
// nil when there is nothing left to animate -- callers can safely batch it.
func (b *shortlistBloom) Start(key string) tea.Cmd {
	b.key = key
	if anim.ReducedMotion() {
		b.frame = len(bloomFrames) - 1
		b.active = false
		return nil
	}
	b.frame = 0
	b.active = true
	return bloomTick()
}

// Advance moves to the next frame, returning the next tick command or nil
// once the bloom has settled on the filled star.
func (b *shortlistBloom) Advance() tea.Cmd {
	if !b.active {
		return nil
	}
	b.frame++
	if b.frame >= len(bloomFrames)-1 {
		b.frame = len(bloomFrames) - 1
		b.active = false
		return nil
	}
	return bloomTick()
}

// Clear ends any in-flight bloom. Called when the row is un-shortlisted,
// so a half-finished bloom cannot leave a star on a row that no longer
// has one.
func (b *shortlistBloom) Clear() {
	b.active = false
	b.key = ""
}

// frameFor returns the glyph this bloom contributes for a row, and whether
// it applies to that row at all.
func (b shortlistBloom) frameFor(key string) (string, bool) {
	if !b.active || b.key != key {
		return "", false
	}
	return bloomFrames[b.frame], true
}

func bloomTick() tea.Cmd {
	return tea.Tick(bloomFrameInterval, func(time.Time) tea.Msg {
		return ShortlistBloomMsg{}
	})
}

// ShortlistMarker renders the one-cell marker that precedes a row.
//
// Always one cell wide, for every combination of state: a marker that
// appeared and disappeared would shift every column on the row as the
// cursor moved down the list.
func ShortlistMarker(th theme.Theme, favorited, isCursorRow bool, bloomGlyph string) string {
	switch {
	case bloomGlyph != "":
		return lipgloss.NewStyle().Foreground(th.Peach).Bold(true).Render(bloomGlyph)
	case favorited:
		return lipgloss.NewStyle().Foreground(th.Peach).Render(starFilled)
	case isCursorRow:
		return lipgloss.NewStyle().Foreground(th.Subtext).Render(starHollow)
	default:
		return " "
	}
}

// shortlistGutterWidth is the marker's column plus the space after it.
// Every line of a row is indented by exactly this much, marker or not.
const shortlistGutterWidth = 2

// shortlistRowWidth is the row budget left after the gutter. Clamped at
// zero: sidebarInnerWidth is already small on a narrow terminal, and a
// negative width panics lipgloss.
func shortlistRowWidth(inner int) int {
	if w := inner - shortlistGutterWidth; w > 0 {
		return w
	}
	return 0
}

// withShortlistGutter puts the marker in a gutter column to the LEFT of an
// already-rendered row, indenting EVERY line of it by the same amount.
//
// The uniform indent is the whole point. A sidebar row is two lines (score
// + company, then the title -- see renderSidebarRowTagged), and the
// selected row's pink hover bar is drawn by that renderer on both of them.
// Prefixing the rendered string alone shifts only the first line, so the
// bar steps two columns sideways halfway down the row and reads as a
// rendering glitch. Anything else that renders into this gutter has to
// pad continuation lines the same way.
func withShortlistGutter(marker, row string) string {
	pad := strings.Repeat(" ", shortlistGutterWidth)
	lines := strings.Split(row, "\n")
	for i, line := range lines {
		if i == 0 {
			lines[i] = marker + " " + line
			continue
		}
		lines[i] = pad + line
	}
	return strings.Join(lines, "\n")
}
