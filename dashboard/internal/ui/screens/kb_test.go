package screens

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
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
