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
    // Load the current theme (same logic as the rest of the dashboard).
    t := theme.NewTheme("") // "" triggers auto detection.
    data, err := bootstrap.Run(t)
    if err != nil {
        log.Fatalf("bootstrap wizard cancelled or errored: %v", err)
    }
    // Emit JSON for the Python side to consume.
    fmt.Println(data.ToJSON())
}
