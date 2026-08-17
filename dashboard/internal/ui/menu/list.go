// Package menu provides a Bubble Tea list based main menu that follows the dashboard design system.
package menu

import (
	"charm.land/bubbles/v2/list"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/screens"
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
	list     list.Model
	theme    theme.Theme
	showHelp bool
	width    int
	height   int
}

// NewMenuModel builds a list of top‑level commands using the token palette.
func NewMenuModel(t theme.Theme) MenuModel {
	items := []list.Item{
		MenuItem{title: "Pipeline", desc: "Career pipeline view", icon: t.Icons.Pipeline},
		MenuItem{title: "Progress", desc: "Analytics and funnel", icon: t.Icons.Progress},
		MenuItem{title: "Reports", desc: "Open a markdown report", icon: t.Icons.Report},
		MenuItem{title: "Jobs", desc: "Browse & Manage Jobs", icon: t.Icons.Jobs},
		MenuItem{title: "Exit", desc: "Leave the dashboard", icon: t.Icons.Quit},
	}

	// Width/height are arbitrary – the list will be resized by the parent view.
	delegate := list.NewDefaultDelegate()

	// Selected row: left-border '┃' indicator in Mauve, matching sidebar hover language.
	// 1 border char + 1 padding char = 2 cells total, aligning with unselected rows (padding 2).
	selectedTitle := theme.HoverStyle(lipgloss.NewStyle().Bold(true).Foreground(t.Token.Mauve), t)
	selectedDesc := lipgloss.NewStyle().Foreground(t.Token.Subtext).PaddingLeft(2)

	normalTitle := lipgloss.NewStyle().Bold(true).Foreground(t.Token.Text).PaddingLeft(2)
	normalDesc := lipgloss.NewStyle().Foreground(t.Token.Subtext).PaddingLeft(2)

	delegate.Styles.SelectedTitle = selectedTitle
	delegate.Styles.SelectedDesc = selectedDesc
	delegate.Styles.NormalTitle = normalTitle
	delegate.Styles.NormalDesc = normalDesc

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

// Update handles key presses.
func (m MenuModel) Update(msg tea.Msg) (MenuModel, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		if m.showHelp {
			switch msg.String() {
			case "?", "esc", "q":
				m.showHelp = false
				return m, nil
			}
			return m, nil
		}
		switch msg.String() {
		case "?":
			m.showHelp = true
			return m, nil
		case "q", "ctrl+c":
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
	titleText := m.theme.Icons.Menu + "  " + theme.RenderColorGradient("✦ MAIN MENU ✧", m.theme.Mauve, m.theme.Blue)
	header := headerStyle.Render(titleText)

	captionStyle := theme.PadHorizontal(
		lipgloss.NewStyle().
			Foreground(m.theme.Token.Text).
			Background(m.theme.Surface).
			Width(width),
	)
	caption := captionStyle.Render("Review And Triage Your Job Search — The resume CLI Builds")

	body := m.list.View()

	footerStyle := theme.PadHorizontal(
		lipgloss.NewStyle().
			Foreground(m.theme.Token.Subtext).
			Background(m.theme.Surface).
			Width(width),
	)
	footer := footerStyle.Render("←↑↓→ navigate • ↩ select • ? help • q quit")

	return lipgloss.JoinVertical(lipgloss.Left, header, caption, body, footer)
}

// Messages exposed to the parent application.
type MenuSelectMsg struct{ Command string }
type MenuQuitMsg struct{}
