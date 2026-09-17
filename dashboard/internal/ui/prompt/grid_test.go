package prompt

import (
	"fmt"
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func testGrid(n int) gridModel {
	spec := Spec{Type: "grid", Message: "Pick"}
	for i := 0; i < n; i++ {
		spec.Options = append(spec.Options, Option{Label: fmt.Sprintf("[Tool] Skill %03d", i), Value: fmt.Sprint(i)})
	}
	m := newGridModel(theme.NewTheme("resume-builder"), spec)
	next, _ := m.Update(tea.WindowSizeMsg{Width: 120, Height: 30})
	return next.(gridModel)
}

func TestGridUsesMultipleColumns(t *testing.T) {
	m := testGrid(200)
	if m.cols() < 4 {
		t.Fatalf("expected >=4 columns at width 120, got %d", m.cols())
	}
	if !strings.Contains(m.View().Content, "Skill 005") {
		t.Fatal("first row should render several items")
	}
}

func TestGridClickTogglesCell(t *testing.T) {
	m := testGrid(200)
	x := 1 + 2*m.colWidth() + 3 // third column, first row
	next, _ := m.Update(tea.MouseClickMsg{X: x, Y: gridHeaderRows, Button: tea.MouseLeft})
	g := next.(gridModel)
	if !g.checked[2] || g.selectedCount() != 1 {
		t.Fatalf("click should toggle item 2, checked=%v", g.checked[:4])
	}
}

func TestGridThrottlesHeldArrow(t *testing.T) {
	m := testGrid(200)
	var model tea.Model = m
	for i := 0; i < 10; i++ { // a burst, like key repeat
		model, _ = model.Update(tea.KeyPressMsg{Code: tea.KeyRight})
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
