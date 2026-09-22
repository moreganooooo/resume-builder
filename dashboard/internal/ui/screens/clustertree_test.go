package screens

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func testClusterNodes() []ClusterNode {
	return []ClusterNode{
		{Label: "Tools", Count: 4, HasCount: true, Children: []ClusterNode{
			{Label: "Adobe Sign"},
			{Label: "HubSpot"},
			{Label: "Looker"},
			{Label: "Salesforce"},
		}},
		{Label: "Projects", Count: 2, HasCount: true, Children: []ClusterNode{
			{Label: "Adobe Sign pilot"},
			{Label: "Treering migration"},
		}},
	}
}

// The whole cursor contract rests on one row per node, so the row count the
// callers scroll against has to match what actually renders. A Lip Gloss
// version that wrapped or padded a row would break that silently.
func TestClusterTreeRowCountMatchesRenderedLines(t *testing.T) {
	nodes := testClusterNodes()
	lines := RenderClusterTree(theme.NewTheme("catppuccin-mocha"), nodes, 0, 60)
	if got, want := len(lines), ClusterRowCount(nodes); got != want {
		t.Fatalf("rendered %d lines, ClusterRowCount says %d:\n%s",
			got, want, strings.Join(lines, "\n"))
	}
	if want := 8; len(lines) != want { // 2 groups + 6 entries
		t.Errorf("expected %d rows, got %d", want, len(lines))
	}
}

// The flattened index is depth-first, and it is what a cursor means -- if
// ClusterNodeAt and the renderer ever disagreed, the bar would sit on a
// different row than the one being acted on.
func TestClusterNodeAtWalksDepthFirst(t *testing.T) {
	nodes := testClusterNodes()
	cases := []struct {
		index   int
		label   string
		isGroup bool
	}{
		{0, "Tools", true},
		{1, "Adobe Sign", false},
		{4, "Salesforce", false},
		{5, "Projects", true},
		{6, "Adobe Sign pilot", false},
	}
	for _, c := range cases {
		node, isGroup, ok := ClusterNodeAt(nodes, c.index)
		if !ok || node.Label != c.label || isGroup != c.isGroup {
			t.Errorf("index %d = (%q, group=%v, ok=%v), want (%q, group=%v)",
				c.index, node.Label, isGroup, ok, c.label, c.isGroup)
		}
	}
	if _, _, ok := ClusterNodeAt(nodes, 8); ok {
		t.Error("an index past the last row resolved to a node")
	}
	if _, _, ok := ClusterNodeAt(nodes, -1); ok {
		t.Error("a negative index resolved to a node")
	}
}

// The selection bar marks exactly one row and does not move the others
// sideways, which is the reason the gutter is reserved on every line.
func TestClusterTreeMarksOneRowWithoutShiftingTheRest(t *testing.T) {
	nodes := testClusterNodes()
	lines := RenderClusterTree(theme.NewTheme("modern"), nodes, 3, 60)
	bars := 0
	for i, line := range lines {
		plain := ansi.Strip(line)
		if strings.HasPrefix(plain, "┃ ") {
			bars++
			if i != 3 {
				t.Errorf("row %d carried the bar, cursor was 3", i)
			}
			continue
		}
		if !strings.HasPrefix(plain, "  ") {
			t.Errorf("row %d did not reserve the gutter: %q", i, plain)
		}
	}
	if bars != 1 {
		t.Errorf("%d rows carried the selection bar, want 1", bars)
	}
}

// A thin group says so in words, not only in color -- the Peach alone is
// invisible to anyone reading a monochrome capture.
func TestClusterTreeFlagsThinGroups(t *testing.T) {
	nodes := []ClusterNode{
		{Label: "Metrics", Count: 9, HasCount: true, Children: []ClusterNode{{Label: "one"}}},
		{Label: "Facts", Count: 1, HasCount: true, Children: []ClusterNode{{Label: "two"}}},
	}
	out := ansi.Strip(strings.Join(RenderClusterTree(theme.NewTheme("modern"), nodes, -1, 60), "\n"))
	if !strings.Contains(out, "9 entries") {
		t.Errorf("a healthy group lost its count:\n%s", out)
	}
	if !strings.Contains(out, "1 entry — thin") {
		t.Errorf("a one-entry group was not flagged thin (and not pluralized):\n%s", out)
	}
	if strings.Contains(out, "9 entries — thin") {
		t.Errorf("a nine-entry group was flagged thin:\n%s", out)
	}
}

// Branch glyphs come from Lip Gloss's rounded set, and the last child of a
// group closes it -- that is what makes the grouping readable at a glance.
func TestClusterTreeDrawsRoundedBranches(t *testing.T) {
	lines := RenderClusterTree(theme.NewTheme("modern"), testClusterNodes(), -1, 60)
	fourth := ansi.Strip(lines[4]) // last entry under "Tools"
	if !strings.Contains(fourth, "╰── ") {
		t.Errorf("the last child did not close its group: %q", fourth)
	}
	if second := ansi.Strip(lines[1]); !strings.Contains(second, "├── ") {
		t.Errorf("a middle child had no branch glyph: %q", second)
	}
}

// Long labels are truncated with the single-rune ellipsis and stay inside
// the width they were given, count column included.
func TestClusterTreeRespectsWidth(t *testing.T) {
	nodes := []ClusterNode{{
		Label:    strings.Repeat("Knowledge ", 12),
		Count:    7,
		HasCount: true,
		Children: []ClusterNode{{Label: strings.Repeat("entry ", 20)}},
	}}
	const width = 40
	for _, line := range RenderClusterTree(theme.NewTheme("modern"), nodes, -1, width) {
		if w := ansi.StringWidth(line); w > width {
			t.Errorf("row is %d columns wide, limit was %d: %q", w, width, ansi.Strip(line))
		}
		if strings.Contains(ansi.Strip(line), "...") {
			t.Errorf("ASCII ellipsis used for truncation: %q", ansi.Strip(line))
		}
	}
}

// Nothing to draw renders nothing, rather than an empty bordered husk.
func TestClusterTreeEmptyInputs(t *testing.T) {
	if got := RenderClusterTree(theme.NewTheme("modern"), nil, 0, 60); got != nil {
		t.Errorf("an empty node set rendered %v", got)
	}
	if got := RenderClusterTree(theme.NewTheme("modern"), testClusterNodes(), 0, 0); got != nil {
		t.Errorf("a zero-width render produced %v", got)
	}
}
