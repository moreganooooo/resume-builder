package theme

// SubscoreLabels maps each fit/interview-odds/practical-pursue subscore
// schema key -- as persisted verbatim in a JD's `_evaluation` JSON (see
// jd_manager.save_evaluation) -- to the human-readable label a job seeker
// should see. Without this, the Jobs screen's subscore line rendered raw
// snake_case schema keys (e.g. "functional_alignment: 4") straight from
// the evaluation JSON, which is internal-jargon leakage the same class of
// bug this project's own CLI never allows onto the screen.
//
// Ported from scripts/cli_art.py's _FIT_DIMENSION_GROUPS, the CLI's own
// source of truth for these labels (render_comparison_table's grouped
// subscore table) -- flattened into one map since formatSubscores()
// (internal/ui/screens/jobs.go) renders one dict at a time with no need
// for _FIT_DIMENSION_GROUPS's own layer grouping, and every key across
// all three layers is already unique.
//
// GENERATED from scripts/cli_art.py by scripts/sync_dashboard_theme.py --
// do not hand-edit. Re-run that script after changing
// _FIT_DIMENSION_GROUPS.
var SubscoreLabels = map[string]string{
	"company_reputation": "Reputation",
	"compensation_viability": "Comp",
	"cultural_signals": "Culture",
	"domain_credibility": "Domain Cred.",
	"evidence_match": "Evidence Match",
	"functional_alignment": "Functional",
	"funnel_friction": "Funnel Friction",
	"growth_value": "Growth",
	"level_plausibility": "Level Fit",
	"narrative_burden": "Narrative Burden",
	"north_star_alignment": "North Star",
	"posting_legitimacy_score": "Legitimacy",
	"recruiter_legibility": "Recruiter Legibility",
	"remote_quality": "Remote",
	"time_to_offer": "Speed",
	"title_continuity": "Title Continuity",
	"tools_process_overlap": "Tools",
	"work_style_sustainability": "Sustainability",
}
