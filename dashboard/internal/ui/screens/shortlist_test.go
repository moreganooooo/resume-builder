package screens

import (
	"strings"
	"testing"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func shortlistTheme() theme.Theme { return theme.NewTheme("catppuccin-mocha") }

// A shortlisted role must survive the actionable bar on BOTH screens. This
// is the whole point of the feature: an explicit human choice outranks an
// inferred one, so a 3.4-scoring role the user starred may not vanish.
func TestShortlistedRoleIsExemptFromActionableBar(t *testing.T) {
	belowBar := ActionableScore - 0.1

	app := model.CareerApplication{
		Company: "Acme", Role: "Designer",
		Status: "Evaluated", Score: belowBar,
	}
	if !belowActionableBar(app, "evaluated") {
		t.Fatal("unstarred sub-bar role should be hidden by the bar")
	}
	app.Favorite = true
	if belowActionableBar(app, "evaluated") {
		t.Fatal("shortlisted sub-bar role must NOT be hidden by the bar")
	}

	row := model.JobRow{
		Company: "Acme", Title: "Designer", Status: "Pending",
		Evaluation: model.Evaluation{CompositeScore: belowBar},
	}
	m := NewJobsModel(shortlistTheme(), []model.JobRow{row}, 100, 30)
	m.filter = "all"
	if m.matchesPrimaryFilter(row) {
		t.Fatal("unstarred sub-bar row should be hidden on Jobs")
	}
	row.Favorite = true
	if !m.matchesPrimaryFilter(row) {
		t.Fatal("shortlisted sub-bar row must NOT be hidden on Jobs")
	}
}

// A shortlisted role is also exempt from the terminal gate. Starring an
// archived or skip-recommended posting is how a user says "keep this in
// front of me anyway", so [d] must not be required to see it.
func TestShortlistedRoleIsNotTerminal(t *testing.T) {
	cases := []model.CareerApplication{
		{Status: "archived"},
		{Status: "expired"},
		{Status: "Pending", SkipRecommended: true},
	}
	for _, app := range cases {
		if !data.IsTerminalApplication(app) {
			t.Fatalf("expected %+v to be terminal", app)
		}
		app.Favorite = true
		if data.IsTerminalApplication(app) {
			t.Fatalf("shortlisted %+v must not be terminal", app)
		}
	}
}

// A Skip verdict is displayed as terminal WITHOUT being written into the
// row's status -- picker.py now exports those rows rather than withholding
// them, and the row keeps its real file-derived status.
func TestSkipRecommendedIsTerminalButKeepsItsStatus(t *testing.T) {
	app := model.CareerApplication{Status: "Pending", SkipRecommended: true}
	if data.IsTerminalStatus(app.Status) {
		t.Fatal("skip_recommended must not be conflated with a terminal STATUS")
	}
	if !data.IsTerminalApplication(app) {
		t.Fatal("a skip-recommended role should display as terminal")
	}
}

// The SHORTLIST tab shows starred roles regardless of score or terminal
// state, and nothing else.
func TestPipelineShortlistTab(t *testing.T) {
	apps := []model.CareerApplication{
		{Company: "Starred", Role: "Low scorer", Status: "Evaluated", Score: 1.0, Favorite: true},
		{Company: "Starred", Role: "Archived one", Status: "archived", Score: 4.5, Favorite: true},
		{Company: "Plain", Role: "Good one", Status: "Evaluated", Score: 4.5},
	}
	pm := NewPipelineModel(shortlistTheme(), apps, model.PipelineMetrics{Total: len(apps)}, "..", 120, 40)
	for i, tab := range pipelineTabs {
		if tab.filter == filterShortlist {
			pm.activeTab = i
		}
	}
	pm.applyFilterAndSort()

	if len(pm.filtered) != 2 {
		t.Fatalf("expected both starred roles, got %d: %+v", len(pm.filtered), pm.filtered)
	}
	for _, app := range pm.filtered {
		if !app.Favorite {
			t.Fatalf("unstarred role %q leaked into the SHORTLIST tab", app.Role)
		}
	}
	// The tab count must agree with the list it labels.
	if got := pm.countForFilter(filterShortlist); got != 2 {
		t.Fatalf("tab count %d disagrees with the %d rows shown", got, len(pm.filtered))
	}
}

// The bloom is keyed by row identity because the list re-sorts underneath
// it -- an index-keyed animation would bloom on whichever role slid into
// the vacated slot.
func TestBloomIsKeyedByRowNotIndex(t *testing.T) {
	var b shortlistBloom
	b.Start(ShortlistKey("Acme", "Designer"))

	if _, ok := b.frameFor(ShortlistKey("Acme", "Designer")); !ok {
		t.Fatal("bloom should apply to the row it started on")
	}
	if _, ok := b.frameFor(ShortlistKey("Other", "Role")); ok {
		t.Fatal("bloom must not apply to an unrelated row")
	}
	// Keys are case- and whitespace-insensitive, since company and title
	// reach the two screens from different export fields.
	if ShortlistKey(" acme ", "DESIGNER") != ShortlistKey("Acme", "Designer") {
		t.Fatal("ShortlistKey should normalize case and surrounding whitespace")
	}
}

// The bloom settles on the filled star and stops asking for ticks, rather
// than cycling forever.
func TestBloomSettles(t *testing.T) {
	var b shortlistBloom
	b.Start(ShortlistKey("Acme", "Designer"))
	for i := 0; i < len(bloomFrames)*2; i++ {
		if b.Advance() == nil {
			break
		}
	}
	if b.active {
		t.Fatal("bloom should have settled")
	}
	glyph := bloomFrames[b.frame]
	if glyph != starFilled {
		t.Fatalf("bloom should settle on %q, got %q", starFilled, glyph)
	}
}

// The marker is always exactly one cell, in every state, or the columns to
// its right shift as the cursor moves down the list.
func TestShortlistMarkerIsAlwaysOneCell(t *testing.T) {
	th := shortlistTheme()
	cases := []struct {
		name                 string
		favorited, cursorRow bool
		bloom                string
	}{
		{"plain", false, false, ""},
		{"cursor row", false, true, ""},
		{"favorited", true, false, ""},
		{"favorited on cursor", true, true, ""},
		{"blooming", false, true, bloomFrames[0]},
		{"bloom settled", true, true, starFilled},
	}
	for _, tc := range cases {
		got := ShortlistMarker(th, tc.favorited, tc.cursorRow, tc.bloom)
		if w := lipgloss.Width(ansi.Strip(got)); w != 1 {
			t.Errorf("%s: marker width = %d, want 1 (%q)", tc.name, w, got)
		}
	}
}

// The marker sits in a gutter, so EVERY line of a row is indented by the
// same amount. Prefixing the rendered string alone shifted only the first
// line, which stepped the selected row's pink hover bar two columns
// sideways halfway down the row (reported from a live dashboard, and the
// reason this renders through withShortlistGutter rather than "marker + row").
func TestShortlistGutterIndentsEveryLineEqually(t *testing.T) {
	row := "line one\nline two\nline three"

	got := withShortlistGutter(starFilled, row)
	lines := strings.Split(got, "\n")
	if len(lines) != 3 {
		t.Fatalf("gutter changed the line count: %d", len(lines))
	}

	indents := make([]int, len(lines))
	for i, line := range lines {
		indents[i] = lipgloss.Width(ansi.Strip(line)) - lipgloss.Width(ansi.Strip(strings.Split(row, "\n")[i]))
	}
	for i, indent := range indents {
		if indent != shortlistGutterWidth {
			t.Errorf("line %d indented by %d, want %d (got %q)", i, indent, shortlistGutterWidth, lines[i])
		}
	}

	// The marker itself only appears on the first line.
	if !strings.HasPrefix(lines[0], starFilled) {
		t.Errorf("marker missing from the first line: %q", lines[0])
	}
	for _, line := range lines[1:] {
		if strings.Contains(line, starFilled) || strings.Contains(line, starHollow) {
			t.Errorf("marker leaked onto a continuation line: %q", line)
		}
	}
}

// A real sidebar row is two lines, and the selected one carries the hover
// bar on both. This pins the actual renderer, not just the helper.
func TestRenderedSidebarRowStaysAlignedWithMarker(t *testing.T) {
	th := shortlistTheme()
	for _, selected := range []bool{false, true} {
		row := renderSidebarRowTagged(th, 4.2, "Acme", "", "Lifecycle Marketing Manager", shortlistRowWidth(60), selected)
		marked := withShortlistGutter(ShortlistMarker(th, true, selected, ""), row)

		widths := map[int]bool{}
		for _, line := range strings.Split(marked, "\n") {
			widths[lipgloss.Width(ansi.Strip(line))] = true
		}
		if len(widths) != 1 {
			t.Errorf("selected=%v: row lines have differing widths %v -- the gutter is misaligned", selected, widths)
		}
	}
}

// The Jobs screen is the live worklist: expired, archived and
// Skip-recommended roles are exported for the Pipeline's [d] toggle and
// must not leak into it, at any filter stop. A star outranks a Skip
// verdict but not an expired or archived posting.
func TestJobsHidesTerminalRoles(t *testing.T) {
	base := model.JobRow{
		Company: "Acme", Title: "Designer", Status: "Pending",
		Evaluation: model.Evaluation{CompositeScore: ActionableScore + 0.5},
	}
	m := NewJobsModel(shortlistTheme(), []model.JobRow{base}, 100, 30)

	terminal := map[string]model.JobRow{}
	for _, status := range []string{"Expired", "Archived"} {
		r := base
		r.Status = status
		terminal[status] = r
	}
	skip := base
	skip.SkipRecommended = true
	terminal["Skip"] = skip

	for _, filter := range []string{"all", "pending", "good_fit", "low", "recent"} {
		m.filter = filter
		for name, r := range terminal {
			if m.matchesPrimaryFilter(r) {
				t.Errorf("%s row leaked into Jobs at filter %q", name, filter)
			}
		}
	}

	m.filter = "all"
	if !m.matchesPrimaryFilter(base) {
		t.Fatal("a live pending row must still show")
	}
	starred := terminal["Expired"]
	starred.Favorite = true
	if m.matchesPrimaryFilter(starred) {
		t.Fatal("a starred expired role belongs in the Pipeline only")
	}
	starredSkip := terminal["Skip"]
	starredSkip.Favorite = true
	if !m.matchesPrimaryFilter(starredSkip) {
		t.Fatal("a star must still outrank a Skip verdict")
	}
}
