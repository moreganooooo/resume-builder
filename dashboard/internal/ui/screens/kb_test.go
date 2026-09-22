package screens

import (
	"strings"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

func sampleKBItems() []data.KBItem {
	return []data.KBItem{
		{
			ID:         "tool_001",
			Title:      "Go / Bubble Tea",
			Category:   "Tools",
			Content:    "### Go / Bubble Tea\n\nExpertise in building Charm TUIs with Elm architecture.",
			Tags:       []string{"Dev", "TUI"},
			Confidence: "Expert",
			Source:     "verified_tools.json",
		},
		{
			ID:         "metric_001",
			Title:      "10x Faster Build Pipelines",
			Category:   "Metrics",
			Content:    "### 10x Faster Build Pipelines\n\n**Value:** 90% latency reduction\n- Context: Async refactoring",
			Tags:       []string{"Performance"},
			Confidence: "High",
			Source:     "verified_metrics.json",
		},
		{
			ID:         "fact_001",
			Title:      "Designed Core System Architecture",
			Category:   "Facts",
			Content:    "### Designed Core System Architecture\n\nArchitected end-to-end resume pipeline.",
			Tags:       []string{"Architecture"},
			Confidence: "High",
			Source:     "verified_facts.json",
		},
	}
}

func TestKBModel_InitialRender(t *testing.T) {
	th := theme.NewTheme("modern")
	items := sampleKBItems()
	m := NewKBModel(th, items, 100, 30)

	view := m.View()
	if !strings.Contains(view, "KNOWLEDGE BASE EXPLORER") {
		t.Errorf("expected view to contain 'KNOWLEDGE BASE EXPLORER', got:\n%s", view)
	}
	if !strings.Contains(view, "Go / Bubble Tea") {
		t.Errorf("expected view to show item 'Go / Bubble Tea'")
	}
}

func TestKBModel_CategorySwitching(t *testing.T) {
	th := theme.NewTheme("modern")
	items := sampleKBItems()
	m := NewKBModel(th, items, 100, 30)

	// Switch category using Tab
	m, _ = m.Update(tea.KeyPressMsg{Code: tea.KeyTab, Text: "\t"})
	if m.activeCategory != "Tools" {
		t.Errorf("expected active category 'Tools' after Tab, got '%s'", m.activeCategory)
	}

	m, _ = m.Update(tea.KeyPressMsg{Code: tea.KeyTab, Text: "\t"})
	if m.activeCategory != "Metrics" {
		t.Errorf("expected active category 'Metrics' after second Tab, got '%s'", m.activeCategory)
	}

	// Direct numeric category switch
	m, _ = m.Update(tea.KeyPressMsg{Code: '1', Text: "1"})
	if m.activeCategory != "All" {
		t.Errorf("expected category 'All' on '1', got '%s'", m.activeCategory)
	}
}

func TestKBModel_SearchFilter(t *testing.T) {
	th := theme.NewTheme("modern")
	items := sampleKBItems()
	m := NewKBModel(th, items, 100, 30)

	// Open search with '/'
	m, _ = m.Update(tea.KeyPressMsg{Code: '/', Text: "/"})
	if !m.searching {
		t.Errorf("expected searching to be true after '/'")
	}

	// Type 'Build Pipelines'
	for _, ch := range "Build Pipelines" {
		m, _ = m.Update(tea.KeyPressMsg{Code: ch, Text: string(ch)})
	}

	filtered := m.visibleItems()
	if len(filtered) != 1 {
		t.Fatalf("expected 1 visible item matching 'Build Pipelines', got %d", len(filtered))
	}
	if filtered[0].Title != "10x Faster Build Pipelines" {
		t.Errorf("expected matched item '10x Faster Build Pipelines', got '%s'", filtered[0].Title)
	}

	// Press Esc to clear search
	m, _ = m.Update(tea.KeyPressMsg{Code: tea.KeyEscape})
	if m.searching {
		t.Errorf("expected searching to be false after Esc")
	}
	if len(m.visibleItems()) != 3 {
		t.Errorf("expected 3 visible items after clearing search, got %d", len(m.visibleItems()))
	}
}

func TestKBModel_CloseAndQuit(t *testing.T) {
	th := theme.NewTheme("modern")
	items := sampleKBItems()
	m := NewKBModel(th, items, 100, 30)

	// Press 'q' to quit
	_, cmd := m.Update(tea.KeyPressMsg{Code: 'q', Text: "q"})
	if cmd == nil {
		t.Fatalf("expected command on 'q'")
	}
	msg := cmd()
	closeMsg, ok := msg.(KBCloseMsg)
	if !ok || !closeMsg.Quit {
		t.Errorf("expected KBCloseMsg with Quit=true on 'q', got %v", msg)
	}

	// Press 'Esc' to go back
	_, cmd = m.Update(tea.KeyPressMsg{Code: tea.KeyEscape})
	if cmd == nil {
		t.Fatalf("expected command on 'Esc'")
	}
	msg = cmd()
	closeMsg, ok = msg.(KBCloseMsg)
	if !ok || closeMsg.Quit {
		t.Errorf("expected KBCloseMsg with Quit=false on 'Esc', got %v", msg)
	}
}

func TestKBModel_MouseInteractions(t *testing.T) {
	th := theme.NewTheme("modern")
	items := sampleKBItems()
	m := NewKBModel(th, items, 100, 30)

	// Initial cursor is 0
	if m.cursor != 0 {
		t.Fatalf("expected initial cursor 0, got %d", m.cursor)
	}

	// Mouse wheel down moves cursor
	m, _ = m.Update(tea.MouseWheelMsg{Button: tea.MouseWheelDown})
	if m.cursor != 1 {
		t.Errorf("expected cursor 1 after wheel down, got %d", m.cursor)
	}

	// Mouse wheel up moves cursor back
	m, _ = m.Update(tea.MouseWheelMsg{Button: tea.MouseWheelUp})
	if m.cursor != 0 {
		t.Errorf("expected cursor 0 after wheel up, got %d", m.cursor)
	}
}

func TestKBModel_MouseClick(t *testing.T) {
	th := theme.NewTheme("modern")
	items := sampleKBItems()
	m := NewKBModel(th, items, 100, 30)

	_ = zone.Scan(m.View())

	info := zone.WaitFor("kb_item_1", 2*time.Second)
	if info == nil {
		t.Fatalf("zone kb_item_1 never registered after Scan -- the click path is untested if this is skipped")
	}
	m, _ = m.Update(tea.MouseClickMsg{X: info.StartX + 1, Y: info.StartY})
	if m.cursor != 1 {
		t.Errorf("expected cursor 1 after clicking kb item 1, got %d", m.cursor)
	}
}

// TestKB_SkillsTabRunsToolsWithoutTouchingItems pins the two things that make
// the Skills tab safe to sit alongside the content categories: it lists tools
// rather than knowledge-base items, and Enter asks the host to run one instead
// of doing it here.
func TestKB_SkillsTabRunsToolsWithoutTouchingItems(t *testing.T) {
	m := NewKBModel(theme.NewTheme("catppuccin-mocha"), []data.KBItem{
		{Title: "Adobe Sign", Category: "Tools", Content: "verified"},
	}, 120, 40)

	m, _ = m.handleKey("6", "")
	if m.activeCategory != kbSkillsCategory {
		t.Fatalf("expected key 6 to select the Skills tab, got %q", m.activeCategory)
	}
	if got := m.visibleItems(); len(got) != 0 {
		t.Errorf("the Skills tab holds no knowledge-base items, got %d", len(got))
	}

	view := ansi.Strip(m.View())
	for _, want := range []string{"Skills", "View & Manage Profile Skills", "Enter"} {
		if !strings.Contains(view, want) {
			t.Errorf("expected the Skills tab view to contain %q:\n%s", want, view)
		}
	}
	// "Adobe Sign" is a Tools item; it must not leak into this tab.
	if strings.Contains(view, "Adobe Sign") {
		t.Errorf("a knowledge-base item rendered on the Skills tab:\n%s", view)
	}

	_, cmd := m.handleKey("enter", "")
	if cmd == nil {
		t.Fatal("expected Enter to emit a run-tool message")
	}
	msg, ok := cmd().(KBRunToolMsg)
	if !ok || msg.Action != "manage_skills" {
		t.Errorf("expected KBRunToolMsg for manage_skills, got %#v", cmd())
	}
}

func clusterKBItems() []data.KBItem {
	return []data.KBItem{
		{Title: "HubSpot", Category: "Tools"},
		{Title: "Adobe Sign", Category: "Tools"},
		{Title: "42% lift", Category: "Metrics"},
		{Title: "Odd One", Category: "Claims"},
	}
}

// The tree's rows are a superset of the items, and every item row still
// maps back to its own index -- that mapping is what the detail pane, the
// arrow keys and the mouse hit-test all read.
func TestKBClusterNodesMapRowsToItems(t *testing.T) {
	cats := []string{"All", "Tools", "Metrics", "Facts", "Projects", kbSkillsCategory}
	nodes, rowItems := kbClusterNodes(cats, clusterKBItems())

	if len(rowItems) != ClusterRowCount(nodes) {
		t.Fatalf("%d row mappings for %d rows", len(rowItems), ClusterRowCount(nodes))
	}
	// Tools(2) + Metrics(1) + Claims(1) = 3 groups, 4 items, 7 rows.
	if len(nodes) != 3 || len(rowItems) != 7 {
		t.Fatalf("got %d groups / %d rows, want 3 / 7", len(nodes), len(rowItems))
	}
	for row, item := range rowItems {
		node, isGroup, _ := ClusterNodeAt(nodes, row)
		if isGroup != (item < 0) {
			t.Errorf("row %d: group=%v but item index %d", row, isGroup, item)
		}
		if !isGroup && node.Label != clusterKBItems()[item].Title {
			t.Errorf("row %d points at %q, drew %q", row, clusterKBItems()[item].Title, node.Label)
		}
	}
}

// An empty category is dropped, and a category the tab bar never names is
// still drawn -- the flat list showed it, so the tree must not hide it.
func TestKBClusterNodesKeepTabOrderAndUnnamedCategories(t *testing.T) {
	cats := []string{"All", "Tools", "Metrics", "Facts", "Projects", kbSkillsCategory}
	nodes, _ := kbClusterNodes(cats, clusterKBItems())
	var got []string
	for _, n := range nodes {
		got = append(got, n.Label)
	}
	want := []string{"Tools", "Metrics", "Claims"}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Errorf("group order = %v, want %v", got, want)
	}
}

// The "All" tab draws the tree; a single-category tab keeps the flat list,
// where a tree would be one root over a list it adds nothing to.
func TestKBAllTabRendersTheTree(t *testing.T) {
	m := NewKBModel(theme.NewTheme("catppuccin-mocha"), clusterKBItems(), 120, 30)
	all := ansi.Strip(m.View())
	// With the trailing space: the panes' own rounded borders are a run of
	// ─ with no space after, so a bare "╰──" would match those too.
	if !strings.Contains(all, "├── ") && !strings.Contains(all, "╰── ") {
		t.Errorf("the All tab drew no branch glyphs:\n%s", all)
	}
	if strings.Contains(all, "[Tool]") {
		t.Errorf("the All tab still drew the flat category badge:\n%s", all)
	}

	m.activeCategory = "Tools"
	tools := ansi.Strip(m.View())
	if strings.Contains(tools, "╰── ") {
		t.Errorf("a single-category tab drew a tree:\n%s", tools)
	}
}
