package screens

import (
	"fmt"
	"strings"

	"charm.land/lipgloss/v2"
	"charm.land/lipgloss/v2/tree"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// -- ClusterTree --
//
// A two-level hierarchy (group -> entry) drawn with Lip Gloss's own Tree
// rather than hand-written `↳` prefixes. The branch glyphs are the point:
// a flat list of 212 entries with a `[Tool]` badge on each makes the reader
// reconstruct the grouping in their head on every pass, which is why the
// knowledge base is hard to audit even though nothing is missing from it.
//
// Two rules from the spec:
//   - the enumerator is Lip Gloss's ROUNDED set in Overlay. Branch lines are
//     structure, not content, and must never out-weigh the labels.
//   - a group carries its entry count, and a group under thinClusterCount is
//     flagged Peach. In the design's original setting (bullet clusters) a
//     thin group means the extractor mis-grouped; here it means a section of
//     the knowledge base is nearly empty, which is the visible face of the
//     ledger-emptying bugs this project has already had twice. Either way it
//     is "look at this", not "this is fine".
//
// Rendering returns LINES, not one string: every caller has a scrolling
// window, and a caller that had to split the block itself would be deriving
// the same structure twice.

// thinClusterCount is the size below which a group is flagged.
const thinClusterCount = 3

// ClusterNode is one row. A node with children is a group; Count is drawn
// only when HasCount is set, so a genuine zero is distinguishable from
// "this row does not carry a count".
type ClusterNode struct {
	Label    string
	Count    int
	HasCount bool
	Children []ClusterNode
}

// ClusterRowCount is how many rows a node set draws, which is what a
// caller sizes its scroll window against.
func ClusterRowCount(nodes []ClusterNode) int {
	n := 0
	for _, node := range nodes {
		n += 1 + len(node.Children)
	}
	return n
}

// ClusterNodeAt resolves a flattened, depth-first row index back to the
// node it drew, and whether that row is a group. The cursor is an index
// into the RENDERED rows, so this is the one place that mapping lives --
// two copies of it would disagree the first time a group gained a child.
func ClusterNodeAt(nodes []ClusterNode, index int) (ClusterNode, bool, bool) {
	row := 0
	for _, node := range nodes {
		if row == index {
			return node, true, true
		}
		row++
		for _, child := range node.Children {
			if row == index {
				return child, false, true
			}
			row++
		}
	}
	return ClusterNode{}, false, false
}

// RenderClusterTree draws the node set, one string per row, with the row at
// cursor carrying the Mauve selection bar. A negative cursor selects
// nothing, which is what a caller with an empty list or an unfocused pane
// passes.
func RenderClusterTree(t theme.Theme, nodes []ClusterNode, cursor, width int) []string {
	if len(nodes) == 0 || width <= 0 {
		return nil
	}

	// The selection bar occupies its own leading column on EVERY row, drawn
	// transparent when unselected -- reserving it unconditionally is what
	// keeps the branch glyphs from shifting sideways as the cursor moves.
	const barWidth = 2
	labelWidth := width - barWidth
	if labelWidth < 8 {
		labelWidth = 8
	}

	var lines []string
	row := 0
	for _, node := range nodes {
		selected := row == cursor
		sub := tree.New().
			Root(clusterGroupLabel(t, node, selected, labelWidth)).
			Enumerator(tree.RoundedEnumerator).
			// PaddingRight is restored explicitly: setting an enumerator
			// style REPLACES Lip Gloss's default one, which carried the
			// single space separating "├──" from the label.
			EnumeratorStyle(lipgloss.NewStyle().Foreground(t.Overlay).PaddingRight(1))
		row++
		for _, child := range node.Children {
			sub = sub.Child(clusterEntryLabel(t, child, row == cursor, labelWidth))
			row++
		}
		lines = append(lines, strings.Split(sub.String(), "\n")...)
	}

	// The bar is applied AFTER the tree renders, because the tree owns the
	// indentation and would otherwise have to be told about a column that
	// is not part of its structure.
	bar := lipgloss.NewStyle().Foreground(t.Mauve).Render("┃") + " "
	for i := range lines {
		if i == cursor {
			lines[i] = bar + lines[i]
		} else {
			lines[i] = strings.Repeat(" ", barWidth) + lines[i]
		}
	}
	return lines
}

// clusterGroupLabel renders a group's own row: Blue, bold when selected,
// then its count in Subtext, or Peach with a reason when the group is thin.
func clusterGroupLabel(t theme.Theme, node ClusterNode, selected bool, width int) string {
	style := lipgloss.NewStyle().Foreground(t.Blue).Bold(selected)

	count := ""
	if node.HasCount {
		text := fmt.Sprintf("%d %s", node.Count, pluralEntries(node.Count))
		countStyle := lipgloss.NewStyle().Foreground(t.Subtext)
		if node.Count < thinClusterCount {
			text += " — thin"
			countStyle = lipgloss.NewStyle().Foreground(t.Peach)
		}
		count = "  " + countStyle.Render(text)
	}

	room := width - lipgloss.Width(count)
	if room < 4 {
		room = 4
	}
	return style.Render(ansi.Truncate(node.Label, room, "…")) + count
}

// clusterEntryLabel renders a leaf row. Plain Text, bold only when
// selected: an entry is content, and the tree's job is to let the eye skip
// the ones it does not want.
func clusterEntryLabel(t theme.Theme, node ClusterNode, selected bool, width int) string {
	style := lipgloss.NewStyle().Foreground(t.Text).Bold(selected)
	// 4 columns for the enumerator the tree will prepend ("└── ").
	return style.Render(ansi.Truncate(node.Label, max(width-4, 4), "…"))
}

func pluralEntries(n int) string {
	if n == 1 {
		return "entry"
	}
	return "entries"
}
