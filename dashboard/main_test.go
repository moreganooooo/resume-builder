package main

import (
	"strings"
	"testing"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"github.com/moreganooooo/resume-builder/dashboard/internal/data"
	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/menu"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/screens"
)

func TestAppModel_KBTransition(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	pm := screens.NewPipelineModel(th, []model.CareerApplication{}, model.PipelineMetrics{}, ".", 100, 30)
	jm := screens.NewJobsModel(th, []model.JobRow{}, 100, 30)
	prof := data.ProfileInfo{Name: "morgan", Role: "Staff Engineer", IsActive: true}
	kb := screens.NewKBModel(th, []data.KBItem{{ID: "1", Title: "Go Skill", Category: "Tools"}}, 100, 30).WithProfile(prof)
	mm := menu.NewMenuModel(th).WithProfile(prof)

	app := appModel{
		pipeline: pm,
		jobs:     jm,
		kb:       kb,
		menu:     mm,
		state:    viewMenu,
		theme:    th,
		width:    100,
		height:   30,
	}

	// Menu select "Knowledge Base"
	updated, cmd := app.Update(menu.MenuSelectMsg{Command: "Knowledge Base"})
	m, ok := updated.(appModel)
	if !ok {
		t.Fatalf("expected updated model to be appModel")
	}
	if m.state != viewKB {
		t.Errorf("expected app state to be viewKB, got %v", m.state)
	}
	_ = cmd

	// Render view for viewKB
	view := ansi.Strip(m.renderScreen())
	if !strings.Contains(view, "KNOWLEDGE BASE EXPLORER") {
		t.Errorf("expected view to contain 'KNOWLEDGE BASE EXPLORER', got:\n%s", view)
	}

	// Close KB screen
	updated, _ = m.Update(screens.KBCloseMsg{Quit: false})
	m, ok = updated.(appModel)
	if !ok {
		t.Fatalf("expected updated model to be appModel")
	}
	if m.state != viewMenu {
		t.Errorf("expected state to return to viewMenu, got %v", m.state)
	}
}

func TestAppModel_MobileTerminal(t *testing.T) {
	th := theme.NewTheme("catppuccin-mocha")
	app := appModel{
		theme:  th,
		width:  45,
		height: 20,
		state:  viewMenu,
		menu:   menu.NewMenuModel(th),
	}

	// In desktop mode (default), 45x20 triggers compact warning
	desktopView := ansi.Strip(app.renderScreen())
	if !strings.Contains(desktopView, "Terminal Window Too Small") {
		t.Errorf("expected 45x20 to trigger compact warning in desktop mode, got:\n%s", desktopView)
	}

	// In mobile mode, 45x20 is accepted and renders menu
	t.Setenv("RESUME_BUILDER_MOBILE", "1")
	mobileView := ansi.Strip(app.renderScreen())
	if strings.Contains(mobileView, "Terminal Window Too Small") {
		t.Errorf("expected 45x20 to NOT trigger compact warning in mobile mode, got:\n%s", mobileView)
	}
}

// testPaletteApp is an app sitting on the Jobs screen, which has both
// navigation targets and its own bindings.
func testPaletteApp() appModel {
	th := theme.NewTheme("catppuccin-mocha")
	prof := data.ProfileInfo{Name: "morgan", Role: "Staff Engineer", IsActive: true}
	return appModel{
		pipeline: screens.NewPipelineModel(th, []model.CareerApplication{}, model.PipelineMetrics{}, ".", 100, 30),
		jobs:     screens.NewJobsModel(th, []model.JobRow{}, 100, 30),
		kb:       screens.NewKBModel(th, []data.KBItem{}, 100, 30).WithProfile(prof),
		menu:     menu.NewMenuModel(th).WithProfile(prof),
		state:    viewJobs,
		theme:    th,
		width:    100,
		height:   30,
	}
}

func pressKey(app appModel, key string) appModel {
	msg := tea.KeyPressMsg(tea.Key{Code: []rune(key)[0], Text: key})
	if key == "ctrl+k" {
		msg = tea.KeyPressMsg(tea.Key{Code: 'k', Mod: tea.ModCtrl})
	}
	updated, _ := app.Update(msg)
	return updated.(appModel)
}

// ctrl+k opens the palette, and while it is open the keys the user types
// are the query -- they must NOT also reach the screen underneath.
func TestPaletteOpensAndSwallowsKeys(t *testing.T) {
	app := pressKey(testPaletteApp(), "ctrl+k")
	if !app.palette.Open {
		t.Fatal("ctrl+k did not open the palette")
	}
	app = pressKey(app, "p")
	if app.palette.Query() != "p" {
		t.Errorf("typed key did not reach the palette: query = %q", app.palette.Query())
	}
	if app.state != viewJobs {
		t.Errorf("a key typed into the palette changed the screen to %v", app.state)
	}
	view := ansi.Strip(screens.OverlayCentered(app.renderScreen(),
		app.palette.Render(app.theme, app.width, 8), app.width, app.height))
	if !strings.Contains(view, "enter run") {
		t.Errorf("the palette was not drawn over the screen:\n%s", view)
	}
}

// The menu is the navigation the palette stands in for, so it does not
// open there -- and the palette's own navigation rows go through the same
// dispatch the menu uses.
func TestPaletteNavigatesLikeTheMenu(t *testing.T) {
	app := testPaletteApp()
	app.state = viewMenu
	if pressKey(app, "ctrl+k").palette.Open {
		t.Error("the palette opened on the menu screen")
	}

	app = testPaletteApp()
	updated, _ := app.runPaletteCommand(screens.PaletteCommand{Nav: "Pipeline"})
	if got := updated.(appModel).state; got != viewPipeline {
		t.Errorf("palette navigation left the app on %v, want viewPipeline", got)
	}
}
