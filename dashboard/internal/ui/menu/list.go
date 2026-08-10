// Package menu provides a Bubble Tea list based main menu that follows the dashboard design system.
package menu

import (
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
    list  list.Model
    theme theme.Theme
}

// NewMenuModel builds a list of top‑level commands using the token palette.
func NewMenuModel(t theme.Theme) MenuModel {
    items := []list.Item{
        MenuItem{title: "Pipeline", desc: "Career pipeline view", icon: t.Icons.Pipeline},
        MenuItem{title: "Progress", desc: "Analytics and funnel", icon: t.Icons.Progress},
        MenuItem{title: "Reports", desc: "Open a markdown report", icon: t.Icons.Report},
        MenuItem{title: "Jobs", desc: "Evaluated job postings", icon: t.Icons.Jobs},
        MenuItem{title: "Quit", desc: "Exit the dashboard", icon: t.Icons.Quit},
    }

    // Width/height are arbitrary – the list will be resized by the parent view.
    delegate := list.NewDefaultDelegate()
    // Selected row: Mauve background against the theme's own Base as text
    // colour. GradientStart/GradientEnd (BrandColor/AccentColor from
    // tokens.go) used to fill both slots -- those two hex values sit at
    // almost the same perceptual lightness (~1.03:1 contrast, WCAG AA
    // needs 4.5:1), making the currently-focused row the least readable
    // one in the entire menu, in every theme, since GradientStart/End are
    // hardcoded constants rather than per-theme tokens. Base is each
    // theme's own background extreme (near-black for resume-builder/
    // Mocha, near-white for Latte), which is exactly why pairing it
    // against the mid-tone Mauve accent clears 4.5:1+ in all three
    // palettes.
    selectedStyle := lipgloss.NewStyle().
        Bold(true).
        Background(t.Token.Mauve).
        Foreground(t.Base)
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

// Resize fills the menu to the real terminal size -- NewMenuModel's list
// is constructed at a fixed 30x15 (its own comment already says "will be
// resized by the parent view"), which never actually happened, so the
// menu rendered as a small fixed box regardless of terminal size.
func (m *MenuModel) Resize(width, height int) {
    m.list.SetSize(width, height)
}

// Init implements tea.Model. The Main Menu's launch reveal is handled one
// level up, by appModel's harmonica-spring transition in main.go (which
// covers every screen switch, including the initial launch into the menu)
// -- there's nothing left for the menu's own Init to kick off.
func (m MenuModel) Init() tea.Cmd {
    return nil
}

// Update handles key presses.
func (m MenuModel) Update(msg tea.Msg) (MenuModel, tea.Cmd) {
    switch msg := msg.(type) {
    case tea.KeyMsg:
        // While the user is typing a filter query (bubbles/list enables
        // filtering by default, bound to "/"), global commands must not
        // steal keystrokes meant for the query -- otherwise typing e.g.
        // "quit" to jump to the Quit item exits the app on the first "q"
        // instead of reaching the filter input. Same guard pipeline.go's
        // handleKey/handleSearchInput and jobs.go's Update already apply
        // for their own modal sub-states.
        if m.list.FilterState() != list.Filtering {
            switch msg.String() {
            case "q", "ctrl+c":
                return m, func() tea.Msg { return MenuQuitMsg{} }
            case "enter":
                if sel, ok := m.list.SelectedItem().(MenuItem); ok {
                    return m, func() tea.Msg { return MenuSelectMsg{Command: sel.title} }
                }
            }
        }
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
