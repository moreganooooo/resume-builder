package data

import (
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

func TestParseApplicationsUsesTrackerNumberColumn(t *testing.T) {
	tempDir := t.TempDir()
	dataDir := filepath.Join(tempDir, "data")
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		t.Fatalf("failed to create data dir: %v", err)
	}

	applications := `# Applications Tracker

| # | Date | Company | Role | Score | Status | PDF | Report | Notes |
|---|------|---------|------|-------|--------|-----|--------|-------|
| 140 | 2026-04-16 | Arize AI | AI Engineer, Instrumentation | 4.7/5 | Evaluated | ✅ | [140](reports/140-arize-ai-engineer-instrumentation-2026-04-16.md) | Strong fit |
| 143 | 2026-04-16 | Arize AI | AI Sales Engineer, US | 4.1/5 | Evaluated | ❌ | [143](reports/143-arize-ai-sales-engineer-us-2026-04-16.md) | Good fit |
`

	applicationsPath := filepath.Join(dataDir, "applications.md")
	if err := os.WriteFile(applicationsPath, []byte(applications), 0o644); err != nil {
		t.Fatalf("failed to write applications tracker: %v", err)
	}

	apps := ParseApplications(tempDir)
	if len(apps) != 2 {
		t.Fatalf("expected 2 parsed applications, got %d", len(apps))
	}

	if apps[0].Number != 140 {
		t.Fatalf("expected first application number to be 140, got %d", apps[0].Number)
	}
	if apps[1].Number != 143 {
		t.Fatalf("expected second application number to be 143, got %d", apps[1].Number)
	}
	if apps[0].ReportNumber != "140" || apps[1].ReportNumber != "143" {
		t.Fatalf("expected report numbers to stay aligned with tracker IDs, got %q and %q", apps[0].ReportNumber, apps[1].ReportNumber)
	}
}

func TestParseApplicationsResolvesTrackerRelativeReportLinks(t *testing.T) {
	tempDir := t.TempDir()
	dataDir := filepath.Join(tempDir, "data")
	reportsDir := filepath.Join(tempDir, "reports")
	for _, dir := range []string{dataDir, reportsDir} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			t.Fatalf("failed to create dir %s: %v", dir, err)
		}
	}

	// Tracker links are written relative to the tracker file itself
	// (merge-tracker.mjs normalization): ../reports/... when the tracker
	// lives under data/. Legacy trackers may still carry root-relative
	// links; both must resolve to the same on-disk report.
	applications := `# Applications Tracker

| # | Date | Company | Role | Score | Status | PDF | Report | Notes |
|---|------|---------|------|-------|--------|-----|--------|-------|
| 1 | 2026-06-03 | Acme | Engineer | 4.0/5 | Evaluated | ✅ | [1](../reports/001-acme-2026-06-03.md) | Tracker-relative link |
| 2 | 2026-06-03 | Legacy Co | Engineer | 3.0/5 | Evaluated | ❌ | [2](reports/002-legacy-2026-06-03.md) | Legacy root-relative link |
`

	if err := os.WriteFile(filepath.Join(dataDir, "applications.md"), []byte(applications), 0o644); err != nil {
		t.Fatalf("failed to write applications tracker: %v", err)
	}
	for _, name := range []string{"001-acme-2026-06-03.md", "002-legacy-2026-06-03.md"} {
		if err := os.WriteFile(filepath.Join(reportsDir, name), []byte("# Report\n"), 0o644); err != nil {
			t.Fatalf("failed to write report %s: %v", name, err)
		}
	}

	apps := ParseApplications(tempDir)
	if len(apps) != 2 {
		t.Fatalf("expected 2 parsed applications, got %d", len(apps))
	}

	wantFirst := filepath.Join("reports", "001-acme-2026-06-03.md")
	if apps[0].ReportPath != wantFirst {
		t.Fatalf("expected tracker-relative link to resolve to %q, got %q", wantFirst, apps[0].ReportPath)
	}
	wantSecond := filepath.Join("reports", "002-legacy-2026-06-03.md")
	if apps[1].ReportPath != wantSecond {
		t.Fatalf("expected legacy root-relative link to resolve to %q, got %q", wantSecond, apps[1].ReportPath)
	}

	// Every consumer joins ReportPath against careerOpsPath — both rows
	// must point at files that exist.
	for i, app := range apps {
		if _, err := os.Stat(filepath.Join(tempDir, app.ReportPath)); err != nil {
			t.Fatalf("row %d: resolved report path %q does not exist: %v", i, app.ReportPath, err)
		}
	}
}

func TestLoadReportSummaryCachesUntilFileChanges(t *testing.T) {
	tempDir := t.TempDir()
	reportPath := "report.md"
	fullPath := filepath.Join(tempDir, reportPath)

	if err := os.WriteFile(fullPath, []byte("**TL;DR** | first version\n"), 0o644); err != nil {
		t.Fatalf("failed to write report: %v", err)
	}

	_, tldr, _, _ := LoadReportSummary(tempDir, reportPath)
	if tldr != "first version" {
		t.Fatalf("expected first read to see %q, got %q", "first version", tldr)
	}

	// Rewrite with different content but the same mtime (simulating two
	// reads landing in the same second, the case a cache keyed only on
	// mtime -- not content hash -- can't distinguish) -- the cache should
	// still serve the first read's value rather than silently going stale
	// on every call within the same mtime.
	stat, err := os.Stat(fullPath)
	if err != nil {
		t.Fatalf("failed to stat report: %v", err)
	}
	if err := os.WriteFile(fullPath, []byte("**TL;DR** | second version\n"), 0o644); err != nil {
		t.Fatalf("failed to rewrite report: %v", err)
	}
	if err := os.Chtimes(fullPath, stat.ModTime(), stat.ModTime()); err != nil {
		t.Fatalf("failed to pin mtime: %v", err)
	}

	_, tldr, _, _ = LoadReportSummary(tempDir, reportPath)
	if tldr != "first version" {
		t.Fatalf("expected cache hit to still return %q, got %q", "first version", tldr)
	}

	// A real mtime change must invalidate the cache.
	newModTime := stat.ModTime().Add(2 * time.Second)
	if err := os.Chtimes(fullPath, newModTime, newModTime); err != nil {
		t.Fatalf("failed to bump mtime: %v", err)
	}

	_, tldr, _, _ = LoadReportSummary(tempDir, reportPath)
	if tldr != "second version" {
		t.Fatalf("expected mtime change to invalidate cache and return %q, got %q", "second version", tldr)
	}
}

func TestComputeProgressMetrics_DegradedAndEmpty(t *testing.T) {
	// 1. Nil slice
	pm := ComputeProgressMetrics(nil)
	if pm.ActiveApps != 0 || pm.AvgScore != 0 || len(pm.FunnelStages) != 5 {
		t.Fatalf("unexpected progress metrics on nil apps: %+v", pm)
	}

	// 2. Corrupt / invalid date strings
	apps := []model.CareerApplication{
		{Score: -1, Status: "unknown", Date: "invalid-date-format"},
		{Score: 6.0, Status: "interview", Date: "not-a-date"},
	}
	pm2 := ComputeProgressMetrics(apps)
	if pm2.ActiveApps != 2 {
		t.Fatalf("expected 2 active apps, got %d", pm2.ActiveApps)
	}
}
