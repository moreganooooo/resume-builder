package menu

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"
	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
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

	// Pressing '5' selects "Knowledge Base"
	_, cmd = m.Update(pressKey("5"))
	if cmd == nil {
		t.Fatalf("expected non-nil cmd on pressing '5'")
	}
	msg = cmd()
	if sel, ok := msg.(MenuSelectMsg); !ok || sel.Command != "Knowledge Base" {
		t.Errorf("expected MenuSelectMsg with 'Knowledge Base', got: %#v", msg)
	}
}
