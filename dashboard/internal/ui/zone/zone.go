package zone

import (
	"time"

	tea "charm.land/bubbletea/v2"
	zone "github.com/lrstanley/bubblezone"
)

func init() {
	zone.NewGlobal()
	zone.SetEnabled(true)
}

// Mark wraps content in a zone identifier tag.
func Mark(id, content string) string {
	return zone.Mark(id, content)
}

// Scan scans the final rendered view string for zone markers, calculates
// coordinates, and strips markers.
//
// Bounds are published ASYNCHRONOUSLY: Scan pushes each zone onto a
// buffered channel drained by bubblezone's own worker goroutine, so a Get
// issued in the same instant can miss. That is fine in production -- Scan
// runs in View() and the only readers are mouse handlers, which run on a
// LATER event-loop iteration, milliseconds away at human click speed.
//
// Do NOT "fix" this with a sleep here. Scan is on the per-frame render
// path (the Jobs screen ticks springs at 60fps), so any wait is paid on
// every frame forever, and a sleep is a hedge rather than a guarantee
// anyway. Tests that need to Get immediately after Scan use WaitFor.
func Scan(view string) string {
	return zone.Scan(view)
}

// Get returns the published bounds for a zone, or nil if it has not been
// published yet. See Scan for why that is possible in the same instant as
// a Scan -- code that needs to read straight after one uses WaitFor.
func Get(id string) *zone.ZoneInfo {
	return zone.Get(id)
}

// WaitFor polls until the named zone has been published by the background
// worker, returning nil if it never appears within timeout.
//
// Intended for tests, which call Scan and Get back-to-back with no event
// loop in between and would otherwise be racy. Production code reads
// through InBounds and needs no wait -- see Scan.
func WaitFor(id string, timeout time.Duration) *zone.ZoneInfo {
	deadline := time.Now().Add(timeout)
	for {
		if info := zone.Get(id); info != nil && !info.IsZero() {
			return info
		}
		if time.Now().After(deadline) {
			return nil
		}
		time.Sleep(100 * time.Microsecond)
	}
}

// InBounds checks whether an (x, y) coordinate pair falls within the named zone.
func InBounds(id string, x, y int) bool {
	info := zone.Get(id)
	if info == nil || info.IsZero() {
		return false
	}
	return x >= info.StartX && x <= info.EndX && y >= info.StartY && y <= info.EndY
}

// InBoundsMouse checks whether any tea.MouseMsg (click, motion, wheel) falls within the named zone.
func InBoundsMouse(id string, msg tea.MouseMsg) bool {
	if msg == nil {
		return false
	}
	m := msg.Mouse()
	return InBounds(id, m.X, m.Y)
}

// InBoundsClick checks whether a tea.MouseClickMsg falls within the named zone.
func InBoundsClick(id string, msg tea.MouseClickMsg) bool {
	return InBounds(id, msg.X, msg.Y)
}

// InBoundsWheel checks whether a tea.MouseWheelMsg falls within the named zone.
func InBoundsWheel(id string, msg tea.MouseWheelMsg) bool {
	return InBounds(id, msg.X, msg.Y)
}
