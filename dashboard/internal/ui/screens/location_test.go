package screens

import (
	"strings"
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func miles(v float64) *float64 { return &v }

func jobAt(workplace string, distance *float64) model.JobRow {
	return model.JobRow{Workplace: workplace, DistanceMiles: distance}
}

func TestNextWorkplaceFilterCycles(t *testing.T) {
	// "" is part of the cycle, so [w] always returns to showing
	// everything rather than trapping the user in a narrowed view.
	got := ""
	for i := 0; i < 4; i++ {
		got = nextWorkplaceFilter(got)
	}
	if got != "" {
		t.Fatalf("cycle did not return to unrestricted, got %q", got)
	}
}

func TestSortByDistancePutsUnmeasuredLast(t *testing.T) {
	rows := []model.JobRow{
		jobAt(model.WorkplaceRemote, nil),
		jobAt(model.WorkplaceOnsite, miles(30)),
		jobAt(model.WorkplaceUnknown, nil),
		jobAt(model.WorkplaceOnsite, miles(4)),
	}
	sortByDistance(rows)

	if d, ok := rows[0].Miles(); !ok || d != 4 {
		t.Fatalf("nearest job did not sort first: %+v", rows[0])
	}
	if d, ok := rows[1].Miles(); !ok || d != 30 {
		t.Fatalf("second-nearest job out of order: %+v", rows[1])
	}
	// Unmeasured rows must land at the END. Floating them to the top
	// would bury the few genuinely nearby jobs that are the entire
	// reason to sort this way.
	for _, r := range rows[2:] {
		if r.HasDistance() {
			t.Fatalf("measured row sorted behind an unmeasured one: %+v", r)
		}
	}
}

func TestSortByDistanceIsStable(t *testing.T) {
	// Ties keep their incoming (score) order.
	a := model.JobRow{Company: "A", DistanceMiles: miles(5)}
	b := model.JobRow{Company: "B", DistanceMiles: miles(5)}
	rows := []model.JobRow{a, b}
	sortByDistance(rows)
	if rows[0].Company != "A" || rows[1].Company != "B" {
		t.Fatalf("stable order not preserved: %+v", rows)
	}
}

func TestApplyFilterNarrowsByWorkplace(t *testing.T) {
	m := &JobsModel{
		filter: "all",
		rows: []model.JobRow{
			jobAt(model.WorkplaceRemote, nil),
			jobAt(model.WorkplaceOnsite, miles(6)),
			jobAt(model.WorkplaceUnknown, nil),
		},
	}

	m.workplaceFilter = model.WorkplaceOnsite
	m.applyFilter()
	if len(m.filtered) != 1 || m.filtered[0].Workplace != model.WorkplaceOnsite {
		t.Fatalf("expected only the on-site row, got %+v", m.filtered)
	}

	// An undetermined workplace must not be shown under a specific mode:
	// "unknown" is not evidence of anything.
	m.workplaceFilter = model.WorkplaceRemote
	m.applyFilter()
	if len(m.filtered) != 1 || m.filtered[0].Workplace != model.WorkplaceRemote {
		t.Fatalf("unknown workplace leaked into a specific mode: %+v", m.filtered)
	}

	m.workplaceFilter = ""
	m.applyFilter()
	if len(m.filtered) != 3 {
		t.Fatalf("clearing the filter should restore every row, got %d", len(m.filtered))
	}
}

func TestApplyFilterComposesWorkplaceWithScoreFilter(t *testing.T) {
	strong := model.JobRow{Workplace: model.WorkplaceOnsite}
	strong.Evaluation.CompositeScore = 4.5
	weak := model.JobRow{Workplace: model.WorkplaceOnsite}
	weak.Evaluation.CompositeScore = 2.0

	m := &JobsModel{filter: "high_fit", workplaceFilter: model.WorkplaceOnsite,
		rows: []model.JobRow{strong, weak}}
	m.applyFilter()
	if len(m.filtered) != 1 || m.filtered[0].Evaluation.CompositeScore != 4.5 {
		t.Fatalf("workplace and score filters did not compose: %+v", m.filtered)
	}
}

func TestLocationBadge(t *testing.T) {
	tm := theme.NewTheme("catppuccin-mocha")

	if got := locationBadge(tm, jobAt(model.WorkplaceUnknown, nil)); got != "" {
		// Nothing truthful to say -> no badge, rather than "Unknown",
		// which reads like a value the data actually carries.
		t.Fatalf("expected no badge for an unknown job, got %q", got)
	}
	if got := locationBadge(tm, jobAt(model.WorkplaceRemote, nil)); got == "" {
		t.Fatal("expected a badge for a remote job")
	}
	badge := locationBadge(tm, jobAt(model.WorkplaceOnsite, miles(6.25)))
	if badge == "" {
		t.Fatal("expected a badge for a measured on-site job")
	}
	if !strings.Contains(badge, "On-site") || !strings.Contains(badge, "6.2 mi") {
		t.Fatalf("badge missing workplace or distance: %q", badge)
	}
	// A distance with no classified workplace should still show.
	if got := locationBadge(tm, jobAt(model.WorkplaceUnknown, miles(3))); got == "" {
		t.Fatal("expected a badge when only a distance is known")
	}
}
