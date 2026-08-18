package screens

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func TestViewerRebuildRenderClampsScrollOffset(t *testing.T) {
	m := ViewerModel{
		lines:        []string{"short"},
		scrollOffset: 20,
		width:        80,
		height:       20,
		theme:        theme.NewTheme("catppuccin-mocha"),
	}

	m.rebuildRender()

	maxScroll := len(m.renderedLines) - m.bodyHeight()
	if maxScroll < 0 {
		maxScroll = 0
	}
	if m.scrollOffset > maxScroll {
		t.Fatalf("expected scrollOffset <= %d after rebuild, got %d", maxScroll, m.scrollOffset)
	}
}

func TestRenderInlineElementsLeavesTrailingPunctuationUnstyled(t *testing.T) {
	match := reBareURL.FindString("Visit https://example.com.")

	if match != "https://example.com" {
		t.Fatalf("expected URL match without trailing period, got %q", match)
	}
}

func TestViewerWrapsFencedCodeLines(t *testing.T) {
	m := ViewerModel{
		lines: []string{
			"```",
			strings.Repeat("x", 40),
			"```",
		},
		width:  20,
		height: 20,
		theme:  theme.NewTheme("catppuccin-mocha"),
	}

	rendered := m.renderAll()
	maxWidth := m.width - 6
	if maxWidth < 10 {
		maxWidth = 10
	}

	if len(rendered) < 2 {
		t.Fatalf("expected fenced code to wrap into multiple lines, got %d", len(rendered))
	}
	for _, line := range rendered {
		if width := ansi.StringWidth(line); width > maxWidth {
			t.Fatalf("expected fenced code line width <= %d, got %d for %q", maxWidth, width, ansi.Strip(line))
		}
	}
}

func TestViewerRendersInlineMarkdownBeforeParagraphWrapping(t *testing.T) {
	m := ViewerModel{
		lines: []string{
			"See [documentation](https://example.com/really-long-path) before continuing.",
		},
		width:  30,
		height: 20,
		theme:  theme.NewTheme("catppuccin-mocha"),
	}

	rendered := strings.Join(m.renderAll(), "\n")
	plain := ansi.Strip(rendered)

	if strings.Contains(plain, "[") || strings.Contains(plain, "](") {
		t.Fatalf("expected rendered paragraph to hide markdown link syntax, got %q", plain)
	}
	if !strings.Contains(plain, "documentation") {
		t.Fatalf("expected rendered paragraph to keep link text, got %q", plain)
	}
}

func TestViewerEmptyContentRendersPlaceholder(t *testing.T) {
	m := ViewerModel{
		lines:  nil,
		width:  40,
		height: 10,
		theme:  theme.NewTheme("catppuccin-mocha"),
	}
	m.rebuildRender()

	if len(m.renderedLines) != 0 {
		t.Fatalf("expected zero rendered lines for empty content, got %d", len(m.renderedLines))
	}

	body := ansi.Strip(m.renderBody())
	if !strings.Contains(body, "(empty file)") {
		t.Fatalf("expected empty placeholder, got %q", body)
	}
}

func TestViewerInlineRenderingHandlesMixedTokens(t *testing.T) {
	m := ViewerModel{
		width:  60,
		height: 10,
		theme:  theme.NewTheme("catppuccin-mocha"),
	}

	rendered := m.renderInlineElementsAs(
		"start `code` mid **bold** then [link](https://example.com) end https://bare.example.com.",
		m.theme.Subtext,
	)
	plain := ansi.Strip(rendered)

	for _, want := range []string{"start ", "code", " mid ", "bold", " then ", "link", " end ", "https://bare.example.com"} {
		if !strings.Contains(plain, want) {
			t.Fatalf("expected plain output to contain %q, got %q", want, plain)
		}
	}
	for _, syntax := range []string{"`", "**", "[", "](", "](http"} {
		if strings.Contains(plain, syntax) {
			t.Fatalf("expected markdown syntax %q to be hidden, got %q", syntax, plain)
		}
	}
	if strings.HasSuffix(plain, ".") == false {
		t.Fatalf("expected trailing punctuation outside the bare URL, got %q", plain)
	}
}

func TestViewerIndentsWrappedBlockquoteLines(t *testing.T) {
	m := ViewerModel{
		width:  24,
		height: 20,
		theme:  theme.NewTheme("catppuccin-mocha"),
	}

	rendered := m.styleLine("> " + strings.Repeat("quoted ", 8))
	lines := strings.Split(ansi.Strip(rendered), "\n")

	if len(lines) < 2 {
		t.Fatalf("expected wrapped blockquote to render multiple lines, got %d", len(lines))
	}
	if !strings.HasPrefix(lines[0], "▎ ") {
		t.Fatalf("expected first blockquote line to keep border, got %q", lines[0])
	}
	if !strings.HasPrefix(lines[1], "  ") {
		t.Fatalf("expected wrapped blockquote continuation to align with text, got %q", lines[1])
	}
}

func TestViewerGlamourRendering(t *testing.T) {
	content := `# Career Report

## Summary
Experienced **Software Engineer** specializing in distributed systems.

- Delivered 40% latency reduction
- Scaled ingestion pipeline to 1M events/sec

| Skill | Level |
| --- | --- |
| Go | Expert |
| Python | Advanced |
`
	m := ViewerModel{
		rawContent: content,
		lines:      strings.Split(content, "\n"),
		width:      80,
		height:     24,
		theme:      theme.NewTheme("catppuccin-mocha"),
	}

	rendered, err := m.renderWithGlamour()
	if err != nil {
		t.Fatalf("renderWithGlamour failed: %v", err)
	}
	if len(rendered) == 0 {
		t.Fatalf("expected non-empty rendered lines from Glamour")
	}

	joined := ansi.Strip(strings.Join(rendered, "\n"))
	if !strings.Contains(joined, "Career Report") {
		t.Errorf("expected rendered output to contain 'Career Report', got: %s", joined)
	}
	if !strings.Contains(joined, "Summary") {
		t.Errorf("expected rendered output to contain 'Summary', got: %s", joined)
	}
	if !strings.Contains(joined, "Delivered 40% latency reduction") {
		t.Errorf("expected bullet point in output, got: %s", joined)
	}
}

func TestViewerNavigationAndBounds(t *testing.T) {
	content := strings.Repeat("Line of content\n\n", 50)
	m := ViewerModel{
		rawContent: content,
		lines:      strings.Split(content, "\n"),
		width:      80,
		height:     20,
		theme:      theme.NewTheme("catppuccin-mocha"),
	}
	m.rebuildRender()

	// Initial offset is 0
	if m.scrollOffset != 0 {
		t.Errorf("expected initial scrollOffset 0, got %d", m.scrollOffset)
	}

	// Down arrow / 'j' scrolls down
	m, _ = m.Update(pressKey("down"))
	if m.scrollOffset != 1 {
		t.Errorf("expected scrollOffset 1 after down key, got %d", m.scrollOffset)
	}

	// End / 'G' jumps to bottom
	m, _ = m.Update(pressKey("G"))
	maxScroll := len(m.renderedLines) - m.bodyHeight()
	if m.scrollOffset != maxScroll {
		t.Errorf("expected scrollOffset %d at bottom, got %d", maxScroll, m.scrollOffset)
	}

	// Home / 'g' jumps to top
	m, _ = m.Update(pressKey("g"))
	if m.scrollOffset != 0 {
		t.Errorf("expected scrollOffset 0 at top, got %d", m.scrollOffset)
	}

	// '?' toggles help
	m, _ = m.Update(pressKey("?"))
	if !m.showHelp {
		t.Errorf("expected showHelp true after '?'")
	}
	m, _ = m.Update(pressKey("esc"))
	if m.showHelp {
		t.Errorf("expected showHelp false after 'esc'")
	}
}

func TestViewerZeroByteAndExtremeBounds(t *testing.T) {
	// 1. Zero-byte empty content
	m := ViewerModel{
		rawContent: "",
		lines:      nil,
		width:      80,
		height:     24,
		theme:      theme.NewTheme("catppuccin-mocha"),
	}
	m.rebuildRender()
	view := m.View()
	if !strings.Contains(view, "(empty file)") && !strings.Contains(view, "empty") {
		t.Errorf("expected empty file notice in view, got: %s", view)
	}

	// 2. Extreme 0 and negative dimensions must not panic
	m.Resize(0, 0)
	m.View()

	m.Resize(-5, -10)
	m.View()

	m.Resize(10, 4)
	m.View()
}

func TestViewer_SearchAndJump(t *testing.T) {
	lines := []string{
		"Line 0 - intro",
		"Line 1 - normal",
		"Line 2 - normal",
		"Line 3 - normal",
		"Line 4 - normal",
		"Line 5 - normal",
		"Line 6 - TARGET match",
		"Line 7 - normal",
		"Line 8 - normal",
		"Line 9 - normal",
		"Line 10 - normal",
		"Line 11 - normal",
		"Line 12 - TARGET match second",
		"Line 13 - end",
		"Line 14 - end2",
		"Line 15 - end3",
	}
	m := ViewerModel{
		rawContent: strings.Join(lines, "\n"),
		lines:      lines,
		width:      80,
		height:     8,
		theme:      theme.NewTheme("catppuccin-mocha"),
	}
	m.rebuildRender()


	// Press '/' to start search
	m, _ = m.Update(pressKey("/"))
	if !m.searchActive {
		t.Fatalf("expected searchActive=true after '/'")
	}

	// Type query "TARGET"
	for _, ch := range "TARGET" {
		m, _ = m.Update(pressKey(string(ch)))
	}
	// Press Enter to commit search
	m, _ = m.Update(pressKey("enter"))

	if m.searchActive {
		t.Fatalf("expected searchActive=false after enter")
	}
	if len(m.searchMatches) != 2 {
		t.Fatalf("expected 2 matches for 'TARGET', got %d", len(m.searchMatches))
	}

	// Press 'n' to jump to next match
	m, _ = m.Update(pressKey("n"))
	if m.scrollOffset == 0 && m.searchMatches[m.searchMatchIdx] != 0 {
		// should jump to match line
		if m.scrollOffset != m.searchMatches[m.searchMatchIdx] {
			t.Errorf("expected scrollOffset %d, got %d", m.searchMatches[m.searchMatchIdx], m.scrollOffset)
		}
	}
}

