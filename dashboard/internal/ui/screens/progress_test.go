package screens

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func TestProgress_SparklineGeneration(t *testing.T) {
	values := []int{0, 2, 5, 1, 8, 3, 10}
	expected := " ▂▄▂▆▃█"
	actual := RenderSparkline(values)

	if actual != expected {
		t.Errorf("RenderSparkline(%v) = %q; want %q", values, actual, expected)
	}

	// Empty slice returns empty string
	if res := RenderSparkline(nil); res != "" {
		t.Errorf("expected empty string for nil input, got %q", res)
	}

	// Single element returns full block
	if res := RenderSparkline([]int{5}); res != "█" {
		t.Errorf("expected '█' for single element, got %q", res)
	}
}

func TestProgressFunnel_UnicodeEighthBlocks(t *testing.T) {
	// Full width 10, fraction 0.5 -> 5 full blocks + 5 spaces
	barHalf := RenderBlockBar(10, 0.5)
	if barHalf != "█████     " {
		t.Errorf("RenderBlockBar(10, 0.5) = %q; want %q", barHalf, "█████     ")
	}

	// Width 10, fraction 0.25 -> 2 full blocks + 0.5 char (4 eighths = ▌) + 7 spaces
	barQuarter := RenderBlockBar(10, 0.25)
	if barQuarter != "██▌       " {
		t.Errorf("RenderBlockBar(10, 0.25) = %q; want %q", barQuarter, "██▌       ")
	}

	// 0 fraction -> 10 spaces
	barZero := RenderBlockBar(10, 0.0)
	if barZero != "          " {
		t.Errorf("RenderBlockBar(10, 0.0) = %q; want %q", barZero, "          ")
	}

	// 1.0 fraction -> 10 full blocks
	barFull := RenderBlockBar(10, 1.0)
	if barFull != "██████████" {
		t.Errorf("RenderBlockBar(10, 1.0) = %q; want %q", barFull, "██████████")
	}
}

func TestProgressModel_Update_KeyPressMsg(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	metrics := model.ProgressMetrics{
		FunnelStages: []model.FunnelStage{
			{Label: "Discovered", Count: 100, Pct: 100},
			{Label: "Applied", Count: 40, Pct: 40},
			{Label: "Interview", Count: 10, Pct: 10},
			{Label: "Offer", Count: 2, Pct: 2},
		},
		WeeklyActivity: []model.WeekActivity{
			{Week: "2026-W10", Count: 2},
			{Week: "2026-W11", Count: 5},
			{Week: "2026-W12", Count: 8},
			{Week: "2026-W13", Count: 3},
		},
	}
	// Small height=10 forces content to exceed available viewport height, allowing scrolling
	m := NewProgressModel(th, metrics, 80, 10)

	// Pump tea.KeyPressMsg (E4 standardization)
	keyMsg := tea.KeyPressMsg{Code: 'j'}
	updated, _ := m.Update(keyMsg)

	if updated.scrollOffset != 1 {
		t.Errorf("expected scrollOffset=1 after 'j', got %d", updated.scrollOffset)
	}

	// Test Help overlay
	helpKey := tea.KeyPressMsg{Code: '?'}
	updatedHelp, _ := updated.Update(helpKey)
	if !updatedHelp.showHelp {
		t.Errorf("expected showHelp=true after '?'")
	}
}

func TestProgressModel_View_RendersAnalyticsSections(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	metrics := model.ProgressMetrics{
		FunnelStages: []model.FunnelStage{
			{Label: "Discovered", Count: 100, Pct: 100},
			{Label: "Applied", Count: 40, Pct: 40},
		},
		PlatformStats: []model.PlatformStat{
			{Platform: "Greenhouse", TotalRoles: 15, EvaluatedRoles: 12, AvgScore: 4.25},
			{Platform: "LinkedIn", TotalRoles: 8, EvaluatedRoles: 5, AvgScore: 3.80},
		},
		CompanyStats: []model.CompanyStat{
			{Company: "CyberCoders", TotalRoles: 6, EvaluatedRoles: 5, AvgScore: 3.65, IsAgency: true},
			{Company: "Stripe", TotalRoles: 3, EvaluatedRoles: 3, AvgScore: 4.80, IsAgency: false},
		},
		Quadrants: model.QuadrantCounts{
			ReadyToApply:        5,
			HighFitLowCoverage:  3,
			OverCoveredLowerFit: 2,
			Deprioritized:       4,
		},
		HighFitLowCoverageRoles: []model.HighFitLowCoverageRole{
			{Title: "Lead Architect", Company: "Stripe", Score: 4.8, Coverage: 55.0},
		},
	}

	// Each mode renders its own sections and only its own: the whole point
	// of the split is that neither screen is a wall of everything.
	progress := NewProgressModel(th, metrics, 100, 200)
	insights := progress.WithMode(ModeInsights)

	// Stripped: the title is a per-rune gradient, so a raw substring match
	// would never find it.
	progressView, insightsView := ansi.Strip(progress.View()), ansi.Strip(insights.View())
	if progressView == "" || insightsView == "" {
		t.Fatalf("expected non-empty View output from both modes")
	}

	cases := []struct {
		name    string
		view    string
		present []string
		absent  []string
	}{
		{
			name: "progress",
			view: progressView,
			present: []string{
				"SEARCH PROGRESS",
				"Top Employers & Staffing Detection",
				"Score vs. Bullet Coverage (High-ROI Gap Radar)",
				"CyberCoders",
				"[AGENCY]",
				"[DIRECT]",
				"Write Bullets For (High Fit, Low Coverage):",
				"Lead Architect",
			},
			absent: []string{"Source-Platform Yield & Quality", "INSIGHTS"},
		},
		{
			name: "insights",
			view: insightsView,
			present: []string{
				"INSIGHTS",
				"Source-Platform Yield & Quality",
				"Greenhouse",
			},
			absent: []string{"Top Employers & Staffing Detection", "SEARCH PROGRESS"},
		},
	}

	for _, tc := range cases {
		for _, want := range tc.present {
			if !containsSubstring(tc.view, want) {
				t.Errorf("%s: expected View() to contain %q", tc.name, want)
			}
		}
		for _, notWant := range tc.absent {
			if containsSubstring(tc.view, notWant) {
				t.Errorf("%s: expected View() not to contain %q", tc.name, notWant)
			}
		}
	}
}

func containsSubstring(s, substr string) bool {
	return strings.Contains(s, substr)
}
