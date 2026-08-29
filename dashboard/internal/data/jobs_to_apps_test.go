package data

import (
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

func ptr(s string) *string { return &s }

func TestJobRowsToApplications_DropsTerminalStatuses(t *testing.T) {
	// Archived and expired jobs used to render in Pipeline as scoreless
	// rows indistinguishable from live applications -- the "scary red 0"
	// problem. They are terminal states and must not appear.
	rows := []model.JobRow{
		{Title: "Live", Company: "A", Status: "pending"},
		{Title: "Archived", Company: "B", Status: "archived"},
		{Title: "Expired", Company: "C", Status: "expired"},
		{Title: "Discarded", Company: "D", Status: "discarded"},
		{Title: "Applied", Company: "E", Status: "applied"},
	}

	apps := JobRowsToApplications(rows)

	got := make([]string, 0, len(apps))
	for _, a := range apps {
		got = append(got, a.Role)
	}
	if len(got) != 2 || got[0] != "Live" || got[1] != "Applied" {
		t.Fatalf("got %v, want [Live Applied]", got)
	}
}

func TestIsTerminalStatus_IsCaseAndSpaceInsensitive(t *testing.T) {
	for _, s := range []string{"Archived", "  EXPIRED ", "skip"} {
		if !IsTerminalStatus(s) {
			t.Errorf("IsTerminalStatus(%q) = false, want true", s)
		}
	}
	for _, s := range []string{"pending", "applied", "interview", ""} {
		if IsTerminalStatus(s) {
			t.Errorf("IsTerminalStatus(%q) = true, want false", s)
		}
	}
}

func TestJobRowsToApplications_UnscoredJobHasEmptyScoreRaw(t *testing.T) {
	// Rendering "0.00" for "not scored yet" is exactly the confusion this
	// screen had. An unevaluated job must render blank, not zero.
	rows := []model.JobRow{{Title: "Unscored", Company: "A", Status: "pending"}}

	apps := JobRowsToApplications(rows)

	if apps[0].ScoreRaw != "" {
		t.Errorf("ScoreRaw = %q, want empty for an unscored job", apps[0].ScoreRaw)
	}
}

func TestJobRowsToApplications_ScoredJobFormatsTwoDecimals(t *testing.T) {
	rows := []model.JobRow{{
		Title: "Scored", Company: "A", Status: "pending",
		Evaluation: model.Evaluation{CompositeScore: 4.55},
	}}

	apps := JobRowsToApplications(rows)

	if apps[0].ScoreRaw != "4.55" {
		t.Errorf("ScoreRaw = %q, want 4.55", apps[0].ScoreRaw)
	}
	if apps[0].Score != 4.55 {
		t.Errorf("Score = %v, want 4.55", apps[0].Score)
	}
}

func TestJobRowsToApplications_PrefersApplicationStatus(t *testing.T) {
	// A pipeline view is about the funnel, so "Responded" beats the JD's
	// file-location status of "pending".
	rows := []model.JobRow{{
		Title: "X", Company: "A", Status: "pending",
		Application: &model.Application{Status: "Responded"},
	}}

	if got := JobRowsToApplications(rows)[0].Status; got != "Responded" {
		t.Errorf("Status = %q, want Responded", got)
	}
}

func TestJobRowsToApplications_DatesAreTrimmedToDayPrecision(t *testing.T) {
	rows := []model.JobRow{{
		Title: "X", Company: "A", Status: "applied", PostedDate: "2026-08-10",
		Application: &model.Application{
			Status:          "Applied",
			AppliedAt:       ptr("2026-08-16T16:16:14"),
			StatusChangedAt: "2026-08-18T09:00:00",
		},
	}}

	app := JobRowsToApplications(rows)[0]

	// Date is "Date Scanned/Posted" (PostedDate), not when the user applied.
	if app.Date != "2026-08-10" {
		t.Errorf("Date = %q, want 2026-08-10", app.Date)
	}
	if app.LastContact != "2026-08-18" {
		t.Errorf("LastContact = %q, want 2026-08-18", app.LastContact)
	}
}

func TestJobRowsToApplications_NilApplicationIsSafe(t *testing.T) {
	rows := []model.JobRow{{Title: "X", Company: "A", Status: "pending"}}

	app := JobRowsToApplications(rows)[0]

	if app.Date != "" || app.LastContact != "" {
		t.Errorf("expected empty dates, got %q / %q", app.Date, app.LastContact)
	}
}

func TestJobRowsToApplications_NumbersAreContiguousAfterFiltering(t *testing.T) {
	// Number is a display index; skipping a filtered row would leave gaps.
	rows := []model.JobRow{
		{Title: "A", Company: "A", Status: "pending"},
		{Title: "B", Company: "B", Status: "archived"},
		{Title: "C", Company: "C", Status: "pending"},
	}

	apps := JobRowsToApplications(rows)

	if apps[0].Number != 1 || apps[1].Number != 2 {
		t.Errorf("numbers = %d, %d; want 1, 2", apps[0].Number, apps[1].Number)
	}
}

func TestJobRowsToApplications_EmptyInputReturnsEmpty(t *testing.T) {
	if got := JobRowsToApplications(nil); len(got) != 0 {
		t.Errorf("got %d apps, want 0", len(got))
	}
}
