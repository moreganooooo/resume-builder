package data

import (
	"os"
	"path/filepath"
	"testing"
)

func writeTempJobsFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "jobs.json")
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("failed to write temp file: %v", err)
	}
	return path
}

func TestLoadJobs_ValidFile(t *testing.T) {
	content := `[
		{
			"path": "jds/morgan/a.json",
			"status": "Pending",
			"title": "Marketing Lead",
			"company": "Acme",
			"evaluation": {
				"composite_score": 4.66,
				"fit_score": 4.85,
				"recommendation": "Strong pursue",
				"why": "Great fit.",
				"hard_blockers": [],
				"fit_subscores": {"functional_alignment": 5},
				"posting_age_days": 2,
				"evaluated_at": "2026-07-27T03:13:55"
			},
			"liveness": {"result": "active", "reason": "visible apply control detected", "checked_at": "2026-08-07T21:44:03"},
			"application": null
		}
	]`
	path := writeTempJobsFile(t, content)

	rows, err := LoadJobs(path)
	if err != nil {
		t.Fatalf("LoadJobs failed: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("expected 1 row, got %d", len(rows))
	}
	row := rows[0]
	if row.Company != "Acme" || row.Status != "Pending" {
		t.Fatalf("unexpected row: %+v", row)
	}
	if row.Evaluation.CompositeScore != 4.66 {
		t.Fatalf("expected composite_score 4.66, got %v", row.Evaluation.CompositeScore)
	}
	if row.Evaluation.FitSubscores["functional_alignment"] != 5 {
		t.Fatalf("expected fit_subscores.functional_alignment 5, got %+v", row.Evaluation.FitSubscores)
	}
	if row.Liveness == nil || row.Liveness.Result != "active" {
		t.Fatalf("expected liveness.result 'active', got %+v", row.Liveness)
	}
	if row.Application != nil {
		t.Fatalf("expected nil application, got %+v", row.Application)
	}
}

func TestLoadJobs_MalformedJSON(t *testing.T) {
	path := writeTempJobsFile(t, "not json")
	if _, err := LoadJobs(path); err == nil {
		t.Fatal("expected an error for malformed JSON, got nil")
	}
}

func TestLoadJobs_MissingFile(t *testing.T) {
	if _, err := LoadJobs(filepath.Join(t.TempDir(), "does-not-exist.json")); err == nil {
		t.Fatal("expected an error for a missing file, got nil")
	}
}
