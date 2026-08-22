package main

import (
	"strings"
	"testing"

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
