package model

import (
	"encoding/json"
	"strings"
)

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
	Skills         []JobSkill   `json:"skills"`
	Research       *Research    `json:"research"`
	Evaluation     Evaluation   `json:"evaluation"`
	Liveness       *Liveness    `json:"liveness"`
	Application    *Application `json:"application"`
	Coverage       *Coverage    `json:"coverage"`

	// PostedDate is scripts/jd_manager.py's compute_posting_date() --
	// a real posted-date field, else _discovered_at, else the _liveness
	// "confirmed to exist by scan" timestamp, else "" when none exist.
	PostedDate string `json:"posted_date"`

	// Location is the posting's stated location, verbatim. Workplace is
	// "remote"/"hybrid"/"onsite"/"unknown" as classified by Python's
	// location_filter.
	Location  string `json:"location"`
	Workplace string `json:"workplace"`

	// DistanceMiles is a POINTER on purpose. A JSON null means the
	// location could not be resolved, which is a different fact from
	// "zero miles away" -- a float64 would collapse the two and sort
	// every unresolvable posting to the top of a distance sort.
	DistanceMiles *float64 `json:"distance_miles"`

	// EmploymentType is the canonical list from scripts/employment_type.py
	// ("full_time", "part_time", "contract", ...). A posting can honestly
	// be more than one -- "Full-time, Contract" is offered as either --
	// so this is a list, not a string. Empty means the source did not
	// state a type, which is common: Greenhouse never publishes the field.
	//
	// EmploymentTypeRaw is what the provider literally said. Kept because
	// the vocabulary is unbounded free text, so a value that normalized to
	// nothing still has something to show, and an empty normalized list
	// with a non-empty raw string is exactly how a new provider spelling
	// makes itself visible.
	EmploymentType    []string `json:"employment_type"`
	EmploymentTypeRaw string   `json:"employment_type_raw"`

	// PayAnnualMax is the top of the stated range, annualized so one
	// column can sort postings quoted hourly against ones quoted yearly.
	// A POINTER for the same reason as DistanceMiles: most postings state
	// no pay at all, and a zero would sort as the worst-paying job rather
	// than as an unknown.
	//
	// PayText is the posting's OWN phrasing ("$25/hr", "$80,000 -
	// $95,000"). Shown in preference to the annualized number, because
	// $52,000 is a figure the posting never printed and displaying only
	// that reads as the app inventing a salary.
	PayAnnualMax *float64 `json:"pay_annual_max"`
	PayText      string   `json:"pay_text"`

	// HoursMin/HoursMax are weekly hours, and are usually nil -- only
	// about 2% of postings state them (about a quarter of part-time
	// ones). Either bound alone can be set: "up to 25 hours a week"
	// states a ceiling and nothing about the floor.
	HoursMin  *float64 `json:"hours_min"`
	HoursMax  *float64 `json:"hours_max"`
	HoursText string   `json:"hours_text"`
}

// PayLabel renders stated pay for a list cell, or "" when none was stated.
// Blank rather than "Unknown" because saying nothing about pay is the
// normal case, not a data problem worth flagging on three quarters of rows.
func (j JobRow) PayLabel() string {
	return strings.TrimSpace(j.PayText)
}

// HoursLabel renders stated weekly hours, or "" when none were stated.
func (j JobRow) HoursLabel() string {
	return strings.TrimSpace(j.HoursText)
}

// HasStatedPay reports whether the posting disclosed pay at all. This is
// the distinction that matters most when reading a filtered list: a pay
// floor can only act on postings that disclose, so "no pay stated" and
// "pay clears your floor" are very different reasons for a row to appear.
func (j JobRow) HasStatedPay() bool {
	return j.PayAnnualMax != nil
}

// EmploymentLabel renders the employment type for a list cell, preferring
// the canonical form and falling back to whatever the provider said.
// Returns "" when the posting stated nothing -- callers should render that
// as blank, not as "Unknown", since not stating a type is the norm.
func (j JobRow) EmploymentLabel() string {
	if len(j.EmploymentType) > 0 {
		parts := make([]string, 0, len(j.EmploymentType))
		for _, t := range j.EmploymentType {
			// A canonical value added in Python before it is added here
			// must show as itself, not as an empty cell.
			if label, ok := EmploymentLabels[t]; ok {
				parts = append(parts, label)
			} else {
				parts = append(parts, t)
			}
		}
		return strings.Join(parts, ", ")
	}
	return strings.TrimSpace(j.EmploymentTypeRaw)
}

// HasEmploymentType reports whether this posting is offered as the given
// canonical type. A posting that stated nothing matches nothing -- absence
// is not evidence that it qualifies.
func (j JobRow) HasEmploymentType(want string) bool {
	for _, t := range j.EmploymentType {
		if t == want {
			return true
		}
	}
	return false
}

// EmploymentLabels keys match scripts/employment_type.py's CANONICAL tuple.
var EmploymentLabels = map[string]string{
	"full_time":        "Full-time",
	"part_time":        "Part-time",
	"contract":         "Contract",
	"contract_to_hire": "Contract-to-hire",
	"temporary":        "Temporary",
	"internship":       "Internship",
}

// Workplace values, matching scripts/location_filter.py.
const (
	WorkplaceRemote  = "remote"
	WorkplaceHybrid  = "hybrid"
	WorkplaceOnsite  = "onsite"
	WorkplaceUnknown = "unknown"
)

// HasDistance reports whether this row has a real measured distance.
func (j JobRow) HasDistance() bool {
	return j.DistanceMiles != nil
}

// Miles returns the measured distance, and whether there was one.
func (j JobRow) Miles() (float64, bool) {
	if j.DistanceMiles == nil {
		return 0, false
	}
	return *j.DistanceMiles, true
}

// JobSkill is one entry of a JD's extracted skill list.
//
// The Python exporter emits these as objects -- {"skill", "score",
// "type"} -- but this field was declared []string, so encoding/json
// failed the whole document and data.LoadJobs returned an error for
// every export. The dashboard logged a warning and fell back to nil
// rows, which is why Browse & Manage Jobs rendered permanently empty
// however it was launched. UnmarshalJSON also accepts a bare string so
// older exports, and any hand-written fixture, still load.
type JobSkill struct {
	Name  string `json:"skill"`
	Score int    `json:"score"`
	Type  string `json:"type"`
}

func (s *JobSkill) UnmarshalJSON(data []byte) error {
	trimmed := strings.TrimSpace(string(data))
	if strings.HasPrefix(trimmed, "\"") {
		var name string
		if err := json.Unmarshal(data, &name); err != nil {
			return err
		}
		s.Name = name
		return nil
	}

	// Alias to avoid recursing back into this method.
	type rawSkill JobSkill
	var raw rawSkill
	if err := json.Unmarshal(data, &raw); err != nil {
		return err
	}
	*s = JobSkill(raw)
	return nil
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
	CompositeScore       float64  `json:"composite_score"`
	FitScore             float64  `json:"fit_score"`
	InterviewOddsScore   float64  `json:"interview_odds_score"`
	PracticalPursueScore float64  `json:"practical_pursue_score"`
	Recommendation       string   `json:"recommendation"`
	Why                  string   `json:"why"`
	RecruiterRead        string   `json:"recruiter_read"`
	HardBlockers         []string `json:"hard_blockers"`

	// CapabilityGaps is the softer counterpart to HardBlockers, and the
	// two must not be conflated. A hard blocker disqualifies (a licence
	// you don't hold); a capability gap is an experience prerequisite the
	// posting asks for that the resume does not yet evidence -- which is
	// usually addressable, and is exactly what to write about in the
	// cover letter. Produced by CapabilityEvaluationSchema in
	// scripts/schemas.py and carried through orchestrator's evaluation.
	CapabilityGaps           []string           `json:"capability_gaps"`
	PostingLegitimacy        string             `json:"posting_legitimacy"`
	PostingLegitimacyNotes   string             `json:"posting_legitimacy_notes"`
	Archetype                string             `json:"archetype"`
	FitSubscores             map[string]float64 `json:"fit_subscores"`
	InterviewOddsSubscores   map[string]float64 `json:"interview_odds_subscores"`
	PracticalPursueSubscores map[string]float64 `json:"practical_pursue_subscores"`
	SkillMatrix              []SkillCoverage    `json:"skill_matrix"`
	PostingAgeDays           int                `json:"posting_age_days"`
	ApplicantCount           int                `json:"applicant_count"`
	EvaluatedAt              string             `json:"evaluated_at"`
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

type SkillCoverage struct {
	Skill    string  `json:"skill"`
	Coverage float64 `json:"coverage"`
}
