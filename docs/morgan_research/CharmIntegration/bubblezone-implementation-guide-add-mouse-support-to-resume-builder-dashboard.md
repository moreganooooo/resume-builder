# 🖱️ Bubblezone Implementation Guide

*Step-by-step guide to add mouse support to your resume-builder dashboard*

> **This is the #1 critical gap preventing Crush-level interactivity.** Adding Bubblezone will transform your dashboard with clickable rows, tabs, and scrollable content.

## Why Bubblezone?

Bubblezone adds **mouse area detection** to Bubble Tea applications. It enables:
- Clickable pipeline rows (select with mouse)
- Clickable filter tabs (switch with mouse)
- Clickable status picker dropdown
- Scrollable viewer with mouse wheel
- Clickable help overlay elements

**Current state**: Your dashboard is keyboard-only. After this: Full mouse + keyboard support like Crush!

---

## Step 1: Add Bubblezone Dependency

```bash
cd /home/user/resume-builder/dashboard
go get github.com/lrstanley/bubblezone
```

**Verify it's in go.mod:**
```
require github.com/lrstanley/bubblezone v0.19.0
```

---

## Step 2: Create a Zone Manager

Create a new file: `dashboard/internal/ui/zone/manager.go`

```go
package zone

import (
	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbletea"
	"github.com/lrstanley/bubblezone"
)

// Manager handles mouse zones for the application
type Manager struct {
	zone *bubblezone.Zone
	// Track which UI elements are clickable
	pipelineRowZones map[int]string // row index -> zone ID
	filterTabZones    map[string]string // tab name -> zone ID
	statusPickerZone string
	viewerZone       string
	hasMouseSupport   bool
}

// New creates a new zone manager
func New() *Manager {
	return &Manager{
		zone:               bubblezone.New(),
		pipelineRowZones:   make(map[int]string),
		filterTabZones:     make(map[string]string),
		hasMouseSupport:    true,
	}
}

// UpdateZones regenerates all zones based on current UI state
func (m *Manager) UpdateZones(
	pipelineRows int,
	filterTabs []string,
	pipelineList *list.Model,
	viewerWidth, viewerHeight int,
) {
	m.zone.Clear()
	
	// Add zones for pipeline rows
	for i := 0; i < pipelineRows; i++ {
		zoneID := "pipeline-row-" + string(rune(i+'0'))
		m.pipelineRowZones[i] = zoneID
		// Calculate position based on list item
		m.zone.AddZone(zoneID, bubblezone.NewZone(
			pipelineList.Width-4, // width
			1,                   // height (1 row)
			2,                   // x offset
			2+i,                 // y offset (start at row 2)
		))
	}
	
	// Add zones for filter tabs
	for i, tab := range filterTabs {
		zoneID := "tab-" + tab
		m.filterTabZones[tab] = zoneID
		// Tabs are typically at the top, calculate x based on tab position
		tabWidth := 10 // adjust based on your actual tab width
		m.zone.AddZone(zoneID, bubblezone.NewZone(
			tabWidth,
			1,
			2+i*tabWidth,
			0, // top row
		))
	}
	
	// Add zone for status picker
	m.statusPickerZone = "status-picker"
	m.zone.AddZone(m.statusPickerZone, bubblezone.NewZone(
		20, // width
		5,  // height (dropdown)
		10, // x
		2,  // y
	))
	
	// Add zone for viewer
	m.viewerZone = "viewer"
	m.zone.AddZone(m.viewerZone, bubblezone.NewZone(
		viewerWidth,
		viewerHeight,
		0,
		0,
	))
}

// GetZone returns the zone manager for rendering
func (m *Manager) GetZone() *bubblezone.Zone {
	return m.zone
}

// HandleMouseEvent processes mouse messages and returns actions
func (m *Manager) HandleMouseEvent(msg tea.MouseMsg) (action string, rowIndex int, tabName string) {
	if !m.hasMouseSupport {
		return "", -1, ""
	}
	
	// Check if mouse is in any zone
	zoneID, ok := m.zone.Contains(msg)
	if !ok {
		return "", -1, ""
	}
	
	// Handle click based on zone type
	if msg.Type == tea.MouseLeftClick {
		// Check pipeline row zones
		for idx, zoneID := range m.pipelineRowZones {
			if zoneID == zoneID {
				return "select-row", idx, ""
			}
		}
		
		// Check filter tab zones
		for tab, zoneID := range m.filterTabZones {
			if zoneID == zoneID {
				return "select-tab", -1, tab
			}
		}
		
		// Check other zones
		switch zoneID {
		case m.statusPickerZone:
			return "toggle-status-picker", -1, ""
		case m.viewerZone:
			return "viewer-click", -1, ""
		}
	}
	
	// Handle scroll wheel in viewer
	if msg.Type == tea.MouseScrollDown && zoneID == m.viewerZone {
		return "viewer-scroll-down", -1, ""
	}
	if msg.Type == tea.MouseScrollUp && zoneID == m.viewerZone {
		return "viewer-scroll-up", -1, ""
	}
	
	return "", -1, ""
}

// DisableMouseSupport disables mouse zone detection
func (m *Manager) DisableMouseSupport() {
	m.hasMouseSupport = false
}

// EnableMouseSupport enables mouse zone detection
func (m *Manager) EnableMouseSupport() {
	m.hasMouseSupport = true
}
```

---

## Step 3: Integrate Zone Manager into Main Application

Modify `dashboard/main.go` or your root TUI model:

```go
// Add import
import "github.com/lrstanley/bubblezone"

// Add to your model struct
type model struct {
	// ... existing fields
	zoneManager *zone.Manager
	mouseEnabled bool
}

// In your initial model creation
func initialModel() model {
	m := model{
		// ... existing initialization
		zoneManager:   zone.New(),
		mouseEnabled:  true,
	}
	return m
}

// Update your Update function to handle mouse events
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	
	switch msg := msg.(type) {
	case tea.MouseMsg:
		action, rowIndex, tabName := m.zoneManager.HandleMouseEvent(msg)
		
		switch action {
		case "select-row":
			// Handle row selection
			m.pipelineList.Select(rowIndex)
			// Trigger the same action as keyboard Enter
			return m, tea.Batch(
				// Your existing row selection command
			)
			
		case "select-tab":
			// Handle tab selection
			m.activeFilter = tabName
			m.updatePipeline()
			return m, nil
			
		case "toggle-status-picker":
			// Toggle status picker visibility
			m.statusPickerOpen = !m.statusPickerOpen
			return m, nil
			
		case "viewer-scroll-down":
			// Scroll viewer down
			m.viewer.ScrollDown()
			return m, nil
			
		case "viewer-scroll-up":
			// Scroll viewer up
			m.viewer.ScrollUp()
			return m, nil
		}
		
		// If we didn't handle it, pass to other handlers
		fallthrough
		
	default:
		// Handle other messages
		}
		
	// ... rest of your Update logic
	
	return m, cmd
}

// Update your View function to include zone rendering
func (m model) View() string {
	// Update zones before rendering
	m.zoneManager.UpdateZones(
		m.pipelineList.Length(),
		[]string{"All", "Recent", "Archived"}, // your filter tabs
		&m.pipelineList,
		m.viewer.Width,
		m.viewer.Height,
	)
	
	// Render your UI as before
	view := m.renderUI() // your existing render function
	
	// Add zone debug overlay (optional, for development)
	if m.mouseEnabled {
		view = m.zoneManager.GetZone().Render(view)
	}
	
	return view
}
```

---

## Step 4: Update Pipeline View (Example)

Modify your pipeline rendering to work with zones:

```go
// In your pipeline rendering function
func (m model) renderPipeline() string {
	var sb strings.Builder
	
	// Add header
	sb.WriteString("Pipeline\n")
	
	// Render each row with zone awareness
	for i, item := range m.pipelineList.Items() {
		// Get the row content
		rowContent := m.renderPipelineRow(item, i)
		
		// If mouse is enabled, the zone manager will handle clicks
		// The zone IDs are already registered in UpdateZones
		sb.WriteString(rowContent)
	}
	
	return sb.String()
}

// For better UX, add visual feedback on hover
func (m model) renderPipelineRow(item list.Item, index int) string {
	// Check if mouse is hovering over this row
	zoneID := "pipeline-row-" + string(rune(index+'0'))
	isHovered := m.zoneManager.GetZone().IsInZone(zoneID, m.lastMousePos)
	
	// Apply different style if hovered
	style := m.theme.PipelineRow
	if isHovered {
		style = m.theme.PipelineRowHover // Make sure this exists in your theme
	}
	
	// Render the row
	return style.Render("▶ " + item.Title())
}

// Track mouse position in your Update function
func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.MouseMsg:
		m.lastMousePos = msg // Store for hover detection
		// ... rest of mouse handling
	}
	// ...
}
```

---

## Step 5: Add Hover Styles to Theme

Update `dashboard/internal/theme/resumebuilder.go`:

```go
// Add to your Theme struct
type Theme struct {
	// ... existing fields
	
	// Mouse interaction styles
	PipelineRowHover    lipgloss.Style
	TabHover            lipgloss.Style
	StatusPickerHover   lipgloss.Style
	ViewerHover         lipgloss.Style
	
	// Active/selected states for mouse
	PipelineRowActive  lipgloss.Style
	TabActive           lipgloss.Style
}

// In your NewTheme function, add hover styles
func NewTheme(cp catppuccin.Palette) Theme {
	t := Theme{
		// ... existing theme initialization
		
		PipelineRowHover: lipgloss.NewStyle()
			.Foreground(cp.Lavender)
			.Background(cp.Surface)
			.Bold(true),
			
		TabHover: lipgloss.NewStyle()
			.Foreground(cp.Pink)
			.Underline(true),
			
		StatusPickerHover: lipgloss.NewStyle()
			.Foreground(cp.Mauve)
			.Background(cp.Crust),
			
		PipelineRowActive: lipgloss.NewStyle()
			.Foreground(cp.Text)
			.Background(cp.Blue)
			.Bold(true),
			
		TabActive: lipgloss.NewStyle()
			.Foreground(cp.Lavender)
			.Background(cp.Surface)
			.Underline(true),
	}
	
	return t
}
```

---

## Step 6: Handle Mouse in Specific Components

### Pipeline Component

```go
// In your pipeline update logic
func (m *model) handlePipelineInput(msg tea.Msg) tea.Cmd {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		// Existing keyboard handling
		switch msg.String() {
		case "enter":
			// Select row
			return m.selectPipelineRow(m.pipelineList.Index())
		}
		
	case tea.MouseMsg:
		// Mouse handling
		action, rowIndex, _ := m.zoneManager.HandleMouseEvent(msg)
		if action == "select-row" && rowIndex >= 0 {
			m.pipelineList.Select(rowIndex)
			return m.selectPipelineRow(rowIndex)
		}
	}
	
	return nil
}
```

### Filter Tabs Component

```go
// In your tab rendering
func (m model) renderFilterTabs() string {
	tabs := []string{"All", "Recent", "Archived"}
	var sb strings.Builder
	
	for i, tab := range tabs {
		zoneID := "tab-" + tab
		isActive := tab == m.activeFilter
		isHovered := m.zoneManager.GetZone().IsInZone(zoneID, m.lastMousePos)
		
		style := m.theme.Tab
		if isActive {
			style = m.theme.TabActive
		} else if isHovered {
			style = m.theme.TabHover
		}
		
		sb.WriteString(style.Render(tab))
		if i < len(tabs)-1 {
			sb.WriteString(" ")
		}
	}
	
	return sb.String()
}
```

### Status Picker Component

```go
// In your status picker handling
func (m *model) handleStatusPicker(msg tea.Msg) tea.Cmd {
	switch msg := msg.(type) {
	case tea.MouseMsg:
		action, _, _ := m.zoneManager.HandleMouseEvent(msg)
		if action == "toggle-status-picker" {
			m.statusPickerOpen = !m.statusPickerOpen
			return nil
		}
		
		// Handle clicks on status options
		for i, status := range m.statusOptions {
			zoneID := "status-option-" + strconv.Itoa(i)
			if m.zoneManager.GetZone().IsInZone(zoneID, msg) && msg.Type == tea.MouseLeftClick {
				m.selectedStatus = status
				m.statusPickerOpen = false
				return m.applyStatusFilter()
			}
		}
	}
	
	return nil
}

// Update your UpdateZones to include status options
func (m *Manager) UpdateZones(
	// ... existing params
	statusOptions []string,
) {
	// ... existing zone setup
	
	// Add zones for status options
	for i, status := range statusOptions {
		zoneID := "status-option-" + strconv.Itoa(i)
		m.zone.AddZone(zoneID, bubblezone.NewZone(
			20, // width
			1,  // height
			10, // x
			4+i, // y (start below picker header)
		))
	}
}
```

### Viewer Component

```go
// Handle mouse scroll in viewer
func (m *model) handleViewerInput(msg tea.Msg) tea.Cmd {
	switch msg := msg.(type) {
	case tea.MouseMsg:
		action, _, _ := m.zoneManager.HandleMouseEvent(msg)
		
		switch action {
		case "viewer-scroll-down":
			m.viewer.ScrollDown()
			return nil
			
		case "viewer-scroll-up":
			m.viewer.ScrollUp()
			return nil
			
		case "viewer-click":
			// Handle click on links or interactive elements
			if m.viewer.HasLinkAtPosition(msg.X, msg.Y) {
				return m.openLink(m.viewer.GetLinkAtPosition(msg.X, msg.Y))
			}
		}
	}
	
	return nil
}
```

---

## Step 7: Add Mouse Support to Help Overlay

```go
// In your help overlay rendering
func (m model) renderHelpOverlay() string {
	if !m.helpOpen {
		return ""
	}
	
	// Create a semi-transparent overlay
	overlay := m.theme.HelpOverlay
	
	// Add close button zone
	closeZoneID := "help-close"
	m.zoneManager.GetZone().AddZone(closeZoneID, bubblezone.NewZone(
		10, // width of "[Close]"
		1,
		m.width-12, // right-aligned
		2,         // top
	))
	
	// Check if mouse is over close button
	isCloseHovered := m.zoneManager.GetZone().IsInZone(closeZoneID, m.lastMousePos)
	
	closeStyle := m.theme.HelpClose
	if isCloseHovered {
		closeStyle = m.theme.HelpCloseHover
	}
	
	helpContent := `
` + m.theme.HelpTitle.Render("Help") + `

` +
		m.theme.HelpText.Render("Press ? to toggle help\n") +
		m.theme.HelpText.Render("Use arrow keys or mouse to navigate\n") +
		m.theme.HelpText.Render("Press Enter or click to select\n") +
		closeStyle.Render("[Close]")
	
	return overlay.Render(helpContent)
}

// Handle help close with mouse
func (m *model) handleHelpInput(msg tea.Msg) tea.Cmd {
	switch msg := msg.(type) {
	case tea.MouseMsg:
		if m.helpOpen {
			zoneID := "help-close"
			if m.zoneManager.GetZone().IsInZone(zoneID, msg) && msg.Type == tea.MouseLeftClick {
				m.helpOpen = false
				return nil
			}
			
			// Click anywhere else to close
			return nil
		}
		
		// Handle ? key to open help (keyboard)
		if msg.String() == "?" {
			m.helpOpen = !m.helpOpen
			return nil
		}
	}
	
	return nil
}
```

---

## Step 8: Update Go Mod and Verify

```bash
# Update dependencies
cd /home/user/resume-builder/dashboard
go mod tidy

# Build and test
go build ./...

# Run the dashboard
./dashboard
```

**Test mouse interactions:**
- [ ] Click on pipeline rows
- [ ] Click on filter tabs
- [ ] Click on status picker
- [ ] Scroll viewer with mouse wheel
- [ ] Click help overlay close button
- [ ] Hover over interactive elements (should show visual feedback)

---

## Step 9: Add Mouse Detection and Fallback

For terminals that don't support mouse:

```go
// In your initial model creation
func initialModel() model {
	// Check if terminal supports mouse
	mouseSupported := termenv.HasMouseSupport()
	
	m := model{
		// ... existing initialization
		zoneManager:   zone.New(),
		mouseEnabled:  mouseSupported,
	}
	
	return m
}

// Add a warning if mouse isn't supported
func (m model) View() string {
	if !m.mouseEnabled && m.showMouseWarning {
		return m.theme.Warning.Render("⚠️  Mouse not supported in this terminal. Use keyboard navigation.") + "\n\n" + m.renderUI()
	}
	
	return m.renderUI()
}
```

---

## Step 10: Clean Up and Optimize

### Remove Debug Zone Visualization

Once you're confident everything works, remove the debug overlay:

```go
// In your View function, change:
// view = m.zoneManager.GetZone().Render(view)
// to just:
return view
```

### Optimize Zone Updates

Only update zones when UI state changes:

```go
// In your model struct
type model struct {
	// ...
	zonesNeedUpdate bool
}

// Set flag when UI changes
func (m *model) updatePipeline() {
	m.pipelineItems = getPipelineItems(m.activeFilter)
	m.zonesNeedUpdate = true
}

// In View function
func (m model) View() string {
	if m.zonesNeedUpdate && m.mouseEnabled {
		m.zoneManager.UpdateZones(
			m.pipelineList.Length(),
			[]string{"All", "Recent", "Archived"},
			&m.pipelineList,
			m.viewer.Width,
			m.viewer.Height,
			m.statusOptions,
		)
		m.zonesNeedUpdate = false
	}
	
	return m.renderUI()
}
```

---

## Complete Example: Modified main.go Structure

Here's how your main file might look after integration:

```go
package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/charmbracelet/bubbles/list"
	"github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
	"github.com/lrstanley/bubblezone"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

type model struct {
	// UI Components
	pipelineList    list.Model
	viewer          *Viewer // your custom viewer
	statusPicker    *StatusPicker
	
	// State
	activeFilter    string
	statusOptions   []string
	selectedStatus  string
	statusPickerOpen bool
	helpOpen        bool
	
	// Mouse support
	zoneManager     *zone.Manager
	mouseEnabled    bool
	lastMousePos    tea.MouseMsg
	zonesNeedUpdate bool
	
	// Theme
	theme theme.Theme
	
	// Dimensions
	width, height int
}

func initialModel() model {
	// Initialize theme
	t := theme.New()
	
	// Initialize components
	pipelineList := list.New([]list.Item{}, list.NewDefaultDelegate(), 0, 0)
	pipelineList.SetShowStatusBar(false)
	pipelineList.SetFilteringEnabled(false)
	
	// Check mouse support
	mouseSupported := true // Add actual detection
	
	return model{
		pipelineList:    pipelineList,
		viewer:          NewViewer(),
		statusPicker:    NewStatusPicker(),
		activeFilter:    "All",
		statusOptions:   []string{"Active", "Pending", "Completed"},
		statusPickerOpen: false,
		helpOpen:        false,
		zoneManager:     zone.New(),
		mouseEnabled:    mouseSupported,
		zonesNeedUpdate: true,
		theme:          t,
	}
}

func (m model) Init() tea.Cmd {
	return nil
}

func (m model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		m.zonesNeedUpdate = true
		
	case tea.MouseMsg:
		m.lastMousePos = msg
		
		// Handle mouse events
		action, rowIndex, tabName := m.zoneManager.HandleMouseEvent(msg)
		
		switch action {
		case "select-row":
			if rowIndex >= 0 && rowIndex < m.pipelineList.Length() {
				m.pipelineList.Select(rowIndex)
				return m, m.selectPipelineRow(rowIndex)
			}
			
		case "select-tab":
			m.activeFilter = tabName
			m.updatePipeline()
			return m, nil
			
		case "toggle-status-picker":
			m.statusPickerOpen = !m.statusPickerOpen
			m.zonesNeedUpdate = true
			return m, nil
			
		case "viewer-scroll-down":
			m.viewer.ScrollDown()
			return m, nil
			
		case "viewer-scroll-up":
			m.viewer.ScrollUp()
			return m, nil
			
		case "help-close":
			m.helpOpen = false
			return m, nil
		}
		
		// If mouse moved, we might need to redraw for hover effects
		if msg.Type == tea.MouseMotion {
			return m, nil
		}
		
		fallthrough
		
	case tea.KeyMsg:
		// Handle keyboard
		switch msg.String() {
		case "q", "ctrl+c":
			return m, tea.Quit
			
		case "?":
			m.helpOpen = !m.helpOpen
			return m, nil
			
		case "enter":
			// Handle enter key for selected item
			if m.pipelineList.FilterState() == list.Filtering {
				break
			}
			return m, m.selectPipelineRow(m.pipelineList.Index())
			
		case "tab":
			// Cycle through filter tabs
			m.cycleFilterTabs()
			m.updatePipeline()
			return m, nil
			
		case "s":
			// Toggle status picker
			m.statusPickerOpen = !m.statusPickerOpen
			m.zonesNeedUpdate = true
			return m, nil
			
		case "up", "down":
			// Handle keyboard navigation
			if m.statusPickerOpen {
				// Handle status picker navigation
				return m.handleStatusPickerKeyboard(msg)
			}
			// Handle pipeline navigation
			var cmd tea.Cmd
			m.pipelineList, cmd = m.pipelineList.Update(msg)
			return m, cmd
		}
	}
	}
	
	// Update components
	var cmd2 tea.Cmd
	m.pipelineList, cmd2 = m.pipelineList.Update(msg)
	cmd = tea.Batch(cmd, cmd2)
	
	return m, cmd
}

func (m model) View() string {
	// Update zones if needed
	if m.zonesNeedUpdate && m.mouseEnabled {
		m.zoneManager.UpdateZones(
			m.pipelineList.Length(),
			[]string{"All", "Recent", "Archived"},
			&m.pipelineList,
			m.viewer.Width,
			m.viewer.Height,
			m.statusOptions,
		)
		m.zonesNeedUpdate = false
	}
	
	// Build the view
	var sb strings.Builder
	
	// Header
	sb.WriteString(m.renderHeader())
	
	// Filter tabs
	sb.WriteString(m.renderFilterTabs())
	
	// Pipeline
	sb.WriteString(m.renderPipeline())
	
	// Status picker (if open)
	if m.statusPickerOpen {
		sb.WriteString(m.renderStatusPicker())
	}
	
	// Viewer
	sb.WriteString(m.renderViewer())
	
	// Help overlay
	if m.helpOpen {
		sb.WriteString(m.renderHelpOverlay())
	}
	
	// Mouse warning
	if !m.mouseEnabled && m.showMouseWarning {
		sb.WriteString(m.theme.Warning.Render("⚠️  Mouse not supported. Use keyboard."))
	}
	
	// Add zone rendering for mouse support
	if m.mouseEnabled {
		return m.zoneManager.GetZone().Render(sb.String())
	}
	
	return sb.String()
}

func main() {
	p := tea.NewProgram(initialModel())
	
	// Enable mouse cell motion events
	p.EnableMouseCellMotion()
	
	if _, err := p.Run(); err != nil {
		fmt.Printf("Error: %v\n", err)
		os.Exit(1)
	}
}
```

---

## Troubleshooting

### Mouse Events Not Working

1. **Check terminal support**: Not all terminals support mouse events
   ```bash
   # Test if your terminal supports mouse
   printf '\e[?1000h'  # Enable mouse tracking
   ```

2. **Enable mouse cell motion**: Make sure you call `p.EnableMouseCellMotion()`

3. **Check Bubblezone version**: Use v0.19.0 or later
   ```bash
   go get github.com/lrstanley/bubblezone@v0.19.0
   ```

4. **Verify zone positions**: Use debug rendering to see zone boundaries:
   ```go
   // In View():
   if m.mouseEnabled {
		return m.zoneManager.GetZone().RenderWithDebug(sb.String())
	}
   ```

### Zone Detection Not Working

1. **Check zone IDs**: Make sure zone IDs match between registration and checking
2. **Check coordinates**: Zone coordinates are relative to the entire view
3. **Check layering**: Zones on top will capture clicks first

### Performance Issues

1. **Reduce zone updates**: Only update zones when UI state changes
2. **Simplify zones**: Use larger zones for groups of items when possible
3. **Disable debug rendering**: Remove debug overlay in production

---

## Final Checklist

Before considering this complete:

- [ ] Bubblezone added to go.mod
- [ ] Zone manager created and integrated
- [ ] Pipeline rows clickable
- [ ] Filter tabs clickable
- [ ] Status picker clickable
- [ ] Viewer scrollable with mouse wheel
- [ ] Help overlay close button clickable
- [ ] Hover effects working
- [ ] Keyboard navigation still works
- [ ] Mouse fallback for non-supported terminals
- [ ] All zones properly sized and positioned
- [ ] No debug rendering in production

---

## Next Steps After Bubblezone

Once Bubblezone is integrated, consider these minor optimizations:

1. **Make colorprofile a direct dependency** (1 hour, low impact)
2. **Add contrast ratio checking** to your color linter (1-2 days, low impact)
3. **Consider two-way theme sync** (Go → Python) (2-3 days, low impact)

But **Bubblezone is the only critical gap** - everything else is already excellent!

---

## Resources

- [Bubblezone GitHub](https://github.com/lrstanley/bubblezone)
- [Bubblezone Documentation](https://pkg.go.dev/github.com/lrstanley/bubblezone)
- [Bubble Tea Mouse Support](https://github.com/charmbracelet/bubbletea#mouse-support)
- [Charmbracelet Crush](https://github.com/charmbracelet/crush) - Reference for "shockingly beautiful" TUI

---

**🎉 Congratulations!** Once you complete this guide, your dashboard will have Crush-level mouse interactivity and be truly "shockingly beautiful"! 🖱️✨