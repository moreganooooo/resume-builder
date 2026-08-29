package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/screens"
)

func main() {
	t := theme.NewTheme("resume-builder")

	apps := []model.CareerApplication{
		{Company: "Acme Corp", Role: "Senior Engineer", Score: 4.5, Status: "applied", Date: "2026-07-10", ReportPath: "reports/acme.md", JobURL: "https://example.com"},
		{Company: "Beta Inc", Role: "Lead Designer", Score: 3.8, Status: "interview", Date: "2026-07-08", ReportPath: "reports/beta.md", JobURL: "https://example.com"},
		{Company: "Gamma LLC", Role: "Product Manager", Score: 4.1, Status: "offer", Date: "2026-07-05", ReportPath: "reports/gamma.md", JobURL: "https://example.com"},
		{Company: "Delta Co", Role: "Data Scientist", Score: 3.2, Status: "rejected", Date: "2026-07-01", ReportPath: "", JobURL: ""},
	}
	pm := screens.NewPipelineModel(t, apps, model.PipelineMetrics{
		Total:    4,
		AvgScore: 3.9,
		ByStatus: map[string]int{"applied": 1, "interview": 1, "offer": 1, "rejected": 1},
	}, "/tmp/career", 120, 40)

	jobRows := []model.JobRow{
		{Path: "a.json", Status: "Pending", Company: "Acme", Title: "Role A", Evaluation: model.Evaluation{CompositeScore: 4.5, FitScore: 4.0, InterviewOddsScore: 3.8, Why: "Strong fit", RecruiterRead: "Matches well", Recommendation: "Strong pursue", FitSubscores: map[string]float64{"functional_alignment": 5, "evidence_match": 4}}},
		{Path: "b.json", Status: "Completed", Company: "Beta", Title: "Role B", Evaluation: model.Evaluation{CompositeScore: 3.0, Recommendation: "Maybe consider"}},
	}
	jm := screens.NewJobsModel(t, jobRows, 120, 40)

	mdFile, err := os.CreateTemp("", "sample_report_*.md")
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to create sample report file: %v\n", err)
		os.Exit(1)
	}
	tmpFile := mdFile.Name()
	mdFile.Close()
	defer os.Remove(tmpFile)
	md := strings.Join([]string{
		"# Engineering Manager Report",
		"",
		"This is a **bold** statement with a [link](https://example.com) and some `inline code`.",
		"",
		"```go",
		"func main() {",
		"    fmt.Println(\"hello world\")",
		"}",
		"```",
		"",
		"---",
		"",
		"> This is a blockquote that should wrap nicely.",
		"",
		"## Evaluation Summary",
		"",
		"- Functional alignment: 5",
		"- Evidence match: 4",
		"- Narrative burden: 3",
	}, "\n")
	_ = os.WriteFile(tmpFile, []byte(md), 0644)

	vm := screens.NewViewerModel(t, tmpFile, "Acme Corp — Engineering Manager", 120, 40)

	progressMetrics := data.ComputeProgressMetrics(apps)
	progressModel := screens.NewProgressModel(t, progressMetrics, 120, 40)

	out, err := os.CreateTemp("", "dashboard_render_*.txt")
	if err != nil {
		fmt.Fprintf(os.Stderr, "failed to create render output file: %v\n", err)
		os.Exit(1)
	}
	defer out.Close()

	fmt.Fprintln(out, "=== PIPELINE ===")
	_, _ = out.WriteString(pm.View())
	_, _ = out.WriteString("\n\n=== PROGRESS ===\n")
	_, _ = out.WriteString(progressModel.View())
	_, _ = out.WriteString("\n\n=== JOBS ===\n")
	_, _ = out.WriteString(jm.View())
	_, _ = out.WriteString("\n\n=== VIEWER ===\n")
	_, _ = out.WriteString(vm.View())
	_, _ = out.WriteString("\n")

	// Report the temp file's path on stdout so callers (e.g.
	// scripts/capture_tui_visuals.py) don't have to guess a fixed name.
	fmt.Println(out.Name())
}
