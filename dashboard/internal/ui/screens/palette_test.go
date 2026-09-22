package screens

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func testPaletteCommands() []PaletteCommand {
	return paletteCommandsFor("Jobs", []helpCategory{
		{label: "Move", bindings: []helpBinding{
			{key: "↑ ↓ / j k", desc: "Move between roles"},
			{key: "enter", desc: "Open the role"},
		}},
		{label: "Act", bindings: []helpBinding{
			{key: "t", desc: "Tailor this resume"},
			{key: "a", desc: "Archive the role"},
		}},
	}, []string{"Pipeline", "Jobs", "Knowledge Base"})
}

// Movement bindings are skipped: "↑ ↓ / j k" names four keys, so there is
// nothing for the palette to dispatch -- and the current screen is not
// offered as a place to navigate to.
func TestPaletteCommandsSkipMovementAndSelf(t *testing.T) {
	cmds := testPaletteCommands()
	for _, c := range cmds {
		if strings.ContainsAny(c.Key, " /") {
			t.Errorf("multi-key binding leaked into the palette: %+v", c)
		}
		if c.Nav == "Jobs" {
			t.Errorf("the current screen was offered as a navigation target")
		}
	}
	if len(cmds) != 5 { // Pipeline, Knowledge Base, enter, t, a
		t.Errorf("expected 5 commands, got %d: %+v", len(cmds), cmds)
	}
}

// The real screens must actually yield actions, not just navigation --
// this is what catches a help-category rename silently emptying the
// palette's action half.
func TestPaletteCommandsForRealScreens(t *testing.T) {
	for _, screen := range []string{"Pipeline", "Jobs", "Progress"} {
		cmds := PaletteCommandsForScreen(screen)
		actions := 0
		for _, c := range cmds {
			if c.Key != "" {
				actions++
			}
		}
		if actions == 0 {
			t.Errorf("%s contributed no dispatchable actions to the palette", screen)
		}
		if len(cmds)-actions != len(PaletteNavTargets)-1 {
			t.Errorf("%s: %d navigation rows, want %d",
				screen, len(cmds)-actions, len(PaletteNavTargets)-1)
		}
	}
}

// An empty query lists everything, so the palette is browsable without
// knowing what to type.
func TestPaletteEmptyQueryListsEverything(t *testing.T) {
	m := NewPalette(testPaletteCommands())
	if m.ResultCount() != 5 {
		t.Errorf("empty query matched %d of 5", m.ResultCount())
	}
}

// Typing filters, backspace restores, and esc closes AND forgets -- a
// reopened palette should not be answering the last question.
func TestPaletteTypingFiltersAndEscForgets(t *testing.T) {
	m := NewPalette(testPaletteCommands())
	for _, key := range []string{"t", "a", "i"} {
		if consumed, _ := m.HandleKey(key); !consumed {
			t.Fatalf("palette did not consume %q", key)
		}
	}
	if m.Query() != "tai" {
		t.Fatalf("query = %q, want %q", m.Query(), "tai")
	}
	sel, ok := m.Selected()
	if !ok || !strings.Contains(sel.Label, "Tailor") {
		t.Errorf("'tai' should select the tailor command, got %+v", sel)
	}

	m.HandleKey("backspace")
	if m.Query() != "ta" {
		t.Errorf("backspace left %q", m.Query())
	}

	m.HandleKey("esc")
	if m.Open || m.Query() != "" {
		t.Errorf("esc left the palette open=%v query=%q", m.Open, m.Query())
	}
}

// Enter reports a choice only when something is actually selected -- an
// empty result list must not dispatch a zero command.
func TestPaletteEnterNeedsAMatch(t *testing.T) {
	m := NewPalette(testPaletteCommands())
	for _, key := range []string{"z", "z", "z"} {
		m.HandleKey(key)
	}
	if m.ResultCount() != 0 {
		t.Fatalf("'zzz' matched %d commands", m.ResultCount())
	}
	if _, chosen := m.HandleKey("enter"); chosen {
		t.Error("enter chose a command with no matches")
	}
}

// The cursor cannot walk off either end of the result list.
func TestPaletteCursorClamps(t *testing.T) {
	m := NewPalette(testPaletteCommands())
	for i := 0; i < 20; i++ {
		m.HandleKey("down")
	}
	sel, ok := m.Selected()
	if !ok {
		t.Fatal("cursor ran off the end of the list")
	}
	last := m.results[len(m.results)-1].cmd
	if sel != last {
		t.Errorf("cursor stopped at %+v, want the last row %+v", sel, last)
	}
	for i := 0; i < 20; i++ {
		m.HandleKey("up")
	}
	if sel, _ := m.Selected(); sel != m.results[0].cmd {
		t.Errorf("cursor did not return to the first row, got %+v", sel)
	}
}

// The rendered box carries the prompt, the binding each row stands for
// (that is the teaching part), and the footer.
func TestPaletteRenderShowsKeysAndFooter(t *testing.T) {
	m := NewPalette(testPaletteCommands())
	out := ansi.Strip(m.Render(theme.NewTheme("catppuccin-mocha"), 100, 10))
	for _, want := range []string{"❯", "Search screens and actions", "Tailor this resume", "↑↓ move · enter run · esc close"} {
		if !strings.Contains(out, want) {
			t.Errorf("palette render missing %q:\n%s", want, out)
		}
	}
	// The binding is shown beside its description, not just the description.
	if !strings.Contains(out, "Archive the role") || !strings.Contains(out, " a") {
		t.Errorf("palette did not show the key for its row:\n%s", out)
	}
}

// An unmatched query says so rather than rendering an empty box, which
// reads as a hang.
func TestPaletteEmptyStateNamesTheQuery(t *testing.T) {
	m := NewPalette(testPaletteCommands())
	for _, key := range []string{"z", "q", "x"} {
		m.HandleKey(key)
	}
	out := ansi.Strip(m.Render(theme.NewTheme("modern"), 100, 10))
	if !strings.Contains(out, `No match for "zqx"`) {
		t.Errorf("empty state did not name the query:\n%s", out)
	}
}

// A closed palette renders nothing at all, and a terminal too narrow to
// hold the box renders nothing rather than a broken one.
func TestPaletteRendersNothingWhenClosedOrTooNarrow(t *testing.T) {
	var closed PaletteModel
	if got := closed.Render(theme.NewTheme("modern"), 100, 10); got != "" {
		t.Errorf("a closed palette rendered %q", got)
	}
	m := NewPalette(testPaletteCommands())
	if got := m.Render(theme.NewTheme("modern"), 24, 10); got != "" {
		t.Errorf("a 24-column terminal rendered a palette: %q", got)
	}
}

// The window scrolls with the cursor: a selection made below the fold has
// to be visible while it is acted on.
func TestPaletteRenderScrollsToTheCursor(t *testing.T) {
	m := NewPalette(testPaletteCommands())
	for i := 0; i < 4; i++ {
		m.HandleKey("down")
	}
	out := ansi.Strip(m.Render(theme.NewTheme("modern"), 100, 2))
	sel, _ := m.Selected()
	if !strings.Contains(out, sel.Label) {
		t.Errorf("the selected row %q was not drawn:\n%s", sel.Label, out)
	}
}
