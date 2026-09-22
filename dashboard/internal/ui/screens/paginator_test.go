package screens

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// A list that fits says nothing: an indicator reading "1/1" is furniture.
func TestPaginatorHidesWhenTheListFits(t *testing.T) {
	p := PageState{TotalItems: 6, ItemsPerPage: 10, FirstItem: 0}
	if !p.Fits() {
		t.Fatalf("6 items in a window of 10 should fit, got %d pages", p.TotalPages())
	}
	if got := RenderPaginator(theme.NewTheme("modern"), p, 40); got != "" {
		t.Errorf("a fitting list rendered an indicator: %q", got)
	}
}

// The page is DERIVED from the scroll offset, so the caption cannot drift
// from the rows drawn above it -- including at a partial last window, where
// an offset past the last full page still belongs to the last page.
func TestPaginatorPageDerivesFromOffsetAndClamps(t *testing.T) {
	cases := []struct {
		first, wantPage, wantTotal int
	}{
		{0, 0, 3},
		{9, 0, 3},
		{10, 1, 3},
		{22, 2, 3}, // past the last full window, still the last page
	}
	for _, c := range cases {
		p := PageState{TotalItems: 25, ItemsPerPage: 10, FirstItem: c.first}
		if got := p.TotalPages(); got != c.wantTotal {
			t.Errorf("FirstItem %d: TotalPages = %d, want %d", c.first, got, c.wantTotal)
		}
		if got := p.Page(); got != c.wantPage {
			t.Errorf("FirstItem %d: Page = %d, want %d", c.first, got, c.wantPage)
		}
	}
}

// Dots up to the limit, a number past it -- counting 24 dots is slower than
// reading "13/24", which is the only reason the dots are there.
func TestPaginatorSwitchesToArabicPastTheDotLimit(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")

	dots := ansi.Strip(RenderPaginator(th, PageState{TotalItems: 30, ItemsPerPage: 10, FirstItem: 10}, 40))
	if !strings.Contains(dots, "●") {
		t.Errorf("three pages should render dots, got %q", dots)
	}
	if !strings.Contains(dots, "11–20 of 30") {
		t.Errorf("missing the item range: %q", dots)
	}

	many := ansi.Strip(RenderPaginator(th, PageState{TotalItems: 500, ItemsPerPage: 10, FirstItem: 0}, 40))
	if strings.Contains(many, "●") {
		t.Errorf("50 pages should not render as dots: %q", many)
	}
	if !strings.Contains(many, "1/50") {
		t.Errorf("expected an n/m readout, got %q", many)
	}
}

// The last page's range stops at the real total, not at a full window.
func TestPaginatorRangeStopsAtTheTotal(t *testing.T) {
	got := ansi.Strip(RenderPaginator(theme.NewTheme("modern"),
		PageState{TotalItems: 25, ItemsPerPage: 10, FirstItem: 20}, 40))
	if !strings.Contains(got, "21–25 of 25") {
		t.Errorf("last page overshot its range: %q", got)
	}
}
