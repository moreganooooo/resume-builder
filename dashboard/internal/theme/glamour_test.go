package theme

import (
	"strings"
	"testing"

	"github.com/charmbracelet/glamour"
)

func TestGlamour_NoExtraneousPadding(t *testing.T) {
	th := NewTheme("catppuccin-mocha")
	opts := GlamourConfig(th)

	r, err := glamour.NewTermRenderer(opts...)
	if err != nil {
		t.Fatalf("glamour.NewTermRenderer failed: %v", err)
	}

	doc := "# Title\n\nThis is a paragraph with **bold** text.\n\n> Blockquote text here.\n"
	rendered, err := r.Render(doc)
	if err != nil {
		t.Fatalf("Render failed: %v", err)
	}

	if len(rendered) == 0 {
		t.Fatalf("expected non-empty rendered markdown")
	}

	// Should not have excessive trailing newlines
	lines := strings.Split(rendered, "\n")
	trailingEmpty := 0
	for i := len(lines) - 1; i >= 0; i-- {
		if strings.TrimSpace(lines[i]) == "" {
			trailingEmpty++
		} else {
			break
		}
	}
	if trailingEmpty > 2 {
		t.Errorf("expected at most 2 trailing empty lines, got %d", trailingEmpty)
	}
}
