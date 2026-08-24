package zone

import (
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
)

func TestZoneMarkScanAndBounds(t *testing.T) {
	rendered := Mark("tab_pipeline", "Pipeline Tab")
	if rendered == "Pipeline Tab" {
		t.Fatalf("expected Mark to insert zone metadata tags, got unmodified string")
	}

	scanned := Scan(rendered)
	if scanned != "Pipeline Tab" {
		t.Fatalf("expected Scan to strip markers and return 'Pipeline Tab', got '%s'", scanned)
	}

	// WaitFor, not bzone.Get: Scan publishes bounds through a worker
	// goroutine, so an immediate read here is racy -- this test failed
	// under -race -count=5 when it read directly. See zone.Scan.
	info := WaitFor("tab_pipeline", 2*time.Second)
	if info == nil {
		t.Fatalf("tab_pipeline never registered after Scan")
	}

	// Tab should start at (0, 0) and have length ~12
	if !InBounds("tab_pipeline", 2, 0) {
		t.Errorf("expected coordinate (2, 0) to be in bounds for tab_pipeline, got %+v", info)
	}
	if InBounds("tab_pipeline", 50, 50) {
		t.Errorf("expected coordinate (50, 50) to NOT be in bounds for tab_pipeline")
	}

	clickMsg := tea.MouseClickMsg{
		X: 2,
		Y: 0,
	}
	if !InBoundsClick("tab_pipeline", clickMsg) {
		t.Errorf("expected InBoundsClick to return true for clickMsg at (2,0)")
	}
	if !InBoundsMouse("tab_pipeline", clickMsg) {
		t.Errorf("expected InBoundsMouse to return true for clickMsg at (2,0)")
	}
}
