package screens

import (
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

func floatPtr(v float64) *float64 { return &v }

func TestPayLabelPrefersThePostingsOwnWording(t *testing.T) {
	// The annualized number is for sorting. Showing $52,000 for a job
	// advertised at "$25/hr" would print a figure the posting never did.
	row := model.JobRow{PayAnnualMax: floatPtr(52000), PayText: "$25/hr"}
	if got := row.PayLabel(); got != "$25/hr" {
		t.Fatalf("PayLabel() = %q, want %q", got, "$25/hr")
	}
}

func TestPayLabelIsBlankWhenUnstated(t *testing.T) {
	// Blank, not "Unknown": three quarters of postings state no pay, and
	// flagging that as missing data on most rows is noise, not signal.
	if got := (model.JobRow{}).PayLabel(); got != "" {
		t.Fatalf("PayLabel() = %q, want empty", got)
	}
}

func TestHasStatedPayDistinguishesSilenceFromZero(t *testing.T) {
	if (model.JobRow{}).HasStatedPay() {
		t.Fatal("a row with no pay data must not report stated pay")
	}
	// A real zero is still a disclosure, and must not read as silence.
	if !(model.JobRow{PayAnnualMax: floatPtr(0)}).HasStatedPay() {
		t.Fatal("an explicit zero is a stated value, not an absence")
	}
}

func TestHoursLabel(t *testing.T) {
	row := model.JobRow{HoursText: "20-25 hours per week"}
	if got := row.HoursLabel(); got != "20-25 hours per week" {
		t.Fatalf("HoursLabel() = %q", got)
	}
	if got := (model.JobRow{}).HoursLabel(); got != "" {
		t.Fatalf("HoursLabel() = %q, want empty", got)
	}
}

func TestPayFilterCycleReturnsToUnfiltered(t *testing.T) {
	// Same contract as [w] and [e]: pressing the key repeatedly must
	// always get back to showing everything.
	current := ""
	for i := 0; i < len(payFilterCycle); i++ {
		current = nextPayFilter(current)
	}
	if current != "" {
		t.Fatalf("cycling %d times landed on %q, want unfiltered", len(payFilterCycle), current)
	}
}

func TestPayFilterCycleRecoversFromAnUnknownValue(t *testing.T) {
	if got := nextPayFilter("nonsense"); got != "" {
		t.Fatalf("nextPayFilter(unknown) = %q, want empty", got)
	}
}

func TestPayFilterNarrowsByDisclosureNotAmount(t *testing.T) {
	m := JobsModel{rows: []model.JobRow{
		{Title: "discloses", PayAnnualMax: floatPtr(95000), PayText: "$95,000/yr"},
		{Title: "silent"},
	}}

	m.payFilter = "stated"
	m.applyFilter()
	if len(m.filtered) != 1 || m.filtered[0].Title != "discloses" {
		t.Fatalf("stated filter kept %d rows, want just the disclosing one", len(m.filtered))
	}

	// "unstated" is a legitimate thing to ask FOR: those are exactly the
	// rows a configured pay floor could not judge either way.
	m.payFilter = "unstated"
	m.applyFilter()
	if len(m.filtered) != 1 || m.filtered[0].Title != "silent" {
		t.Fatalf("unstated filter kept %d rows, want just the silent one", len(m.filtered))
	}

	m.payFilter = ""
	m.applyFilter()
	if len(m.filtered) != 2 {
		t.Fatalf("unfiltered kept %d rows, want 2", len(m.filtered))
	}
}

func TestPayFilterLabel(t *testing.T) {
	if payFilterLabel("stated") == "" || payFilterLabel("unstated") == "" {
		t.Fatal("active modes must name themselves for the status bar")
	}
	if payFilterLabel("") != "" {
		t.Fatal("the unfiltered mode must render no badge")
	}
}
