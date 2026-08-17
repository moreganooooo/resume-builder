package theme

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"
)

func TestThemeTokensAndPalettes(t *testing.T) {
	themes := []string{"catppuccin-mocha", "catppuccin-latte", "default"}
	for _, name := range themes {
		th := NewTheme(name)
		if th.Base == nil || th.Text == nil || th.Mauve == nil || th.Blue == nil {
			t.Errorf("expected non-nil core palette colors for %s", name)
		}
	}
}

func TestColorToHex(t *testing.T) {
	th := NewTheme("catppuccin-mocha")
	hex := ColorToHex(th.Mauve)
	if !strings.HasPrefix(hex, "#") || len(hex) != 7 {
		t.Errorf("expected #rrggbb hex format, got: %s", hex)
	}
}

func TestRenderColorGradient(t *testing.T) {
	th := NewTheme("catppuccin-mocha")
	rendered := RenderColorGradient("Hello World", th.Mauve, th.Blue)
	plain := ansi.Strip(rendered)
	if plain != "Hello World" {
		t.Errorf("expected stripped text to match 'Hello World', got: %s", plain)
	}
	if rendered == "Hello World" {
		t.Errorf("expected ANSI escape sequences in rendered gradient")
	}
}

func TestRenderFlowingGradient(t *testing.T) {
	th := NewTheme("catppuccin-mocha")
	rendered1 := RenderFlowingGradient("Pipeline Active", th.Mauve, th.Blue, 0.0)
	rendered2 := RenderFlowingGradient("Pipeline Active", th.Mauve, th.Blue, 1.57)

	plain1 := ansi.Strip(rendered1)
	plain2 := ansi.Strip(rendered2)

	if plain1 != "Pipeline Active" || plain2 != "Pipeline Active" {
		t.Errorf("expected stripped text to match original")
	}

	// Different phase should yield different color sequence
	if rendered1 == rendered2 {
		t.Errorf("expected different phase to produce different ANSI color sequence")
	}
}
