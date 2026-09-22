package screens

import (
	"fmt"
	"strings"

	tea "charm.land/bubbletea/v2"
	lipgloss "charm.land/lipgloss/v2"
	"github.com/charmbracelet/glamour"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
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
		categories:     []string{"All", "Tools", "Metrics", "Facts", "Projects", kbSkillsCategory},
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

	if m.activeCategory == kbSkillsCategory {
		// The Skills tab lists tools, not knowledge-base items; every item
		// reader on this screen goes through here, so returning nothing is
		// what keeps the cursor, the detail pane and the mouse hit-test
		// from reading an item list this tab does not have.
		return nil
	}

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
	switch msg := msg.(type) {
	case tea.MouseClickMsg:
		if m.searching {
			return m, nil
		}
		for i, cat := range m.categories {
			if zone.InBoundsClick(fmt.Sprintf("kb_cat_%d", i), msg) {
				m.activeCategory = cat
				m.cursor = 0
				return m, nil
			}
		}
		if m.activeCategory == kbSkillsCategory {
			for i := range kbSkillTools {
				if zone.InBoundsClick(fmt.Sprintf("kb_skill_%d", i), msg) {
					m.cursor = i
					return m, nil
				}
			}
			return m, nil
		}
		vis := m.visibleItems()
		for i := range vis {
			if zone.InBoundsClick(fmt.Sprintf("kb_item_%d", i), msg) {
				m.cursor = i
				return m, nil
			}
		}
		return m, nil

	case tea.MouseWheelMsg:
		vis := m.visibleItems()
		if len(vis) > 0 {
			// Button, not Y (always >= 0, the screen row -- not a delta),
			// determines wheel direction. See jobs.go's identical fix.
			switch msg.Button {
			case tea.MouseWheelUp:
				if m.cursor > 0 {
					m.cursor--
				}
			case tea.MouseWheelDown:
				if m.cursor < len(vis)-1 {
					m.cursor++
				}
			}
		}
		return m, nil

	case tea.KeyPressMsg:
		return m.handleKey(msg.String(), msg.Text)
	case tea.KeyMsg:
		return m.handleKey(msg.String(), "")
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
	case "enter":
		if m.activeCategory == kbSkillsCategory && m.cursor >= 0 && m.cursor < len(kbSkillTools) {
			tool := kbSkillTools[m.cursor]
			return m, func() tea.Msg { return KBRunToolMsg{Action: tool.action, Label: tool.label} }
		}
		return m, nil
	case "1", "2", "3", "4", "5", "6":
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
		if m.activeCategory == kbSkillsCategory {
			if m.cursor < len(kbSkillTools)-1 {
				m.cursor++
			}
			return m, nil
		}
		vis := m.visibleItems()
		if m.cursor < len(vis)-1 {
			m.cursor++
		}
		return m, nil
	case "home", "g":
		m.cursor = 0
		return m, nil
	case "end", "G":
		if m.activeCategory == kbSkillsCategory {
			m.cursor = len(kbSkillTools) - 1
			return m, nil
		}
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
		var renderedTab string
		if cat == m.activeCategory {
			renderedTab = lipgloss.NewStyle().
				Bold(true).
				Foreground(t.Base).
				Background(t.Mauve).
				Padding(0, 1).
				Render(numStr + cat)
		} else {
			renderedTab = lipgloss.NewStyle().
				Foreground(t.Subtext).
				Padding(0, 1).
				Render(numStr + cat)
		}
		tabRenders = append(tabRenders, zone.Mark(fmt.Sprintf("kb_cat_%d", i), renderedTab))
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
	if m.activeCategory == kbSkillsCategory {
		listLines = m.renderSkillsList(leftWidth)
	} else if m.activeCategory == "All" && len(vis) > 0 {
		listLines = m.renderClusteredList(t, vis, leftWidth, contentHeight)
	} else if len(vis) == 0 {
		listLines = append(listLines, lipgloss.NewStyle().Foreground(t.Overlay).Italic(true).Render("No matching items found."))
	} else {
		// One body line goes to the paginator caption once the list is
		// longer than the pane, so the window has to shrink with it --
		// otherwise the caption pushes the last row out of the border.
		listHeight := contentHeight
		if len(vis) > contentHeight {
			listHeight--
		}
		startIdx := 0
		if m.cursor >= listHeight {
			startIdx = m.cursor - listHeight + 1
		}
		endIdx := min(len(vis), startIdx+listHeight)

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
			var renderedItem string
			if selected {
				renderedItem = lipgloss.NewStyle().
					Bold(true).
					Foreground(t.Base).
					Background(t.Sky).
					Width(leftWidth).
					Render("▶ " + lineContent)
			} else {
				renderedItem = lipgloss.NewStyle().
					Foreground(t.Text).
					Width(leftWidth).
					Render("  " + lineContent)
			}
			listLines = append(listLines, zone.Mark(fmt.Sprintf("kb_item_%d", i), renderedItem))
		}

		// Same affordance the Jobs sidebar gets: a knowledge base runs to
		// hundreds of entries, and a window with no caption gives the user
		// nothing to judge how much of it they have seen.
		if pager := RenderPaginator(t, PageState{
			TotalItems:   len(vis),
			ItemsPerPage: listHeight,
			FirstItem:    startIdx,
		}, leftWidth); pager != "" {
			listLines = append(listLines, pager)
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
	if m.activeCategory == kbSkillsCategory {
		detailContent = m.renderSkillsDetail()
	} else if len(vis) > 0 && m.cursor < len(vis) {
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
	if m.activeCategory == kbSkillsCategory {
		actions = []HelpBinding{
			{Key: "↑/↓", Desc: "Select"},
			{Key: "Enter", Desc: "Run tool"},
		}
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

// renderClusteredList draws the "All" tab as a ClusterTree rather than a
// flat list with a truncated `[Cate]` badge on every row. The badge was
// the only thing carrying the grouping, so reading it meant reconstructing
// the structure line by line; the tree draws it once, and a category that
// has nearly emptied out announces itself instead of being four rows that
// happen to share a prefix.
//
// Only this tab: every other tab is already one category, where a tree
// would be a single root over a list it adds nothing to.
//
// The cursor stays an index into the ITEMS, exactly as the rest of this
// screen -- the detail pane, the mouse hit-test and the arrow keys all read
// it -- so the group rows the tree adds are translated into, and never out
// of, that numbering here.
func (m KBModel) renderClusteredList(t theme.Theme, vis []data.KBItem, width, height int) []string {
	nodes, rowItems := kbClusterNodes(m.categories, vis)

	cursorRow := 0
	for row, item := range rowItems {
		if item == m.cursor {
			cursorRow = row
			break
		}
	}

	lines := RenderClusterTree(t, nodes, cursorRow, width)

	listHeight := height
	if len(lines) > height {
		listHeight-- // the paginator caption takes a body line, as above
	}
	start := 0
	if cursorRow >= listHeight {
		start = cursorRow - listHeight + 1
	}
	end := min(len(lines), start+listHeight)

	var out []string
	for i := start; i < end; i++ {
		if item := rowItems[i]; item >= 0 {
			out = append(out, zone.Mark(fmt.Sprintf("kb_item_%d", item), lines[i]))
			continue
		}
		out = append(out, lines[i])
	}
	if pager := RenderPaginator(t, PageState{
		TotalItems:   len(lines),
		ItemsPerPage: listHeight,
		FirstItem:    start,
	}, width); pager != "" {
		out = append(out, pager)
	}
	return out
}

// kbClusterNodes groups the visible items by category and returns, beside
// the nodes, one entry per rendered row holding the index of the item that
// row draws -- or -1 for a group heading, which is not selectable.
// Categories keep the tab order they are listed in, so the tree and the
// tab bar cannot disagree about what the knowledge base contains.
func kbClusterNodes(categories []string, vis []data.KBItem) ([]ClusterNode, []int) {
	order := make([]string, 0, len(categories))
	seen := map[string]bool{}
	for _, c := range categories {
		if c == "All" || c == kbSkillsCategory {
			continue
		}
		order, seen[c] = append(order, c), true
	}
	// A category the tab bar does not name still has to be drawn: dropping
	// it would hide entries the flat list used to show.
	for _, it := range vis {
		if !seen[it.Category] {
			order, seen[it.Category] = append(order, it.Category), true
		}
	}

	var nodes []ClusterNode
	var rowItems []int
	for _, cat := range order {
		var children []ClusterNode
		var indexes []int
		for i, it := range vis {
			if it.Category == cat {
				children = append(children, ClusterNode{Label: it.Title})
				indexes = append(indexes, i)
			}
		}
		if len(children) == 0 {
			continue
		}
		nodes = append(nodes, ClusterNode{
			Label: cat, Count: len(children), HasCount: true, Children: children,
		})
		rowItems = append(rowItems, -1)
		rowItems = append(rowItems, indexes...)
	}
	return nodes, rowItems
}
