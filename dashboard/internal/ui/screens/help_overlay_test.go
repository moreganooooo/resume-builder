package screens

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// A help overlay is drawn TWICE -- renderHelpOverlay borders it, then
// renderModalOverlay borders that -- so the width a caller builds it at must
// be the width the modal will actually render it into. While the two sized
// themselves independently (callers took 75% of the terminal, the modal
// capped itself at 100 columns), every terminal wider than ~133 columns
// handed the modal a block wider than its own content area and lipgloss
// WRAPPED the overflow out past the left border. renderHelpOverlay's own
// ansi.Truncate guard cannot catch it: it clips to the width it was given,
// which was already the wrong one -- so this is asserted at the seam between
// the two functions rather than inside either.
//
// The two sides are therefore derived INDEPENDENTLY on purpose: the overlay
// is built through helpOverlayWidth (what every caller now passes) and
// measured against modalBoxWidth (what renderModalOverlay actually reserves).
// An earlier version of this test took both numbers from helpOverlayWidth and
// was vacuous -- self-consistent at any width, including the broken one.
// Asserting on renderModalOverlay's own output cannot work either: it pads
// and clips every row to exactly the terminal width, so a wrapped line still
// measures correct there.
//
// Every help screen crosses the same seam, so all four are checked; the Jobs
// `[f]` binding was merely the first description long enough to reach the
// 100-column cap and make the bug visible.
func TestHelpOverlayFitsInsideTheModalAtEveryWidth(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")

	screens := []struct {
		title      string
		categories []helpCategory
	}{
		{"Jobs", jobsHelpCategories},
		{"Pipeline", pipelineHelpCategories},
		{"Progress", progressHelpCategories},
		{"Viewer", viewerHelpCategories},
	}

	// 133 is where the modal's 100-column cap starts binding; the widths on
	// either side of it are what the old arithmetic got wrong.
	for _, termWidth := range []int{80, 100, 120, 133, 160, 200, 300} {
		// What the modal will give the content: its box, less its border.
		avail := modalBoxWidth(termWidth) - 2

		for _, s := range screens {
			overlay := renderHelpOverlay(th, s.title, s.categories, helpOverlayWidth(termWidth), 60)
			for _, line := range strings.Split(overlay, "\n") {
				if got := ansi.StringWidth(line); got > avail {
					t.Errorf("%s at term %d: overlay line is %d wide, modal reserves %d: %q",
						s.title, termWidth, got, avail, ansi.Strip(line))
				}
			}
		}
	}
}
