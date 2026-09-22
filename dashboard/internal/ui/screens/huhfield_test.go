package screens

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

var testStatuses = []string{"Evaluated", "Applied", "Interview", "Offer"}

// One row carries the cursor glyph and the rest carry the rail, all in the
// same two columns -- that is what stops the labels sliding sideways as the
// cursor moves, which is the whole reason the rail is drawn at all.
func TestSelectFieldMarksOneRowAndHoldsTheGutter(t *testing.T) {
	lines := RenderSelectField(theme.NewTheme("catppuccin-mocha"),
		"Change status:", testStatuses, 2, FieldFocused, 30)
	if got, want := len(lines), len(testStatuses)+1; got != want {
		t.Fatalf("rendered %d lines, want %d (label + options)", got, want)
	}
	cursors := 0
	for i, line := range lines[1:] {
		plain := ansi.Strip(line)
		switch {
		case strings.HasPrefix(plain, "┃ "):
			cursors++
			if i != 2 {
				t.Errorf("option %d carried the cursor, cursor was 2", i)
			}
		case strings.HasPrefix(plain, "│ "):
		default:
			t.Errorf("option %d has no gutter: %q", i, plain)
		}
	}
	if cursors != 1 {
		t.Errorf("%d rows carried the cursor, want exactly 1", cursors)
	}
}

// The selected option has to be findable without color: it is the bold,
// brightest row, and the others step back to Subtext.
func TestSelectFieldSeparatesTheCurrentOption(t *testing.T) {
	lines := RenderSelectField(theme.NewTheme("modern"), "", testStatuses, 1, FieldFocused, 30)
	if optLead(lines[0]) == optLead(lines[1]) {
		t.Errorf("the cursor row is styled the same as an idle one:\n%q\n%q", lines[0], lines[1])
	}
	if optLead(lines[0]) != optLead(lines[2]) {
		t.Errorf("two idle rows are styled differently:\n%q\n%q", lines[0], lines[2])
	}
}

// A field's state is its accent color; if two states rendered alike, the
// four-state contract would be decorative.
func TestSelectFieldStatesDiffer(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	seen := map[string]FieldState{}
	for _, st := range []FieldState{FieldBlurred, FieldFocused, FieldError} {
		key := lead(RenderSelectField(th, "Label", testStatuses, 0, st, 30)[0])
		if prev, dup := seen[key]; dup {
			t.Errorf("states %d and %d render the label identically", prev, st)
		}
		seen[key] = st
	}
}

// Long labels are cut with the single-rune ellipsis and nothing exceeds the
// width it was handed -- these rows are spliced into a pane that wraps.
func TestSelectFieldRespectsWidth(t *testing.T) {
	const width = 24
	opts := []string{strings.Repeat("Interview scheduled ", 5)}
	for _, line := range RenderSelectField(theme.NewTheme("modern"),
		strings.Repeat("Change the status ", 4), opts, 0, FieldFocused, width) {
		if w := ansi.StringWidth(line); w > width {
			t.Errorf("row is %d columns, limit %d: %q", w, width, ansi.Strip(line))
		}
		if strings.Contains(ansi.Strip(line), "...") {
			t.Errorf("ASCII ellipsis used: %q", ansi.Strip(line))
		}
	}
	if got := RenderSelectField(theme.NewTheme("modern"), "x", opts, 0, FieldFocused, 0); got != nil {
		t.Errorf("a zero-width render produced %v", got)
	}
}

// An idle screen shows no search bar at all; a committed query shows one
// without the typing affordances.
func TestSearchBarAppearsOnlyWhenThereIsASearch(t *testing.T) {
	th := theme.NewTheme("modern")
	if got := RenderSearchBar(th, SearchBarState{Width: 80}); got != "" {
		t.Errorf("an idle screen drew a search bar: %q", got)
	}
	committed := ansi.Strip(RenderSearchBar(th, SearchBarState{
		Query: "acme", Matched: 3, Total: 40, Width: 80,
	}))
	if !strings.Contains(committed, "acme") || !strings.Contains(committed, "3/40 matching") {
		t.Errorf("a committed query lost its text or count: %q", committed)
	}
	if strings.Contains(committed, "SEARCH") {
		t.Errorf("a committed query still showed the typing badge: %q", committed)
	}
}

// An empty box the user is typing into says what goes in it, rather than
// showing a lone cursor that reads as a hung screen.
func TestSearchBarPromptsWhenEmpty(t *testing.T) {
	out := ansi.Strip(RenderSearchBar(theme.NewTheme("modern"), SearchBarState{
		Typing: true, Total: 40, Width: 80,
	}))
	if !strings.Contains(out, "company or title") {
		t.Errorf("an empty search box offered no placeholder: %q", out)
	}
	if !strings.Contains(out, "SEARCH") {
		t.Errorf("the typing badge is missing: %q", out)
	}
}

// The placeholder must not survive into a real query, or it would read as
// part of what the user typed.
func TestSearchBarDropsPlaceholderOnceTyping(t *testing.T) {
	out := ansi.Strip(RenderSearchBar(theme.NewTheme("modern"), SearchBarState{
		Query: "a", Typing: true, Matched: 9, Total: 40, Width: 80,
	}))
	if strings.Contains(out, "company or title") {
		t.Errorf("the placeholder stayed behind a real query: %q", out)
	}
}

// optLead is the escape sequence on the OPTION text, past the gutter. The
// gutter's own color is Mauve on every row (rail and cursor alike), so
// reading the leading sequence would compare the part that is meant to
// match and miss the part that is meant to differ.
func optLead(s string) string {
	if i := strings.Index(s, " "); i > 0 {
		return lead(s[i:])
	}
	return lead(s)
}

// lead is the opening escape sequence, which is where the color and weight
// of a rendered line live.
func lead(s string) string {
	if i := strings.Index(s, "m"); i > 0 {
		return s[:i]
	}
	return s
}
