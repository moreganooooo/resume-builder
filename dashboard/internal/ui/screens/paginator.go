package screens

import (
	"fmt"
	"strings"

	"charm.land/bubbles/v2/paginator"
	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// -- Paginator --
//
// The design system's Paginator, over bubbles/paginator. The gap it closes is
// narrow and specific: the long lists here (286 evaluated roles, a bullet bank
// in the hundreds) already SCROLL and already have PgUp/PgDn bound, but they
// say nothing about where in the list the window sits, so a person cannot tell
// a set of 12 from a set of 600 without pressing a key and watching.
//
// It deliberately does NOT convert those lists to real pagination. Cursor
// movement that slides a window is the better interaction for a list you are
// triaging one row at a time -- paging would make `j` at the window's edge jump
// the eye a whole screen. What is adopted is the AFFORDANCE: dots when there
// are few enough pages to count at a glance, an "n/m" readout when there are
// not, and always the item range. The window's position is derived from the
// scroll offset, so there is one source of truth and the indicator cannot
// disagree with what is drawn above it.

// paginatorDotLimit is where dots stop being readable. Past it, counting dots
// is slower than reading a number, which is the whole reason the dots exist.
const paginatorDotLimit = 12

// PageState is a scrolling window expressed as pages. ItemsPerPage is how many
// list ITEMS fit in the window (not lines -- Jobs rows are two lines each, and
// a paginator that counted lines would report pages the user cannot land on).
type PageState struct {
	TotalItems   int
	ItemsPerPage int
	FirstItem    int // zero-based index of the first item currently shown
}

// TotalPages is the number of windows the list divides into, at least 1.
func (p PageState) TotalPages() int {
	if p.ItemsPerPage <= 0 || p.TotalItems <= 0 {
		return 1
	}
	pages := p.TotalItems / p.ItemsPerPage
	if p.TotalItems%p.ItemsPerPage != 0 {
		pages++
	}
	return pages
}

// Page is the zero-based index of the window currently shown, clamped into
// range -- a scroll offset parked past the last full window still belongs to
// the last page, not to one that does not exist.
func (p PageState) Page() int {
	if p.ItemsPerPage <= 0 {
		return 0
	}
	page := p.FirstItem / p.ItemsPerPage
	if last := p.TotalPages() - 1; page > last {
		page = last
	}
	if page < 0 {
		page = 0
	}
	return page
}

// Fits reports whether the whole list is on screen, in which case there is
// nothing to indicate and the component renders nothing at all -- the same
// rule as ScrollIndicator's hidden rail, for the same reason.
func (p PageState) Fits() bool {
	return p.TotalPages() <= 1
}

// RenderPaginator draws the indicator as a single centered line: dots (or an
// "n/m" readout past paginatorDotLimit) followed by the item range. Returns ""
// when the list fits, so a caller can append it unconditionally.
func RenderPaginator(t theme.Theme, p PageState, width int) string {
	if p.Fits() || width <= 0 {
		return ""
	}

	// bubbles/paginator owns the dot rendering itself; this passes it the
	// derived page rather than keeping a second cursor in the model, so the
	// indicator cannot drift from the rows actually drawn above it.
	model := paginator.New()
	model.TotalPages = p.TotalPages()
	model.Page = p.Page()
	model.ActiveDot = lipgloss.NewStyle().Foreground(t.Mauve).Render("●")
	model.InactiveDot = lipgloss.NewStyle().Foreground(t.Overlay).Render("○")

	var indicator string
	if model.TotalPages > paginatorDotLimit {
		model.Type = paginator.Arabic
		model.ArabicFormat = lipgloss.NewStyle().Foreground(t.Subtext).Render("%d/%d")
	} else {
		model.Type = paginator.Dots
	}
	indicator = model.View()

	first, last := p.FirstItem+1, p.FirstItem+p.ItemsPerPage
	if last > p.TotalItems {
		last = p.TotalItems
	}
	rangeText := lipgloss.NewStyle().Foreground(t.Subtext).
		Render(fmt.Sprintf("%d–%d of %d", first, last, p.TotalItems))

	line := indicator + "  " + rangeText
	if w := lipgloss.Width(line); w < width {
		// Centered, because it reads as a caption for the list above it
		// rather than as another row of it.
		pad := (width - w) / 2
		line = strings.Repeat(" ", pad) + line
	}
	return line
}
