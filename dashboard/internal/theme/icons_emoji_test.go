package theme

import (
	"reflect"
	"testing"

	"github.com/mattn/go-runewidth"
)

// unicodeIconFields returns every glyph in the Unicode fallback set,
// keyed by its struct field name.
func unicodeIconFields(t *testing.T) map[string]string {
	t.Helper()
	t.Setenv("RESUME_BUILDER_ICONS", "unicode")
	icons := NewMenuIcons()

	v := reflect.ValueOf(icons)
	ty := v.Type()
	out := make(map[string]string, ty.NumField())
	for i := 0; i < ty.NumField(); i++ {
		if v.Field(i).Kind() != reflect.String {
			continue
		}
		out[ty.Field(i).Name] = v.Field(i).String()
	}
	return out
}

// TestUnicodeIcons_AreTextNotEmoji guards the same drift scripts/theme.py
// guards on the Python side: the Unicode fallback exists precisely for
// terminals without a Nerd Font, and emoji defeat it. They render
// double-width and full-color, which breaks Lipgloss's width math and
// ignores the theme palette entirely.
func TestUnicodeIcons_AreTextNotEmoji(t *testing.T) {
	// Text-presentation codepoints inside the dingbat/symbol blocks that
	// are legitimate picks, not emoji-by-default.
	allow := map[rune]bool{'⚙': true, '✕': true, '✦': true, '↗': true, '✎': true, '✓': true, '★': true, '⊘': true}

	inEmojiBlock := func(r rune) bool {
		switch {
		case r >= 0x1F000 && r <= 0x1FAFF:
			return true
		case r >= 0x2600 && r <= 0x27BF:
			return true
		}
		return false
	}

	for name, glyph := range unicodeIconFields(t) {
		for _, r := range glyph {
			if allow[r] {
				continue
			}
			if inEmojiBlock(r) {
				t.Errorf("icon %s = %q contains emoji U+%04X; use a text-presentation glyph", name, glyph, r)
			}
		}
	}
}

// TestUnicodeIcons_AreSingleWidth keeps every fallback glyph at one cell.
// A two-cell glyph silently shifts every column to its right, and the
// menu rows are laid out assuming one.
func TestUnicodeIcons_AreSingleWidth(t *testing.T) {
	for name, glyph := range unicodeIconFields(t) {
		if glyph == "" {
			continue
		}
		if w := runewidth.StringWidth(glyph); w != 1 {
			t.Errorf("icon %s = %q has display width %d, want 1", name, glyph, w)
		}
	}
}
