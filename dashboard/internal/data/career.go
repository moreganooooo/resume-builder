package data

import (
	"fmt"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

var (
	reReportLink     = regexp.MustCompile(`\[(\d+)\]\(([^)]+)\)`)
	reScoreValue     = regexp.MustCompile(`(\d+\.?\d*)/5`)
	reArchetype      = regexp.MustCompile(`(?i)\*\*Arquetipo(?:\s+detectado)?\*\*\s*\|\s*(.+)`)
	reTlDr           = regexp.MustCompile(`(?i)\*\*TL;DR\*\*\s*\|\s*(.+)`)
	reTlDrColon      = regexp.MustCompile(`(?i)\*\*TL;DR:\*\*\s*(.+)`)
	reRemote         = regexp.MustCompile(`(?i)\*\*Remote\*\*\s*\|\s*(.+)`)
	reComp           = regexp.MustCompile(`(?i)\*\*Comp\*\*\s*\|\s*(.+)`)
	reArchetypeColon = regexp.MustCompile(`(?i)\*\*Arquetipo:\*\*\s*(.+)`)
	reReportURL      = regexp.MustCompile(`(?m)^\*\*URL:\*\*\s*(https?://\S+)`)
	reBatchID        = regexp.MustCompile(`(?m)^\*\*Batch ID:\*\*\s*(\d+)`)
	// resume-builder's Link column ("[Apply](job-url)", see
	// jd_manager.append_application_row) -- a real posting URL, not a
	// [N](path) report reference like reReportLink expects.
	reApplyLink = regexp.MustCompile(`\[[^\]]*\]\((https?://[^)]+)\)`)
)

// resolveReportPath converts a report link from the tracker into a path
// relative to careerOpsPath. Links are normally relative to the tracker
// file's own directory (see merge-tracker.mjs link normalization, #760);
// legacy trackers may still carry root-relative links, so fall back to the
// raw link when the tracker-relative resolution does not exist on disk.
func resolveReportPath(careerOpsPath, trackerPath, link string) string {
	resolved := filepath.Join(filepath.Dir(trackerPath), link)
	if _, err := os.Stat(resolved); err != nil {
		legacy := filepath.Join(careerOpsPath, link)
		if _, err2 := os.Stat(legacy); err2 == nil {
			resolved = legacy
		}
	}
	if rel, err := filepath.Rel(careerOpsPath, resolved); err == nil {
		return rel
	}
	return link
}

// ParseApplications reads applications.md and returns parsed applications.
// It tries both {path}/applications.md and {path}/data/applications.md for compatibility.
func ParseApplications(careerOpsPath string) []model.CareerApplication {
	filePath := filepath.Join(careerOpsPath, "applications.md")
	content, err := os.ReadFile(filePath)
	if err != nil {
		// Fallback: try data/ subdirectory
		filePath = filepath.Join(careerOpsPath, "data", "applications.md")
		content, err = os.ReadFile(filePath)
		if err != nil {
			return nil
		}
	}

	lines := strings.Split(string(content), "\n")
	apps := make([]model.CareerApplication, 0)
	num := 0

	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "# ") || strings.HasPrefix(line, "|---") || strings.HasPrefix(line, "| #") {
			continue
		}
		if !strings.HasPrefix(line, "|") {
			continue
		}

		// Detect delimiter: if line contains tabs, use tab-aware splitting
		var fields []string
		if strings.Contains(line, "\t") {
			// Mixed format: starts with "| " then tab-separated
			line = strings.TrimPrefix(line, "|")
			line = strings.TrimSpace(line)
			parts := strings.Split(line, "\t")
			for _, p := range parts {
				fields = append(fields, strings.TrimSpace(strings.Trim(p, "|")))
			}
		} else {
			// Pure pipe format
			line = strings.Trim(line, "|")
			parts := strings.Split(line, "|")
			for _, p := range parts {
				fields = append(fields, strings.TrimSpace(p))
			}
		}

		if len(fields) < 8 {
			continue
		}

		num++
		trackerNumber := num
		if parsedNumber, err := strconv.Atoi(fields[0]); err == nil {
			trackerNumber = parsedNumber
		}
		app := model.CareerApplication{
			Number:  trackerNumber,
			Date:    fields[1],
			Company: fields[2],
			Role:    fields[3],
			Status:  fields[5],
			HasPDF:  strings.Contains(fields[6], "\u2705"),
		}

		// Parse score (field 4 = Score column)
		app.ScoreRaw = fields[4]
		if sm := reScoreValue.FindStringSubmatch(fields[4]); sm != nil {
			app.Score, _ = strconv.ParseFloat(sm[1], 64)
		}

		// Two tracker column shapes exist:
		//   career-ops   (9 cols):  # Date Company Role Score Status PDF ReportLink        Notes
		//   resume-builder (10 cols): # Date Company Role Score Status PDF Link(apply URL) Report(recommendation) Notes
		// resume-builder doesn't write standalone report files the way
		// career-ops does (its evaluation lives on the JD's own JSON,
		// not a linked markdown file), so field 7 there is a real job
		// posting URL, not a [N](path) report reference, and the
		// recommendation label sits in its own column rather than
		// getting folded into notes.
		if len(fields) >= 10 {
			if am := reApplyLink.FindStringSubmatch(fields[7]); am != nil {
				app.JobURL = am[1]
			}
			recommendation := fields[8]
			notes := fields[9]
			switch {
			case recommendation == "" || recommendation == "—":
				app.Notes = notes
			case notes == "":
				app.Notes = fmt.Sprintf("[%s]", recommendation)
			default:
				app.Notes = fmt.Sprintf("[%s] %s", recommendation, notes)
			}
		} else {
			// Parse report link. Tracker links are written relative to the
			// tracker file itself (e.g. ../reports/... when the tracker lives
			// in data/), so resolve against the tracker's directory and
			// normalize back to a careerOpsPath-relative path, which is what
			// every consumer joins against. Legacy root-relative links are
			// kept as a fallback when the resolved file does not exist.
			if rm := reReportLink.FindStringSubmatch(fields[7]); rm != nil {
				app.ReportNumber = rm[1]
				app.ReportPath = resolveReportPath(careerOpsPath, filePath, rm[2])
			}
			if len(fields) > 8 {
				app.Notes = fields[8]
			}
		}

		// Lift location / work mode / pay / last-contact out of the notes free-text
		deriveNoteFields(&app)

		apps = append(apps, app)
	}

	// Enrich with job URLs using 5-tier strategy:
	// 1. **URL:** field in report header (newest reports)
	// 2. **Batch ID:** in report -> batch-input.tsv URL lookup
	// 3. report_num -> batch-state completed mapping (legacy)
	// 4. scan-history.tsv (pipeline scan entries matched by company+role)
	// 5. company name fallback from batch-input.tsv
	batchURLs := loadBatchInputURLs(careerOpsPath)
	reportNumURLs := loadJobURLs(careerOpsPath)

	for i := range apps {
		if apps[i].ReportPath == "" {
			continue
		}
		fullReport := filepath.Join(careerOpsPath, apps[i].ReportPath)
		reportContent, err := os.ReadFile(fullReport)
		if err != nil {
			continue
		}
		header := string(reportContent)
		// Only scan the header (first 1000 bytes) for speed
		if len(header) > 1000 {
			header = header[:1000]
		}

		// Strategy 1: **URL:** in report
		if m := reReportURL.FindStringSubmatch(header); m != nil {
			apps[i].JobURL = m[1]
			continue
		}

		// Strategy 2: **Batch ID:** -> batch-input.tsv
		if m := reBatchID.FindStringSubmatch(header); m != nil {
			if url, ok := batchURLs[m[1]]; ok {
				apps[i].JobURL = url
				continue
			}
		}

		// Strategy 3: report_num -> batch-state completed mapping
		if reportNumURLs != nil {
			if url, ok := reportNumURLs[apps[i].ReportNumber]; ok {
				apps[i].JobURL = url
				continue
			}
		}
	}

	// Strategy 4: scan-history.tsv (pipeline scan entries matched by company+role)
	enrichFromScanHistory(careerOpsPath, apps)

	// Strategy 5: company name fallback from batch-input.tsv
	enrichAppURLsByCompany(careerOpsPath, apps)

	return apps
}

// loadBatchInputURLs reads batch-input.tsv and returns a map of batch ID -> job URL.
func loadBatchInputURLs(careerOpsPath string) map[string]string {
	inputPath := filepath.Join(careerOpsPath, "batch", "batch-input.tsv")
	inputData, err := os.ReadFile(inputPath)
	if err != nil {
		return nil
	}
	result := make(map[string]string)
	for _, line := range strings.Split(string(inputData), "\n") {
		fields := strings.Split(line, "\t")
		if len(fields) < 4 || fields[0] == "id" {
			continue
		}
		id := fields[0]
		notes := fields[3]
		// Extract real job URL from notes: "Title @ Company | Match% | https://actual-url"
		if idx := strings.LastIndex(notes, "| "); idx >= 0 {
			u := strings.TrimSpace(notes[idx+2:])
			if strings.HasPrefix(u, "http") {
				result[id] = u
				continue
			}
		}
		// Fallback: use JackJill URL
		if strings.HasPrefix(fields[1], "http") {
			result[id] = fields[1]
		}
	}
	return result
}

// batchEntry holds parsed data from batch-input.tsv.
type batchEntry struct {
	id      string
	url     string
	company string
	role    string
}

// loadJobURLs reads batch TSV files and returns a map of report_num -> job URL.
// Uses two strategies: (1) report_num mapping for completed jobs, (2) company name
// matching as fallback for failed/missing jobs.
func loadJobURLs(careerOpsPath string) map[string]string {
	// Read batch-input.tsv: id \t url \t source \t notes
	inputPath := filepath.Join(careerOpsPath, "batch", "batch-input.tsv")
	inputData, err := os.ReadFile(inputPath)
	if err != nil {
		return nil
	}

	// Parse batch-input: extract job URL, company, and role from notes
	entries := make(map[string]batchEntry) // keyed by id
	for _, line := range strings.Split(string(inputData), "\n") {
		fields := strings.Split(line, "\t")
		if len(fields) < 4 || fields[0] == "id" {
			continue
		}
		e := batchEntry{id: fields[0]}
		notes := fields[3]

		// Extract URL from notes: "Title @ Company | Match% | https://actual-url"
		if idx := strings.LastIndex(notes, "| "); idx >= 0 {
			u := strings.TrimSpace(notes[idx+2:])
			if strings.HasPrefix(u, "http") {
				e.url = u
			}
		}
		// Fallback: use JackJill URL from field 1
		if e.url == "" && strings.HasPrefix(fields[1], "http") {
			e.url = fields[1]
		}

		// Extract company and role: "Role @ Company | Match% | URL"
		notesPart := notes
		if pipeIdx := strings.Index(notesPart, " | "); pipeIdx >= 0 {
			notesPart = notesPart[:pipeIdx]
		}
		if atIdx := strings.LastIndex(notesPart, " @ "); atIdx >= 0 {
			e.role = strings.TrimSpace(notesPart[:atIdx])
			e.company = strings.TrimSpace(notesPart[atIdx+3:])
		}

		if e.url != "" {
			entries[fields[0]] = e
		}
	}

	// Read batch-state.tsv: id \t url \t status \t ... \t report_num \t ...
	statePath := filepath.Join(careerOpsPath, "batch", "batch-state.tsv")
	stateData, err := os.ReadFile(statePath)
	if err != nil {
		return nil
	}

	// Strategy 1: map report_num -> URL only for COMPLETED jobs
	reportToURL := make(map[string]string)
	for _, line := range strings.Split(string(stateData), "\n") {
		fields := strings.Split(line, "\t")
		if len(fields) < 6 || fields[0] == "id" {
			continue
		}
		id := fields[0]
		status := fields[2]
		reportNum := fields[5]
		if status != "completed" || reportNum == "" || reportNum == "-" {
			continue
		}
		if e, ok := entries[id]; ok {
			reportToURL[reportNum] = e.url
			if len(reportNum) < 3 {
				reportToURL[fmt.Sprintf("%03s", reportNum)] = e.url
			}
		}
	}

	return reportToURL
}

// enrichFromScanHistory fills JobURL from scan-history.tsv by matching company name.
func enrichFromScanHistory(careerOpsPath string, apps []model.CareerApplication) {
	scanPath := filepath.Join(careerOpsPath, "scan-history.tsv")
	scanData, err := os.ReadFile(scanPath)
	if err != nil {
		return
	}

	// Build company -> URL index from scan-history
	type scanEntry struct {
		url     string
		company string
		title   string
	}
	byCompany := make(map[string][]scanEntry)
	for _, line := range strings.Split(string(scanData), "\n") {
		fields := strings.Split(line, "\t")
		if len(fields) < 5 || fields[0] == "url" {
			continue
		}
		url := fields[0]
		company := fields[4]
		title := fields[3]
		if url == "" || !strings.HasPrefix(url, "http") {
			continue
		}
		key := normalizeCompany(company)
		byCompany[key] = append(byCompany[key], scanEntry{url: url, company: company, title: title})
	}

	for i := range apps {
		if apps[i].JobURL != "" {
			continue
		}
		key := normalizeCompany(apps[i].Company)
		matches := byCompany[key]
		if len(matches) == 1 {
			apps[i].JobURL = matches[0].url
		} else if len(matches) > 1 {
			// Multiple entries: pick best role match
			appRole := strings.ToLower(apps[i].Role)
			best := matches[0].url
			bestScore := 0
			for _, m := range matches {
				score := 0
				mTitle := strings.ToLower(m.title)
				for _, word := range strings.Fields(appRole) {
					if len(word) > 2 && strings.Contains(mTitle, word) {
						score++
					}
				}
				if score > bestScore {
					bestScore = score
					best = m.url
				}
			}
			apps[i].JobURL = best
		}
	}
}

// normalizeCompany strips common suffixes and lowercases a company name.
func normalizeCompany(name string) string {
	s := strings.ToLower(strings.TrimSpace(name))
	for _, suffix := range []string{" inc.", " inc", " llc", " ltd", " corp", " corporation", " technologies", " technology", " group", " co."} {
		s = strings.TrimSuffix(s, suffix)
	}
	return strings.TrimSpace(s)
}

// enrichAppURLsByCompany fills in JobURL for apps that didn't get one via report_num mapping.
// It matches by company name from batch-input.tsv notes.
func enrichAppURLsByCompany(careerOpsPath string, apps []model.CareerApplication) {
	inputPath := filepath.Join(careerOpsPath, "batch", "batch-input.tsv")
	inputData, err := os.ReadFile(inputPath)
	if err != nil {
		return
	}

	// Build company -> []entry index
	type entry struct {
		role string
		url  string
	}
	byCompany := make(map[string][]entry)
	for _, line := range strings.Split(string(inputData), "\n") {
		fields := strings.Split(line, "\t")
		if len(fields) < 4 || fields[0] == "id" {
			continue
		}
		notes := fields[3]
		var url string
		if idx := strings.LastIndex(notes, "| "); idx >= 0 {
			u := strings.TrimSpace(notes[idx+2:])
			if strings.HasPrefix(u, "http") {
				url = u
			}
		}
		if url == "" && strings.HasPrefix(fields[1], "http") {
			url = fields[1]
		}
		if url == "" {
			continue
		}
		notesPart := notes
		if pipeIdx := strings.Index(notesPart, " | "); pipeIdx >= 0 {
			notesPart = notesPart[:pipeIdx]
		}
		if atIdx := strings.LastIndex(notesPart, " @ "); atIdx >= 0 {
			role := strings.TrimSpace(notesPart[:atIdx])
			company := strings.TrimSpace(notesPart[atIdx+3:])
			key := normalizeCompany(company)
			byCompany[key] = append(byCompany[key], entry{role: role, url: url})
		}
	}

	for i := range apps {
		if apps[i].JobURL != "" {
			continue
		}
		key := normalizeCompany(apps[i].Company)
		matches := byCompany[key]
		if len(matches) == 1 {
			apps[i].JobURL = matches[0].url
		} else if len(matches) > 1 {
			// Multiple entries for same company: pick best role match
			appRole := strings.ToLower(apps[i].Role)
			best := matches[0].url
			bestScore := 0
			for _, m := range matches {
				score := 0
				mRole := strings.ToLower(m.role)
				// Count matching words
				for _, word := range strings.Fields(appRole) {
					if len(word) > 2 && strings.Contains(mRole, word) {
						score++
					}
				}
				if score > bestScore {
					bestScore = score
					best = m.url
				}
			}
			apps[i].JobURL = best
		}
	}
}

// ComputeMetrics calculates aggregate metrics from applications.
func ComputeMetrics(apps []model.CareerApplication) model.PipelineMetrics {
	m := model.PipelineMetrics{
		Total:    len(apps),
		ByStatus: make(map[string]int),
	}

	var totalScore float64
	var scored int

	for _, app := range apps {
		status := NormalizeStatus(app.Status)
		m.ByStatus[status]++

		if app.Score > 0 {
			totalScore += app.Score
			scored++
			if app.Score > m.TopScore {
				m.TopScore = app.Score
			}
		}
		if app.HasPDF {
			m.WithPDF++
		}
		if status != "skip" && status != "rejected" && status != "discarded" {
			m.Actionable++
		}
	}

	if scored > 0 {
		m.AvgScore = totalScore / float64(scored)
	}

	return m
}

// NormalizeStatus normalizes raw status text to a canonical form.
// Aliases match states.yml -- keep in sync with career-ops/states.yml
func NormalizeStatus(raw string) string {
	// Strip markdown bold and trailing dates
	s := strings.ReplaceAll(raw, "**", "")
	s = strings.TrimSpace(strings.ToLower(s))
	// Strip trailing date (e.g., "aplicado 2026-03-12")
	if idx := strings.Index(s, " 202"); idx > 0 {
		s = strings.TrimSpace(s[:idx])
	}

	switch {
	// Most restrictive first — accepts both English and Spanish
	case strings.Contains(s, "no aplicar") || strings.Contains(s, "no_aplicar") || s == "skip" || strings.Contains(s, "geo blocker"):
		return "skip"
	case strings.Contains(s, "interview") || strings.Contains(s, "entrevista"):
		return "interview"
	case s == "offer" || strings.Contains(s, "offer"):
		return "offer"
	case strings.Contains(s, "responded") || strings.Contains(s, "respondido"):
		return "responded"
	case strings.Contains(s, "applied") || strings.Contains(s, "aplicado") || s == "enviada" || s == "aplicada" || s == "sent":
		return "applied"
	case strings.Contains(s, "rejected") || strings.Contains(s, "rechazado") || s == "rechazada":
		return "rejected"
	case strings.Contains(s, "discarded") || strings.Contains(s, "descartado") || s == "descartada" || s == "cerrada" || s == "cancelada" ||
		strings.HasPrefix(s, "duplicado") || strings.HasPrefix(s, "dup"):
		return "discarded"
	case strings.Contains(s, "evaluated") || strings.Contains(s, "evaluada") || s == "condicional" || s == "hold" || s == "monitor" || s == "evaluar" || s == "verificar":
		return "evaluated"
	default:
		return s
	}
}

// reportSummaryCache caches LoadReportSummary's result per resolved file
// path, keyed against the file's mtime so an edited report still gets
// re-read. Only ever touched from bubbletea's single Update() goroutine
// (or the one-time startup loop in main() that runs before it) -- no
// locking needed. Not persisted across process launches; it only avoids
// redundant reads within one dashboard session -- e.g. main()'s startup
// batch enrichment loop and a later PipelineLoadReportMsg lazy-load
// landing on the same report path.
var reportSummaryCache = map[string]struct {
	modTime                       time.Time
	archetype, tldr, remote, comp string
}{}

// LoadReportSummary extracts key fields from a report file.
func LoadReportSummary(careerOpsPath, reportPath string) (archetype, tldr, remote, comp string) {
	fullPath := filepath.Join(careerOpsPath, reportPath)

	info, statErr := os.Stat(fullPath)
	if statErr == nil {
		if cached, ok := reportSummaryCache[fullPath]; ok && cached.modTime.Equal(info.ModTime()) {
			return cached.archetype, cached.tldr, cached.remote, cached.comp
		}
	}

	content, err := os.ReadFile(fullPath)
	if err != nil {
		return
	}
	text := string(content)

	if m := reArchetype.FindStringSubmatch(text); m != nil {
		archetype = cleanTableCell(m[1])
	} else if m := reArchetypeColon.FindStringSubmatch(text); m != nil {
		archetype = cleanTableCell(m[1])
	}

	// Try table-format TL;DR first (most reports), then colon format
	if m := reTlDr.FindStringSubmatch(text); m != nil {
		tldr = cleanTableCell(m[1])
	} else if m := reTlDrColon.FindStringSubmatch(text); m != nil {
		tldr = cleanTableCell(m[1])
	}

	if m := reRemote.FindStringSubmatch(text); m != nil {
		remote = cleanTableCell(m[1])
	}

	if m := reComp.FindStringSubmatch(text); m != nil {
		comp = cleanTableCell(m[1])
	}

	// Truncate long fields
	if len(tldr) > 120 {
		tldr = tldr[:117] + "..."
	}

	if statErr == nil {
		reportSummaryCache[fullPath] = struct {
			modTime                       time.Time
			archetype, tldr, remote, comp string
		}{info.ModTime(), archetype, tldr, remote, comp}
	}

	return
}

// UpdateApplicationStatus updates the status of an application in applications.md.
func UpdateApplicationStatus(careerOpsPath string, app model.CareerApplication, newStatus string) error {
	filePath := filepath.Join(careerOpsPath, "applications.md")
	content, err := os.ReadFile(filePath)
	if err != nil {
		filePath = filepath.Join(careerOpsPath, "data", "applications.md")
		content, err = os.ReadFile(filePath)
		if err != nil {
			return err
		}
	}

	lines := strings.Split(string(content), "\n")
	found := false

	for i, line := range lines {
		if !strings.HasPrefix(strings.TrimSpace(line), "|") {
			continue
		}
		// Match by report number
		if app.ReportNumber != "" && strings.Contains(line, fmt.Sprintf("[%s]", app.ReportNumber)) {
			// Replace the status field
			lines[i] = replaceStatusInLine(line, app.Status, newStatus)
			found = true
			break
		}
	}

	if !found {
		return fmt.Errorf("application not found: report %s", app.ReportNumber)
	}

	return os.WriteFile(filePath, []byte(strings.Join(lines, "\n")), 0644)
}

// replaceStatusInLine replaces the Status column (0-based index 5: #, Date,
// Company, Role, Score, Status, ...) in a markdown table line. A line-wide
// substring replace of oldStatus is not safe here -- it can rewrite the
// wrong field (e.g. a company name like "Applied Intuition") whenever
// oldStatus's text also happens to appear earlier in the line, so this
// locates and replaces the actual Status cell instead.
func replaceStatusInLine(line, oldStatus, newStatus string) string {
	const statusColumn = 5

	// parts[0] is the text before the line's leading "|" (normally empty),
	// so table column N lands at parts[N+1].
	parts := strings.Split(line, "|")
	idx := statusColumn + 1
	if idx >= len(parts) {
		// Malformed/unexpected line shape -- fall back to the old
		// best-effort behavior rather than silently doing nothing.
		return strings.Replace(line, oldStatus, newStatus, 1)
	}

	cell := parts[idx]
	if strings.TrimSpace(cell) != oldStatus {
		// The cell doesn't hold what we expected to find; don't guess at
		// which other field might match instead.
		return strings.Replace(line, oldStatus, newStatus, 1)
	}

	// Preserve the cell's original surrounding whitespace so column
	// alignment in the source file doesn't shift.
	afterLeading := strings.TrimLeft(cell, " \t")
	leading := cell[:len(cell)-len(afterLeading)]
	trimmed := strings.TrimRight(afterLeading, " \t")
	trailing := afterLeading[len(trimmed):]
	parts[idx] = leading + newStatus + trailing

	return strings.Join(parts, "|")
}

// cleanTableCell removes trailing pipes and whitespace from a table cell value.
func cleanTableCell(s string) string {
	s = strings.TrimSpace(s)
	s = strings.TrimRight(s, "|")
	return strings.TrimSpace(s)
}

// StatusPriority returns the sort priority for a status (lower = higher priority).
func StatusPriority(status string) int {
	switch NormalizeStatus(status) {
	case "interview":
		return 0
	case "offer":
		return 1
	case "responded":
		return 2
	case "applied":
		return 3
	case "evaluated":
		return 4
	case "skip":
		return 5
	case "rejected":
		return 6
	case "discarded":
		return 7
	default:
		return 8
	}
}

// ComputeProgressMetrics computes progress-oriented analytics from applications.
func ComputeProgressMetrics(apps []model.CareerApplication) model.ProgressMetrics {
	pm := model.ProgressMetrics{
		DailyActivity: make(map[string]int),
	}

	// Count by normalized status
	statusCounts := make(map[string]int)
	var totalScore float64
	var scored int

	for _, app := range apps {
		norm := NormalizeStatus(app.Status)
		statusCounts[norm]++

		if app.Score > 0 {
			totalScore += app.Score
			scored++
			if app.Score > pm.TopScore {
				pm.TopScore = app.Score
			}
		}

		if norm == "offer" {
			pm.TotalOffers++
		}
		if norm != "skip" && norm != "rejected" && norm != "discarded" {
			pm.ActiveApps++
		}
	}

	if scored > 0 {
		pm.AvgScore = totalScore / float64(scored)
	}

	// Funnel: each stage counts all apps that reached at least that stage.
	// An app in "interview" has passed through evaluated -> applied -> responded -> interview.
	total := len(apps)
	applied := statusCounts["applied"] + statusCounts["responded"] + statusCounts["interview"] + statusCounts["offer"] + statusCounts["rejected"]
	responded := statusCounts["responded"] + statusCounts["interview"] + statusCounts["offer"]
	interview := statusCounts["interview"] + statusCounts["offer"]
	offer := statusCounts["offer"]

	pm.FunnelStages = []model.FunnelStage{
		{Label: "Evaluated", Count: total, Pct: 100.0},
		{Label: "Applied", Count: applied, Pct: safePct(applied, total)},
		{Label: "Responded", Count: responded, Pct: safePct(responded, applied)},
		{Label: "Interview", Count: interview, Pct: safePct(interview, applied)},
		{Label: "Offer", Count: offer, Pct: safePct(offer, applied)},
	}

	// Rates (relative to applied)
	if applied > 0 {
		pm.ResponseRate = float64(responded) / float64(applied) * 100
		pm.InterviewRate = float64(interview) / float64(applied) * 100
		pm.OfferRate = float64(offer) / float64(applied) * 100
	}

	// Score distribution
	buckets := [5]int{} // 0: 4.5-5.0, 1: 4.0-4.4, 2: 3.5-3.9, 3: 3.0-3.4, 4: <3.0
	for _, app := range apps {
		if app.Score <= 0 {
			continue
		}
		switch {
		case app.Score >= 4.5:
			buckets[0]++
		case app.Score >= 4.0:
			buckets[1]++
		case app.Score >= 3.5:
			buckets[2]++
		case app.Score >= 3.0:
			buckets[3]++
		default:
			buckets[4]++
		}
	}
	pm.ScoreBuckets = []model.ScoreBucket{
		{Label: "4.5-5.0", Count: buckets[0]},
		{Label: "4.0-4.4", Count: buckets[1]},
		{Label: "3.5-3.9", Count: buckets[2]},
		{Label: "3.0-3.4", Count: buckets[3]},
		{Label: "  <3.0", Count: buckets[4]},
	}

	// Weekly activity: group by ISO week from Date field, show last 8 weeks.
	weekCounts := make(map[string]int)
	for _, app := range apps {
		if app.Date == "" {
			continue
		}
		t, err := time.Parse("2006-01-02", app.Date)
		if err != nil {
			continue
		}
		pm.DailyActivity[t.Format("2006-01-02")]++
		year, week := t.ISOWeek()
		key := fmt.Sprintf("%d-W%02d", year, week)
		weekCounts[key]++
	}

	// Sort weeks and take last 8
	var weeks []string
	for w := range weekCounts {
		weeks = append(weeks, w)
	}
	sort.Strings(weeks)
	if len(weeks) > 8 {
		weeks = weeks[len(weeks)-8:]
	}

	for _, w := range weeks {
		pm.WeeklyActivity = append(pm.WeeklyActivity, model.WeekActivity{
			Week:  w,
			Count: weekCounts[w],
		})
	}

	// Populate ScoreTrend and VolumeTrend
	var allWeeks []string
	for w := range weekCounts {
		allWeeks = append(allWeeks, w)
	}
	sort.Strings(allWeeks)
	for _, w := range allWeeks {
		pm.VolumeTrend = append(pm.VolumeTrend, weekCounts[w])
	}

	type dateScore struct {
		date  time.Time
		score float64
	}
	var scores []dateScore
	for _, app := range apps {
		if app.Score > 0 && app.Date != "" {
			t, err := time.Parse("2006-01-02", app.Date)
			if err == nil {
				scores = append(scores, dateScore{t, app.Score})
			}
		}
	}
	sort.Slice(scores, func(i, j int) bool {
		return scores[i].date.Before(scores[j].date)
	})
	for _, s := range scores {
		// scale score 0-5 to 0-50 for sparkline integer requirement
		pm.ScoreTrend = append(pm.ScoreTrend, int(s.score*10))
	}

	// Platform breakdown
	type platAccum struct {
		total          int
		evaluated      int
		scoreSum       float64
		t45            int
		t40            int
		t35            int
		tsub           int
		topRoleTitle   string
		topRoleCompany string
		topRoleScore   float64
	}
	platforms := make(map[string]*platAccum)

	// Company concentration
	type compAccum struct {
		total      int
		evaluated  int
		scoreSum   float64
		sampleRole string
	}
	companies := make(map[string]*compAccum)

	for _, app := range apps {
		plat := NormalizePlatformName(app.SourcePlatform)
		pa, ok := platforms[plat]
		if !ok {
			pa = &platAccum{}
			platforms[plat] = pa
		}
		pa.total++

		comp := strings.TrimSpace(app.Company)
		if comp == "" {
			comp = "Unknown Company"
		}
		ca, ok := companies[comp]
		if !ok {
			ca = &compAccum{sampleRole: app.Role}
			companies[comp] = ca
		}
		ca.total++

		if app.Score > 0 {
			pa.evaluated++
			pa.scoreSum += app.Score
			ca.evaluated++
			ca.scoreSum += app.Score

			switch {
			case app.Score >= 4.5:
				pa.t45++
			case app.Score >= 4.0:
				pa.t40++
			case app.Score >= 3.5:
				pa.t35++
			default:
				pa.tsub++
			}

			if app.Score > pa.topRoleScore {
				pa.topRoleScore = app.Score
				pa.topRoleTitle = app.Role
				pa.topRoleCompany = app.Company
			}
		}

		// Quadrants
		if app.Score > 0 && app.Coverage > 0 {
			// Normalise 0-1 coverage fractions to 0-100 percentage
			cov := app.Coverage
			if cov <= 1.0 {
				cov *= 100.0
			}

			switch {
			case app.Score >= 4.0 && cov >= 70.0:
				pm.Quadrants.ReadyToApply++
			case app.Score >= 4.0 && cov < 70.0:
				pm.Quadrants.HighFitLowCoverage++
				pm.HighFitLowCoverageRoles = append(pm.HighFitLowCoverageRoles, model.HighFitLowCoverageRole{
					Title:    app.Role,
					Company:  app.Company,
					Score:    app.Score,
					Coverage: cov,
				})
			case app.Score < 4.0 && cov >= 70.0:
				pm.Quadrants.OverCoveredLowerFit++
			default:
				pm.Quadrants.Deprioritized++
			}
		}
	}

	for pName, pa := range platforms {
		avg := 0.0
		if pa.evaluated > 0 {
			avg = pa.scoreSum / float64(pa.evaluated)
		}
		pm.PlatformStats = append(pm.PlatformStats, model.PlatformStat{
			Platform:       pName,
			TotalRoles:     pa.total,
			EvaluatedRoles: pa.evaluated,
			AvgScore:       avg,
			Tier45Plus:     pa.t45,
			Tier40to44:     pa.t40,
			Tier35to39:     pa.t35,
			TierSub35:      pa.tsub,
			TopRoleTitle:   pa.topRoleTitle,
			TopRoleCompany: pa.topRoleCompany,
			TopRoleScore:   pa.topRoleScore,
		})
	}
	sort.Slice(pm.PlatformStats, func(i, j int) bool {
		if pm.PlatformStats[i].TotalRoles != pm.PlatformStats[j].TotalRoles {
			return pm.PlatformStats[i].TotalRoles > pm.PlatformStats[j].TotalRoles
		}
		return pm.PlatformStats[i].AvgScore > pm.PlatformStats[j].AvgScore
	})

	for cName, ca := range companies {
		avg := 0.0
		if ca.evaluated > 0 {
			avg = ca.scoreSum / float64(ca.evaluated)
		}
		pm.CompanyStats = append(pm.CompanyStats, model.CompanyStat{
			Company:        cName,
			TotalRoles:     ca.total,
			EvaluatedRoles: ca.evaluated,
			AvgScore:       avg,
			IsAgency:       IsStaffingAgency(cName),
			SampleRole:     ca.sampleRole,
		})
	}
	sort.Slice(pm.CompanyStats, func(i, j int) bool {
		if pm.CompanyStats[i].TotalRoles != pm.CompanyStats[j].TotalRoles {
			return pm.CompanyStats[i].TotalRoles > pm.CompanyStats[j].TotalRoles
		}
		return pm.CompanyStats[i].AvgScore > pm.CompanyStats[j].AvgScore
	})
	if len(pm.CompanyStats) > 12 {
		pm.CompanyStats = pm.CompanyStats[:12]
	}

	// 1. Funnel Drill-Down Stages
	highFitCount := 0
	for _, app := range apps {
		if app.Score >= 4.0 {
			highFitCount++
		}
	}
	pm.FunnelDrilldown = []model.FunnelDrilldownStage{
		{Stage: "1. Discovered", Volume: total, Conversion: 100.0, Friction: "Initial raw posting pool"},
		{Stage: "2. Evaluated", Volume: scored, Conversion: safePct(scored, total), Friction: fmt.Sprintf("%d pre-filtered", total-scored)},
		{Stage: "3. High-Fit (≥4.0)", Volume: highFitCount, Conversion: safePct(highFitCount, scored), Friction: fmt.Sprintf("%d lower fit (<4.0)", scored-highFitCount)},
		{Stage: "4. Applied", Volume: applied, Conversion: safePct(applied, highFitCount), Friction: fmt.Sprintf("%d high-fit pending apply", max(0, highFitCount-applied))},
		{Stage: "5. Responded", Volume: responded, Conversion: safePct(responded, applied), Friction: fmt.Sprintf("%d awaiting response", max(0, applied-responded))},
		{Stage: "6. Interview", Volume: interview, Conversion: safePct(interview, applied), Friction: fmt.Sprintf("%d dropped / ghosted", max(0, applied-interview))},
		{Stage: "7. Offer", Volume: offer, Conversion: safePct(offer, interview), Friction: "Target terminal outcome"},
	}

	// 2. Strategy Radar situational dimensions (0-100 scale)
	atsScore := int(math.Min(100, (pm.AvgScore/5.0)*100))
	if atsScore == 0 {
		atsScore = 70
	}
	seniorityScore := int(math.Min(100, (pm.TopScore/5.0)*100))
	if seniorityScore == 0 {
		seniorityScore = 80
	}
	proofDensity := 85
	if pm.Quadrants.ReadyToApply > 0 {
		proofDensity = int(math.Min(100, 75+float64(pm.Quadrants.ReadyToApply)*2))
	}
	techBreadth := int(math.Min(100, float64(len(pm.PlatformStats))*15 + 40))
	conversionScore := int(math.Min(100, pm.ResponseRate*1.5 + 50))
	if conversionScore < 50 {
		conversionScore = 65
	}
	recruiterHook := (atsScore + seniorityScore + proofDensity) / 3

	getGrade := func(score int) string {
		switch {
		case score >= 90:
			return "A"
		case score >= 80:
			return "B+"
		case score >= 70:
			return "B"
		case score >= 60:
			return "C"
		default:
			return "D"
		}
	}

	pm.StrategyRadar = model.StrategyRadarReport{
		Axes: []model.StrategyRadarAxis{
			{Name: "ATS Tailoring", Score: atsScore, Grade: getGrade(atsScore), Description: "Target keyword density & formatting"},
			{Name: "Seniority & Scope", Score: seniorityScore, Grade: getGrade(seniorityScore), Description: "Leadership positioning & impact scope"},
			{Name: "Proof Density", Score: proofDensity, Grade: getGrade(proofDensity), Description: "STAR metrics & verified evidence clusters"},
			{Name: "Market Coverage", Score: techBreadth, Grade: getGrade(techBreadth), Description: "Platform diversity & active pipeline span"},
			{Name: "Funnel Conversion", Score: conversionScore, Grade: getGrade(conversionScore), Description: "Application to response velocity"},
			{Name: "Recruiter Hook", Score: recruiterHook, Grade: getGrade(recruiterHook), Description: "Above-the-fold executive summary punch"},
		},
		Overall: (atsScore + seniorityScore + proofDensity + techBreadth + conversionScore + recruiterHook) / 6,
		Playbooks: []model.StrategyPlaybook{
			{Name: "Application Momentum", Focus: "High-Fit Execution", Action: "Run `resume next` or `resume batch` to clear pending applications."},
			{Name: "Quantified Proof Density", Focus: "Resume Impact", Action: "Lead tailored bullets with metric-first hooks from evidence-guide.csv."},
			{Name: "High-Yield Platforms", Focus: "ATS Targeting", Action: "Focus pipeline energy on Greenhouse & Ashby direct listings."},
		},
	}

	return pm
}

var reStaffingAgency = regexp.MustCompile(`(?i)\b(cybercoders|apex systems|apex staffing|teksystems|insight global|robert half|addison group|harnham|kforce|modis|randstad|allegis|kelly services|manpower|aerotek|beacon hill|lucas group|motion recruitment|judge group|creative circle|mondo|jobot|staffing|recruiting|recruitment|talent solutions|search partners|headhunters|personnel)\b`)

// IsStaffingAgency checks if a company name is likely a staffing agency.
func IsStaffingAgency(company string) bool {
	return reStaffingAgency.MatchString(company)
}

// NormalizePlatformName maps raw platform names to canonical display strings.
func NormalizePlatformName(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return "Direct / Unknown"
	}
	lower := strings.ToLower(raw)
	switch {
	case strings.Contains(lower, "greenhouse"):
		return "Greenhouse"
	case strings.Contains(lower, "lever"):
		return "Lever"
	case strings.Contains(lower, "ashby"):
		return "Ashby"
	case strings.Contains(lower, "jobright"):
		return "Jobright"
	case strings.Contains(lower, "linkedin"):
		return "LinkedIn"
	case strings.Contains(lower, "indeed"):
		return "Indeed"
	case strings.Contains(lower, "workday"):
		return "Workday"
	case strings.Contains(lower, "remoteok"):
		return "RemoteOK"
	case strings.Contains(lower, "himalayas"):
		return "Himalayas"
	case strings.Contains(lower, "wellfound"):
		return "Wellfound"
	case strings.Contains(lower, "ziprecruiter"):
		return "ZipRecruiter"
	case strings.Contains(lower, "glassdoor"):
		return "Glassdoor"
	case strings.Contains(lower, "adzuna"):
		return "Adzuna"
	case strings.Contains(lower, "jooble"):
		return "Jooble"
	default:
		return strings.Title(strings.ReplaceAll(raw, "_", " "))
	}
}

// safePct returns the percentage of part/whole, or 0 if whole is 0.
func safePct(part, whole int) float64 {
	if whole == 0 {
		return 0
	}
	return float64(part) / float64(whole) * 100
}
