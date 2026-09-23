package screens

import (
	"fmt"
	"time"

	"charm.land/bubbles/v2/stopwatch"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// -- ElapsedTimer --
//
// The design system's ElapsedTimer, over bubbles/stopwatch. The product's
// LLM calls take anywhere from four seconds to fifteen minutes, and the
// honest thing is to say so rather than imply a percentage nobody can
// compute. Three rules from the spec:
//   - under the expectation, show the spinner, label and elapsed clock only;
//   - past it, turn the clock Yellow and add the overrun sentence on its own
//     line, naming the usual duration -- that is what lets the user decide;
//   - the clock is m:ss and never ticks backwards.
//
// Countdown mode (bubbles/timer) is deliberately not built: the spec allows
// it only for things that fire on their own, and nothing here does yet.

// ElapsedTimer is a running stopwatch plus the duration the work usually
// takes. The zero value is stopped and renders nothing.
type ElapsedTimer struct {
	sw       stopwatch.Model
	expected time.Duration
	started  time.Time
	running  bool
}

// NewElapsedTimer returns a stopped timer with a one-second resolution --
// the clock shows whole seconds, so ticking faster only burns CPU.
func NewElapsedTimer() ElapsedTimer {
	return ElapsedTimer{sw: stopwatch.New(stopwatch.WithInterval(time.Second))}
}

// Start resets the clock to zero and starts it, recording how long this
// kind of work usually takes.
func (e ElapsedTimer) Start(expected time.Duration) (ElapsedTimer, tea.Cmd) {
	return e.StartAt(time.Now(), expected)
}

// StartAt is Start with an explicit start time, for a caller that already
// recorded when its work began.
func (e ElapsedTimer) StartAt(started time.Time, expected time.Duration) (ElapsedTimer, tea.Cmd) {
	e.expected = expected
	e.started = started
	e.running = true
	return e, tea.Sequence(e.sw.Reset(), e.sw.Start())
}

// Stop halts the clock. A stopped timer ignores its remaining ticks.
func (e ElapsedTimer) Stop() (ElapsedTimer, tea.Cmd) {
	e.running = false
	return e, e.sw.Stop()
}

// Update routes the stopwatch's own messages; anything else is ignored.
func (e ElapsedTimer) Update(msg tea.Msg) (ElapsedTimer, tea.Cmd) {
	var cmd tea.Cmd
	e.sw, cmd = e.sw.Update(msg)
	return e, cmd
}

// Running reports whether the clock is live.
func (e ElapsedTimer) Running() bool { return e.running }

// Elapsed is the time on the clock. It is read from the start time, not
// summed from the stopwatch's ticks: the stopwatch is what redraws the clock
// each second, but a tick dropped while the program was busy would otherwise
// make the clock run slow.
func (e ElapsedTimer) Elapsed() time.Duration {
	if !e.running {
		return 0
	}
	return time.Since(e.started)
}

// Over reports whether the work has run past its usual duration.
func (e ElapsedTimer) Over() bool {
	return e.running && e.expected > 0 && e.Elapsed() > e.expected
}

// formatClock renders m:ss. Negative input clamps to zero: the spec's clock
// never runs backwards, and a clock reading -0:01 would say it did.
func formatClock(d time.Duration) string {
	if d < 0 {
		d = 0
	}
	s := int(d / time.Second)
	return fmt.Sprintf("%d:%02d", s/60, s%60)
}

// ElapsedTimerStyles are the colors of each segment. They are passed in
// rather than chosen here because the spec's colors sit on whatever bar the
// caller draws -- the Jobs action bar needs a Surface background on every
// segment or the fill breaks between them.
type ElapsedTimerStyles struct {
	Spinner, Label, Clock, Over, Hint lipgloss.Style
}

// DefaultElapsedTimerStyles is the spec's palette: Blue spinner, Text label,
// Subtext clock and cancel hint, Yellow once over.
func DefaultElapsedTimerStyles(t theme.Theme) ElapsedTimerStyles {
	return ElapsedTimerStyles{
		Spinner: lipgloss.NewStyle().Foreground(t.Blue),
		Label:   lipgloss.NewStyle().Foreground(t.Text),
		Clock:   lipgloss.NewStyle().Foreground(t.Subtext),
		Over:    lipgloss.NewStyle().Foreground(t.Yellow),
		Hint:    lipgloss.NewStyle().Foreground(t.Subtext),
	}
}

// Line renders the first line: spinner, label, clock and cancel key. Pass
// cancelKey "" when the work genuinely cannot be cancelled.
func (e ElapsedTimer) Line(s ElapsedTimerStyles, spinnerFrame, label, cancelKey string) string {
	clock := s.Clock
	if e.Over() {
		clock = s.Over
	}
	sep := s.Label.Render(" ")
	out := s.Spinner.Render(spinnerFrame) + sep + s.Label.Render(label) + sep + clock.Render(formatClock(e.Elapsed()))
	if cancelKey != "" {
		out += sep + s.Hint.Render("("+cancelKey+" to cancel)")
	}
	return out
}

// OverrunLine renders the second line, or "" while the work is within its
// usual duration -- the sentence only earns its row once it is true.
func (e ElapsedTimer) OverrunLine(s ElapsedTimerStyles) string {
	if !e.Over() {
		return ""
	}
	return s.Over.Render(fmt.Sprintf("  -- still going after %s, which is longer than the usual %s",
		formatClock(e.Elapsed()), formatClock(e.expected)))
}
