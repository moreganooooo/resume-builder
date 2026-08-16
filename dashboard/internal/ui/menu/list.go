// Package menu provides a Bubble Tea list based main menu that follows the dashboard design system.
package menu

import (
	"charm.land/bubbles/v2/list"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

type MenuItem struct {
	title string
	desc  string
	icon  string
}

func (i MenuItem) Title() string       { return i.icon + "  " + i.title }
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
		// Wording deliberately mirrors the `resume` CLI menu for the two
		// entries that genuinely overlap: "Browse & Manage Jobs" and
		// "Exit". The rest of this menu intentionally does NOT mirror the
		// CLI -- Progress and Reports have no CLI equivalent, and the CLI's
		// Build Documents has no dashboard equivalent, because these are
		// different tools for different moments (triage here, building
		// there). An audit flagged the two menus as sharing no vocabulary;
		// the fix is matching the words for the same actions, not forcing
		// the same structure onto two different jobs.
		MenuItem{title: "Jobs", desc: "Browse & Manage Jobs", icon: t.Icons.Jobs},
		MenuItem{title: "Exit", desc: "Leave the dashboard", icon: t.Icons.Quit},
	}

	// Width/height are arbitrary – the list will be resized by the parent view.
	delegate := list.NewDefaultDelegate()
	// Selected row: Mauve background against the theme's own Base as text
	// colour. Base is each theme's own background extreme (near-black for
	// resume-builder/Mocha, near-white for Latte), which clears 4.5:1+
	// against the mid-tone Mauve accent in all three palettes.
	selectedStyle := lipgloss.NewStyle().
		Bold(true).
		Background(t.Token.Mauve).
		Foreground(t.Base)
	// Apply selected styles to the delegate.
	delegate.Styles.SelectedTitle = selectedStyle
	// Show description ONLY when selected (highlighted) - gray text
	delegate.Styles.SelectedDesc = lipgloss.NewStyle().
		Foreground(t.Token.Subtext).
		Background(t.Base)
	// Unselected rows: bold white titles for primary actions, normal for others.
	// Description hidden (same color as background) when not selected.
	delegate.Styles.NormalTitle = lipgloss.NewStyle().Foreground(t.Token.Text).Bold(true)
	delegate.Styles.NormalDesc = lipgloss.NewStyle().Foreground(t.Surface).Background(t.Surface)
	l := list.New(items, delegate, 30, 15)

	// list.Model defaults every one of these to true, which renders its own
	// title/item-count/keybinding-help chrome underneath View()'s own
	// manually-built header/footer below -- doubling the "MAIN MENU" title
	// and stacking an unthemed "5 items" status line plus a second, slightly
	// inconsistent help bar on top of the real one. Filtering ("/") stays on
	// (untouched by these) since Update already guards global keys against
	// it via m.list.FilterState().
	l.SetShowTitle(false)
	l.SetShowStatusBar(false)
	l.SetShowHelp(false)
	l.SetShowPagination(false)

	// Header text (icon + title) -- styled and backgrounded at render time
	// in View(), so it can track the list's live width across resizes.
	l.Title = t.Icons.Menu + "  ✦ MAIN MENU ✧"

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
		// Handle global menu commands (q to quit, enter to select).
		// No filter state check needed since filtering isn't essential for
		// a 5-item menu and the FilterState constant doesn't exist in bubbles v1.0.0.
		switch msg.String() {
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

// View renders the menu with a consistent header/footer layout. Header and
// footer are explicitly backgrounded with the theme's Surface colour --
// every other screen (jobs.go, pipeline.go, viewer.go) does the same for
// its own header/help bars; this screen previously didn't, so the Main
// Menu (the very first screen the user sees) showed its chrome floating on
// the terminal's ambient background instead of the app's surface colour.
func (m MenuModel) View() string {
	width := m.list.Width()

	headerStyle := theme.PadHorizontal(
		lipgloss.NewStyle().
			Bold(true).
			Foreground(m.theme.Token.Mauve).
			Background(m.theme.Surface).
			Width(width),
	)
	header := headerStyle.Render(m.list.Title)

	// This screen only ever exposes 5 items (Pipeline/Progress/Reports/
	// Jobs/Quit) against the `resume` CLI's own 15 -- nothing signaled that
	// gap was intentional rather than a smaller, less-finished menu. One
	// caption line states the dashboard's actual scope: review and
	// triage what the CLI already produced, not build it from here.
	// White to match the bold white primary labels.
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
	footer := footerStyle.Render("←↑↓→ navigate • ↩ select • q quit")

	return lipgloss.JoinVertical(lipgloss.Left, header, caption, body, footer)
}

// Messages exposed to the parent application.
type MenuSelectMsg struct{ Command string }
type MenuQuitMsg struct{}
