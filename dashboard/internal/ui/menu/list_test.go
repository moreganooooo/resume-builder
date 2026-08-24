package menu

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

func pressKey(s string) tea.KeyPressMsg {
	if len(s) == 1 {
		return tea.KeyPressMsg(tea.Key{Code: rune(s[0]), Text: s})
	}
	switch s {
	case "up":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyUp})
	case "down":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyDown})
	case "esc":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyEsc})
	case "enter":
		return tea.KeyPressMsg(tea.Key{Code: tea.KeyEnter})
	}
	return tea.KeyPressMsg(tea.Key{})
}

func TestMenuModelNavigationAndHelp(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	m := NewMenuModel(th)
	m.Resize(80, 24)

	// Initial view should contain MAIN MENU, hover border, and footer
	view := ansi.Strip(m.View())
	if !strings.Contains(view, "MAIN MENU") {
		t.Errorf("expected view to contain 'MAIN MENU', got: %s", view)
	}
	if !strings.Contains(view, "? help") {
		t.Errorf("expected view footer to contain '? help', got: %s", view)
	}
	if !strings.Contains(view, "┃") {
		t.Errorf("expected selected item to have '┃' hover border, got: %s", view)
	}

	// Pressing '?' toggles help overlay
	m, _ = m.Update(pressKey("?"))
	if !m.showHelp {
		t.Errorf("expected showHelp to be true after pressing '?'")
	}
	helpView := ansi.Strip(m.View())
	if !strings.Contains(helpView, "Main Menu Help") {
		t.Errorf("expected help view to contain 'Main Menu Help', got: %s", helpView)
	}
	if !strings.Contains(helpView, "Navigation") {
		t.Errorf("expected help view to contain 'Navigation', got: %s", helpView)
	}

	// Pressing 'esc' dismisses help
	m, _ = m.Update(pressKey("esc"))
	if m.showHelp {
		t.Errorf("expected showHelp to be false after pressing Esc")
	}

	// Pressing 'q' sends quit message
	_, cmd := m.Update(pressKey("q"))
	if cmd == nil {
		t.Fatalf("expected non-nil cmd on quit")
	}
	msg := cmd()
	if _, ok := msg.(MenuQuitMsg); !ok {
		t.Errorf("expected MenuQuitMsg, got: %T", msg)
	}

	// Pressing 'enter' sends select message
	_, cmd = m.Update(pressKey("enter"))
	if cmd == nil {
		t.Fatalf("expected non-nil cmd on enter")
	}
	selMsg := cmd()
	if sm, ok := selMsg.(MenuSelectMsg); !ok || sm.Command == "" {
		t.Errorf("expected MenuSelectMsg with non-empty command, got: %#v", selMsg)
	}
}

func TestMenuModel_DynamicMotivationalHeader(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	m := NewMenuModel(th)
	m.SetSubtitle("✦ 4 applications submitted this week • Keep up the momentum! ✧")
	m.Resize(80, 24)

	view := ansi.Strip(m.View())
	if !strings.Contains(view, "4 applications submitted this week") {
		t.Errorf("expected view to contain dynamic motivational copy, got:\n%s", view)
	}
}

func TestMenuModel_ProfileBadge(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	m := NewMenuModel(th)
	m = m.WithProfile(data.ProfileInfo{
		Name:     "morgan",
		Role:     "Staff Software Engineer",
		IsActive: true,
	})
	m.Resize(80, 24)

	view := ansi.Strip(m.View())
	if !strings.Contains(view, "Profile: morgan") {
		t.Errorf("expected view to contain 'Profile: morgan', got:\n%s", view)
	}
	if !strings.Contains(view, "Staff Software Engineer") {
		t.Errorf("expected view to contain role 'Staff Software Engineer', got:\n%s", view)
	}
}

func TestMenuModel_SparkleEasterEgg(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	m := NewMenuModel(th)
	m.Resize(80, 24)

	// Type "sparkle"
	keys := []string{"s", "p", "a", "r", "k", "l", "e"}
	for _, k := range keys {
		m, _ = m.Update(pressKey(k))
	}

	if !m.SparkleActive() {
		t.Errorf("expected sparkle easter egg mode to activate after typing 'sparkle'")
	}
}

func TestMenuModel_NumericShortcuts(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	m := NewMenuModel(th)
	m.Resize(80, 24)

	// Pressing '1' selects "Pipeline"
	_, cmd := m.Update(pressKey("1"))
	if cmd == nil {
		t.Fatalf("expected non-nil cmd on pressing '1'")
	}
	msg := cmd()
	if sel, ok := msg.(MenuSelectMsg); !ok || sel.Command != "Pipeline" {
		t.Errorf("expected MenuSelectMsg with 'Pipeline', got: %#v", msg)
	}

	// Pressing '2' selects "Progress"
	_, cmd = m.Update(pressKey("2"))
	if cmd == nil {
		t.Fatalf("expected non-nil cmd on pressing '2'")
	}
	msg = cmd()
	if sel, ok := msg.(MenuSelectMsg); !ok || sel.Command != "Progress" {
		t.Errorf("expected MenuSelectMsg with 'Progress', got: %#v", msg)
	}

	// Pressing '4' selects "Knowledge Base" -- 4, not 5, since the dead
	// "Reports" entry was removed from the menu.
	_, cmd = m.Update(pressKey("4"))
	if cmd == nil {
		t.Fatalf("expected non-nil cmd on pressing '4'")
	}
	msg = cmd()
	if sel, ok := msg.(MenuSelectMsg); !ok || sel.Command != "Knowledge Base" {
		t.Errorf("expected MenuSelectMsg with 'Knowledge Base', got: %#v", msg)
	}
}

// TestMenuModel_ShortcutsMatchVisibleOrder pins the numeric shortcuts to
// the rendered menu rather than to hard-coded expectations. Removing the
// "Reports" row silently shifted every shortcut below it; asserting the
// two agree means the next add/remove can't desync them.
func TestMenuModel_ShortcutsMatchVisibleOrder(t *testing.T) {
	m := NewMenuModel(theme.NewTheme("resume-builder"))

	for i, item := range m.list.Items() {
		entry, ok := item.(MenuItem)
		if !ok {
			t.Fatalf("item %d is not a MenuItem", i)
		}

		key := string(rune('1' + i))
		_, cmd := m.Update(pressKey(key))
		if cmd == nil {
			t.Fatalf("pressing %q produced no command", key)
		}

		switch msg := cmd().(type) {
		case MenuSelectMsg:
			if msg.Command != entry.title {
				t.Errorf("key %q selected %q, but row %d is %q", key, msg.Command, i, entry.title)
			}
		case MenuQuitMsg:
			// The Exit row is wired to quit directly rather than to a
			// select message, so it is the one legitimate mismatch.
			if entry.title != "Exit" {
				t.Errorf("key %q quit, but row %d is %q, not Exit", key, i, entry.title)
			}
		default:
			t.Errorf("key %q produced unexpected %#v", key, msg)
		}
	}
}

// TestMenuModel_HasNoReportsEntry keeps the dead-end from coming back:
// the Reports viewer had no resume-builder-produced reports to open, so
// the row always rendered an empty screen.
func TestMenuModel_HasNoReportsEntry(t *testing.T) {
	m := NewMenuModel(theme.NewTheme("resume-builder"))

	for _, item := range m.list.Items() {
		if entry, ok := item.(MenuItem); ok && entry.title == "Reports" {
			t.Fatal("the Reports menu entry is back; it opens an empty viewer")
		}
	}
}

func TestMenuModel_MouseInteraction(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	m := NewMenuModel(th)
	m.Resize(80, 24)

	// Render view to populate zones
	_ = m.View()

	// Mouse wheel down moves cursor
	origIdx := m.list.Index()
	m, _ = m.Update(tea.MouseWheelMsg{Y: 1})
	if m.list.Index() != origIdx+1 {
		t.Errorf("expected cursor index %d after wheel down, got %d", origIdx+1, m.list.Index())
	}

	// Mouse wheel up moves cursor back
	m, _ = m.Update(tea.MouseWheelMsg{Y: -1})
	if m.list.Index() != origIdx {
		t.Errorf("expected cursor index %d after wheel up, got %d", origIdx, m.list.Index())
	}
}

func TestMenuModel_MouseClick(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	m := NewMenuModel(th)
	m.Resize(80, 24)

	// Render and scan view to populate zones
	_ = zone.Scan(m.View())

	// Test bounds click on item 1
	info := zone.WaitFor("menu_item_1", 2*time.Second)
	if info == nil {
		t.Fatalf("zone menu_item_1 never registered after Scan -- the click path is untested if this is skipped")
	}
	m, cmd := m.Update(tea.MouseClickMsg{X: info.StartX + 1, Y: info.StartY})
	if m.list.Index() != 1 {
		t.Errorf("expected cursor index 1 after click, got %d", m.list.Index())
	}
	if cmd == nil {
		t.Errorf("expected non-nil cmd from clicking menu item")
	}
}
