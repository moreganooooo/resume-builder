package model

// JobRow is one JD with a persisted evaluation, as exported by
// scripts/dashboard.py's JSON bridge (picker.list_all_evaluated_jds()).
type JobRow struct {
	Path        string       `json:"path"`
	Status      string       `json:"status"` // "Pending" or "Completed"
	Title       string       `json:"title"`
	Company     string       `json:"company"`
	Evaluation  Evaluation   `json:"evaluation"`
	Liveness    *Liveness    `json:"liveness"`
	Application *Application `json:"application"`
}

// Evaluation mirrors the _evaluation key persisted by
// scripts/jd_manager.py's save_evaluation().
type Evaluation struct {
	CompositeScore           float64        `json:"composite_score"`
	FitScore                 float64        `json:"fit_score"`
	InterviewOddsScore       float64        `json:"interview_odds_score"`
	PracticalPursueScore     float64        `json:"practical_pursue_score"`
	Recommendation           string         `json:"recommendation"`
	Why                      string         `json:"why"`
	RecruiterRead            string         `json:"recruiter_read"`
	HardBlockers             []string       `json:"hard_blockers"`
	PostingLegitimacy        string         `json:"posting_legitimacy"`
	PostingLegitimacyNotes   string         `json:"posting_legitimacy_notes"`
	Archetype                string         `json:"archetype"`
	FitSubscores             map[string]int `json:"fit_subscores"`
	InterviewOddsSubscores   map[string]int `json:"interview_odds_subscores"`
	PracticalPursueSubscores map[string]int `json:"practical_pursue_subscores"`
	PostingAgeDays           int            `json:"posting_age_days"`
	EvaluatedAt              string         `json:"evaluated_at"`
}

// Liveness mirrors the _liveness key persisted by
// scripts/jd_manager.py's save_liveness().
type Liveness struct {
	Result    string `json:"result"`
	Reason    string `json:"reason"`
	CheckedAt string `json:"checked_at"`
}

// Application mirrors the _application key persisted by
// scripts/jd_manager.py's save_application_status().
type Application struct {
	Status          string  `json:"status"`
	AppliedAt       *string `json:"applied_at"`
	StatusChangedAt string  `json:"status_changed_at"`
	FollowUpCount   int     `json:"follow_up_count"`
	LastFollowupAt  *string `json:"last_followup_at"`
}
