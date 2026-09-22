package screens

import (
	"fmt"
	"strings"

	lipgloss "charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

// KBRunToolMsg asks the host to run one Python skills tool, by the same name
// Settings & Upkeep dispatches it under (menu.py's _SKILLS_TOOLS).
//
// The dashboard does not run these itself: each one prompts, writes to the
// knowledge base, and in two cases spends API calls, all of which already
// exist in Python. Naming the tool rather than describing the work keeps a
// single definition of what "Refresh Skill Embeddings" actually does.
type KBRunToolMsg struct {
	Action string
	Label  string
}

// kbSkillsCategory is the tab name. It sits alongside the content categories
// rather than behind a separate mode switch, because a user looking for what
// the knowledge base knows about their skills is already on this screen --
// and Tab, the numeric keys and the mouse all reach it with no new grammar.
const kbSkillsCategory = "Skills"

type kbSkillTool struct {
	action string
	label  string
	desc   string
}

// kbSkillTools is the group that used to live under Settings & Upkeep's "Your
// Skills" heading. They are knowledge-base operations, not settings: every one
// of them reads or rewrites verified_tools.json or the coverage matrices this
// screen displays.
var kbSkillTools = []kbSkillTool{
	{"manage_skills", "View & Manage Profile Skills",
		"Browse, add, edit and remove the verified tools ledger the Tools tab shows."},
	{"scan_pending_skills", "Scan Pending Pipeline for Skills to Verify",
		"Reads the skills your pending roles ask for and offers the ones you have not verified yet."},
	{"refresh_skill_embeddings", "Refresh Skill Embeddings",
		"Re-embeds every verified skill name so the Skills Gap Matrix scores against the current ledger. Spends API calls."},
	{"clear_stale_skill_matrices", "Recompute Stale (0%) Skill Gap Matrices",
		"Finds roles whose coverage matrix came out empty and computes them again. Spends API calls."},
	{"discover_employers", "Discover Local Employers with ATS Boards",
		"Reads local postings, probes each employer for a public ATS board, and appends confirmed hits to tracked_companies.yml."},
}

// renderSkillsList draws the left pane for the Skills tab.
func (m KBModel) renderSkillsList(width int) []string {
	t := m.theme
	lines := make([]string, 0, len(kbSkillTools))
	for i, tool := range kbSkillTools {
		label := tool.label
		if len([]rune(label)) > width-4 {
			label = string([]rune(label)[:max(0, width-5)]) + "…"
		}
		var rendered string
		if i == m.cursor {
			rendered = lipgloss.NewStyle().Bold(true).Foreground(t.Base).Background(t.Sky).
				Width(width).Render("▶ " + label)
		} else {
			rendered = lipgloss.NewStyle().Foreground(t.Text).Width(width).Render("  " + label)
		}
		lines = append(lines, zone.Mark(fmt.Sprintf("kb_skill_%d", i), rendered))
	}
	return lines
}

// renderSkillsDetail draws the right pane for the Skills tab: what the focused
// tool does, and how to run it. Stated plainly because two of these spend API
// calls, which is not something to discover by pressing Enter.
func (m KBModel) renderSkillsDetail() string {
	t := m.theme
	if m.cursor < 0 || m.cursor >= len(kbSkillTools) {
		return ""
	}
	tool := kbSkillTools[m.cursor]
	return lipgloss.JoinVertical(lipgloss.Left,
		lipgloss.NewStyle().Bold(true).Foreground(t.Mauve).Render(tool.label),
		"",
		lipgloss.NewStyle().Foreground(t.Text).Render(tool.desc),
		"",
		lipgloss.NewStyle().Foreground(t.Subtext).Render(
			strings.TrimSpace("Press Enter to run it. The dashboard steps aside while it runs and comes back when it finishes.")),
	)
}
