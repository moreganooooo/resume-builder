// Package bootstrap implements the new‑user onboarding wizard using charmbracelet/huh.
package bootstrap

import (
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
    "strings"
    "github.com/charmbracelet/huh"
    "github.com/moreganooooo/resume-builder/dashboard/internal/theme"
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

    // Build the form using Huh. The theme conversion lives in theme.Theme.
    form := huh.NewForm(
        huh.NewGroup(
            // Profile name – required.
            huh.NewInput().
                Title("👤 Profile name").
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
                Title("📂 Source of your career data").
                Options(
                    huh.NewOption("Resume PDF", "pdf"),
                    huh.NewOption("LinkedIn export (JSON)", "linkedin"),
                    huh.NewOption("Manual markdown", "manual"),
                ).
                Value(&data.SourceChoice),
            // Path to source – only show when not manual.
            huh.NewInput().
                Title("📁 Path to source file/folder").
                Value(&data.IngestPath).
                CharLimit(256).
                Description("Absolute path on your machine.").
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
                }).
                ShowIf(func() bool { return data.SourceChoice != "manual" }),
            // Whether to generate the bullet bank now.
            huh.NewConfirm().
                Title("🪄 Build the bullet‑bank now?").
                Description("You can always run it later with `resume bullet‑bank`. ").
                Value(&data.CreateBullet),
        ),
    ).WithTheme(t.HuhTheme())

    err := form.Run()
    if err == nil {
        // Persist wizard data for future runs
        if cfgDir, e := os.UserConfigDir(); e == nil {
            cfgPath := filepath.Join(cfgDir, "resume-builder", "wizard.json")
            _ = os.MkdirAll(filepath.Dir(cfgPath), 0o755)
            _ = os.WriteFile(cfgPath, []byte(data.ToJSON()), 0o644)
        }
    }
    return data, err
}
