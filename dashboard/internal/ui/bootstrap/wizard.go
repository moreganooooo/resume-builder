// Package bootstrap implements the new‑user onboarding wizard using charmbracelet/huh.
package bootstrap

import (
	"encoding/json"
	"fmt"
	"github.com/charmbracelet/huh"
	"github.com/charmbracelet/log"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"os"
	"path/filepath"
	"strings"
)

// WizardData holds the values collected from the user.
type WizardData struct {
	ProfileName  string `json:"profile_name"`
	SourceChoice string `json:"source_choice"`
	IngestPath   string `json:"ingest_path,omitempty"`
	CreateBullet bool   `json:"create_bullet"`
}

// ToJSON returns a JSON representation of the wizard data.
func (w WizardData) ToJSON() string {
	b, _ := json.Marshal(w)
	return string(b)
}

// Run launches the wizard and returns the filled WizardData.
func Run(t theme.Theme) (WizardData, error) {
	var data WizardData

	// Sensible default starting point for the file picker below: the
	// user's home directory, not this binary's own working directory
	// (which could be anywhere -- wherever `resume dashboard` happened to
	// be launched from). Falls back to "." only if the OS genuinely can't
	// report a home directory (HOME unset, no passwd entry, etc.).
	homeDir, err := os.UserHomeDir()
	if err != nil || homeDir == "" {
		homeDir = "."
	}

	// Build the form using Huh. The theme conversion lives in theme.Theme.
	// Titles route through t.Icons rather than hardcoded emoji so they honor
	// RESUME_BUILDER_ICONS=unicode the same way every other dashboard glyph
	// does, and render consistently across terminal fonts instead of
	// whatever the local emoji font happens to draw.
	form := huh.NewForm(
		huh.NewGroup(
			// Profile name – required.
			huh.NewInput().
				Title(t.Icons.Profile+" Profile name").
				Value(&data.ProfileName).
				Description("A short, memorable identifier (e.g. “morgan”).").
				Validate(func(s string) error {
					if s == "" {
						return fmt.Errorf("profile name cannot be empty")
					}
					return nil
				}),
			// Choose source type.
			huh.NewSelect[string]().
				Title(t.Icons.Source+" Source of your career data").
				Options(
					huh.NewOption("Resume PDF", "pdf"),
					huh.NewOption("LinkedIn export (JSON)", "linkedin"),
					huh.NewOption("Manual markdown", "manual"),
				).
				Value(&data.SourceChoice),
			// Path to source. Previously a plain text Input demanding a
			// typed absolute filesystem path -- fluency this project's own
			// audience (job seekers, not developers) can't be assumed to
			// have. huh v0.4.1 vendors a real FilePicker (bubbles'
			// filepicker.Model under the hood), so this browses instead of
			// asking for a path to be typed from memory, starting in the
			// user's home directory rather than wherever the dashboard
			// process happens to have been launched from -- a much more
			// "sensible default" starting point than this binary's own cwd.
			// huh v0.4.1's fields have no per-field ShowIf, so this stays
			// visible even when SourceChoice is "manual" -- the Validate
			// func below already treats it as a no-op in that case.
			huh.NewFilePicker().
				Title(t.Icons.Path+" Source file").
				Value(&data.IngestPath).
				CurrentDirectory(homeDir).
				AllowedTypes([]string{".pdf", ".json", ".jsonl"}).
				Description("Press Enter to browse and pick the file (starts in your home folder).").
				Validate(func(s string) error {
					if data.SourceChoice == "manual" {
						return nil
					}
					if s == "" {
						return fmt.Errorf("path cannot be empty")
					}
					info, err := os.Stat(s)
					if err != nil {
						return fmt.Errorf("path does not exist")
					}
					ext := strings.ToLower(filepath.Ext(s))
					switch data.SourceChoice {
					case "pdf":
						if ext != ".pdf" {
							return fmt.Errorf("expected .pdf file")
						}
					case "linkedin":
						if ext != ".json" && ext != ".jsonl" {
							return fmt.Errorf("expected .json export for LinkedIn")
						}
					}
					_ = info // silence unused variable warning
					return nil
				}),
			// Whether to generate the bullet bank now.
			huh.NewConfirm().
				Title(t.Icons.Magic+" Build the bullet‑bank now?").
				Description("You can always run it later with `resume bullet‑bank`. ").
				Value(&data.CreateBullet),
		),
	).WithTheme(t.HuhTheme())

	err = form.Run()
	if err == nil {
		// Persist wizard data for future runs -- best-effort convenience,
		// not required for this run to have succeeded, so a persistence
		// failure logs (rather than fails the wizard) and only affects a
		// future run's defaults.
		if cfgDir, e := os.UserConfigDir(); e == nil {
			cfgPath := filepath.Join(cfgDir, "resume-builder", "wizard.json")
			if e := os.MkdirAll(filepath.Dir(cfgPath), 0o755); e != nil {
				log.Warnf("could not create %s: %v", filepath.Dir(cfgPath), e)
			} else if e := os.WriteFile(cfgPath, []byte(data.ToJSON()), 0o644); e != nil {
				log.Warnf("could not write %s: %v", cfgPath, e)
			}
		} else {
			log.Warnf("could not determine user config dir: %v", e)
		}
	}
	return data, err
}
