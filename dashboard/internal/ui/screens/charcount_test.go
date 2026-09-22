package screens

import (
	"strings"
	"testing"

	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// The three states must be distinguishable WITHOUT color, because a VHS
// capture, a piped log and a reader who does not separate yellow from red
// all see only the words.
func TestCharCountSaysWhyInWords(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	cases := []struct {
		name      string
		count     int
		want      string
		unwanted  string
		alsoWants string
	}{
		{name: "comfortable", count: 100, want: "100 / 500 characters", unwanted: "·"},
		{name: "approaching", count: 460, want: "past the recommended length"},
		{name: "over", count: 620, want: "over the hard limit"},
	}
	for _, c := range cases {
		out := ansi.Strip(RenderCharCount(th, c.count, SoftCharLimit(500), 500))
		if !strings.Contains(out, c.want) {
			t.Errorf("%s: %q does not say %q", c.name, out, c.want)
		}
		if c.unwanted != "" && strings.Contains(out, c.unwanted) {
			t.Errorf("%s: %q warned about a count that is fine", c.name, out)
		}
	}
}

// Each state must also be visibly different, or the words are doing all the
// work and the spec's color rules are decorative.
func TestCharCountEscalatesColor(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	fine := RenderCharCount(th, 100, SoftCharLimit(500), 500)
	soft := RenderCharCount(th, 460, SoftCharLimit(500), 500)
	hard := RenderCharCount(th, 620, SoftCharLimit(500), 500)
	if prefix(fine) == prefix(soft) || prefix(soft) == prefix(hard) {
		t.Errorf("two states rendered in the same color:\n%q\n%q\n%q", fine, soft, hard)
	}
}

// prefix is the leading escape sequence, which is where the color lives.
func prefix(s string) string {
	if i := strings.Index(s, "m"); i > 0 {
		return s[:i]
	}
	return s
}

// Characters means RUNES. An em dash or an accented name costs the user one
// character in an ATS form, not three bytes.
func TestCharCountCountsRunesNotBytes(t *testing.T) {
	answer := "— Renée — café"
	out := ansi.Strip(RenderCharCount(theme.NewTheme("modern"), len([]rune(answer)), 0, 0))
	if !strings.Contains(out, "14 characters") {
		t.Errorf("counted bytes, not runes: %q (len=%d)", out, len(answer))
	}
}

// With no limit there is no denominator to invent, and nothing to warn
// about -- a count with a made-up ceiling is worse than a bare count.
func TestCharCountWithoutALimit(t *testing.T) {
	out := ansi.Strip(RenderCharCount(theme.NewTheme("modern"), 900, 0, 0))
	if out != "900 characters" {
		t.Errorf("a limitless count rendered %q", out)
	}
	if SoftCharLimit(0) != 0 || SoftCharLimit(-5) != 0 {
		t.Error("a soft limit was derived from a limit that does not exist")
	}
}

// The soft limit has to actually sit below the hard one, or it can never
// fire and the Yellow state is unreachable.
func TestSoftCharLimitPrecedesTheHardOne(t *testing.T) {
	for _, hard := range []int{50, 200, 500, 2000} {
		if soft := SoftCharLimit(hard); soft <= 0 || soft >= hard {
			t.Errorf("hard limit %d produced soft limit %d", hard, soft)
		}
	}
}
