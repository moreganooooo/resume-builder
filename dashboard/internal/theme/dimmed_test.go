package theme

import (
	"testing"
)

// The first attempt at dimming inactive sidebar rows collapsed every span to
// a single muted token, which rendered as an unreadable wall of gray -- the
// score banding, employment tag and subtitle all mean different things, and
// flattening them lost more than the added focus was worth. Dimmed() must
// therefore move colors toward the background WITHOUT converging them.

func TestDimmedMovesEveryColorTowardTheBackground(t *testing.T) {
	th := NewTheme("catppuccin-mocha")
	d := th.Dimmed()

	baseLum := RelativeLuminance(th.Base)
	for _, tc := range []struct {
		name        string
		normal, dim interface {
			RGBA() (uint32, uint32, uint32, uint32)
		}
	}{
		{"Text", th.Text, d.Text},
		{"Green", th.Green, d.Green},
		{"Mauve", th.Mauve, d.Mauve},
		{"Blue", th.Blue, d.Blue},
		{"Yellow", th.Yellow, d.Yellow},
		{"Red", th.Red, d.Red},
		{"Peach", th.Peach, d.Peach},
		{"Sky", th.Sky, d.Sky},
		{"Pink", th.Pink, d.Pink},
	} {
		normalGap := RelativeLuminance(tc.normal) - baseLum
		dimGap := RelativeLuminance(tc.dim) - baseLum
		if normalGap <= 0 {
			continue // a color darker than Base on this theme; nothing to assert
		}
		if dimGap >= normalGap {
			t.Errorf("%s: dimmed contrast against Base (%.4f) is not lower than normal (%.4f)",
				tc.name, dimGap, normalGap)
		}
		if dimGap <= 0 {
			t.Errorf("%s: dimmed to or past the background -- it would be invisible", tc.name)
		}
		t.Logf("%-7s %s -> %s", tc.name, ColorToHex(tc.normal), ColorToHex(tc.dim))
	}
}

func TestDimmedKeepsDistinctColorsDistinct(t *testing.T) {
	th := NewTheme("catppuccin-mocha")
	d := th.Dimmed()

	// The regression this guards: every accent landing on the same value.
	seen := map[string]string{}
	for name, c := range map[string]interface {
		RGBA() (uint32, uint32, uint32, uint32)
	}{
		"Text": d.Text, "Green": d.Green, "Mauve": d.Mauve, "Blue": d.Blue,
		"Yellow": d.Yellow, "Red": d.Red, "Peach": d.Peach, "Sky": d.Sky, "Pink": d.Pink,
	} {
		hex := ColorToHex(c)
		if prev, dup := seen[hex]; dup {
			t.Errorf("%s and %s both dimmed to %s -- the palette is collapsing to one tone", prev, name, hex)
		}
		seen[hex] = name
	}
}

func TestDimmedLeavesBackgroundsAlone(t *testing.T) {
	// Backgrounds are what the text blends INTO; dimming them would move the
	// target while aiming at it.
	th := NewTheme("catppuccin-mocha")
	d := th.Dimmed()
	for _, tc := range []struct {
		name        string
		normal, dim interface {
			RGBA() (uint32, uint32, uint32, uint32)
		}
	}{
		{"Base", th.Base, d.Base},
		{"Surface", th.Surface, d.Surface},
		{"Overlay", th.Overlay, d.Overlay},
	} {
		if ColorToHex(tc.normal) != ColorToHex(tc.dim) {
			t.Errorf("%s changed: %s -> %s", tc.name, ColorToHex(tc.normal), ColorToHex(tc.dim))
		}
	}
}
