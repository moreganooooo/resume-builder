package screens

import (
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// newPipelineFilterFixture builds a PipelineModel with the "ALL" tab
// active and no search/sort side effects, so applyFilterAndSort's result
// reflects only the opt-in [w]/[e]/[$]/[t]/[x] filters under test.
func newPipelineFilterFixture(apps []model.CareerApplication) *PipelineModel {
	m := &PipelineModel{
		apps:      apps,
		activeTab: 0, // filterAll
		sortMode:  sortScore,
		viewMode:  "flat",
	}
	m.applyFilterAndSort()
	return m
}

func TestWorkplaceFilterAcceptsMatchingRejectsOther(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", Workplace: model.WorkplaceRemote},
		{Company: "B", Workplace: model.WorkplaceOnsite},
	})
	m.workplaceFilter = model.WorkplaceRemote
	m.applyFilterAndSort()
	if len(m.filtered) != 1 || m.filtered[0].Company != "A" {
		t.Fatalf("filtered = %+v, want only A", m.filtered)
	}
}

func TestWorkplaceFilterTogglesBackToUnrestricted(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", Workplace: model.WorkplaceRemote},
		{Company: "B", Workplace: model.WorkplaceOnsite},
	})
	m.workplaceFilter = model.WorkplaceRemote
	m.applyFilterAndSort()
	if len(m.filtered) != 1 {
		t.Fatalf("expected narrowed set of 1, got %d", len(m.filtered))
	}
	m.workplaceFilter = ""
	m.applyFilterAndSort()
	if len(m.filtered) != 2 {
		t.Errorf("unrestricted filter dropped rows: %d", len(m.filtered))
	}
}

func TestEmploymentFilterAcceptsMatchingRejectsOther(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", EmploymentType: []string{"full_time"}},
		{Company: "B", EmploymentType: []string{"contract"}},
		{Company: "C"}, // stated nothing
	})
	m.employmentFilter = "full_time"
	m.applyFilterAndSort()
	if len(m.filtered) != 1 || m.filtered[0].Company != "A" {
		t.Fatalf("filtered = %+v, want only A", m.filtered)
	}
}

func TestEmploymentFilterTogglesBackToUnrestricted(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", EmploymentType: []string{"full_time"}},
		{Company: "B", EmploymentType: []string{"contract"}},
	})
	m.employmentFilter = "full_time"
	m.applyFilterAndSort()
	if len(m.filtered) != 1 {
		t.Fatalf("expected narrowed set of 1, got %d", len(m.filtered))
	}
	m.employmentFilter = ""
	m.applyFilterAndSort()
	if len(m.filtered) != 2 {
		t.Errorf("unrestricted filter dropped rows: %d", len(m.filtered))
	}
}

func TestPayFilterStatedAndUnstatedAreMutuallyExclusive(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "A", HasStatedPay: true},
		{Company: "B", HasStatedPay: false},
	}

	stated := newPipelineFilterFixture(apps)
	stated.payFilter = "stated"
	stated.applyFilterAndSort()
	if len(stated.filtered) != 1 || stated.filtered[0].Company != "A" {
		t.Fatalf("stated filter = %+v, want only A", stated.filtered)
	}

	unstated := newPipelineFilterFixture(apps)
	unstated.payFilter = "unstated"
	unstated.applyFilterAndSort()
	if len(unstated.filtered) != 1 || unstated.filtered[0].Company != "B" {
		t.Fatalf("unstated filter = %+v, want only B", unstated.filtered)
	}
}

func TestPayFilterTogglesBackToUnrestricted(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", HasStatedPay: true},
		{Company: "B", HasStatedPay: false},
	})
	m.payFilter = "stated"
	m.applyFilterAndSort()
	if len(m.filtered) != 1 {
		t.Fatalf("expected narrowed set of 1, got %d", len(m.filtered))
	}
	m.payFilter = ""
	m.applyFilterAndSort()
	if len(m.filtered) != 2 {
		t.Errorf("unrestricted filter dropped rows: %d", len(m.filtered))
	}
}

func TestPipelineRoleTrackFilterMirrorsJobsIsManagerTrack(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", RoleTrack: "manager", RoleTrackConfidence: "high"},
		{Company: "B", RoleTrack: "player_coach", RoleTrackConfidence: "high"},
		{Company: "C", RoleTrack: "manager", RoleTrackConfidence: "medium"},
		{Company: "D", RoleTrack: "ic", RoleTrackConfidence: "high"},
	})
	m.roleTrackFilter = true
	m.applyFilterAndSort()
	if len(m.filtered) != 2 {
		t.Fatalf("filtered = %+v, want A and B only", m.filtered)
	}
}

func TestPipelineRoleTrackFilterTogglesBackToUnrestricted(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", RoleTrack: "manager", RoleTrackConfidence: "high"},
		{Company: "B", RoleTrack: "ic", RoleTrackConfidence: "high"},
	})
	m.roleTrackFilter = true
	m.applyFilterAndSort()
	if len(m.filtered) != 1 {
		t.Fatalf("expected narrowed set of 1, got %d", len(m.filtered))
	}
	m.roleTrackFilter = false
	m.applyFilterAndSort()
	if len(m.filtered) != 2 {
		t.Errorf("unrestricted filter dropped rows: %d", len(m.filtered))
	}
}

func TestExperienceBlockerFilterAcceptsOnlyFlaggedRows(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", ExperienceBlockers: []model.HardBlocker{{Text: "5+ years required", Category: "years_experience"}}},
		{Company: "B"},
	})
	m.experienceBlockerFilter = true
	m.applyFilterAndSort()
	if len(m.filtered) != 1 || m.filtered[0].Company != "A" {
		t.Fatalf("filtered = %+v, want only A", m.filtered)
	}
}

func TestExperienceBlockerFilterTogglesBackToUnrestricted(t *testing.T) {
	m := newPipelineFilterFixture([]model.CareerApplication{
		{Company: "A", ExperienceBlockers: []model.HardBlocker{{Text: "Bachelor's required", Category: "degree"}}},
		{Company: "B"},
	})
	m.experienceBlockerFilter = true
	m.applyFilterAndSort()
	if len(m.filtered) != 1 {
		t.Fatalf("expected narrowed set of 1, got %d", len(m.filtered))
	}
	m.experienceBlockerFilter = false
	m.applyFilterAndSort()
	if len(m.filtered) != 2 {
		t.Errorf("unrestricted filter dropped rows: %d", len(m.filtered))
	}
}
