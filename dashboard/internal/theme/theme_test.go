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

func TestNewMenuIcons_DefaultToNerdFont(t *testing.T) {
	// When unset, must default to Nerd Font icons (C8 fix)
	t.Setenv("RESUME_BUILDER_ICONS", "")
	icons := NewMenuIcons()
	if icons.Pipeline != "" {
		t.Errorf("expected default Pipeline icon to be Nerd Font '', got: %q", icons.Pipeline)
	}

	// When set to "unicode", must fall back to Unicode
	t.Setenv("RESUME_BUILDER_ICONS", "unicode")
	uIcons := NewMenuIcons()
	if uIcons.Pipeline != "⚙" {
		t.Errorf("expected Unicode Pipeline icon to be '⚙', got: %q", uIcons.Pipeline)
	}
}

func TestShimmerColor_PhaseShift(t *testing.T) {
	th := NewTheme("catppuccin-mocha")
	col1 := ShimmerColor(th.Mauve, th.Blue, 0.0)
	col2 := ShimmerColor(th.Mauve, th.Blue, 1.57)

	if col1 == nil || col2 == nil {
		t.Fatalf("expected non-nil shimmer colors")
	}

	hex1 := ColorToHex(col1)
	hex2 := ColorToHex(col2)

	if hex1 == hex2 {
		t.Errorf("expected different phase to produce different shimmer colors, got %s and %s", hex1, hex2)
	}
}

func TestFormatTrackedHeader(t *testing.T) {
	cases := []struct {
		input    string
		expected string
	}{
		{"PIPELINE", "✦  P I P E L I N E  ✧"},
		{"JOBS", "✦  J O B S  ✧"},
		{"", "✦  ✧"},
		{"A", "✦  A  ✧"},
	}

	for _, tc := range cases {
		actual := FormatTrackedHeader(tc.input)
		if actual != tc.expected {
			t.Errorf("FormatTrackedHeader(%q) = %q; want %q", tc.input, actual, tc.expected)
		}
	}
}

func TestTheme_WCAGContrastCompliance(t *testing.T) {
	themes := []string{"catppuccin-mocha", "catppuccin-latte"}
	for _, name := range themes {
		th := NewTheme(name)
		ratio := ContrastRatio(th.Text, th.Base)
		if ratio < 4.5 {
			t.Errorf("theme %s text contrast ratio %.2f < 4.5 against base", name, ratio)
		}
	}
}

