package screens

import (
	"strings"
	"testing"
	"time"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func TestFormatClockIsMinutesSecondsAndNeverNegative(t *testing.T) {
	cases := map[time.Duration]string{
		0:                               "0:00",
		9 * time.Second:                 "0:09",
		7*time.Minute + 5*time.Second:   "7:05",
		-3 * time.Second:                "0:00",
		61*time.Minute + 59*time.Second: "61:59",
	}
	for d, want := range cases {
		if got := formatClock(d); got != want {
			t.Errorf("formatClock(%v) = %q, want %q", d, got, want)
		}
	}
}

// The spec: under the expectation, the clock only; past it, the Yellow
// sentence naming the usual duration.
func TestElapsedTimerOverrunNamesTheUsualDuration(t *testing.T) {
	s := DefaultElapsedTimerStyles(theme.NewTheme("resume-builder"))
	e, _ := NewElapsedTimer().StartAt(time.Now().Add(-30*time.Second), time.Minute)
	if e.OverrunLine(s) != "" {
		t.Error("within the usual duration there should be no overrun line")
	}
	if line := e.Line(s, "⠋", "Working", "esc"); !strings.Contains(line, "0:30") || !strings.Contains(line, "(esc to cancel)") {
		t.Errorf("line missing clock or cancel hint: %q", line)
	}
	e, _ = NewElapsedTimer().StartAt(time.Now().Add(-2*time.Minute), time.Minute)
	if got := e.OverrunLine(s); !strings.Contains(got, "longer than the usual 1:00") {
		t.Errorf("overrun line = %q", got)
	}
	if line := e.Line(s, "⠋", "Working", ""); strings.Contains(line, "cancel") {
		t.Errorf("empty cancelKey should omit the hint: %q", line)
	}
}
