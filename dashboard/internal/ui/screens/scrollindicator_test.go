package screens

import (
	"strings"
	"testing"

	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// Content that fits gets no rail and no readout: a full-height thumb is
// furniture, not information.
func TestScrollIndicatorHidesWhenContentFits(t *testing.T) {
	th := theme.NewTheme("modern")
	s := ScrollState{Total: 5, Visible: 10}
	if !s.Fits() {
		t.Fatal("5 lines in a 10-line window should fit")
	}
	if got := ScrollRail(th, s, 10); got != nil {
		t.Errorf("ScrollRail on fitting content = %v, want nil", got)
	}
	if got := ScrollReadout(th, s); got != "" {
		t.Errorf("ScrollReadout on fitting content = %q, want empty", got)
	}
	block := "a\nb\nc"
	if got := AttachScrollRail(th, block, s, 20); got != block {
		t.Errorf("AttachScrollRail changed a fitting block")
	}
}

func TestScrollPercentClampsAtBothEnds(t *testing.T) {
	cases := []struct {
		name  string
		state ScrollState
		want  int
	}{
		{"top", ScrollState{Total: 100, Visible: 10, Offset: 0}, 0},
		{"negative offset", ScrollState{Total: 100, Visible: 10, Offset: -5}, 0},
		{"middle", ScrollState{Total: 100, Visible: 10, Offset: 45}, 50},
		{"last full window", ScrollState{Total: 100, Visible: 10, Offset: 90}, 100},
		{"past the end", ScrollState{Total: 100, Visible: 10, Offset: 999}, 100},
		{"fits", ScrollState{Total: 4, Visible: 10, Offset: 0}, 0},
	}
	for _, tc := range cases {
		if got := tc.state.Percent(); got != tc.want {
			t.Errorf("%s: Percent() = %d, want %d", tc.name, got, tc.want)
		}
	}
}

// The thumb must reach the bottom at the last scroll position, or the rail
// claims there is more content below a pane that has none.
func TestScrollRailThumbTravelsTopToBottom(t *testing.T) {
	th := theme.NewTheme("modern")
	const height = 10

	top := ScrollRail(th, ScrollState{Total: 100, Visible: 10, Offset: 0}, height)
	if len(top) != height {
		t.Fatalf("rail has %d lines, want %d", len(top), height)
	}
	thumb := lipgloss.NewStyle().Foreground(th.Mauve).Render("█")
	if top[0] != thumb {
		t.Error("at offset 0 the thumb should start on the first line")
	}
	if top[height-1] == thumb {
		t.Error("at offset 0 the thumb should not reach the last line")
	}

	bottom := ScrollRail(th, ScrollState{Total: 100, Visible: 10, Offset: 90}, height)
	if bottom[height-1] != thumb {
		t.Error("at the last offset the thumb should park on the final line")
	}
	if bottom[0] == thumb {
		t.Error("at the last offset the thumb should have left the first line")
	}
}

func TestAttachScrollRailPadsRaggedLines(t *testing.T) {
	th := theme.NewTheme("modern")
	s := ScrollState{Total: 100, Visible: 3, Offset: 0}
	out := AttachScrollRail(th, "short\na much longer line\nx", s, 20)

	lines := strings.Split(out, "\n")
	if len(lines) != 3 {
		t.Fatalf("got %d lines, want 3", len(lines))
	}
	for i, line := range lines {
		if w := lipgloss.Width(line); w != 21 {
			t.Errorf("line %d width = %d, want 21 (innerWidth 20 + one rail cell)", i, w)
		}
	}
}

func TestScrollCountReadout(t *testing.T) {
	th := theme.NewTheme("modern")
	if got := ScrollCountReadout(th, 2, 28); !strings.Contains(got, "3 of 28") {
		t.Errorf("ScrollCountReadout(2, 28) = %q, want it to contain %q", got, "3 of 28")
	}
	if got := ScrollCountReadout(th, 0, 0); got != "" {
		t.Errorf("an empty list should have no readout, got %q", got)
	}
}
