package data

import (
	"os"
	"path/filepath"
	"testing"
)

func TestLoadKBItems(t *testing.T) {
	tempDir := t.TempDir()

	// Write mock verified_tools.json
	toolsJSON := `{
  "tools": [
    {
      "id": "tool_001",
      "name": "Go",
      "category": "Languages",
      "confidence": "Expert",
      "evidence_count": 5,
      "use_notes": "Daily use building Charm TUIs"
    }
  ]
}`
	_ = os.WriteFile(filepath.Join(tempDir, "verified_tools.json"), []byte(toolsJSON), 0644)

	// Write mock verified_metrics.json
	metricsJSON := `{
  "metrics": [
    {
      "id": "metric_001",
      "label": "Pipeline Speedup",
      "value": "90% faster",
      "category": "Performance",
      "confidence": "High",
      "context": "Refactored async loaders"
    }
  ]
}`
	_ = os.WriteFile(filepath.Join(tempDir, "verified_metrics.json"), []byte(metricsJSON), 0644)

	// Write mock verified_facts.json
	factsJSON := `{
  "facts": [
    {
      "id": "fact_001",
      "statement": "Architected distributed pipeline",
      "category": "Experience",
      "confidence": "High"
    }
  ]
}`
	_ = os.WriteFile(filepath.Join(tempDir, "verified_facts.json"), []byte(factsJSON), 0644)

	items := LoadKBItems(tempDir)
	if len(items) != 3 {
		t.Fatalf("expected 3 KB items, got %d", len(items))
	}

	foundTool := false
	foundMetric := false
	foundFact := false

	for _, it := range items {
		switch it.Category {
		case "Tools":
			foundTool = true
			if it.Title != "Go" {
				t.Errorf("expected tool title 'Go', got '%s'", it.Title)
			}
		case "Metrics":
			foundMetric = true
			if it.Title != "Pipeline Speedup" {
				t.Errorf("expected metric title 'Pipeline Speedup', got '%s'", it.Title)
			}
		case "Facts":
			foundFact = true
			if it.Title != "Architected distributed pipeline" {
				t.Errorf("expected fact title 'Architected distributed pipeline', got '%s'", it.Title)
			}
		}
	}

	if !foundTool || !foundMetric || !foundFact {
		t.Errorf("missing expected category items: tool=%v, metric=%v, fact=%v", foundTool, foundMetric, foundFact)
	}
}
