package theme

import (
	"image/color"

	lipglossv1 "github.com/charmbracelet/lipgloss"
	"github.com/charmbracelet/log"
)

// -- Themed logging --
//
// The dashboard already logs through charmbracelet/log (main.go's warnings
// about an unreadable jobs export, the wizard's best-effort config write),
// but at the library's DEFAULT colors -- so the one part of the program that
// speaks up when something is wrong was the one part not speaking in this
// project's palette.
//
// A trap worth naming, because it is the same one theme.go's HuhTheme header
// warns about, running the other way: log v1.0.0's Styles are
// `github.com/charmbracelet/lipgloss` **v1** styles, while this package's
// tokens are `image/color.Color` values produced by lipgloss **v2**. v1's
// Foreground wants a v1 TerminalColor, so a token cannot be handed over
// directly; it is converted to a hex string here and rebuilt as a v1 color.
// Going the other way -- letting a v1 color satisfy a v2 field -- is what
// silently renders black, so this conversion is deliberately one-way and
// lives in exactly one place.

// v1 restates a theme token as a lipgloss v1 color, via the hex string both
// versions agree on. ColorToHex is the package's existing converter -- the
// same one TestHuhThemeTitleIsNotBlack uses to prove a color did not land on
// black -- so there is one definition of "this token as text".
func v1(col color.Color) lipglossv1.TerminalColor {
	return lipglossv1.Color(ColorToHex(col))
}

// LogStyles is this theme's palette as charmbracelet/log styles. The level
// tags keep the library's uppercase short labels and its bold weight -- the
// level is what a reader scans for -- and only the colors change, so a log
// line stays greppable and looks like the program that wrote it.
func (t Theme) LogStyles() *log.Styles {
	s := log.DefaultStyles()
	s.Timestamp = s.Timestamp.Foreground(v1(t.Overlay))
	s.Caller = s.Caller.Foreground(v1(t.Overlay))
	s.Prefix = s.Prefix.Foreground(v1(t.Mauve)).Bold(true)
	s.Message = s.Message.Foreground(v1(t.Text))
	s.Key = s.Key.Foreground(v1(t.Subtext))
	s.Value = s.Value.Foreground(v1(t.Text))
	s.Separator = s.Separator.Foreground(v1(t.Overlay))

	levels := map[log.Level]color.Color{
		log.DebugLevel: t.Overlay,
		log.InfoLevel:  t.Blue,
		log.WarnLevel:  t.Yellow,
		log.ErrorLevel: t.Red,
		log.FatalLevel: t.Red,
	}
	for level, col := range levels {
		s.Levels[level] = s.Levels[level].Foreground(v1(col))
	}
	return s
}

// ApplyLogStyles points the package-level logger at this theme. Called once,
// from main, before anything can log.
func (t Theme) ApplyLogStyles() {
	log.SetStyles(t.LogStyles())
}
