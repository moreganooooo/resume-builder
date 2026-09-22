package screens

import (
	"fmt"
	"image/color"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// -- Toast --
//
// The design system's Toast: tea.Printf's above-the-program output, rendered
// as a bottom-right stack. The rule that decides toast vs. panel is what makes
// it safe to expire -- a toast reports something that ALREADY happened and
// needs no answer, because a toast that vanishes takes the user's only chance
// to act with it. Anything the user must decide stays a panel (the `notice`
// bar and the action-error bar both remain exactly that).
//
// Three rules from the spec are load-bearing:
//   - success and info auto-dismiss; warning and error WAIT for a keypress,
//     since an unread failure is worse than a crowded corner.
//   - at most three render. Older ones collapse into "+2 earlier" rather than
//     scrolling, so the newest is always in the same place.
//   - one line each. A toast that needs two lines is a panel.

// ToastTone selects the glyph, the border color, and whether the toast
// expires on its own.
type ToastTone int

// The four tones, in the design system's order.
const (
	ToastSuccess ToastTone = iota
	ToastError
	ToastWarning
	ToastInfo
)

// Seconds each self-dismissing tone survives. Errors and warnings have no
// entry here on purpose: they are dismissed by a keypress, not by time.
const (
	toastSuccessSeconds = 4
	toastInfoSeconds    = 6
	toastMaxVisible     = 3
)

// Sticky reports whether this tone waits for a keypress instead of expiring.
func (t ToastTone) Sticky() bool {
	return t == ToastError || t == ToastWarning
}

func (t ToastTone) glyph() string {
	switch t {
	case ToastSuccess:
		return "✓"
	case ToastError:
		return "✗"
	case ToastWarning:
		return "⚠"
	default:
		return "✦"
	}
}

func (t ToastTone) color(th theme.Theme) color.Color {
	switch t {
	case ToastSuccess:
		return th.Green
	case ToastError:
		return th.Red
	case ToastWarning:
		return th.Yellow
	default:
		return th.Mauve
	}
}

// toastItem is one line of the stack plus its remaining life.
type toastItem struct {
	text    string
	tone    ToastTone
	seconds int
}

// ToastStack is the bottom-right stack itself. The zero value is usable.
type ToastStack struct {
	items    []toastItem // newest first
	overflow int
}

// Push adds a toast as the newest entry. When that makes a fourth, the oldest
// leaves the stack and is counted into the "+N earlier" line rather than
// pushing the newest one to a different row.
func (s *ToastStack) Push(tone ToastTone, format string, args ...any) {
	seconds := 0
	switch tone {
	case ToastSuccess:
		seconds = toastSuccessSeconds
	case ToastInfo:
		seconds = toastInfoSeconds
	}
	item := toastItem{text: fmt.Sprintf(format, args...), tone: tone, seconds: seconds}
	s.items = append([]toastItem{item}, s.items...)
	for len(s.items) > toastMaxVisible {
		s.items = s.items[:len(s.items)-1]
		s.overflow++
	}
}

// Empty reports whether there is anything to draw.
func (s *ToastStack) Empty() bool {
	return len(s.items) == 0
}

// HasSticky reports whether a warning or error is waiting to be acknowledged.
// A screen uses this to decide whether a keypress should be spent dismissing
// rather than acted on.
func (s *ToastStack) HasSticky() bool {
	for _, it := range s.items {
		if it.tone.Sticky() {
			return true
		}
	}
	return false
}

// TickSecond ages the self-dismissing toasts by one second. Sticky ones are
// untouched. The overflow counter resets once the stack drains, so a later
// burst does not inherit an old "+N earlier".
func (s *ToastStack) TickSecond() {
	kept := s.items[:0]
	for _, it := range s.items {
		if !it.tone.Sticky() {
			it.seconds--
			if it.seconds <= 0 {
				continue
			}
		}
		kept = append(kept, it)
	}
	s.items = kept
	if len(s.items) == 0 {
		s.overflow = 0
	}
}

// DismissSticky clears the warnings and errors a keypress acknowledges, and
// reports whether it removed anything -- the caller consumes the keypress only
// when it did.
func (s *ToastStack) DismissSticky() bool {
	if !s.HasSticky() {
		return false
	}
	kept := s.items[:0]
	for _, it := range s.items {
		if !it.tone.Sticky() {
			kept = append(kept, it)
		}
	}
	s.items = kept
	if len(s.items) == 0 {
		s.overflow = 0
	}
	return true
}

// Clear empties the stack, for a screen leaving the foreground.
func (s *ToastStack) Clear() {
	s.items = nil
	s.overflow = 0
}

// toastMaxWidth keeps a long path from spanning the terminal: the stack sits
// over content, so it has to stay a corner rather than become a banner.
const toastMaxWidth = 56

// Render draws the stack as one line per toast, the "+N earlier" line first
// so the newest toast is closest to the bottom. Returns "" when empty, so a
// caller can splice it unconditionally.
func (s *ToastStack) Render(th theme.Theme, width int) string {
	if len(s.items) == 0 {
		return ""
	}
	box := toastMaxWidth
	if width-4 < box {
		box = width - 4
	}
	if box < 12 {
		return ""
	}

	var lines []string
	if s.overflow > 0 {
		lines = append(lines, lipgloss.NewStyle().Foreground(th.Subtext).
			Render(fmt.Sprintf("+%d earlier", s.overflow)))
	}
	// Oldest first top-to-bottom: the newest toast lands on the bottom row,
	// nearest the footer, which is where the eye already is after a keypress.
	for i := len(s.items) - 1; i >= 0; i-- {
		it := s.items[i]
		c := it.tone.color(th)
		glyph := lipgloss.NewStyle().Foreground(c).Background(th.Surface).Bold(true).
			Render(it.tone.glyph())
		hint := ""
		if it.tone.Sticky() {
			hint = lipgloss.NewStyle().Foreground(th.Subtext).Background(th.Surface).
				Render(" (any key)")
		}
		// One ROW, not a bordered box: the spec's "one line each" is the
		// load-bearing rule, and a rounded border costs three terminal rows
		// per toast -- three toasts would then be nine rows of covered
		// content. The Surface fill does the separating a border does on the
		// web mock.
		textBudget := box - lipgloss.Width(ansi.Strip(hint)) - 4 // glyph, gap, padding
		text := lipgloss.NewStyle().Foreground(th.Text).Background(th.Surface).
			Render(Truncate(it.text, textBudget))
		lines = append(lines, lipgloss.NewStyle().
			Background(th.Surface).
			Padding(0, 1).
			Render(glyph+" "+text+hint))
	}

	// Deliberately NOT padded to `width` here: OverlayBottomRight needs each
	// line's own width to right-align it against whatever it covers.
	return strings.Join(lines, "\n")
}

// OverlayBottomRight splices an already-rendered block onto the bottom-right
// of a view WITHOUT changing its line count -- a toast that reflowed the
// layout under it would be a worse interruption than the thing it reports.
// bottomOffset is how many lines above the last one to sit (1 to clear a
// footer). Lines the block covers keep their left-hand content; the block
// occupies the right edge.
func OverlayBottomRight(view, block string, width, bottomOffset int) string {
	if block == "" {
		return view
	}
	viewLines := strings.Split(view, "\n")
	blockLines := strings.Split(block, "\n")

	// Anchor the block's LAST line bottomOffset rows up, then walk upward.
	end := len(viewLines) - 1 - bottomOffset
	start := end - len(blockLines) + 1
	if start < 0 || end < 0 {
		return view
	}

	for i, bl := range blockLines {
		row := start + i
		blockW := lipgloss.Width(bl)
		if blockW > width {
			continue
		}
		// Each block line is its own natural width, so the left offset is
		// computed per row: the background is kept up to where the toast
		// starts, then the toast line replaces the rest.
		keep := width - blockW - 1 // one column of right margin
		if keep < 0 {
			continue
		}
		left := ansi.Truncate(viewLines[row], keep, "")
		if w := lipgloss.Width(left); w < keep {
			left += strings.Repeat(" ", keep-w)
		}
		viewLines[row] = left + bl
	}
	return strings.Join(viewLines, "\n")
}

// ToastTickMsg is the one-second heartbeat that ages the stack. It is not a
// continuous animation loop: a screen starts it when it pushes a toast and
// stops rescheduling once the stack drains, so an idle screen ticks nothing
// (the same battery rule as the mobile guidelines' idle-animation ban).
type ToastTickMsg time.Time

// ToastTick schedules the next heartbeat.
func ToastTick() tea.Cmd {
	return tea.Tick(time.Second, func(t time.Time) tea.Msg { return ToastTickMsg(t) })
}

// Age advances the stack one second and returns the command that keeps the
// heartbeat going, or nil once nothing is left to expire. Sticky toasts alone
// do not keep it alive -- they wait for a keypress, not for time.
func (s *ToastStack) Age() tea.Cmd {
	s.TickSecond()
	for _, it := range s.items {
		if !it.tone.Sticky() {
			return ToastTick()
		}
	}
	return nil
}
