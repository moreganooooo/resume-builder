package theme

import (
	"testing"

	lipglossv1 "github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/log"
)

// v1hex reads a lipgloss v1 color back out as "#rrggbb". v1's Color is a
// string type, so a themed style's foreground is exactly what v1() put there
// -- and a v2 color that leaked through would not be one, which is the case
// this exists to catch.
func v1hex(col lipglossv1.TerminalColor) string {
	if c, ok := col.(lipglossv1.Color); ok {
		return string(c)
	}
	return "#000000"
}

// The same regression TestHuhThemeTitleIsNotBlack guards, on the other side of
// the version line: log v1.0.0's Styles are lipgloss **v1** styles, and a v2
// color assigned into one resolves as black rather than failing to compile.
// A nil check cannot see it, so the colors are read back out as hex.
func TestLogStylesAreThemedAndNotBlack(t *testing.T) {
	for _, name := range []string{"resume-builder", "catppuccin-mocha", "catppuccin-latte"} {
		th := NewTheme(name)
		s := th.LogStyles()

		if got := v1hex(s.Message.GetForeground()); got != ColorToHex(th.Text) {
			t.Errorf("%s: Message foreground = %s, want the theme's Text %s", name, got, ColorToHex(th.Text))
		}
		if got := v1hex(s.Levels[log.ErrorLevel].GetForeground()); got != ColorToHex(th.Red) {
			t.Errorf("%s: ERROR level = %s, want the theme's Red %s", name, got, ColorToHex(th.Red))
		}
		if got := v1hex(s.Levels[log.WarnLevel].GetForeground()); got == "#000000" {
			t.Errorf("%s: WARN level renders as black", name)
		}
	}
}

// TestLogStylesKeepTheLevelLabels is the reason only colors are overridden:
// the level tag is what a reader greps for, so its text must survive theming.
func TestLogStylesKeepTheLevelLabels(t *testing.T) {
	s := NewTheme("resume-builder").LogStyles()
	for _, level := range []log.Level{log.DebugLevel, log.InfoLevel, log.WarnLevel, log.ErrorLevel, log.FatalLevel} {
		if s.Levels[level].Value() == "" {
			t.Errorf("level %v lost its label", level)
		}
	}
}
