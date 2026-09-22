package screens

import (
	"fmt"
	"strings"

	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

// -- HelpBar --
//
// The design system's HelpBar: "The footer today prints every binding at
// once, so the four that matter compete with the twelve that do not." Every
// screen here did exactly that -- Jobs listed fourteen keys on one line, and
// the two that a person actually reaches for were indistinguishable from the
// twelve they do not. The short bar therefore shows at most five bindings and
// always ends with "? more", which is the contract with the `?` overlay
// (renderHelpOverlay): the bar is a reminder, the overlay is the reference.
//
// Backed by this package rather than bubbles/help deliberately. bubbles/help
// renders its own ShortHelp/FullHelp line from key.Binding values and gives no
// seam to wrap an individual binding in a zone marker, which is the whole
// point of the bar being clickable (see the design system's layout-mouse card:
// "footer keybinding hints -> fires that action"). Its model is what this
// follows; its renderer is not what this uses.

// helpBarMaxBindings is the design system's cap on the short form. Above it
// the bar stops being scannable, which is the defect it exists to fix.
const helpBarMaxBindings = 5

// helpBarMoreKey is appended to every short bar. It is the pointer to the
// full reference, so it is never one of the five.
const helpBarMoreKey = "?"

// HelpBarZonePrefix namespaces one screen's footer zones. Two screens are on
// screen at once only in the sense that one replaces the other, but zone ids
// are global, so a shared prefix would let a stale Pipeline zone answer a
// click on Jobs.
type HelpBarZonePrefix string

// RenderHelpBar renders the short footer bar: up to five bindings, then
// "? more", with the brand text right-aligned. Each binding is zone-marked so
// a click fires the same action its key does -- resolve one with
// HelpBarClicked.
//
// A binding whose Action is empty sends its Key. Set Action when the label is
// not itself typeable ("↑↓/jk" is a legend, "down" is the key the handler
// wants).
func RenderHelpBar(t theme.Theme, width int, prefix HelpBarZonePrefix, bindings []HelpBinding, brand string) string {
	style := lipgloss.NewStyle().
		Foreground(t.Blue).
		Background(t.Surface).
		Width(width).
		Padding(0, 1)

	keyStyle := lipgloss.NewStyle().Bold(true).Foreground(t.Blue).Background(t.Surface)
	descStyle := lipgloss.NewStyle().Foreground(t.Subtext).Background(t.Surface)

	shown := bindings
	if len(shown) > helpBarMaxBindings {
		shown = shown[:helpBarMaxBindings]
	}

	parts := make([]string, 0, len(shown)+1)
	for i, b := range shown {
		hint := keyStyle.Render(b.Key) + descStyle.Render(" "+b.Desc)
		parts = append(parts, zone.Mark(helpBarZoneID(prefix, i), hint))
	}
	parts = append(parts, zone.Mark(helpBarZoneID(prefix, len(shown)),
		keyStyle.Render(helpBarMoreKey)+descStyle.Render(" more")))

	keys := strings.Join(parts, "  ")
	brandText := lipgloss.NewStyle().Foreground(t.Subtext).Background(t.Surface).Render(brand)

	// Reserve 2 for Padding(0, 1)'s own columns, matching every other bar in
	// this package.
	keys, brandText, gap := fitBar(keys, brandText, width, 2, t.Surface)
	return style.Render(keys + gap + brandText)
}

// helpBarKeyMsg turns a resolved hint key back into the KeyPressMsg a screen's
// own handler already understands. Screens that keep their key handling inline
// in the Update switch (Jobs, Pipeline) have no handleKeyString to call, and
// synthesising the press is better than duplicating that switch: a click then
// travels the identical code path as the key, which is the only way the
// design system's "a click never produces a state the keyboard cannot reach"
// stays true as those handlers change.
func helpBarKeyMsg(k string) tea.KeyPressMsg {
	switch k {
	case "esc":
		return tea.KeyPressMsg{Code: tea.KeyEscape}
	case "enter":
		return tea.KeyPressMsg{Code: tea.KeyEnter}
	case "up":
		return tea.KeyPressMsg{Code: tea.KeyUp}
	case "down":
		return tea.KeyPressMsg{Code: tea.KeyDown}
	case "pgup":
		return tea.KeyPressMsg{Code: tea.KeyPgUp}
	case "pgdown":
		return tea.KeyPressMsg{Code: tea.KeyPgDown}
	case "tab":
		return tea.KeyPressMsg{Code: tea.KeyTab}
	}
	r := []rune(k)
	if len(r) == 1 {
		return tea.KeyPressMsg{Code: r[0], Text: k}
	}
	// A multi-rune key with no case above is a label that was never meant to
	// be sent -- Text alone keeps String() honest rather than inventing a Code.
	return tea.KeyPressMsg{Text: k}
}

func helpBarZoneID(prefix HelpBarZonePrefix, i int) string {
	return fmt.Sprintf("%s_help_%d", prefix, i)
}

// HelpBarClicked reports which binding a mouse message landed on, returning
// the key string to feed to the screen's own key handler. The trailing
// "? more" hint resolves to "?", so clicking it opens the overlay exactly as
// typing it does -- a click never reaches a state the keyboard cannot.
func HelpBarClicked(prefix HelpBarZonePrefix, bindings []HelpBinding, msg tea.MouseMsg) (string, bool) {
	shown := bindings
	if len(shown) > helpBarMaxBindings {
		shown = shown[:helpBarMaxBindings]
	}
	for i, b := range shown {
		if zone.InBoundsMouse(helpBarZoneID(prefix, i), msg) {
			if b.Action != "" {
				return b.Action, true
			}
			return b.Key, true
		}
	}
	if zone.InBoundsMouse(helpBarZoneID(prefix, len(shown)), msg) {
		return helpBarMoreKey, true
	}
	return "", false
}
