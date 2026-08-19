package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/log"

	"github.com/moreganooooo/resume-builder/dashboard/internal/anim"
	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/menu"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/screens"
)

type viewState int

const (
	viewPipeline viewState = iota
	viewReport
	viewProgress
	viewMenu
	viewJobs
	viewKB
)

type appModel struct {
	pipeline        screens.PipelineModel
	viewer          screens.ViewerModel
	progress        screens.ProgressModel
	jobs            screens.JobsModel
	kb              screens.KBModel
	menu            menu.MenuModel
	state           viewState
	previousState   viewState // screen to return to on "back" (esc); set by startTransition
	careerOpsPath   string
	theme           theme.Theme
	progressMetrics model.ProgressMetrics
	profile         data.ProfileInfo
	width, height   int // real terminal size, tracked from tea.WindowSizeMsg

	// Every screen switch (including the initial launch into the menu)
	// plays a harmonica-eased top-down reveal of the incoming screen's
	// already-rendered View() output, rather than a hard cut. Generic --
	// works on any screen's output as-is, no per-screen rendering changes.
	transitioning    bool
	transitionSpring anim.Spring
	transitionPos    float64

	// transitionRender caches the incoming screen's full View() output for
	// the current tick, computed once in the transitionTickMsg handler
	// below and reused by View() instead of calling m.renderScreen() a
	// second time per frame -- screens don't change mid-reveal, so the
	// second call (styling, and on the Viewer screen a full markdown
	// re-parse) was pure duplicated work at ~60fps for the reveal's
	// duration. Cleared in startTransition so a new transition never shows
	// a stale screen's content before its own first tick lands.
	transitionRender string
}

// transitionTickMsg drives the reveal's ~60fps animation loop.
type transitionTickMsg struct{}

func tickTransition() tea.Cmd {
	return tea.Tick(time.Second/60, func(time.Time) tea.Msg {
		return transitionTickMsg{}
	})
}

// startTransition switches to newState and begins revealing it top-down.
// Damping of 0.7 provides an organic, responsive underdamped bounce that
// settles smoothly without rigid abruptness, matching the TUI motion design.
//
// Recording m.state as previousState before overwriting it -- rather than
// only setting previousState at each menu-selection/open-report/open-
// progress call site -- gives every screen a "back" target for free:
// Whichever screen was active when a transition starts is always the correct one to return to.
func (m appModel) startTransition(newState viewState) (tea.Model, tea.Cmd) {
	m.previousState = m.state
	m.state = newState
	if anim.ReducedMotion() {
		m.transitioning = false
		return m, nil
	}
	m.transitioning = true
	m.transitionRender = m.renderScreen()
	target := float64(len(strings.Split(m.transitionRender, "\n")))
	m.transitionSpring = anim.NewSpring(anim.Organic, 0, target)
	m.transitionPos = 0
	return m, tickTransition()
}

func isMobileTerminal() bool {
	return os.Getenv("TERMUX_VERSION") != "" || os.Getenv("RESUME_BUILDER_MOBILE") == "1" || os.Getenv("RESUME_BUILDER_COMPACT") == "1"
}

// renderScreen is the undecorated View() for the current state -- shared
// by View() itself and by the transition tick handler (which needs the
// incoming screen's line count as the reveal's target, without recursing
// through View()'s own reveal-clamping logic).
func (m appModel) renderScreen() string {
	minWidth := 80
	minHeight := 24
	if isMobileTerminal() {
		minWidth = 35
		minHeight = 12
	}

	if m.width > 0 && m.height > 0 && (m.width < minWidth || m.height < minHeight) {
		return renderCompactWarning(m.theme, m.width, m.height, minWidth, minHeight)
	}

	switch m.state {
	case viewReport:
		return m.viewer.View()
	case viewProgress:
		return m.progress.View()
	case viewMenu:
		return m.menu.View()
	case viewJobs:
		return m.jobs.View()
	case viewKB:
		return m.kb.View()
	default:
		return m.pipeline.View()
	}
}

func renderCompactWarning(t theme.Theme, width, height, minWidth, minHeight int) string {
	return screens.RenderWindowResizeGuidance(width, height, minWidth, minHeight, t)
}

// pipelineDataLoadedMsg carries the result of reloadPipelineDataCmd's
// off-thread reload back into Update().
type pipelineDataLoadedMsg struct {
	apps            []model.CareerApplication
	metrics         model.PipelineMetrics
	progressMetrics model.ProgressMetrics
}

// reloadPipelineDataCmd re-reads and reparses applications.md as a tea.Cmd
func (m appModel) reloadPipelineDataCmd() tea.Cmd {
	careerOpsPath := m.careerOpsPath
	return func() tea.Msg {
		apps := data.ParseApplications(careerOpsPath)
		metrics := data.ComputeMetrics(apps)
		progressMetrics := data.ComputeProgressMetrics(apps)
		return pipelineDataLoadedMsg{apps: apps, metrics: metrics, progressMetrics: progressMetrics}
	}
}

// Init only returns a tea.Cmd, not a model
func (m appModel) Init() tea.Cmd {
	return tea.Batch(m.menu.Init(), tickTransition())
}

func (m appModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	// Ctrl+C is handled here so it quits cleanly from every screen
	if key, ok := msg.(tea.KeyPressMsg); ok {
		keyStr := key.String()
		minWidth, minHeight := 80, 24
		if isMobileTerminal() {
			minWidth, minHeight = 35, 12
		}
		if keyStr == "ctrl+c" || (keyStr == "q" && m.width > 0 && (m.width < minWidth || m.height < minHeight)) {
			return m, tea.Quit
		}
	}

	// Handled ahead of the viewMenu early-return
	if _, ok := msg.(transitionTickMsg); ok {
		if !m.transitioning {
			return m, nil
		}
		pos, settled := m.transitionSpring.Update()
		m.transitionPos = pos
		if settled {
			m.transitioning = false
			return m, nil
		}
		return m, tickTransition()
	}

	// Handle window resize for all views
	if wsm, ok := msg.(tea.WindowSizeMsg); ok {
		m.width, m.height = wsm.Width, wsm.Height
		m.menu.Resize(wsm.Width, wsm.Height)
		m.pipeline.Resize(wsm.Width, wsm.Height)
		m.jobs.Resize(wsm.Width, wsm.Height)
		m.kb.Resize(wsm.Width, wsm.Height)
		if m.state == viewReport {
			m.viewer.Resize(wsm.Width, wsm.Height)
		}
		if m.state == viewProgress {
			m.progress.Resize(wsm.Width, wsm.Height)
		}
		pm, cmd := m.pipeline.Update(msg)
		m.pipeline = pm
		return m, cmd
	}

	// Menu view message dispatch
	if m.state == viewMenu {
		if _, ok := msg.(menu.MenuQuitMsg); ok {
			return m, tea.Quit
		}
		if menuMsg, ok := msg.(menu.MenuSelectMsg); ok {
			switch menuMsg.Command {
			case "Pipeline":
				return m.startTransition(viewPipeline)
			case "Progress":
				m.progress = screens.NewProgressModel(m.theme, m.progressMetrics, m.width, m.height)
				return m.startTransition(viewProgress)
			case "Reports":
				m.viewer = screens.NewEmptyViewerModel(m.theme, m.width, m.height)
				return m.startTransition(viewReport)
			case "Jobs":
				return m.startTransition(viewJobs)
			case "Knowledge Base":
				return m.startTransition(viewKB)
			case "Exit":
				return m, tea.Quit
			}
			return m, nil
		}
		var cmd tea.Cmd
		m.menu, cmd = m.menu.Update(msg)
		return m, cmd
	}

	switch msg := msg.(type) {
	case screens.PipelineClosedMsg:
		if msg.Quit {
			return m, tea.Quit
		}
		return m.startTransition(m.previousState)

	case screens.JobsClosedMsg:
		if msg.Quit {
			return m, tea.Quit
		}
		return m.startTransition(m.previousState)

	case screens.KBCloseMsg:
		if msg.Quit {
			return m, tea.Quit
		}
		return m.startTransition(m.previousState)

	case screens.PipelineLoadReportMsg:
		archetype, tldr, remote, comp := data.LoadReportSummary(msg.CareerOpsPath, msg.ReportPath)
		m.pipeline.EnrichReport(msg.ReportPath, archetype, tldr, remote, comp)
		return m, nil

	case screens.PipelineUpdateStatusMsg:
		err := data.UpdateApplicationStatus(msg.CareerOpsPath, msg.App, msg.NewStatus)
		if err != nil {
			m.pipeline.SetNotice(fmt.Sprintf("Status update failed: %v", err))
		}
		return m, m.reloadPipelineDataCmd()

	case screens.PipelineRefreshMsg:
		return m, m.reloadPipelineDataCmd()

	case pipelineDataLoadedMsg:
		m.progressMetrics = msg.progressMetrics
		m.pipeline = m.pipeline.WithReloadedData(msg.apps, msg.metrics)
		return m, nil

	case screens.PipelineOpenReportMsg:
		m.viewer = screens.NewViewerModel(
			m.theme,
			msg.Path, msg.Title,
			m.width, m.height,
		)
		return m.startTransition(viewReport)

	case screens.ViewerClosedMsg:
		if msg.Quit {
			return m, tea.Quit
		}
		return m.startTransition(m.previousState)

	case screens.PipelineOpenProgressMsg:
		m.progress = screens.NewProgressModel(
			m.theme,
			m.progressMetrics,
			m.width, m.height,
		)
		return m.startTransition(viewProgress)

	case screens.ProgressClosedMsg:
		if msg.Quit {
			return m, tea.Quit
		}
		return m.startTransition(m.previousState)

	case screens.PipelineOpenURLMsg:
		return m, func() tea.Msg {
			var err error
			switch runtime.GOOS {
			case "darwin":
				err = exec.Command("open", msg.URL).Run()
			case "linux":
				err = exec.Command("xdg-open", msg.URL).Run()
			case "windows":
				err = exec.Command("cmd", "/c", "start", "", msg.URL).Run()
			default:
				err = exec.Command("xdg-open", msg.URL).Run()
			}
			if err != nil {
				return screens.PipelineURLOpenFailedMsg{Err: err}
			}
			return nil
		}

	default:
		if m.state == viewReport {
			vm, cmd := m.viewer.Update(msg)
			m.viewer = vm
			return m, cmd
		}
		if m.state == viewProgress {
			pg, cmd := m.progress.Update(msg)
			m.progress = pg
			return m, cmd
		}
		if m.state == viewJobs {
			jm, cmd := m.jobs.Update(msg)
			m.jobs = jm
			return m, cmd
		}
		if m.state == viewKB {
			km, cmd := m.kb.Update(msg)
			m.kb = km
			return m, cmd
		}
		pm, cmd := m.pipeline.Update(msg)
		m.pipeline = pm
		return m, cmd
	}
}

func (m appModel) View() tea.View {
	target := m.transitionRender
	if !m.transitioning || target == "" {
		target = m.renderScreen()
	}
	var content string
	if !m.transitioning {
		content = target
	} else {
		lines := strings.Split(target, "\n")
		revealed := int(m.transitionPos)
		if revealed < 0 {
			revealed = 0
		}
		if revealed >= len(lines) {
			content = target
		} else {
			content = strings.Join(lines[:revealed], "\n")
		}
	}
	v := tea.NewView(content)
	v.AltScreen = true
	return v
}

func main() {
	pathFlag := flag.String("path", ".", "Path to career-ops directory")
	jobsPathFlag := flag.String("jobs-path", "", "Path to the JD evaluation export JSON (see scripts/dashboard.py)")
	pythonPathFlag := flag.String("python-path", "python3", "Path to the Python interpreter for dashboard actions (see scripts/dashboard.py)")
	projectRootFlag := flag.String("project-root", ".", "Path to the resume-builder project root (for locating scripts/dashboard_actions.py)")
	profileFlag := flag.String("profile", "morgan", "Active user profile name")
	themeFlag := flag.String("theme", "resume-builder", "Theme name: resume-builder, catppuccin-mocha, catppuccin-latte, or auto")
	flag.Parse()

	careerOpsPath := *pathFlag

	// Load applications
	apps := data.ParseApplications(careerOpsPath)
	if apps == nil {
		log.Fatalf("could not find applications.md in %s or %s/data/", careerOpsPath, careerOpsPath)
	}

	// Compute metrics
	metrics := data.ComputeMetrics(apps)
	progressMetrics := data.ComputeProgressMetrics(apps)

	// Load active profile
	profile := data.LoadActiveProfile(*projectRootFlag, *profileFlag)

	// Batch-load all report summaries
	t := theme.NewTheme(*themeFlag)
	pm := screens.NewPipelineModel(t, apps, metrics, careerOpsPath, 120, 40)

	for _, app := range apps {
		if app.ReportPath == "" {
			continue
		}
		archetype, tldr, remote, comp := data.LoadReportSummary(careerOpsPath, app.ReportPath)
		if archetype != "" || tldr != "" || remote != "" || comp != "" {
			pm.EnrichReport(app.ReportPath, archetype, tldr, remote, comp)
		}
	}

	var jobRows []model.JobRow
	if *jobsPathFlag != "" {
		rows, err := data.LoadJobs(*jobsPathFlag)
		if err != nil {
			log.Warnf("failed to load jobs export: %v", err)
		} else {
			jobRows = rows
		}
	}
	jm := screens.NewJobsModel(t, jobRows, 120, 40).WithActionConfig(*jobsPathFlag, *pythonPathFlag, *projectRootFlag)

	// Load Knowledge Base assets
	kbDir := filepath.Join(*projectRootFlag, "profiles", *profileFlag, "knowledge_base")
	kbItems := data.LoadKBItems(kbDir)
	kbScreen := screens.NewKBModel(t, kbItems, 120, 40).WithProfile(profile)

	m := appModel{
		pipeline:        pm,
		jobs:            jm,
		kb:              kbScreen,
		careerOpsPath:   careerOpsPath,
		theme:           t,
		progressMetrics: progressMetrics,
		profile:         profile,

		state:            viewMenu,
		menu:             menu.NewMenuModel(t).WithProfile(profile),
		transitioning:    !anim.ReducedMotion(),
		transitionSpring: anim.NewSpring(anim.Organic, 0, 24),
	}

	p := tea.NewProgram(m)
	if _, err := p.Run(); err != nil && !errors.Is(err, tea.ErrInterrupted) {
		log.Fatalf("%v", err)
	}
}
