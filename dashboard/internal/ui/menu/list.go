// Package menu provides a Bubble Tea list based main menu that follows the dashboard design system.
package menu

import (
    "time"

    "github.com/charmbracelet/bubbles/list"
    tea "github.com/charmbracelet/bubbletea"
    "github.com/charmbracelet/lipgloss"

    "github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

type MenuItem struct {
    title string
    desc  string
    icon  string
}

func (i MenuItem) Title() string       { return i.title }
func (i MenuItem) Description() string { return i.desc }
func (i MenuItem) FilterValue() string { return i.title }

type MenuModel struct {
    list     list.Model
    theme    theme.Theme
    animDone bool
}

// NewMenuModel builds a list of top‑level commands using the token palette.
func NewMenuModel(t theme.Theme) MenuModel {
    items := []list.Item{
        MenuItem{title: "Pipeline", desc: "Career pipeline view", icon: t.Icons.Pipeline},
        MenuItem{title: "Progress", desc: "Analytics and funnel", icon: t.Icons.Progress},
        MenuItem{title: "Reports", desc: "Open a markdown report", icon: t.Icons.Report},
        MenuItem{title: "Quit", desc: "Exit the dashboard", icon: t.Icons.Quit},
    }

    // Width/height are arbitrary – the list will be resized by the parent view.
    delegate := list.NewDefaultDelegate()
    // Gradient background for the selected row – using two token colours.
    selectedStyle := lipgloss.NewStyle().
        Background(t.Token.GradientStart).
        Foreground(t.Token.GradientEnd)
    // Apply selected styles to the delegate.
    delegate.Styles.SelectedTitle = selectedStyle
    delegate.Styles.SelectedDesc = selectedStyle
    l := list.New(items, delegate, 30, 15)

    // Header uses a bold, mauve‑styled title with an icon.
    l.Title = lipgloss.NewStyle().
        Bold(true).
        Foreground(t.Token.Mauve).
        Render(t.Icons.Menu + "  MAIN MENU")


    // Normal rows use the regular text colour.
    l.Styles.Title = lipgloss.NewStyle().Foreground(t.Token.Text)

    return MenuModel{list: l, theme: t}
}

type animationMsg struct{}

// Init starts a short tick‑based animation similar to the pipeline screen.
func (m MenuModel) Init() tea.Cmd {
    return tea.Tick(time.Millisecond*50, func(t time.Time) tea.Msg { return animationMsg{} })
}

// Update handles key presses and the animation tick.
func (m MenuModel) Update(msg tea.Msg) (MenuModel, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.KeyMsg:
        switch msg.String() {
        case "q", "ctrl+c":
            return m, func() tea.Msg { return MenuQuitMsg{} }
        case "enter":
            if sel, ok := m.list.SelectedItem().(MenuItem); ok {
                return m, func() tea.Msg { return MenuSelectMsg{Command: sel.title} }
            }
        }
    case animationMsg:
        m.animDone = true
    }

    var cmd tea.Cmd
    m.list, cmd = m.list.Update(msg)
    return m, cmd
}

// View renders the menu with a consistent header/footer layout.
func (m MenuModel) View() string {
    header := m.list.Title
    body := m.list.View()
    footer := lipgloss.NewStyle().
        Foreground(m.theme.Token.Subtext).
        Render("←↑↓→ navigate • ↩ select • q quit")

    // Apply the shared padding helpers.
    header = theme.PadHorizontal(lipgloss.NewStyle()).Render(header)
    body = theme.PadHorizontal(lipgloss.NewStyle()).Render(body)
    footer = theme.PadHorizontal(lipgloss.NewStyle()).Render(footer)

    return lipgloss.JoinVertical(lipgloss.Left, header, body, footer)
}

// Messages exposed to the parent application.
type MenuSelectMsg struct{ Command string }
type MenuQuitMsg struct{}
