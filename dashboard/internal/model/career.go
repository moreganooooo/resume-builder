package model

// CareerApplication represents a single job application from the tracker.
type CareerApplication struct {
	Number       int
	Date         string
	Company      string
	Role         string
	Status       string
	Score        float64
	ScoreRaw     string
	HasPDF       bool
	ReportPath   string
	ReportNumber string
	Notes        string
	JobURL       string // URL of the original job posting
	// Derived from Notes free-text (see data.deriveNoteFields)
	Location    string  // "City, ST" when a US city+state appears in the notes
	WorkMode    string  // "Remote" | "Hybrid" | "Full" (onsite), "" when unknown
	PayRange    string  // first $-range found in the notes, e.g. "$140-210K"
	PayMax      float64 // top of PayRange in dollars (sort key), 0 when unknown
	PaySource   string  // "POSTED" when the JD listed it, "est" for estimates, "" unknown
	LastContact string  // max YYYY-MM-DD found in notes (falls back to applied date)
	// Platform and Coverage
	SourcePlatform string
	Coverage       float64
	// Enrichment (lazy loaded from report)
	Archetype    string
	TlDr         string
	Remote       string
	CompEstimate string
}

// PipelineMetrics holds aggregate stats for the pipeline dashboard.
type PipelineMetrics struct {
	Total      int
	ByStatus   map[string]int
	AvgScore   float64
	TopScore   float64
	WithPDF    int
	Actionable int
}

// ProgressMetrics holds job search progress analytics.
type ProgressMetrics struct {
	// Funnel
	FunnelStages []FunnelStage

	// Score distribution
	ScoreBuckets []ScoreBucket

	// Timeline (weekly activity)
	WeeklyActivity []WeekActivity

	// Rates
	ResponseRate  float64 // Responded / Applied
	InterviewRate float64 // Interview / Applied
	OfferRate     float64 // Offer / Applied

	// Averages
	AvgScore    float64
	TopScore    float64
	TotalOffers int
	ActiveApps  int // not skip/rejected/discarded

	// Heatmap & Sparkline data
	DailyActivity map[string]int
	ScoreTrend    []int
	VolumeTrend   []int

	// Source platform analytics
	PlatformStats []PlatformStat

	// Company concentration analytics
	CompanyStats []CompanyStat

	// Score-vs-Coverage scatter quadrants
	Quadrants               QuadrantCounts
	HighFitLowCoverageRoles []HighFitLowCoverageRole

	// Strategy Radar situational metrics & playbooks
	StrategyRadar StrategyRadarReport

	// Funnel Drill-Down stage diagnostics
	FunnelDrilldown []FunnelDrilldownStage
}

// StrategyRadarAxis represents a situational analysis dimension score (0-100).
type StrategyRadarAxis struct {
	Name        string
	Score       int
	Grade       string
	Description string
}

// StrategyPlaybook holds a tactical situation playbook recommendation.
type StrategyPlaybook struct {
	Name   string
	Focus  string
	Action string
}

// StrategyRadarReport holds tactical coaching & radar metrics for the dashboard.
type StrategyRadarReport struct {
	Axes      []StrategyRadarAxis
	Playbooks []StrategyPlaybook
	Overall   int
}

// FunnelDrilldownStage holds bottleneck conversion rates and drop-off diagnostics.
type FunnelDrilldownStage struct {
	Stage      string
	Volume     int
	Conversion float64
	Friction   string
}


// PlatformStat holds aggregate stats for a single job source/ATS.
type PlatformStat struct {
	Platform       string
	TotalRoles     int
	EvaluatedRoles int
	AvgScore       float64
	Tier45Plus     int
	Tier40to44     int
	Tier35to39     int
	TierSub35      int
	TopRoleTitle   string
	TopRoleCompany string
	TopRoleScore   float64
}

// CompanyStat holds employer frequency and staffing agency detection.
type CompanyStat struct {
	Company        string
	TotalRoles     int
	EvaluatedRoles int
	AvgScore       float64
	IsAgency       bool
	SampleRole     string
}

// QuadrantCounts holds role counts for the score-vs-coverage matrix.
type QuadrantCounts struct {
	ReadyToApply        int // Fit >= 4.0, Coverage >= 70%
	HighFitLowCoverage  int // Fit >= 4.0, Coverage < 70%
	OverCoveredLowerFit int // Fit < 4.0, Coverage >= 70%
	Deprioritized       int // Fit < 4.0, Coverage < 70%
}

// HighFitLowCoverageRole represents a role needing bullet-bank enrichment.
type HighFitLowCoverageRole struct {
	Title    string
	Company  string
	Score    float64
	Coverage float64
}

// FunnelStage represents one stage of the application funnel.
type FunnelStage struct {
	Label string
	Count int
	Pct   float64 // percentage of total
}

// ScoreBucket represents a score range and its count.
type ScoreBucket struct {
	Label string // e.g., "4.5-5.0", "4.0-4.4", "3.5-3.9", "3.0-3.4", "<3.0"
	Count int
}

// WeekActivity represents application activity for a given ISO week.
type WeekActivity struct {
	Week  string // e.g., "2026-W14", "2026-W13"
	Count int
}
