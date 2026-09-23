package main

import (
	"charm.land/fang/v2"
	"context"
	"errors"
	"fmt"
	"github.com/spf13/cobra"
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
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/zone"
)

type viewState int

const (
	viewPipeline viewState = iota
	viewReport
	viewProgress
	viewMenu
	viewJobs
	viewKB
	viewAnswers
)

type appModel struct {
	pipeline        screens.PipelineModel
	viewer          screens.ViewerModel
	progress        screens.ProgressModel
	jobs            screens.JobsModel
	kb              screens.KBModel
	answers         screens.AnswersModel
	menu            menu.MenuModel
	state           viewState
	previousState   viewState // screen to return to on "back" (esc); set by startTransition
	careerOpsPath   string
	jobsPath        string
	pythonPath      string
	projectRoot     string
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

	// palette is the ctrl+k / `:` command palette. It lives here rather
	// than on any one screen because it spans them: half its rows navigate
	// somewhere else, and the other half are the CURRENT screen's own
	// bindings, which only the app model knows how to route.
	palette screens.PaletteModel
}

// currentScreenName is the palette's (and any future cross-screen feature's)
// name for whatever is showing -- the same strings menu.MenuSelectMsg uses,
// so a palette row can be dispatched straight back through the existing
// navigation switch.
func (m appModel) currentScreenName() string {
	switch m.state {
	case viewPipeline:
		return "Pipeline"
	case viewJobs:
		return "Jobs"
	case viewKB:
		return "Knowledge Base"
	case viewProgress:
		if m.progress.Mode() == screens.ModeInsights {
			return "Insights"
		}
		return "Progress"
	case viewReport:
		return "Report"
	case viewAnswers:
		return "Answers"
	default:
		return "Menu"
	}
}

// paletteKeyPress turns a palette row's key string back into a real key
// press for the screen underneath. Only the keys a help bar actually
// advertises need to survive this trip -- single runes and the handful of
// named keys screens bind.
func paletteKeyPress(key string) (tea.KeyPressMsg, bool) {
	named := map[string]rune{
		"enter": tea.KeyEnter,
		"esc":   tea.KeyEscape,
		"tab":   tea.KeyTab,
		"space": tea.KeySpace,
	}
	if code, ok := named[key]; ok {
		return tea.KeyPressMsg(tea.Key{Code: code}), true
	}
	if r := []rune(key); len(r) == 1 {
		return tea.KeyPressMsg(tea.Key{Code: r[0], Text: key}), true
	}
	return tea.KeyPressMsg{}, false
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
	case viewAnswers:
		return m.answers.View()
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

// reloadPipelineDataCmd re-reads the pipeline's data off-thread.
//
// It must read the SAME source startup does -- the jobs export, falling
// back to applications.md -- or a refresh would silently swap Pipeline
// back to the old, unmerged data set mid-session.
func (m appModel) reloadPipelineDataCmd() tea.Cmd {
	careerOpsPath := m.careerOpsPath
	jobsPath := m.jobsPath
	return func() tea.Msg {
		var apps []model.CareerApplication
		if jobsPath != "" {
			if rows, err := data.LoadJobs(jobsPath); err == nil {
				apps = data.JobRowsToApplications(rows)
			} else {
				log.Warnf("pipeline reload could not read the jobs export: %v", err)
			}
		}
		if len(apps) == 0 {
			apps = data.ParseApplications(careerOpsPath)
		}
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

		// The palette eats every key while it is open -- including plain
		// letters, which are the query. Checked BEFORE the open binding so
		// typing ":" into a search stays a colon.
		if m.palette.Open {
			_, chosen := m.palette.HandleKey(keyStr)
			if !chosen {
				return m, nil
			}
			cmd, _ := m.palette.Selected()
			m.palette.Close()
			return m.runPaletteCommand(cmd)
		}
		// Not offered on the menu (which IS the navigation the palette
		// stands in for) nor on Answers, where `:` and most letters are
		// text the user is typing into a question.
		if (keyStr == "ctrl+k" || keyStr == ":") && m.state != viewMenu && m.state != viewAnswers {
			m.palette = screens.NewPalette(
				screens.PaletteCommandsForScreen(m.currentScreenName()))
			return m, nil
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
		m.answers.Resize(wsm.Width, wsm.Height)
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
			return m.navigateTo(menuMsg.Command)
		}
		var cmd tea.Cmd
		m.menu, cmd = m.menu.Update(msg)
		return m, cmd
	}
	return m.updateScreen(msg)
}

// navigateTo is the ONE place a named destination becomes a screen. Both
// the menu's own selection and the command palette route through it, so a
// screen can never be reachable from one and not the other.
func (m appModel) navigateTo(command string) (tea.Model, tea.Cmd) {
	switch command {
	case "Pipeline":
		return m.startTransition(viewPipeline)
	case "Progress":
		m.progress = screens.NewProgressModel(m.theme, m.progressMetrics, m.width, m.height)
		return m.startTransition(viewProgress)
	case "Insights":
		// The same model and the same viewProgress state: Insights
		// is the other half of this screen, not another place in
		// the app, so every route already wired for Progress --
		// View, Update, ProgressClosedMsg, resize -- carries it
		// with no second copy to keep in step.
		m.progress = screens.NewProgressModel(m.theme, m.progressMetrics, m.width, m.height).
			WithMode(screens.ModeInsights)
		return m.startTransition(viewProgress)
	case "Jobs":
		return m.startTransition(viewJobs)
	case "Documents":
		// Suspends the dashboard and hands the terminal to the
		// Python Build Documents submenu, which already owns every
		// one of these flows (batch tailor, recruiter resume,
		// re-render, polish) and the prompts they need. Rebuilding
		// them here would be a second copy of the same flow to keep
		// in step with that one, and each still has to shell out to
		// Python to do the actual work regardless.
		return m, m.runBuildDocuments()
	case "Knowledge Base":
		return m.startTransition(viewKB)
	case "Exit":
		return m, tea.Quit
	}
	return m, nil
}

// runPaletteCommand acts on the row the user chose. A navigation row goes
// through navigateTo, the same path the menu uses. An action row is
// replayed as the keypress it advertises, so the screen's own handler does
// the work -- the palette never reimplements an action, which is what
// keeps the two from drifting apart.
func (m appModel) runPaletteCommand(cmd screens.PaletteCommand) (tea.Model, tea.Cmd) {
	if cmd.Nav != "" {
		return m.navigateTo(cmd.Nav)
	}
	key, ok := paletteKeyPress(cmd.Key)
	if !ok {
		return m, nil
	}
	return m.updateScreen(key)
}

// updateScreen handles a message once a screen other than the menu is
// showing. Split out of Update so the palette can replay a keypress into
// it directly, without re-entering Update's own key interception and
// having the palette swallow the key it just dispatched.
func (m appModel) updateScreen(msg tea.Msg) (tea.Model, tea.Cmd) {
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

	case screens.KBRunToolMsg:
		// Same suspend-and-run shape as the Documents entry: the tool is a
		// Python flow with its own prompts, and the alt screen has to be
		// released for it rather than shared with it.
		return m, m.runSkillsTool(msg.Action)

	case screens.KBCloseMsg:
		if msg.Quit {
			return m, tea.Quit
		}
		return m.startTransition(m.previousState)

	case screens.AnswersClosedMsg:
		if msg.Quit {
			return m, tea.Quit
		}
		return m.startTransition(m.previousState)

	case screens.OpenAnswersMsg:
		m.answers = screens.NewAnswersModel(
			m.theme, msg.Job, m.pythonPath, m.projectRoot, m.width, m.height,
		)
		return m.startTransition(viewAnswers)

	case screens.PipelineLoadReportMsg:
		archetype, tldr, remote, comp := data.LoadReportSummary(msg.CareerOpsPath, msg.ReportPath)
		m.pipeline.EnrichReport(msg.ReportPath, archetype, tldr, remote, comp)
		return m, nil

	case screens.PipelineUpdateStatusMsg:
		err := data.UpdateApplicationStatus(msg.CareerOpsPath, msg.App, msg.NewStatus)
		if err != nil {
			m.pipeline.SetNotice(fmt.Sprintf("Status update failed: %v", err))
			return m, m.reloadPipelineDataCmd()
		}
		// Success previously showed nothing at all: the row moved and that
		// was the only evidence, which on a grouped view is easy to miss.
		toastCmd := m.pipeline.PushToast(screens.ToastSuccess,
			"%s \u2192 %s", msg.App.Company, msg.NewStatus)
		return m, tea.Batch(m.reloadPipelineDataCmd(), toastCmd)

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

	case screens.OpenURLMsg:
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
				return screens.URLOpenFailedMsg{Err: err}
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
		if m.state == viewAnswers {
			am, cmd := m.answers.Update(msg)
			m.answers = am
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
	// Drawn after the reveal clamp, so opening the palette mid-transition
	// still shows the palette rather than waiting for the screen under it
	// to finish arriving.
	if m.palette.Open {
		rows := m.height/2 - 4
		if rows > 12 {
			rows = 12
		}
		content = screens.OverlayCentered(content,
			m.palette.Render(m.theme, m.width, rows), m.width, m.height)
	}

	v := tea.NewView(zone.Scan(content))
	v.AltScreen = true
	v.MouseMode = tea.MouseModeCellMotion
	return v
}

// runBuildDocuments releases the alt screen, runs the Python Build Documents
// submenu attached to the real terminal, and restores the dashboard when it
// exits. tea.ExecProcess, not exec.Command: that submenu draws its own huh
// prompts and needs the terminal to itself, and anything less leaves two
// programs writing to the same screen.
func (m appModel) runBuildDocuments() tea.Cmd {
	c := exec.Command(m.pythonPath, filepath.Join(m.projectRoot, "scripts", "menu.py"), "--build-documents")
	c.Dir = m.projectRoot
	return tea.ExecProcess(c, func(err error) tea.Msg {
		// The submenu exiting is not an event this dashboard acts on -- the
		// menu redraws itself on the next frame either way -- but a failure
		// to launch it at all is worth surfacing through the same path a
		// failed URL open uses.
		if err != nil {
			return screens.URLOpenFailedMsg{Err: err}
		}
		return nil
	})
}

// runSkillsTool suspends the dashboard and runs one Knowledge Base skills
// tool, named by the same key menu.py's _SKILLS_TOOLS dispatches on.
func (m appModel) runSkillsTool(action string) tea.Cmd {
	c := exec.Command(m.pythonPath, filepath.Join(m.projectRoot, "scripts", "menu.py"), "--skills-tool", action)
	c.Dir = m.projectRoot
	return tea.ExecProcess(c, func(err error) tea.Msg {
		if err != nil {
			return screens.URLOpenFailedMsg{Err: err}
		}
		return nil
	})
}

// generateJobsExport writes a JD evaluation export to a temp file by
// invoking the same Python bridge scripts/dashboard.py uses, and returns
// its path. Used only as the startup fallback when --jobs-path was not
// supplied; the export is a fresh snapshot either way, so regenerating it
// here matches what the menu launch path would have handed us.
//
// The temp file is deliberately not removed on exit: jobs.go's actions
// rewrite this same path to refresh the running screen, so it has to
// outlive this function. It lands in the OS temp dir like the Python
// side's own mkstemp export does.
func generateJobsExport(pythonPath, projectRoot string) (string, error) {
	f, err := os.CreateTemp("", "dashboard_jobs_*.json")
	if err != nil {
		return "", err
	}
	path := f.Name()
	if err := f.Close(); err != nil {
		return "", err
	}

	cmd := exec.Command(
		pythonPath,
		filepath.Join(projectRoot, "scripts", "dashboard_actions.py"),
		"export", "--jobs-path", path,
	)
	cmd.Dir = projectRoot

	if out, err := cmd.CombinedOutput(); err != nil {
		_ = os.Remove(path)
		return "", fmt.Errorf("%w: %s", err, strings.TrimSpace(string(out)))
	}
	return path, nil
}

// cliOptions are the dashboard binary's flags. They were stdlib flag
// values; they are Cobra flags now so fang can style --help, --version and
// errors in the design system's CLI palette (guidelines/cli-fang.card.html).
type cliOptions struct {
	path, jobsPath, pythonPath, projectRoot, profile, theme, view, job string
	backlog                                                            int
}

func main() {
	var o cliOptions
	root := &cobra.Command{
		Use:           "dashboard",
		Short:         "The resume-builder terminal dashboard.",
		Long:          "The resume-builder terminal dashboard: pipeline, progress, insights, jobs, documents and knowledge base.\nUsually launched by `resume dashboard`, which supplies the export and interpreter flags.",
		Example:       "  dashboard --profile morgan\n  dashboard --view answers --job jds/morgan/example.json",
		Args:          cobra.NoArgs,
		SilenceUsage:  true,
		SilenceErrors: true,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if err := checkProfile(o.projectRoot, o.profile); err != nil {
				return err
			}
			return runDashboard(o)
		},
	}
	f := root.Flags()
	f.StringVar(&o.path, "path", ".", "Path to career-ops directory")
	f.StringVar(&o.jobsPath, "jobs-path", "", "Path to the JD evaluation export JSON (see scripts/dashboard.py)")
	f.StringVar(&o.pythonPath, "python-path", "python3", "Python interpreter for dashboard actions")
	f.StringVar(&o.projectRoot, "project-root", ".", "The resume-builder project root")
	f.StringVar(&o.profile, "profile", "morgan", "Active user profile name")
	f.IntVar(&o.backlog, "backlog", 0, "Pending roles not yet evaluated; 0 hides the readout")
	f.StringVar(&o.theme, "theme", "resume-builder", "Theme: resume-builder, catppuccin-mocha, catppuccin-latte, or auto")
	f.StringVar(&o.view, "view", "", "Initial view: answers")
	f.StringVar(&o.job, "job", "", "Job path or ID for the answers view")
	f.Bool("no-color", false, "Disable colour output (NO_COLOR does the same)")

	// Stdlib flag accepted -profile as well as --profile, and older scripts and
	// docs still say `dashboard -profile morgan`; Cobra would read that as -p
	// -r -o... so single-dash long names are promoted before it parses.
	for i, a := range os.Args[1:] {
		name, _, _ := strings.Cut(strings.TrimPrefix(a, "-"), "=")
		if strings.HasPrefix(a, "-") && !strings.HasPrefix(a, "--") && len(name) > 1 && f.Lookup(name) != nil {
			os.Args[i+1] = "-" + a
		}
	}

	// --no-color has to take effect before fang builds its writer, which
	// happens before Cobra parses anything -- so it is read off argv here and
	// turned into NO_COLOR, the one switch colorprofile already honours.
	for _, a := range os.Args[1:] {
		if a == "--no-color" {
			_ = os.Setenv("NO_COLOR", "1")
		}
	}

	themeName := "resume-builder"
	for i, a := range os.Args[1:] {
		if a == "--theme" && i+2 < len(os.Args) {
			themeName = os.Args[i+2]
		} else if v, ok := strings.CutPrefix(a, "--theme="); ok {
			themeName = v
		}
	}
	t := theme.NewTheme(themeName)

	if err := fang.Execute(context.Background(), root,
		fang.WithTheme(fangColorScheme(t)),
		fang.WithErrorHandler(fangErrorHandler(t)),
		fang.WithoutManpage(),
		fang.WithoutCompletions(),
	); err != nil {
		os.Exit(1)
	}
}

func runDashboard(o cliOptions) error {
	pathFlag, jobsPathFlag, pythonPathFlag, projectRootFlag := &o.path, &o.jobsPath, &o.pythonPath, &o.projectRoot
	profileFlag, backlogFlag, themeFlag, viewFlag, jobFlag := &o.profile, &o.backlog, &o.theme, &o.view, &o.job

	// The theme is resolved here rather than just before the first screen is
	// built, because the warnings below this point are the earliest thing the
	// program can print -- and until now they printed in the log library's own
	// default colors, so the first thing a user saw when something went wrong
	// was the one line that did not look like this program.
	t := theme.NewTheme(*themeFlag)
	t.ApplyLogStyles()

	careerOpsPath := *pathFlag

	jobsPath := *jobsPathFlag
	if jobsPath == "" {
		generated, err := generateJobsExport(*pythonPathFlag, *projectRootFlag)
		if err != nil {
			log.Warnf("could not generate a jobs export (Browse & Manage Jobs will be empty): %v", err)
		} else {
			jobsPath = generated
		}
	}

	var jobRows []model.JobRow
	if jobsPath != "" {
		rows, err := data.LoadJobs(jobsPath)
		if err != nil {
			log.Warnf("failed to load jobs export: %v", err)
		} else {
			jobRows = rows
		}
	}

	// Pipeline and Browse & Manage Jobs now read the SAME export. They used
	// to parse two unrelated sources -- applications.md and this JSON --
	// so the same job could appear in one screen and not the other, with
	// different scores, and Pipeline showed archived/expired jobs as
	// scoreless rows. applications.md remains the fallback for a checkout
	// with no export (career-ops data, or a profile that has never run a
	// scan).
	apps := data.JobRowsToApplications(jobRows)
	if len(apps) == 0 {
		apps = data.ParseApplications(careerOpsPath)
	}

	// Compute metrics
	metrics := data.ComputeMetrics(apps)
	progressMetrics := data.ComputeProgressMetrics(apps)

	// Load active profile
	profile := data.LoadActiveProfile(*projectRootFlag, *profileFlag)

	// Batch-load all report summaries
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

	// Browse & Manage Jobs reads a JSON export produced by the Python
	// side, not the database directly. scripts/dashboard.py writes one
	// per launch and passes --jobs-path; a dashboard started straight from
	// the binary (`dashboard --profile morgan`) has no such flag, and used
	// to render a permanently empty Jobs screen with no indication why.
	// Generate our own export in that case rather than showing nothing.
	jm := screens.NewJobsModel(t, jobRows, 120, 40).WithActionConfig(jobsPath, *pythonPathFlag, *projectRootFlag).WithBacklog(*backlogFlag)

	// Load Knowledge Base assets
	kbDir := filepath.Join(*projectRootFlag, "profiles", *profileFlag, "knowledge_base")
	kbItems := data.LoadKBItems(kbDir)
	kbScreen := screens.NewKBModel(t, kbItems, 120, 40).WithProfile(profile)
	answerJob := model.JobRow{Path: *jobFlag, Title: "Application question", Company: "Selected job"}
	for _, row := range jobRows {
		if row.Path == *jobFlag {
			answerJob = row
			break
		}
	}
	answersScreen := screens.NewAnswersModel(t, answerJob, *pythonPathFlag, *projectRootFlag, 120, 40)

	m := appModel{
		pipeline:        pm,
		jobs:            jm,
		kb:              kbScreen,
		answers:         answersScreen,
		careerOpsPath:   careerOpsPath,
		jobsPath:        jobsPath,
		pythonPath:      *pythonPathFlag,
		projectRoot:     *projectRootFlag,
		theme:           t,
		progressMetrics: progressMetrics,
		profile:         profile,

		state:            viewMenu,
		menu:             menu.NewMenuModel(t).WithProfile(profile).WithNextBestMoves(screens.CountNextBestMoves(jobRows)),
		transitioning:    !anim.ReducedMotion(),
		transitionSpring: anim.NewSpring(anim.Organic, 0, 24),
	}
	if *viewFlag == "answers" && *jobFlag != "" {
		m.state = viewAnswers
	}

	p := tea.NewProgram(m)
	if _, err := p.Run(); err != nil && !errors.Is(err, tea.ErrInterrupted) {
		return err
	}
	return nil
}
