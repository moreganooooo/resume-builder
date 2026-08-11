// Package main provides a tiny wrapper that runs the Huh onboarding wizard
// and prints the collected data as JSON to stdout. The Go dashboard binary
// can be invoked from the Python menu to replace the existing questionary
// bootstrap flow.
package main

import (
    "errors"
    "fmt"
    "log"
    "os"

    "github.com/charmbracelet/huh"
    "github.com/moreganooooo/resume-builder/dashboard/internal/ui/bootstrap"
    "github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// cancelExitCode matches the shell SIGINT convention (128 + SIGINT's 2),
// distinguishing "user backed out" from a real error -- same constant
// dashboard/cmd/prompt/main.go uses, so callers on the Python side can
// treat both binaries' cancellation the same way.
const cancelExitCode = 130

func main() {
    // Match dashboard/main.go's own default (-theme resume-builder) rather
    // than falling back to generic Catppuccin auto-detection -- this
    // binary is launched standalone by scripts/menu.py with no --theme
    // flag, so "" here would otherwise put a new user's first-ever screen
    // off-brand while every screen after it is on-brand.
    t := theme.NewTheme("resume-builder")
    data, err := bootstrap.Run(t)
    if err != nil {
        // Previously any cancellation (Esc/Ctrl-C) hit log.Fatalf just like
        // a real error, exiting 1 -- indistinguishable to a caller from an
        // actual failure. cmd/prompt/main.go already made this distinction
        // for huh.ErrUserAborted; this wraps the same huh form library, so
        // it gets the same treatment.
        if errors.Is(err, huh.ErrUserAborted) {
            os.Exit(cancelExitCode)
        }
        log.Fatalf("bootstrap wizard errored: %v", err)
    }
    // Emit JSON for the Python side to consume.
    fmt.Println(data.ToJSON())
}
