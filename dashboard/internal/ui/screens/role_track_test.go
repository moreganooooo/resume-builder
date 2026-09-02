package screens

import (
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// A player-coach still manages people, so it must clear the filter the
// same as a plain manager verdict -- the measured 90.3% precision covers
// the combined manager/player_coach excluded class, not manager alone.
func TestIsManagerTrackAcceptsPlayerCoach(t *testing.T) {
	row := model.JobRow{Evaluation: model.Evaluation{
		RoleTrack: "player_coach", RoleTrackConfidence: "high",
	}}
	if !row.IsManagerTrack() {
		t.Error("player_coach at high confidence must be manager-track")
	}
}

// The precision bar was only cleared at high confidence -- a medium or
// low verdict is exactly what the confidence gate exists to exclude.
func TestIsManagerTrackRequiresHighConfidence(t *testing.T) {
	row := model.JobRow{Evaluation: model.Evaluation{
		RoleTrack: "manager", RoleTrackConfidence: "medium",
	}}
	if row.IsManagerTrack() {
		t.Error("medium-confidence manager verdict must not clear the filter")
	}
}

// ic and unknown -- unknown is the expected, correct answer for ~40% of
// postings, not a failure -- must never clear the filter regardless of
// confidence.
func TestIsManagerTrackRejectsICAndUnknown(t *testing.T) {
	for _, track := range []string{"ic", "unknown", ""} {
		row := model.JobRow{Evaluation: model.Evaluation{
			RoleTrack: track, RoleTrackConfidence: "high",
		}}
		if row.IsManagerTrack() {
			t.Errorf("role_track=%q at high confidence must not be manager-track", track)
		}
	}
}

// [r] must always return to showing everything rather than trapping the
// user in a narrowed view -- the same contract as [w]/[e]/[$].
func TestRoleTrackFilterTogglesBackToUnrestricted(t *testing.T) {
	m := &JobsModel{filter: "all", roleTrackFilter: true}
	m.rows = []model.JobRow{
		{Title: "A", Evaluation: model.Evaluation{RoleTrack: "manager", RoleTrackConfidence: "high"}},
		{Title: "B", Evaluation: model.Evaluation{RoleTrack: "player_coach", RoleTrackConfidence: "high"}},
		{Title: "C", Evaluation: model.Evaluation{RoleTrack: "manager", RoleTrackConfidence: "medium"}},
		{Title: "D", Evaluation: model.Evaluation{RoleTrack: "ic", RoleTrackConfidence: "high"}},
		{Title: "E"}, // stated nothing
	}
	m.applyFilter()
	if len(m.filtered) != 2 {
		t.Fatalf("filtered = %+v, want A and B only", m.filtered)
	}

	m.roleTrackFilter = false
	m.applyFilter()
	if len(m.filtered) != 5 {
		t.Errorf("unrestricted filter dropped rows: %d", len(m.filtered))
	}
}
