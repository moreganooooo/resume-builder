package prompt

import (
	"fmt"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// testGrid builds n "[Tool]" options followed by 5 "[Hard Skill]" ones.
func testGrid(n int) gridModel {
	spec := Spec{Type: "grid", Message: "Pick"}
	for i := 0; i < n; i++ {
		spec.Options = append(spec.Options, Option{Label: fmt.Sprintf("[Tool] Skill %03d", i), Value: fmt.Sprint(i)})
	}
	for i := 0; i < 5; i++ {
		spec.Options = append(spec.Options, Option{Label: fmt.Sprintf("[Hard Skill] Hard %d", i), Value: fmt.Sprint("h", i)})
	}
	m := newGridModel(theme.NewTheme("resume-builder"), spec)
	next, _ := m.Update(tea.WindowSizeMsg{Width: 120, Height: 40})
	return next.(gridModel)
}

func press(m tea.Model, code rune) tea.Model {
	g := m.(gridModel)
	g.lastMove = g.lastMove.AddDate(-1, 0, 0)
	next, _ := g.Update(tea.KeyPressMsg{Code: code})
	return next
}

func TestGridSectionsAndColumnMajorOrder(t *testing.T) {
	m := testGrid(20) // 5 columns at width 120 -> 4 rows per column
	if m.cols() != 5 {
		t.Fatalf("expected 5 columns, got %d", m.cols())
	}
	if m.lines[0].header != "Tool" || m.lines[0].count != 20 {
		t.Fatalf("first line should be the Tool header, got %+v", m.lines[0])
	}
	// Down the first column, then across: row 1 col 0 is item 1, row 0 col 1 is item 4.
	if m.lines[2].cells[0] != 1 || m.lines[1].cells[1] != 4 {
		t.Fatalf("expected column-major fill, rows=%v / %v", m.lines[1].cells, m.lines[2].cells)
	}
	view := m.View().Content
	if !strings.Contains(view, "TOOLS") || !strings.Contains(view, "HARD SKILLS") {
		t.Fatal("both section headers should render")
	}
	if strings.Contains(view, "[Tool]") {
		t.Fatal("category prefix should be stripped from cells")
	}
}

func TestGridArrowNavigation(t *testing.T) {
	var model tea.Model = testGrid(20)
	model = press(model, tea.KeyDown)
	if c := model.(gridModel).cursor; c != 1 {
		t.Fatalf("down should go to next item in column, got %d", c)
	}
	model = press(model, tea.KeyRight) // same row, next column: item 5
	if c := model.(gridModel).cursor; c != 5 {
		t.Fatalf("right should move one column over, got %d", c)
	}
	for i := 0; i < 3; i++ {
		model = press(model, tea.KeyDown)
	}
	if c := model.(gridModel).cursor; c != 21 { // same column (2nd) in Hard Skills
		t.Fatalf("down past a section should land in the next section, got %d", c)
	}
}

func TestGridClickTogglesCell(t *testing.T) {
	m := testGrid(20)
	x := 1 + 1*m.colWidth() + 3 // second column
	y := gridHeaderRows + 1     // first cell row (line 1, after header)
	next, _ := m.Update(tea.MouseClickMsg{X: x, Y: y, Button: tea.MouseLeft})
	g := next.(gridModel)
	if !g.checked[4] || g.selectedCount() != 1 {
		t.Fatalf("click should toggle item 4")
	}
}

func TestGridThrottlesHeldArrow(t *testing.T) {
	var model tea.Model = testGrid(20)
	for i := 0; i < 10; i++ { // a burst, like key repeat
		model, _ = model.Update(tea.KeyPressMsg{Code: tea.KeyDown})
	}
	if c := model.(gridModel).cursor; c != 1 {
		t.Fatalf("burst should move once, cursor=%d", c)
	}
}

func TestGridFilterAndSelectAll(t *testing.T) {
	m := testGrid(200)
	m.filter = "Skill 01"
	m.applyFilter()
	next, _ := m.Update(tea.KeyPressMsg{Code: 'a', Text: "a"})
	if n := next.(gridModel).selectedCount(); n != 10 {
		t.Fatalf("select-all should respect filter, got %d", n)
	}
}
