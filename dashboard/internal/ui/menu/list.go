// Package menu provides a Bubble Tea list based main menu that follows the dashboard design system.
package menu

import (
	"bytes"
	"fmt"
	"io"
	"strings"

	"charm.land/bubbles/v2/list"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/screens"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

type MenuItem struct {
	title string
	desc  string
	icon  string
}

func (i MenuItem) Title() string       { return i.icon + "  " + i.title }
func (i MenuItem) Description() string { return i.desc }
func (i MenuItem) FilterValue() string { return i.title }

var menuHelpCategories = []screens.HelpCategory{
	{
		Label: "Navigation",
		Bindings: []screens.HelpBinding{
			{Key: "↑ / k", Desc: "Move selection up"},
			{Key: "↓ / j", Desc: "Move selection down"},
			{Key: "Home / g", Desc: "Jump to first item"},
			{Key: "End / G", Desc: "Jump to last item"},
		},
	},
	{
		Label: "Actions",
		Bindings: []screens.HelpBinding{
			{Key: "Enter", Desc: "Open selected view"},
			{Key: "1-5", Desc: "Direct screen shortcut"},
		},
	},
	{
		Label: "General",
		Bindings: []screens.HelpBinding{
			{Key: "?", Desc: "Toggle help overlay"},
			{Key: "q / Ctrl+C", Desc: "Exit dashboard"},
		},
	},
}

type MenuModel struct {
	list          list.Model
	theme         theme.Theme
	showHelp      bool
	width         int
	height        int
	subtitle      string
	sparkleBuffer string
	sparkleActive bool
	profile       data.ProfileInfo
}

// SetSubtitle updates the dynamic motivational header text under the main menu title.
func (m *MenuModel) SetSubtitle(sub string) {
	m.subtitle = sub
}

// WithProfile sets the active profile for display in the main menu banner.
func (m MenuModel) WithProfile(p data.ProfileInfo) MenuModel {
	m.profile = p
	return m
}

// SparkleActive returns whether the sparkle easter egg mode is triggered.
func (m MenuModel) SparkleActive() bool {
	return m.sparkleActive
}

type zoneMenuDelegate struct {
	list.DefaultDelegate
}

func (d zoneMenuDelegate) Render(w io.Writer, m list.Model, index int, item list.Item) {
	var buf bytes.Buffer
	d.DefaultDelegate.Render(&buf, m, index, item)
	fmt.Fprint(w, zone.Mark(fmt.Sprintf("menu_item_%d", index), buf.String()))
}

// NewMenuModel builds a list of top‑level commands using the token palette.
func NewMenuModel(t theme.Theme) MenuModel {
	items := []list.Item{
		MenuItem{title: "Pipeline", desc: "Career pipeline view", icon: t.Icons.Pipeline},
		MenuItem{title: "Progress", desc: "Analytics and funnel", icon: t.Icons.Progress},
		MenuItem{title: "Jobs", desc: "Browse & Manage Jobs", icon: t.Icons.Jobs},
		MenuItem{title: "Knowledge Base", desc: "Inspect claims, metrics & tools", icon: t.Icons.Search},
		MenuItem{title: "Exit", desc: "Leave the dashboard", icon: t.Icons.Quit},
	}

	// Width/height are arbitrary – the list will be resized by the parent view.
	baseDelegate := list.NewDefaultDelegate()

	// Selected row: left-border '┃' indicator in Mauve, matching sidebar hover language.
	// 1 border char + 1 padding char = 2 cells total, aligning with unselected rows (padding 2).
	selectedTitle := theme.HoverStyle(lipgloss.NewStyle().Bold(true).Foreground(t.Token.Mauve), t)
	selectedDesc := lipgloss.NewStyle().Foreground(t.Token.Subtext).PaddingLeft(2)

	normalTitle := lipgloss.NewStyle().Bold(true).Foreground(t.Token.Text).PaddingLeft(2)
	normalDesc := lipgloss.NewStyle().Foreground(t.Token.Subtext).PaddingLeft(2)

	baseDelegate.Styles.SelectedTitle = selectedTitle
	baseDelegate.Styles.SelectedDesc = selectedDesc
	baseDelegate.Styles.NormalTitle = normalTitle
	baseDelegate.Styles.NormalDesc = normalDesc

	delegate := zoneMenuDelegate{DefaultDelegate: baseDelegate}
	l := list.New(items, delegate, 30, 15)

	l.SetShowTitle(false)
	l.SetShowStatusBar(false)
	l.SetShowHelp(false)
	l.SetShowPagination(false)

	l.Title = t.Icons.Menu + "  ✦ MAIN MENU ✧"

	return MenuModel{list: l, theme: t, width: 30, height: 15}
}

// Resize fills the menu to the real terminal size.
func (m *MenuModel) Resize(width, height int) {
	m.width = width
	m.height = height
	m.list.SetSize(width, height)
}

// Init implements tea.Model.
func (m MenuModel) Init() tea.Cmd {
	return nil
}

// Update handles key presses and mouse interactions.
func (m MenuModel) Update(msg tea.Msg) (MenuModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.MouseClickMsg:
		for i, it := range m.list.Items() {
			if zone.InBoundsClick(fmt.Sprintf("menu_item_%d", i), msg) {
				m.list.Select(i)
				if sel, ok := it.(MenuItem); ok {
					return m, func() tea.Msg { return MenuSelectMsg{Command: sel.title} }
				}
			}
		}
	case tea.MouseWheelMsg:
		if msg.Y < 0 {
			m.list.CursorUp()
		} else {
			m.list.CursorDown()
		}
		return m, nil
	}

	var keyStr string
	switch msg := msg.(type) {
	case tea.KeyPressMsg:
		keyStr = msg.String()
	case tea.KeyMsg:
		keyStr = msg.String()
	}

	if keyStr != "" {
		if m.showHelp {
			switch keyStr {
			case "?", "esc", "q":
				m.showHelp = false
				return m, nil
			}
			return m, nil
		}
		// Track character sequence for easter eggs
		if len(keyStr) == 1 {
			m.sparkleBuffer += keyStr
			if len(m.sparkleBuffer) > 20 {
				m.sparkleBuffer = m.sparkleBuffer[len(m.sparkleBuffer)-20:]
			}
			if strings.HasSuffix(m.sparkleBuffer, "sparkle") {
				m.sparkleActive = true
			}
		}
		switch keyStr {
		case "?":
			m.showHelp = true
			return m, nil
		case "q", "ctrl+c":
			return m, func() tea.Msg { return MenuQuitMsg{} }
		case "1":
			return m, func() tea.Msg { return MenuSelectMsg{Command: "Pipeline"} }
		case "2":
			return m, func() tea.Msg { return MenuSelectMsg{Command: "Progress"} }
		// No "Reports" entry: it opened an empty viewer, because the
		// markdown reports it browsed are produced by career-ops, not by
		// resume-builder. Pipeline still opens a report directly when an
		// application actually has one (PipelineOpenReportMsg).
		case "3":
			return m, func() tea.Msg { return MenuSelectMsg{Command: "Jobs"} }
		case "4":
			return m, func() tea.Msg { return MenuSelectMsg{Command: "Knowledge Base"} }
		case "5":
			return m, func() tea.Msg { return MenuQuitMsg{} }
		case "enter":
			if sel, ok := m.list.SelectedItem().(MenuItem); ok {
				return m, func() tea.Msg { return MenuSelectMsg{Command: sel.title} }
			}
		}
	}

	var cmd tea.Cmd
	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

// View renders the menu with a consistent header/footer layout.
func (m MenuModel) View() string {
	width := m.list.Width()
	if width <= 0 {
		width = m.width
	}
	if width <= 0 {
		width = 80
	}

	if m.showHelp {
		h := m.height
		if h <= 0 {
			h = 24
		}
		return screens.RenderHelpOverlay(m.theme, "Main Menu", menuHelpCategories, width, h)
	}

	headerStyle := theme.PadHorizontal(
		lipgloss.NewStyle().
			Bold(true).
			Background(m.theme.Surface).
			Width(width),
	)

	profileBadge := ""
	if m.profile.Name != "" {
		profileBadge = lipgloss.NewStyle().
			Bold(true).
			Foreground(m.theme.Peach).
			Render(fmt.Sprintf("  [Profile: %s • %s]", m.profile.Name, m.profile.Role))
	}

	titleText := m.theme.Icons.Menu + "  " + theme.RenderColorGradient("✦ MAIN MENU ✧", m.theme.Mauve, m.theme.Blue) + profileBadge
	header := headerStyle.Render(titleText)

	captionStyle := theme.PadHorizontal(
		lipgloss.NewStyle().
			Foreground(m.theme.Token.Text).
			Background(m.theme.Surface).
			Width(width),
	)
	sub := m.subtitle
	if sub == "" {
		sub = "Review And Triage Your Job Search — The resume CLI Builds"
	}
	caption := captionStyle.Render(sub)

	body := m.list.View()

	footerStyle := theme.PadHorizontal(
		lipgloss.NewStyle().
			Foreground(m.theme.Token.Subtext).
			Background(m.theme.Surface).
			Width(width),
	)
	footer := footerStyle.Render("←↑↓→ navigate • ↩ select • 1-5 jump • ? help • q quit")

	return lipgloss.JoinVertical(lipgloss.Left, header, caption, body, footer)
}

// Messages exposed to the parent application.
type MenuSelectMsg struct{ Command string }
type MenuQuitMsg struct{}
