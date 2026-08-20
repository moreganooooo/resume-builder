package screens

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func TestRenderModalOverlayCentersAndDims(t *testing.T) {
	theme := theme.NewTheme("catppuccin-mocha")

	// Create a mock background of 20 lines
	bgLines := make([]string, 20)
	for i := range bgLines {
		bgLines[i] = "Background Line text content here"
	}
	background := strings.Join(bgLines, "\n")
	content := "Modal Inner Content"

	width := 80
	height := 20

	rendered := renderModalOverlay(theme, background, content, width, height)
	lines := strings.Split(rendered, "\n")

	if len(lines) != height {
		t.Fatalf("expected output height %d, got %d", height, len(lines))
	}

	// Check if all lines are exactly width characters wide
	for idx, line := range lines {
		w := ansi.StringWidth(line)
		if w != width {
			t.Fatalf("expected line %d to have width %d, got %d (line: %q)", idx, width, w, line)
		}
	}

	// Centered startRow is 7.
	// Row index 7 should be the top border of the modal
	strippedRow7 := ansi.Strip(lines[7])
	if !strings.Contains(strippedRow7, "╭") || !strings.Contains(strippedRow7, "╮") {
		t.Fatalf("expected row 7 to contain top rounded border, got %q", strippedRow7)
	}

	// Row index 8 should contain the modal inner content "Modal Inner Content"
	strippedRow8 := ansi.Strip(lines[8])
	if !strings.Contains(strippedRow8, "Modal Inner Content") {
		t.Fatalf("expected row 8 to contain modal content, got %q", strippedRow8)
	}

	// Row index 9 should be the bottom border of the modal
	strippedRow9 := ansi.Strip(lines[9])
	if !strings.Contains(strippedRow9, "╰") || !strings.Contains(strippedRow9, "╯") {
		t.Fatalf("expected row 9 to contain bottom rounded border, got %q", strippedRow9)
	}

	// The parts of row 8 outside the modal (left col 0-8) should carry dimmed background text
	if !strings.HasPrefix(strippedRow8, "Backgrou") {
		t.Fatalf("expected left padding of row 8 to carry dimmed background prefix, got %q", strippedRow8)
	}
}

func TestToastNotification_Lifecycle(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	toast := NewToastNotification()

	if toast.Visible() {
		t.Fatalf("expected initial toast to be hidden")
	}

	toast.Show("✦", "Application submitted!", 2)
	if !toast.Visible() {
		t.Fatalf("expected toast to be visible after Show")
	}

	rendered := toast.Render(th, 80)
	if !strings.Contains(ansi.Strip(rendered), "Application submitted!") {
		t.Fatalf("expected rendered toast to contain message, got: %s", rendered)
	}

	// Advance ticks until expired
	for i := 0; i < 30; i++ {
		toast.Update()
	}
	toast.TickSecond()
	toast.TickSecond()
	toast.TickSecond()

	if toast.Visible() {
		t.Fatalf("expected toast to expire after 2 seconds")
	}
}

func TestRenderFooter_ThreeTiers(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	primary := []HelpBinding{{"Enter", "Select"}}
	actions := []HelpBinding{{"t", "Tailor"}, {"a", "Archive"}}
	system := []HelpBinding{{"?", "Help"}, {"q", "Quit"}}

	rendered := RenderHierarchicalFooter(th, 80, primary, actions, system)
	plain := ansi.Strip(rendered)

	if !strings.Contains(plain, "Enter") || !strings.Contains(plain, "Select") {
		t.Errorf("expected primary key in footer, got: %s", plain)
	}
	if !strings.Contains(plain, "Tailor") || !strings.Contains(plain, "Archive") {
		t.Errorf("expected actions in footer, got: %s", plain)
	}
	if !strings.Contains(plain, "Help") || !strings.Contains(plain, "Quit") {
		t.Errorf("expected system in footer, got: %s", plain)
	}
}

func TestWindowResize_BelowMinDimensions(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	rendered := RenderWindowResizeGuidance(72, 20, 80, 24, th)
	plain := ansi.Strip(rendered)

	if !strings.Contains(plain, "Current: 72×20") {
		t.Errorf("expected 'Current: 72×20' in guidance, got: %s", plain)
	}
	if !strings.Contains(plain, "Required: 80×24") {
		t.Errorf("expected 'Required: 80×24' in guidance, got: %s", plain)
	}
}

func TestHelpOverlay_Scrolling(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	categories := []HelpCategory{
		{Label: "Navigation", Bindings: []HelpBinding{{"j/k", "Move down/up"}, {"g/G", "Top/Bottom"}}},
		{Label: "Actions", Bindings: []HelpBinding{{"t", "Tailor resume"}, {"a", "Archive job"}}},
		{Label: "System", Bindings: []HelpBinding{{"?", "Toggle help"}, {"q", "Quit"}}},
	}
	// Small height=12 with 3 categories should render with clip/scroll indicator
	rendered := RenderHelpOverlay(th, "Jobs", categories, 80, 12)
	plain := ansi.Strip(rendered)

	if !strings.Contains(plain, "Jobs Help") {
		t.Errorf("expected header 'Jobs Help', got: %s", plain)
	}
}

func TestTruncate_UsesSingleRuneEllipsis(t *testing.T) {
	result := Truncate("VeryLongString", 8)
	if result != "VeryLon…" {
		t.Errorf("Truncate('VeryLongString', 8) = %q; want %q", result, "VeryLon…")
	}
	if ansi.StringWidth(result) != 8 {
		t.Errorf("expected width 8, got %d", ansi.StringWidth(result))
	}
}

func TestStarfield_NarrowSplit_ClampsInnerDimensions(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	// Test very small bounds (3x3), must not panic
	rendered := renderEmptyDetailPane(th, 3, 3)
	if len(rendered) == 0 {
		t.Errorf("expected non-empty rendered detail pane for narrow dimensions")
	}
}

func TestClipboard_OSC52Sequence(t *testing.T) {
	seq := FormatOSC52Copy("https://example.com/job/123")
	if !strings.HasPrefix(seq, "\x1b]52;c;") || !strings.HasSuffix(seq, "\x07") {
		t.Fatalf("expected valid OSC 52 sequence, got %q", seq)
	}
}


