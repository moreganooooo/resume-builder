package screens

import (
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// [i] steps all -> hide AI training -> AI training only -> staffing boards
// and wraps back to all, so the narrowing is never a trap.
func TestCategoryFilterCycleWrapsToAll(t *testing.T) {
	got := []string{}
	f := ""
	for range model.CategoryFilterCycle {
		f = model.NextCategoryFilter(f)
		got = append(got, f)
	}
	want := []string{model.CategoryHideAITraining, model.CategoryAITrainingOnly, model.CategoryStaffingOnly, ""}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("cycle = %v, want %v", got, want)
		}
	}
}

func categoryJobRows() []model.JobRow {
	ev := model.Evaluation{CompositeScore: aboveBar}
	return []model.JobRow{
		{Title: "AI Trainer", AITraining: true, AITrainingEvidence: []string{"title: AI Trainer"}, Evaluation: ev},
		{Title: "Agency role", StaffingAgency: "LHT Services", Evaluation: ev},
		{Title: "Permanent role", Evaluation: ev},
	}
}

func TestJobsCategoryFilterStops(t *testing.T) {
	cases := map[string][]string{
		"":                           {"AI Trainer", "Agency role", "Permanent role"},
		model.CategoryHideAITraining: {"Agency role", "Permanent role"},
		model.CategoryAITrainingOnly: {"AI Trainer"},
		model.CategoryStaffingOnly:   {"Agency role"},
	}
	for filter, want := range cases {
		m := &JobsModel{filter: "all", categoryFilter: filter, rows: categoryJobRows()}
		m.applyFilter()
		if len(m.filtered) != len(want) {
			t.Errorf("%q: got %d rows, want %v", filter, len(m.filtered), want)
			continue
		}
		for i, r := range m.filtered {
			if r.Title != want[i] {
				t.Errorf("%q: row %d = %q, want %q", filter, i, r.Title, want[i])
			}
		}
	}
}

func TestPipelineCategoryFilterMirrorsJobs(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "A", AITraining: true},
		{Company: "B", StaffingAgency: "ComputerPeople"},
		{Company: "C"},
	}
	cases := map[string]int{"": 3, model.CategoryHideAITraining: 2, model.CategoryAITrainingOnly: 1, model.CategoryStaffingOnly: 1}
	for filter, want := range cases {
		m := newPipelineFilterFixture(apps)
		m.categoryFilter = filter
		m.applyFilterAndSort()
		if len(m.filtered) != want {
			t.Errorf("%q: got %d rows, want %d", filter, len(m.filtered), want)
		}
	}
}
