package data

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// The Python exporter writes skills as objects. This field was declared
// []string, so every export failed to unmarshal and LoadJobs returned an
// error -- leaving Browse & Manage Jobs empty on every launch path. These
// tests pin the shape contract in both directions.

func writeJobsFile(t *testing.T, body string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "jobs.json")
	if err := os.WriteFile(path, []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	return path
}

func TestLoadJobs_SkillsAsObjects(t *testing.T) {
	path := writeJobsFile(t, `[{
		"title": "Lifecycle Marketing Manager",
		"skills": [
			{"skill": "Digital Marketing", "score": 3, "type": "hard_skill"},
			{"skill": "Braze", "score": 5, "type": "tool"}
		]
	}]`)

	rows, err := LoadJobs(path)
	if err != nil {
		t.Fatalf("LoadJobs on the real export shape: %v", err)
	}
	if len(rows) != 1 {
		t.Fatalf("got %d rows, want 1", len(rows))
	}
	if len(rows[0].Skills) != 2 {
		t.Fatalf("got %d skills, want 2", len(rows[0].Skills))
	}
	if rows[0].Skills[0].Name != "Digital Marketing" {
		t.Errorf("Name = %q, want %q", rows[0].Skills[0].Name, "Digital Marketing")
	}
	if rows[0].Skills[0].Score != 3 {
		t.Errorf("Score = %d, want 3", rows[0].Skills[0].Score)
	}
	if rows[0].Skills[1].Type != "tool" {
		t.Errorf("Type = %q, want %q", rows[0].Skills[1].Type, "tool")
	}
}

func TestLoadJobs_SkillsAsBareStrings(t *testing.T) {
	// Older exports and hand-written fixtures use plain strings; those
	// must keep loading rather than trading one parse failure for another.
	path := writeJobsFile(t, `[{"title": "X", "skills": ["Braze", "SQL"]}]`)

	rows, err := LoadJobs(path)
	if err != nil {
		t.Fatalf("LoadJobs on the legacy string shape: %v", err)
	}
	if len(rows[0].Skills) != 2 || rows[0].Skills[0].Name != "Braze" {
		t.Fatalf("got %+v, want two named skills", rows[0].Skills)
	}
}

func TestLoadJobs_MixedSkillShapes(t *testing.T) {
	path := writeJobsFile(t, `[{"skills": ["Braze", {"skill": "SQL", "score": 4}]}]`)

	rows, err := LoadJobs(path)
	if err != nil {
		t.Fatalf("LoadJobs on mixed shapes: %v", err)
	}
	if rows[0].Skills[0].Name != "Braze" || rows[0].Skills[1].Name != "SQL" {
		t.Fatalf("got %+v", rows[0].Skills)
	}
}

func TestLoadJobs_MalformedSkillStillErrors(t *testing.T) {
	// Leniency is scoped to the two known shapes -- a number is neither,
	// and must surface rather than silently decode to an empty skill.
	path := writeJobsFile(t, `[{"skills": [42]}]`)

	if _, err := LoadJobs(path); err == nil {
		t.Fatal("expected an error for a numeric skill, got nil")
	}
}

// TestJobSkill_RoundTripsThroughJobRow guards the whole struct, not just
// the custom unmarshaler in isolation.
func TestJobSkill_RoundTripsThroughJobRow(t *testing.T) {
	var row model.JobRow
	if err := json.Unmarshal([]byte(`{"skills":[{"skill":"Braze"}]}`), &row); err != nil {
		t.Fatal(err)
	}
	if row.Skills[0].Name != "Braze" {
		t.Errorf("Name = %q", row.Skills[0].Name)
	}
}
