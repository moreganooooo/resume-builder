package screens

import (
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// [c] must narrow to rows carrying a years_experience/degree blocker and,
// like [r]/[w]/[e]/[$], always return to showing everything rather than
// trapping the user in a narrowed view.
func TestJobsExperienceBlockerFilterTogglesBackToUnrestricted(t *testing.T) {
	m := &JobsModel{filter: "all", experienceBlockerFilter: true}
	m.rows = []model.JobRow{
		{Title: "A", Evaluation: model.Evaluation{
			ExperienceBlockers: []model.HardBlocker{{Text: "Requires 5+ years", Category: "years_experience"}},
		}},
		{Title: "B", Evaluation: model.Evaluation{
			ExperienceBlockers: []model.HardBlocker{{Text: "Bachelor's required", Category: "degree"}},
		}},
		{Title: "C"}, // no blockers
		{Title: "D", Evaluation: model.Evaluation{
			HardBlockers: []model.HardBlocker{{Text: "Active clearance required", Category: "citizenship_clearance"}},
		}},
	}
	m.applyFilter()
	if len(m.filtered) != 2 {
		t.Fatalf("filtered = %+v, want A and B only", m.filtered)
	}

	m.experienceBlockerFilter = false
	m.applyFilter()
	if len(m.filtered) != 4 {
		t.Errorf("unrestricted filter dropped rows: %d", len(m.filtered))
	}
}
