package screens

import (
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func pipelineOnTab(apps []model.CareerApplication, filter string) *PipelineModel {
	idx := 0
	for i, tab := range pipelineTabs {
		if tab.filter == filter {
			idx = i
		}
	}
	m := &PipelineModel{
		theme:     theme.NewTheme("catppuccin-mocha"),
		apps:      apps,
		activeTab: idx,
		sortMode:  sortScore,
		viewMode:  "flat",
	}
	m.applyFilterAndSort()
	return m
}

func pipelineHas(m *PipelineModel, company string) bool {
	for _, app := range m.filtered {
		if app.Company == company {
			return true
		}
	}
	return false
}

// Pipeline, unlike Browse & Manage Jobs, holds live applications, so the
// actionable bar here is deliberately NOT a blanket score test. These are
// the three rows whose handling differs, pinned because getting any of
// them wrong hides something the user is actively working on.
func TestPipelineActionableBarSparesAnythingActedOn(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Passed", Status: "Evaluated", Score: ActionableScore - 0.1},
		{Company: "Applied", Status: "Applied", Score: ActionableScore - 0.1},
		{Company: "Interviewing", Status: "Interview", Score: 1.2},
		{Company: "Rejected", Status: "Rejected", Score: 1.0},
		{Company: "Unevaluated", Status: "Evaluated"}, // no score at all
		{Company: "Strong", Status: "Evaluated", Score: 4.6},
	}

	all := pipelineOnTab(apps, filterAll)
	if pipelineHas(all, "Passed") {
		t.Error("ALL must hide a scored, un-acted-on role below the bar")
	}
	for _, keep := range []string{"Applied", "Interviewing", "Rejected", "Strong"} {
		if !pipelineHas(all, keep) {
			t.Errorf("ALL dropped %q -- a role that was acted on must never be hidden by the bar", keep)
		}
	}
	// An unevaluated role scores 0, which is below the bar arithmetically
	// but means "not triaged yet", not "not worth acting on".
	if !pipelineHas(all, "Unevaluated") {
		t.Error("ALL hid an unevaluated role; the bar must only apply to rows that carry a score")
	}

	evaluated := pipelineOnTab(apps, filterEvaluated)
	if pipelineHas(evaluated, "Passed") {
		t.Error("EVALUATED must hide a scored role below the bar")
	}
	if !pipelineHas(evaluated, "Strong") {
		t.Error("EVALUATED dropped a role above the bar")
	}

	// LOW is the escape hatch: exactly the set the other tabs hide, so
	// nothing becomes unreachable.
	low := pipelineOnTab(apps, filterLow)
	if len(low.filtered) != 1 || low.filtered[0].Company != "Passed" {
		t.Fatalf("LOW must show exactly the hidden set, got %+v", low.filtered)
	}
}

// A tab count that disagrees with the list it labels reads as missing
// data. countForFilter duplicates applyFilterAndSort's switch, so the two
// are checked against each other for every tab rather than trusted.
func TestPipelineTabCountsMatchTheFilteredList(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Passed", Status: "Evaluated", Score: 2.0},
		{Company: "Applied", Status: "Applied", Score: 3.1},
		{Company: "Interviewing", Status: "Interview", Score: 4.4},
		{Company: "Strong", Status: "Evaluated", Score: 4.6},
		{Company: "Unevaluated", Status: "Evaluated"},
		{Company: "Discarded", Status: "Discarded", Score: 4.9},
	}

	for _, tab := range pipelineTabs {
		m := pipelineOnTab(apps, tab.filter)
		if got, want := m.countForFilter(tab.filter), len(m.filtered); got != want {
			t.Errorf("tab %q: count says %d, list has %d", tab.label, got, want)
		}
	}
}
