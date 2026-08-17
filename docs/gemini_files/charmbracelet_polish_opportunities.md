# Visual Polish & Design Opportunities: The Charmbracelet Ecosystem

This design guide outlines premium aesthetic and structural opportunities to elevate the `resume-builder` terminal user interface (TUI) and command-line interface (CLI) to an **award-winning, production-grade command center**.

By marrying the core Go dashboard (`bubbletea` + `lipgloss`) with advanced Charm primitives, we can unlock state-of-the-art terminal experiences that feel fluid, responsive, and incredibly premium.

---

## 🎨 Core Theme & Visual Architecture

Your existing design system (`DESIGN.md` / `dashboard/internal/theme/theme.go`) successfully implements a split-palette strategy: terminal-vibrant neons for the TUI (derived from Charmtone and Catppuccin) and strict monochrome formatting for print exports. 

We can expand this foundation to build richer, highly stylized terminal layouts.

```
       +-----------------------------------------------------------+
       | [⚡] COMMAND CENTER                 Active: Morgan (PRO)  |
       +-----------------------------------------------------------+
       | > Pipeline    [■■■■■■■■░░░] 80%    Expiring soon: 2       |
       |   Jobs        [■■■■■■░░░░░] 60%    Active runs: 1         |
       |   Progress    [■■■■■■■■■■░] 90%    Re-checks due: 4       |
       +-----------------------------------------------------------+
       |                                                           |
       |  Activity Heatmap (Last 12 Weeks)                         |
       |  Mon ░ ░ ▒ ▒ ░ ░ ░ ░ ░ ░ ░ ░                              |
       |  Wed ░ ░ █ ▒ ░ ░ ░ ░ ░ ▒ ░ ░   [■ 0] [▒ 1-2] [▓ 3-4] [█ 5+]|
       |  Fri ░ ░ ░ ░ ░ ░ ▒ █ ░ ░ ░ ░                              |
       |                                                           |
       +-----------------------------------------------------------+
```

---

## 📊 Feature Proposal 1: Calendar Heatmap (Progress Screen)

A GitHub-style daily activity grid is a powerful and visually striking way to display job-hunting momentum (e.g., resumes tailored, letters generated, applications sent).

### The Polish Opportunity
Using `lipgloss`, you can map daily activities from `jd_tracker_log.csv` to custom terminal blocks with Catppuccin Mocha green gradients:
- `░` (#313244 / Surface) — No activity
- `▒` (#12C78F with 30% opacity) — 1–2 actions
- `▓` (#12C78F with 60% opacity) — 3–4 actions
- `█` (#12C78F / Success) — 5+ actions

### Implementation Blueprint
Here is how you can render this grid dynamically inside `dashboard/internal/ui/screens/progress.go`:

```go
package screens

import (
	"strings"
	"time"
	"github.com/charmbracelet/lipgloss"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// RenderHeatmap draws a 7x12 activity grid (last 12 weeks).
func RenderHeatmap(t theme.Theme, activityMap map[string]int, width int) string {
	var sb strings.Builder
	days := []string{"Mon", "Wed", "Fri"}
	
	// Create Catppuccin/Success color scale
	emptyStyle := lipgloss.NewStyle().Foreground(t.Overlay)                      // ░
	lowStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#2a5c4e"))          // ▒
	medStyle := lipgloss.NewStyle().Foreground(lipgloss.Color("#1a9c73"))          // ▓
	highStyle := lipgloss.NewStyle().Foreground(t.Green)                         // █
	
	labelStyle := lipgloss.NewStyle().Foreground(t.Subtext).Width(5)

	sb.WriteString(lipgloss.NewStyle().Bold(true).Foreground(t.Blue).Render("Activity Heatmap (Last 12 Weeks)\n\n"))

	now := time.Now()
	startDate := now.AddDate(0, 0, -12*7) // Go back 12 weeks
	
	for dayIdx := 0; dayIdx < 7; dayIdx++ {
		// Only render Mon, Wed, Fri labels to keep terminal uncluttered
		if dayIdx%2 == 1 {
			sb.WriteString(labelStyle.Render(days[dayIdx/2]) + " ")
		} else {
			sb.WriteString(labelStyle.Render("") + " ")
		}

		for weekIdx := 0; weekIdx < 12; weekIdx++ {
			// Locate target date
			targetDate := startDate.AddDate(0, 0, weekIdx*7+dayIdx)
			dateStr := targetDate.Format("2006-01-02")
			count := activityMap[dateStr]

			// Choose character & style based on count
			var block string
			switch {
			case count == 0:
				block = emptyStyle.Render("░")
			case count <= 2:
				block = lowStyle.Render("▒")
			case count <= 4:
				block = medStyle.Render("▓")
			default:
				block = highStyle.Render("█")
			}
			sb.WriteString(block + " ")
		}
		sb.WriteString("\n")
	}
	
	// Draw legend
	sb.WriteString("\n" + strings.Repeat(" ", 6) + "Less " + 
		emptyStyle.Render("░") + " " + 
		lowStyle.Render("▒") + " " + 
		medStyle.Render("▓") + " " + 
		highStyle.Render("█") + " More\n")
		
	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Overlay).
		Padding(1, 2).
		Width(width - 4).
		Render(sb.String())
}
```

---

## 📊 Feature Proposal 2: Evaluation Dimension Breakdown (Radar Chart Replacement)

When selecting a job, the backend (`evaluate_fit()`) produces a 10-dimension weighted evaluation matrix (e.g., Tech Stack, Salary, WFH/Remote, Scale, Growth). Currently, only the composite score is visible in the TUI.

### The Polish Opportunity
Surfacing this multi-dimensional breakdown using compact, color-graded horizontal bar charts gives the user **90% of a radar chart's analytical value** without fighting terminal rendering limits or cluttering the layout.

```
  Tech Stack    ███████████████░░░░░  75%  (Matches Go/React requirements)
  Salary        ██████████████████░░  90%  (Exceeds base target by 10k)
  WFH/Remote    ██████████░░░░░░░░░░  50%  (Hybrid 3 days/week)
```

### Implementation Blueprint
Using a custom styling wrapper or a mapped `progress.Model` from `github.com/charmbracelet/bubbles/progress`:

```go
func RenderDimensionScores(t theme.Theme, dimensions map[string]float64, width int) string {
	var sb strings.Builder
	maxBarWidth := width - 35 // Leave room for labels and score metadata
	if maxBarWidth < 10 {
		maxBarWidth = 10
	}

	sb.WriteString(lipgloss.NewStyle().Bold(true).Foreground(t.Blue).Render("Match Dimensions Breakdown\n\n"))

	for name, score := range dimensions { // score normalized between 0.0 and 1.0
		barWidth := int(score * float64(maxBarWidth))
		
		// Map score to a gradient
		var color lipgloss.Color
		switch {
		case score >= 0.8:
			color = t.Green
		case score >= 0.6:
			color = t.Sky
		case score >= 0.4:
			color = t.Yellow
		default:
			color = t.Red
		}

		label := lipgloss.NewStyle().Foreground(t.Text).Width(15).Render(name)
		filledBar := lipgloss.NewStyle().Foreground(color).Render(strings.Repeat("█", barWidth))
		emptyBar := lipgloss.NewStyle().Foreground(t.Overlay).Render(strings.Repeat("░", maxBarWidth-barWidth))
		pctText := lipgloss.NewStyle().Foreground(t.Subtext).Render(fmt.Sprintf(" %3.0f%%", score*100))

		sb.WriteString(fmt.Sprintf("  %s %s%s%s\n", label, filledBar, emptyBar, pctText))
	}

	return lipgloss.NewStyle().
		Border(lipgloss.RoundedBorder()).
		BorderForeground(t.Overlay).
		Padding(1, 2).
		Render(sb.String())
}
```

---

## 🏎️ Feature Proposal 3: Dynamic Wizards (`huh` integration)

Your CLI currently relies heavily on single-file command execution (e.g. `resume run jds/...`). Integrating a `huh` multi-step form directly inside the dashboard transforms the workflow into an interactive cockpit.

### The Polish Opportunity
When selecting a job row in the TUI, the user could press `t` to open a modal form that configures the tailoring run:

1. **Step 1 (Select Profile):** A `huh.Select` picker allowing them to choose between loaded profiles (e.g. `Morgan (Core)` vs. `Dominick (Onboarding)`).
2. **Step 2 (Tailor Focus):** A `huh.Select` or `huh.MultiSelect` to specify focus areas (e.g., *Systems Architect*, *Tech Lead*, *General Frontend*).
3. **Step 3 (Cover Letter Options):** A `huh.Confirm` to decide if a cover letter should be generated simultaneously, with a conditional text field for tone preferences (e.g. *enthusiastic*, *authoritative*).
4. **Step 4 (Launch Action):** Upon submission, instead of a hard screen refresh, a `bubbles/spinner` displays inside a clean progress box while displaying real-time stdout logs as the python engine runs under the hood.

This elevates the TUI from a "Read-Only Dashboard" to an **Interactive Command Center**.

---

## 🎬 Feature Proposal 4: Physics-Based Cursor Flourishes (`harmonica`)

Your main file `main.go` already implements a brilliant top-down screen wipe using `harmonica.Spring` when switching views:

```go
m.transitionSpring = harmonica.NewSpring(harmonica.FPS(60), 7.0, 1.0) // Critically damped
```

### The Polish Opportunity
You can extend this exact physics engine to other micro-interactions!
- **Spring-loaded sidebars:** When scrolling down lists of jobs, make the focus bullet (`▸`) or hover selector highlight "elastic". Instead of jumping instantly, it can slide smoothly into place with a subtle overshoot and bounce using a damped harmonica spring.
- **Progress bar filling:** When entering the Progress screen, initialize bar widths at `0` and animate them dynamically up to their target percentage values using the Spring tick loop. It makes the dashboard feel alive and organic.

---

## 📦 Feature Proposal 5: Documentation & Presentation Polish (`vhs` + `freeze`)

The "Portfolio & Presentation" aspect of building an amazing terminal ecosystem is highly underrated. 

### Interactive Screenshot Mode (`freeze`)
You can bind an `s` key globally in your Bubble Tea dashboard. When pressed, it captures the current raw terminal string (including ANSI escape sequences), writes it to a temporary file, and runs a Go sub-process wrapper calling `freeze` to export a pixel-perfect styled PNG of the dashboard.
- Users can instantly save beautiful summaries of their daily application funnels.
- Excellent for sharing job-hunt progress updates on LinkedIn or showing off their setup in a portfolio.

### Automated Demo Tapes (`vhs`)
Create a `.tape` file in your repository root to let `vhs` auto-generate high-quality demonstration GIFs whenever you update your UI:

```tape
# jobhunt_demo.tape
Output assets/demo.gif
Set FontSize 14
Set Theme "Catppuccin Mocha"
Set Width 1200
Set Height 600

Type "resume dashboard"
Enter
Sleep 1s

# Navigate down the pipeline list
Type "j"
Sleep 500ms
Type "j"
Sleep 500ms

# Switch to Progress screen
Type "p"
Sleep 2.5s

# Switch to Jobs list
Type "o"
Sleep 2s

# Open help overlay
Type "?"
Sleep 3s
```

By linking this with a GitHub Action (`vhs-action`), your project's repository documentation README stays perfectly up-to-date with pixel-perfect GIFs whenever visual elements change.

---

## 🌐 Feature Proposal 6: Terminal Cloud Deployments over SSH (`wish`)

Because your core dashboard is built purely in Go and Bubble Tea, you can easily wrap it using **`wish`** (SSH server middleware).

### The Polish Opportunity
Instead of needing to open a laptop, clone the repository, and run things locally, you can deploy your application tracker and builder as an **SSH App**.

Running a simple command:
```bash
ssh jobhunt.yourdomain.com
```
Instantly streams the full, beautiful interactive terminal dashboard to **any device** (your phone over Termius, a library iPad, or a work laptop), securely routing data back to your server's SQLite/CSV files. It creates an incredible, borderless job-tracking cockpit accessible from anywhere in the world.

> [!TIP]
> Wish integrates seamlessly with bubbletea, meaning your existing `appModel` requires almost zero logic changes to run over SSH. It simply handles SSH sessions as standard terminal windows and maps input/output streams automatically.
