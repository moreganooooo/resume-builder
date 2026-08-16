package model

// JobRow is one JD with a persisted evaluation, as exported by
// scripts/dashboard.py's JSON bridge (picker.list_all_evaluated_jds()).
type JobRow struct {
	Path           string       `json:"path"`
	Status         string       `json:"status"` // "Pending" or "Completed"
	Title          string       `json:"title"`
	Company        string       `json:"company"`
	Description    string       `json:"description"`
	SourcePlatform string       `json:"source_platform"`
	SourceURL      string       `json:"source_url"`
	CompanyWebsite string       `json:"company_website"`
	Skills         []string     `json:"skills"`
	Research       *Research    `json:"research"`
	Evaluation     Evaluation   `json:"evaluation"`
	Liveness       *Liveness    `json:"liveness"`
	Application    *Application `json:"application"`
	Coverage       *Coverage    `json:"coverage"`
}

// Coverage mirrors the _coverage key persisted by
// scripts/jd_manager.py's save_coverage().
type Coverage struct {
	Score     float64  `json:"score"`
	Band      string   `json:"band"`
	Matched   []string `json:"matched"`
	Missing   []string `json:"missing"`
	CheckedAt string   `json:"checked_at"`
}

// Research mirrors the _research key persisted by
// scripts/jd_manager.py's save_research().
type Research struct {
	OverallToneAdjective    string   `json:"overall_tone_adjective"`
	ToneRegister            string   `json:"tone_register"`
	PronounFraming          string   `json:"pronoun_framing"`
	SentenceStyle           string   `json:"sentence_style"`
	JargonDensity           string   `json:"jargon_density"`
	RecurringKeywords       []string `json:"recurring_keywords"`
	CompanyFacts            []string `json:"company_facts"`
	CompanyHQLocation       string   `json:"company_hq_location"`
	NotableHighlights       []string `json:"notable_highlights"`
	VocabularySubstitutions []string `json:"vocabulary_substitutions"`
	ResearchedAt            string   `json:"researched_at"`
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
