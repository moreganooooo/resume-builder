package screens

import (
	"strings"
	"testing"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// Success and info expire; warnings and errors wait for a keypress. An unread
// failure is worse than a crowded corner.
func TestToastStickyTonesNeverExpire(t *testing.T) {
	var s ToastStack
	s.Push(ToastSuccess, "tailored")
	s.Push(ToastError, "scan failed")

	for i := 0; i < 30; i++ {
		s.TickSecond()
	}
	if s.Empty() {
		t.Fatal("the error toast expired on its own")
	}
	if !s.HasSticky() {
		t.Fatal("the surviving toast should be the sticky one")
	}
	if got := ansi.Strip(s.Render(theme.NewTheme("modern"), 80)); strings.Contains(got, "tailored") {
		t.Errorf("the success toast should have expired, got %q", got)
	}

	if !s.DismissSticky() {
		t.Fatal("DismissSticky should report that it removed something")
	}
	if !s.Empty() {
		t.Error("the stack should be empty after dismissing the only sticky toast")
	}
	if s.DismissSticky() {
		t.Error("DismissSticky on an empty stack should not consume a keypress")
	}
}

// Three at most, oldest collapsed into a count -- so the newest toast is
// always in the same place rather than scrolling the stack.
func TestToastStackCapsAtThreeAndCountsOverflow(t *testing.T) {
	var s ToastStack
	for _, msg := range []string{"one", "two", "three", "four", "five"} {
		s.Push(ToastInfo, "%s", msg)
	}

	out := ansi.Strip(s.Render(theme.NewTheme("modern"), 80))
	for _, want := range []string{"three", "four", "five", "+2 earlier"} {
		if !strings.Contains(out, want) {
			t.Errorf("render missing %q:\n%s", want, out)
		}
	}
	for _, gone := range []string{"one", "two"} {
		if strings.Contains(out, gone) {
			t.Errorf("render kept %q past the cap of %d:\n%s", gone, toastMaxVisible, out)
		}
	}

	// The newest is on the LAST line, nearest the footer.
	lines := strings.Split(out, "\n")
	if !strings.Contains(lines[len(lines)-1], "five") {
		t.Errorf("newest toast should be on the bottom row, got %q", lines[len(lines)-1])
	}

	// Draining resets the counter, so a later burst is not haunted by it.
	s.Clear()
	s.Push(ToastInfo, "fresh")
	if got := ansi.Strip(s.Render(theme.NewTheme("modern"), 80)); strings.Contains(got, "earlier") {
		t.Errorf("overflow survived a drained stack: %q", got)
	}
}

// A toast that reflowed the layout under it would interrupt more than the
// thing it reports, so the overlay must be line-count neutral.
func TestOverlayBottomRightPreservesLineCount(t *testing.T) {
	const width = 40
	bg := strings.Repeat(strings.Repeat("x", width)+"\n", 9) + strings.Repeat("x", width)

	var s ToastStack
	s.Push(ToastSuccess, "resume tailored")
	block := s.Render(theme.NewTheme("modern"), width)

	out := OverlayBottomRight(bg, block, width, 1)
	lines := strings.Split(out, "\n")
	if len(lines) != 10 {
		t.Fatalf("overlay changed the line count: %d, want 10", len(lines))
	}
	for i, line := range lines {
		if w := lipgloss.Width(line); w > width {
			t.Errorf("line %d is %d wide, over the %d-column view", i, w, width)
		}
	}
	// One row above the last, per bottomOffset=1, and the footer row untouched.
	if !strings.Contains(ansi.Strip(lines[8]), "resume tailored") {
		t.Errorf("toast did not land one row above the bottom:\n%s", ansi.Strip(lines[8]))
	}
	if ansi.Strip(lines[9]) != strings.Repeat("x", width) {
		t.Error("the toast overwrote the footer row it was told to clear")
	}
	if !strings.HasPrefix(ansi.Strip(lines[8]), "xxxx") {
		t.Error("the covered row lost the background to its left")
	}
}

// A status change pushes its toast and reloads the pipeline in the same
// batch, and the reload builds a FRESH model -- so the stack has to be
// carried across or the confirmation is erased before it ever draws.
func TestPipelineToastSurvivesReload(t *testing.T) {
	apps := []model.CareerApplication{{Company: "Acme", Role: "Writer", Status: "applied"}}
	pm := NewPipelineModel(theme.NewTheme("catppuccin-mocha"), apps,
		model.PipelineMetrics{Total: 1}, "..", 120, 40)

	if cmd := pm.PushToast(ToastSuccess, "%s → %s", "Acme", "interview"); cmd == nil {
		t.Fatal("PushToast should return the heartbeat command")
	}
	pm = pm.WithReloadedData(apps, model.PipelineMetrics{Total: 1})

	if pm.toasts.Empty() {
		t.Fatal("the toast was dropped by the reload that follows a status change")
	}
	if got := ansi.Strip(pm.View()); !strings.Contains(got, "Acme → interview") {
		t.Errorf("reloaded view is missing the status toast:\n%s", got)
	}
}
