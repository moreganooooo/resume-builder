package screens

import (
	"strings"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

func helpBarTestBindings() []HelpBinding {
	return []HelpBinding{
		{Key: "↑↓/jk", Desc: "nav", Action: "down"},
		{Key: "/", Desc: "search"},
		{Key: "f", Desc: "filter"},
		{Key: "t", Desc: "tailor"},
		{Key: "Esc", Desc: "back", Action: "esc"},
		{Key: "z", Desc: "never shown"},
		{Key: "x", Desc: "never shown"},
	}
}

// The cap is the whole point of the component: a bar that prints every
// binding is the defect it replaces.
func TestRenderHelpBarCapsAtFiveAndEndsWithMore(t *testing.T) {
	out := zone.Scan(RenderHelpBar(theme.NewTheme("modern"), 120, "test", helpBarTestBindings(), "brand"))

	for _, want := range []string{"nav", "search", "filter", "tailor", "back", "more"} {
		if !strings.Contains(out, want) {
			t.Errorf("bar missing %q:\n%s", want, out)
		}
	}
	if strings.Contains(out, "never shown") {
		t.Errorf("bar rendered a binding past the cap of %d:\n%s", helpBarMaxBindings, out)
	}
	if !strings.Contains(out, "brand") {
		t.Errorf("bar dropped the brand text:\n%s", out)
	}
}

// A click has to reach the same handler the key does, or the design system's
// "a click never produces a state the keyboard cannot reach" is not true.
func TestHelpBarClickedResolvesActionThenKey(t *testing.T) {
	bindings := helpBarTestBindings()
	zone.Scan(RenderHelpBar(theme.NewTheme("modern"), 120, "clicktest", bindings, "brand"))

	cases := []struct {
		id   string
		want string
	}{
		{"clicktest_help_0", "down"}, // Action wins over the legend Key
		{"clicktest_help_1", "/"},    // no Action: Key is typeable as-is
		{"clicktest_help_4", "esc"},
		{"clicktest_help_5", helpBarMoreKey}, // the trailing "? more"
	}
	for _, tc := range cases {
		z := zone.WaitFor(tc.id, 2*time.Second)
		if z == nil {
			t.Fatalf("zone %s never published bounds", tc.id)
		}
		msg := tea.MouseClickMsg{X: z.StartX, Y: z.StartY, Button: tea.MouseLeft}
		got, ok := HelpBarClicked("clicktest", bindings, msg)
		if !ok || got != tc.want {
			t.Errorf("click on %s = (%q, %v), want (%q, true)", tc.id, got, ok, tc.want)
		}
	}

	// Far outside every hint.
	if _, ok := HelpBarClicked("clicktest", bindings, tea.MouseClickMsg{X: 500, Y: 500, Button: tea.MouseLeft}); ok {
		t.Error("a click outside every hint resolved to a binding")
	}
}

func TestHelpBarKeyMsgRoundTrips(t *testing.T) {
	for _, k := range []string{"esc", "enter", "up", "down", "pgup", "pgdown", "tab", "/", "q", "?"} {
		if got := helpBarKeyMsg(k).String(); got != k {
			t.Errorf("helpBarKeyMsg(%q).String() = %q", k, got)
		}
	}
}

// Every adopting screen's bindings must be typeable: a label with no Action
// would send its own text ("↑↓/jk") to a key handler that cannot match it.
func TestScreenHelpBarBindingsAreDispatchable(t *testing.T) {
	sets := map[string][]HelpBinding{
		"jobs":     jobsHelpBindings,
		"pipeline": pipelineHelpBindings,
		"progress": progressHelpBindings,
		"viewer":   viewerHelpBindings,
	}
	for name, set := range sets {
		if len(set) > helpBarMaxBindings {
			t.Errorf("%s declares %d bindings, over the cap of %d", name, len(set), helpBarMaxBindings)
		}
		for _, b := range set {
			send := b.Action
			if send == "" {
				send = b.Key
			}
			if helpBarKeyMsg(send).String() != send {
				t.Errorf("%s binding %q sends %q, which is not a key a handler can match", name, b.Key, send)
			}
		}
	}
}
