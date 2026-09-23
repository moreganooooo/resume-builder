package main

import (
	"errors"
	"fmt"
	"image/color"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"charm.land/fang/v2"
	"charm.land/lipgloss/v2"

	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// fangColorScheme maps the design system's CLI palette onto fang: Mauve for
// the program name, Blue for section headings, Peach for flags, Subtext for
// descriptions (guidelines/cli-fang.card.html). One palette for the TUI and
// its front door, so --help does not look like a different program.
func fangColorScheme(t theme.Theme) fang.ColorScheme {
	return fang.ColorScheme{
		Base:           t.Text,
		Title:          t.Blue,
		Description:    t.Subtext,
		Codeblock:      t.Surface,
		Program:        t.Mauve,
		DimmedArgument: t.Subtext,
		Comment:        t.Subtext,
		Flag:           t.Peach,
		FlagDefault:    t.Subtext,
		Command:        t.Mauve,
		QuotedString:   t.Green,
		Argument:       t.Text,
		Help:           t.Subtext,
		Dash:           t.Subtext,
		ErrorHeader:    [2]color.Color{t.Red, nil},
		ErrorDetails:   t.Text,
	}
}

// fixError carries the plain-language fix the card asks every error to name.
type fixError struct {
	msg, fix string
}

func (e fixError) Error() string { return e.msg }

// fangErrorHandler renders "✗ Error <message>" with the fix on the next
// line and no stack trace -- the same rule as every error in the TUI.
func fangErrorHandler(t theme.Theme) fang.ErrorHandler {
	return func(w io.Writer, _ fang.Styles, err error) {
		head := lipgloss.NewStyle().Foreground(t.Red).Bold(true).Render("✗ Error")
		body := lipgloss.NewStyle().Foreground(t.Text).Render(err.Error())
		_, _ = fmt.Fprintf(w, "\n  %s %s\n", head, body)
		var fe fixError
		if errors.As(err, &fe) && fe.fix != "" {
			_, _ = fmt.Fprintf(w, "  %s\n", lipgloss.NewStyle().Foreground(t.Subtext).Render(fe.fix))
		} else if strings.Contains(err.Error(), "flag") || strings.Contains(err.Error(), "argument") {
			_, _ = fmt.Fprintf(w, "  %s\n", lipgloss.NewStyle().Foreground(t.Subtext).Render("Run dashboard --help for the flags it takes."))
		}
		_, _ = fmt.Fprintln(w)
	}
}

// checkProfile refuses a profile with no folder under <project-root>/profiles,
// naming the closest one. It matches case-insensitively, as the Python side
// does (macOS resolves profiles/Morgan and profiles/morgan to one directory).
// A project root with no profiles/ directory at all is left alone: that is
// a career-ops checkout, which has no profiles.
func checkProfile(projectRoot, profile string) error {
	entries, err := os.ReadDir(filepath.Join(projectRoot, "profiles"))
	if err != nil {
		return nil
	}
	var names []string
	for _, e := range entries {
		if e.IsDir() && !strings.HasPrefix(e.Name(), ".") {
			if strings.EqualFold(e.Name(), profile) {
				return nil
			}
			names = append(names, e.Name())
		}
	}
	if len(names) == 0 {
		return nil
	}
	sort.Strings(names)
	fix := "Profiles live in ./profiles: " + strings.Join(names, ", ") + "."
	if best := closestName(profile, names); best != "" {
		fix = fmt.Sprintf("Did you mean %s? %s", best, fix)
	}
	return fixError{msg: fmt.Sprintf("unknown profile %q", profile), fix: fix}
}

// closestName returns the name within edit distance 2 of s, or "".
func closestName(s string, names []string) string {
	best, bestD := "", 3
	for _, n := range names {
		if d := editDistance(strings.ToLower(s), strings.ToLower(n)); d < bestD {
			best, bestD = n, d
		}
	}
	return best
}

func editDistance(a, b string) int {
	ra, rb := []rune(a), []rune(b)
	prev := make([]int, len(rb)+1)
	for j := range prev {
		prev[j] = j
	}
	for i := 1; i <= len(ra); i++ {
		cur := make([]int, len(rb)+1)
		cur[0] = i
		for j := 1; j <= len(rb); j++ {
			cost := 1
			if ra[i-1] == rb[j-1] {
				cost = 0
			}
			cur[j] = min(prev[j]+1, cur[j-1]+1, prev[j-1]+cost)
		}
		prev = cur
	}
	return prev[len(rb)]
}
