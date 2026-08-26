package data

import (
	"fmt"
	"strings"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// Statuses that mean "this job is out of the pipeline". Archived jobs are
// a terminal state a person chose (jd_manager.archive_jd); expired ones
// were retired by the liveness checker. Neither belongs in a working
// pipeline view -- they used to render as scoreless rows indistinguishable
// from live applications.
var terminalStatuses = map[string]bool{
	"archived":  true,
	"expired":   true,
	"discarded": true,
	"skip":      true,
}

// IsTerminalStatus reports whether a job status means the job should be
// hidden from the pipeline.
func IsTerminalStatus(status string) bool {
	return terminalStatuses[strings.ToLower(strings.TrimSpace(status))]
}

// JobRowsToApplications adapts the JD evaluation export into the shape
// the Pipeline screen consumes.
//
// Pipeline and Browse & Manage Jobs used to read two unrelated sources --
// applications.md and the JSON export -- so the same job could appear in
// one and not the other, with different scores. This converter makes the
// export the single source of truth for both while leaving Pipeline's UI
// untouched.
//
// Terminal-status jobs are dropped. Ordering is preserved: the exporter
// already sorts best-score-first, and Pipeline applies its own sort on
// top.
func JobRowsToApplications(rows []model.JobRow) []model.CareerApplication {
	apps := make([]model.CareerApplication, 0, len(rows))

	for _, row := range rows {
		if IsTerminalStatus(row.Status) {
			continue
		}

		app := model.CareerApplication{
			Number:         len(apps) + 1,
			Company:        row.Company,
			Role:           row.Title,
			Status:         normalizeStatus(row),
			Score:          row.Evaluation.CompositeScore,
			JobURL:         row.SourceURL,
			Notes:          row.Description,
			SourcePlatform: row.SourcePlatform,
		}
		if row.Coverage != nil {
			app.Coverage = row.Coverage.Score
		}

		// ScoreRaw is what the row actually renders. Leaving it empty for
		// an unevaluated job is deliberate: showing "0.00" for "not scored
		// yet" is exactly the red-zero confusion this screen had before.
		if row.Evaluation.CompositeScore > 0 {
			app.ScoreRaw = fmt.Sprintf("%.2f", row.Evaluation.CompositeScore)
		}

		if row.Application != nil {
			if row.Application.AppliedAt != nil && *row.Application.AppliedAt != "" {
				app.Date = datePart(*row.Application.AppliedAt)
				app.LastContact = app.Date
			}
			if row.Application.StatusChangedAt != "" {
				app.LastContact = datePart(row.Application.StatusChangedAt)
			}
		}

		apps = append(apps, app)
	}

	return apps
}

// normalizeStatus prefers the application funnel status (Applied,
// Responded, Interviewing...) over the JD's file-location status, since
// the former is what a pipeline view is actually about.
func normalizeStatus(row model.JobRow) string {
	if row.Application != nil && row.Application.Status != "" {
		return row.Application.Status
	}
	return row.Status
}

// datePart trims an ISO timestamp to YYYY-MM-DD, the form Pipeline sorts
// and displays.
func datePart(timestamp string) string {
	if len(timestamp) >= 10 {
		return timestamp[:10]
	}
	return timestamp
}
