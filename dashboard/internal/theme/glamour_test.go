package theme

import (
	"bytes"
	"os"
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

func TestGlamourJSONMatchesDesignSystem(t *testing.T) {
	docs, err := os.ReadFile("../../../docs/DesignSystem/assets/glamour-resumebuilder.json")
	if err != nil {
		t.Skipf("design system not present: %v", err)
	}
	if !bytes.Equal(docs, resumeBuilderGlamourJSON) {
		t.Fatal("internal/theme/glamour-resumebuilder.json has drifted from docs/DesignSystem/assets -- recopy it")
	}
}

func TestResumeBuilderUsesTheDesignSystemJSON(t *testing.T) {
	cfg := styleFor(NewTheme("resume-builder"))
	if cfg.H1.Prefix != "✦ " {
		t.Errorf("H1 prefix = %q, want the JSON's \"✦ \"", cfg.H1.Prefix)
	}
	if cfg.Document.Margin == nil || *cfg.Document.Margin != 0 {
		t.Error("document margin must be zeroed for viewer.go's exact-width wrapping")
	}
	if styleFor(NewTheme("catppuccin-latte")).H1.Prefix == "✦ " {
		t.Error("Catppuccin themes must keep the palette-derived style")
	}
}
