package screens

import (
	"fmt"
	"strings"

	tea "charm.land/bubbletea/v2"
	lipgloss "charm.land/lipgloss/v2"
	"github.com/charmbracelet/glamour"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// KBCloseMsg indicates the user wants to leave the Knowledge Base explorer.
type KBCloseMsg struct {
	Quit bool
}

// KBModel represents the Knowledge Base Explorer screen.
type KBModel struct {
	theme          theme.Theme
	items          []data.KBItem
	cursor         int
	activeCategory string
	categories     []string
	searchQuery    string
	searching      bool
	width          int
	height         int
	profile        data.ProfileInfo
}

// NewKBModel creates a new Knowledge Base explorer screen model.
func NewKBModel(t theme.Theme, items []data.KBItem, width, height int) KBModel {
	return KBModel{
		theme:          t,
		items:          items,
		cursor:         0,
		activeCategory: "All",
		categories:     []string{"All", "Tools", "Metrics", "Facts", "Projects"},
		width:          width,
		height:         height,
	}
}

// WithProfile sets the active profile info for header/footer display.
func (m KBModel) WithProfile(p data.ProfileInfo) KBModel {
	m.profile = p
	return m
}

// Resize updates the dimensions of the screen.
func (m *KBModel) Resize(w, h int) {
	m.width = w
	m.height = h
}

func (m KBModel) visibleItems() []data.KBItem {
	var results []data.KBItem
	q := strings.ToLower(strings.TrimSpace(m.searchQuery))

	for _, it := range m.items {
		if m.activeCategory != "All" && it.Category != m.activeCategory {
			continue
		}
		if q != "" {
			matchTitle := strings.Contains(strings.ToLower(it.Title), q)
			matchContent := strings.Contains(strings.ToLower(it.Content), q)
			matchCategory := strings.Contains(strings.ToLower(it.Category), q)
			if !matchTitle && !matchContent && !matchCategory {
				continue
			}
		}
		results = append(results, it)
	}
	return results
}

// Update handles UI events.
func (m KBModel) Update(msg tea.Msg) (KBModel, tea.Cmd) {
	if kp, ok := msg.(tea.KeyPressMsg); ok {
		return m.handleKey(kp.String(), kp.Text)
	}
	if km, ok := msg.(tea.KeyMsg); ok {
		return m.handleKey(km.String(), "")
	}
	return m, nil
}

func (m KBModel) handleKey(keyStr, text string) (KBModel, tea.Cmd) {
	if m.searching {
		switch keyStr {
		case "esc", "escape":
			m.searching = false
			m.searchQuery = ""
			m.cursor = 0
			return m, nil
		case "enter":
			m.searching = false
			return m, nil
		case "backspace":
			if len(m.searchQuery) > 0 {
				m.searchQuery = m.searchQuery[:len(m.searchQuery)-1]
				m.cursor = 0
			}
			return m, nil
		default:
			if text != "" {
				m.searchQuery += text
				m.cursor = 0
			} else if len(keyStr) == 1 {
				m.searchQuery += keyStr
				m.cursor = 0
			}
			return m, nil
		}
	}

	keyClean := strings.ToLower(keyStr)
	switch keyClean {
	case "q":
		return m, func() tea.Msg { return KBCloseMsg{Quit: true} }
	case "esc", "escape":
		return m, func() tea.Msg { return KBCloseMsg{Quit: false} }
	case "tab", "\t":
		m.activeCategory = m.nextCategory(1)
		m.cursor = 0
		return m, nil
	case "shift+tab", "backtab":
		m.activeCategory = m.nextCategory(-1)
		m.cursor = 0
		return m, nil
	case "/":
		m.searching = true
		m.searchQuery = ""
		return m, nil
	case "1", "2", "3", "4", "5":
		idx := int(keyClean[0] - '1')
		if idx >= 0 && idx < len(m.categories) {
			m.activeCategory = m.categories[idx]
			m.cursor = 0
		}
		return m, nil
	case "up", "k":
		if m.cursor > 0 {
			m.cursor--
		}
		return m, nil
	case "down", "j":
		vis := m.visibleItems()
		if m.cursor < len(vis)-1 {
			m.cursor++
		}
		return m, nil
	case "home", "g":
		m.cursor = 0
		return m, nil
	case "end", "G":
		vis := m.visibleItems()
		if len(vis) > 0 {
			m.cursor = len(vis) - 1
		}
		return m, nil
	}

	return m, nil
}

func (m KBModel) nextCategory(dir int) string {
	for i, c := range m.categories {
		if c == m.activeCategory {
			next := (i + dir + len(m.categories)) % len(m.categories)
			return m.categories[next]
		}
	}
	return m.categories[0]
}

// View renders the full Knowledge Base explorer interface.
func (m KBModel) View() string {
	t := m.theme
	w := m.width
	if w <= 0 {
		w = 100
	}
	h := m.height
	if h <= 0 {
		h = 30
	}

	// 1. Header
	titleStyle := lipgloss.NewStyle().Bold(true).Foreground(t.Mauve)
	profileStyle := lipgloss.NewStyle().Bold(true).Foreground(t.Peach)
	subStyle := lipgloss.NewStyle().Foreground(t.Subtext)

	profileTag := ""
	if m.profile.Name != "" {
		profileTag = profileStyle.Render(fmt.Sprintf(" [Profile: %s]", m.profile.Name))
	}

	headerLeft := titleStyle.Render("✦ KNOWLEDGE BASE EXPLORER") + profileTag
	headerRight := subStyle.Render(fmt.Sprintf("%d total assets", len(m.items)))
	headerBar := lipgloss.JoinHorizontal(lipgloss.Top,
		headerLeft,
		strings.Repeat(" ", max(2, w-lipgloss.Width(headerLeft)-lipgloss.Width(headerRight)-4)),
		headerRight,
	)

	// 2. Category Tabs & Search Bar
	var tabRenders []string
	for i, cat := range m.categories {
		numStr := fmt.Sprintf("%d:", i+1)
		if cat == m.activeCategory {
			tabRenders = append(tabRenders, lipgloss.NewStyle().
				Bold(true).
				Foreground(t.Base).
				Background(t.Mauve).
				Padding(0, 1).
				Render(numStr+cat))
		} else {
			tabRenders = append(tabRenders, lipgloss.NewStyle().
				Foreground(t.Subtext).
				Padding(0, 1).
				Render(numStr+cat))
		}
	}
	tabsRow := lipgloss.JoinHorizontal(lipgloss.Top, tabRenders...)

	searchBox := ""
	if m.searching {
		searchBox = lipgloss.NewStyle().
			Foreground(t.Peach).
			Bold(true).
			Render(fmt.Sprintf(" Search: %s█", m.searchQuery))
	} else if m.searchQuery != "" {
		searchBox = lipgloss.NewStyle().
			Foreground(t.Subtext).
			Render(fmt.Sprintf(" Filter: '%s'", m.searchQuery))
	}

	navBar := lipgloss.JoinHorizontal(lipgloss.Top,
		tabsRow,
		strings.Repeat(" ", max(2, w-lipgloss.Width(tabsRow)-lipgloss.Width(searchBox)-4)),
		searchBox,
	)

	// 3. Main Content Split View (Left List / Right Details)
	vis := m.visibleItems()
	// Two 30-col-minimum panes plus border/padding/gap need ~70 columns
	// side by side; below that (e.g. the 35-col mobile floor) stack them
	// vertically instead so neither pane gets clipped or wraps its border.
	narrowLayout := w < 70
	leftWidth := max(30, min(45, w/3))
	rightWidth := max(30, w-leftWidth-6)
	contentHeight := max(10, h-8)
	if narrowLayout {
		leftWidth = max(20, w-4)
		rightWidth = leftWidth
		contentHeight = max(4, (h-10)/2)
	}

	// Render Left Item List
	var listLines []string
	if len(vis) == 0 {
		listLines = append(listLines, lipgloss.NewStyle().Foreground(t.Overlay).Italic(true).Render("No matching items found."))
	} else {
		startIdx := 0
		if m.cursor >= contentHeight {
			startIdx = m.cursor - contentHeight + 1
		}
		endIdx := min(len(vis), startIdx+contentHeight)

		for i := startIdx; i < endIdx; i++ {
			it := vis[i]
			selected := i == m.cursor

			catBadge := lipgloss.NewStyle().Foreground(t.Overlay).Render(fmt.Sprintf("[%s]", it.Category[:min(4, len(it.Category))]))
			titleTrunc := it.Title
			maxTitleLen := leftWidth - 10
			if len([]rune(titleTrunc)) > maxTitleLen {
				titleTrunc = string([]rune(titleTrunc)[:max(0, maxTitleLen-1)]) + "…"
			}

			lineContent := fmt.Sprintf("%s %s", catBadge, titleTrunc)
			if selected {
				listLines = append(listLines, lipgloss.NewStyle().
					Bold(true).
					Foreground(t.Base).
					Background(t.Sky).
					Width(leftWidth).
					Render("▶ "+lineContent))
			} else {
				listLines = append(listLines, lipgloss.NewStyle().
					Foreground(t.Text).
					Width(leftWidth).
					Render("  "+lineContent))
			}
		}
	}

	leftPane := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Surface).
		Padding(0, 1).
		Width(leftWidth).
		Height(contentHeight).
		Render(strings.Join(listLines, "\n"))

	// Render Right Markdown Detail View
	var detailContent string
	if len(vis) > 0 && m.cursor < len(vis) {
		selectedItem := vis[m.cursor]
		md := selectedItem.Content
		renderedMD, err := glamour.Render(md, "dark")
		if err == nil {
			detailContent = renderedMD
		} else {
			detailContent = md
		}
	} else {
		detailContent = lipgloss.NewStyle().Foreground(t.Overlay).Italic(true).Render("Select an item to view verified details and claims.")
	}

	rightPane := lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Surface).
		Padding(0, 1).
		Width(rightWidth).
		Height(contentHeight).
		Render(detailContent)

	var splitView string
	if narrowLayout {
		splitView = lipgloss.JoinVertical(lipgloss.Left, leftPane, rightPane)
	} else {
		splitView = lipgloss.JoinHorizontal(lipgloss.Top, leftPane, " ", rightPane)
	}

	// 4. Action Footer
	primary := []HelpBinding{
		{Key: "Tab", Desc: "Category"},
	}
	actions := []HelpBinding{
		{Key: "↑/↓", Desc: "Select"},
		{Key: "/", Desc: "Search"},
	}
	system := []HelpBinding{
		{Key: "Esc", Desc: "Back"},
		{Key: "q", Desc: "Quit"},
	}
	footer := RenderHierarchicalFooter(t, w-2, primary, actions, system)

	return lipgloss.JoinVertical(lipgloss.Left,
		headerBar,
		navBar,
		"",
		splitView,
		"",
		footer,
	)
}
