// Package main provides a tiny wrapper that runs the Huh onboarding wizard
// and prints the collected data as JSON to stdout. The Go dashboard binary
// can be invoked from the Python menu to replace the existing questionary
// bootstrap flow.
package main

import (
    "fmt"
    "log"
    "github.com/moreganooooo/resume-builder/dashboard/internal/ui/bootstrap"
    "github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

func main() {
    // Match dashboard/main.go's own default (-theme resume-builder) rather
    // than falling back to generic Catppuccin auto-detection -- this
    // binary is launched standalone by scripts/menu.py with no --theme
    // flag, so "" here would otherwise put a new user's first-ever screen
    // off-brand while every screen after it is on-brand.
    t := theme.NewTheme("resume-builder")
    data, err := bootstrap.Run(t)
    if err != nil {
        log.Fatalf("bootstrap wizard cancelled or errored: %v", err)
    }
    // Emit JSON for the Python side to consume.
    fmt.Println(data.ToJSON())
}
