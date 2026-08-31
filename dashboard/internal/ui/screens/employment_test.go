package screens

import (
	"encoding/json"
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// A field added to the Python export needs a matching JobRow field, or
// encoding/json fails the WHOLE document and LoadJobs returns zero rows.
// That silently emptied the Jobs screen once already (see CLAUDE.md), so
// the decode is asserted rather than assumed.
func TestEmploymentTypeDecodesFromTheExport(t *testing.T) {
	var row model.JobRow
	payload := `{"title":"Copywriter","employment_type":["full_time","contract"],
	             "employment_type_raw":"Full-time, Contract"}`
	if err := json.Unmarshal([]byte(payload), &row); err != nil {
		t.Fatalf("export shape must decode: %v", err)
	}
	if got := row.EmploymentLabel(); got != "Full-time, Contract" {
		t.Errorf("EmploymentLabel() = %q", got)
	}
}

// An unmappable provider value normalizes to nothing. Showing the raw
// string is how a new spelling becomes visible instead of vanishing.
func TestUnmappedValueFallsBackToWhatTheProviderSaid(t *testing.T) {
	row := model.JobRow{EmploymentTypeRaw: "Fixed Term Contract - Union"}
	if got := row.EmploymentLabel(); got != "Fixed Term Contract - Union" {
		t.Errorf("EmploymentLabel() = %q, want the raw value", got)
	}
}

func TestUnstatedTypeRendersBlankNotUnknown(t *testing.T) {
	if got := (model.JobRow{}).EmploymentLabel(); got != "" {
		t.Errorf("EmploymentLabel() = %q, want empty", got)
	}
}

// A posting offered as full-time OR contract genuinely is both, so it
// must appear under either filter.
func TestMultiTypePostingMatchesEitherFilter(t *testing.T) {
	row := model.JobRow{EmploymentType: []string{"full_time", "contract"}}
	for _, want := range []string{"full_time", "contract"} {
		if !row.HasEmploymentType(want) {
			t.Errorf("HasEmploymentType(%q) = false", want)
		}
	}
	if row.HasEmploymentType("internship") {
		t.Error("HasEmploymentType(internship) = true")
	}
}

// Absence is not evidence that a posting qualifies -- the same rule the
// workplace filter follows for "unknown".
func TestAStatelessPostingMatchesNoEmploymentFilter(t *testing.T) {
	row := model.JobRow{EmploymentTypeRaw: "something unmappable"}
	if row.HasEmploymentType("full_time") {
		t.Error("a posting with no canonical type must match no filter")
	}
}

// [e] must always return to showing everything rather than trapping the
// user in a narrowed view -- the same contract as [w].
func TestEmploymentFilterCycleReturnsToUnrestricted(t *testing.T) {
	current := ""
	seen := map[string]bool{}
	for i := 0; i < len(employmentFilterCycle); i++ {
		current = nextEmploymentFilter(current)
		seen[current] = true
	}
	if current != "" {
		t.Errorf("cycle did not return to unrestricted, ended at %q", current)
	}
	if len(seen) != len(employmentFilterCycle) {
		t.Errorf("cycle visited %d of %d values", len(seen), len(employmentFilterCycle))
	}
}

// A cycle value with no label would render as "All" in the status bar,
// which reads as "no filter" while a filter is active.
func TestEveryCycleValueHasALabel(t *testing.T) {
	for _, value := range employmentFilterCycle {
		if value == "" {
			continue
		}
		if _, ok := model.EmploymentLabels[value]; !ok {
			t.Errorf("cycle value %q has no label", value)
		}
	}
}

func TestEmploymentFilterNarrowsTheList(t *testing.T) {
	m := &JobsModel{filter: "all", employmentFilter: "part_time"}
	m.rows = []model.JobRow{
		{Title: "A", EmploymentType: []string{"part_time"}},
		{Title: "B", EmploymentType: []string{"full_time"}},
		{Title: "C"}, // stated nothing
	}
	m.applyFilter()
	if len(m.filtered) != 1 || m.filtered[0].Title != "A" {
		t.Fatalf("filtered = %+v", m.filtered)
	}

	m.employmentFilter = ""
	m.applyFilter()
	if len(m.filtered) != 3 {
		t.Errorf("unrestricted filter dropped rows: %d", len(m.filtered))
	}
}
