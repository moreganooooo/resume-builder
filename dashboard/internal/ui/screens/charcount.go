package screens

import (
	"fmt"

	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// -- TextEditor: the character counter --
//
// The spec's TextEditor is two halves. The numbered gutter and the `↳`
// soft-wrap marks have no host in this program (see the readme row): there
// is no multi-line prose EDITING surface, in Go or in Python. The counter
// does have one, and it was the half that mattered anyway.
//
// Two rules are carried over verbatim:
//   - CHARACTERS, not words. Cover letters and application answers are
//     truncated by ATS forms at a character count, so characters are the
//     only honest unit -- and it is runes, not bytes, or an em dash would
//     cost three of the user's characters.
//   - the count changes COLOR as it approaches the limit: Subtext, then
//     Yellow past the soft limit, then Red past the hard one, each with the
//     reason in words. Color alone is not the signal; someone reading a
//     monochrome VHS capture, or not distinguishing the two hues, still
//     gets told.
//
// Before this, answers.go rendered "chars 412/500" as plain uncolored text,
// so an answer 80 characters over the limit the form will silently cut
// looked exactly like one comfortably under it.

// softLimitRatio is where "getting close" starts. A warning that only
// arrives after the limit is already blown is an epitaph, not a warning.
const softLimitRatio = 0.9

// SoftCharLimit is the advisory threshold derived from a hard limit, or 0
// when there is no limit to be advisory about.
func SoftCharLimit(hard int) int {
	if hard <= 0 {
		return 0
	}
	return int(float64(hard) * softLimitRatio)
}

// RenderCharCount renders "412 / 500 characters" plus, when the count has
// crossed a threshold, the reason. A hard limit of 0 means none is known,
// which renders the bare count rather than an invented denominator.
func RenderCharCount(t theme.Theme, count, soft, hard int) string {
	text := fmt.Sprintf("%d characters", count)
	if hard > 0 {
		text = fmt.Sprintf("%d / %d characters", count, hard)
	}

	style := lipgloss.NewStyle().Foreground(t.Subtext)
	switch {
	case hard > 0 && count > hard:
		style = lipgloss.NewStyle().Foreground(t.Red)
		text += " · over the hard limit"
	case soft > 0 && count > soft:
		style = lipgloss.NewStyle().Foreground(t.Yellow)
		text += " · past the recommended length"
	}
	return style.Render(text)
}
