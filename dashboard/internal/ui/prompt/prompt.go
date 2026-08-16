// Package prompt renders a single interactive prompt (select, confirm, or
// checkbox) from a JSON spec and returns the answer. Generalizes the
// one-off dashboard/cmd/bootstrap pattern (a bespoke Go/huh binary per
// prompt) into a single reusable binary driven by data instead of code,
// so scripts/menu.py's remaining questionary call sites can move to Charm
// without a new Go binary per prompt.
package prompt

import (
	"fmt"

	"charm.land/huh/v2"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// Option is one selectable item in a select or checkbox prompt.
type Option struct {
	Label string `json:"label"`
	Value string `json:"value"`
}

// Spec describes the prompt to render, decoded from the CLI argument JSON.
// Default is used by "confirm"; DefaultValue is used by "select" -- kept
// as separate fields since they're different JSON types, not a shared
// "default" key.
type Spec struct {
	Type         string   `json:"type"` // "select", "confirm", or "checkbox"
	Message      string   `json:"message"`
	Options      []Option `json:"options,omitempty"`
	Default      bool     `json:"default,omitempty"`
	DefaultValue string   `json:"default_value,omitempty"`
}

// Result is the answer, encoded to stdout JSON. Exactly one field is set,
// matching Spec.Type: Confirmed for "confirm", Value for "select", Values
// for "checkbox".
type Result struct {
	Value     string   `json:"value,omitempty"`
	Values    []string `json:"values,omitempty"`
	Confirmed *bool    `json:"confirmed,omitempty"`
}

// Run renders the prompt described by spec using the given theme and
// returns the answer. On cancellation (ESC/Ctrl-C), the returned error
// wraps huh.ErrUserAborted -- dashboard/cmd/prompt/main.go checks for it
// with errors.Is to map it to a distinct exit code.
func Run(t theme.Theme, spec Spec) (Result, error) {
	switch spec.Type {
	case "confirm":
		return runConfirm(t, spec)
	case "select":
		return runSelect(t, spec)
	case "checkbox":
		return runCheckbox(t, spec)
	default:
		return Result{}, fmt.Errorf("unknown prompt type %q", spec.Type)
	}
}

func runConfirm(t theme.Theme, spec Spec) (Result, error) {
	answer := spec.Default
	field := huh.NewConfirm().
		Title(spec.Message).
		Value(&answer)
	form := huh.NewForm(huh.NewGroup(field)).WithTheme(t.HuhTheme())
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	return Result{Confirmed: &answer}, nil
}

func runSelect(t theme.Theme, spec Spec) (Result, error) {
	answer := spec.DefaultValue
	opts := make([]huh.Option[string], len(spec.Options))
	for i, o := range spec.Options {
		opts[i] = huh.NewOption(o.Label, o.Value)
	}
	field := huh.NewSelect[string]().
		Title(spec.Message).
		Options(opts...).
		Value(&answer)
	form := huh.NewForm(huh.NewGroup(field)).WithTheme(t.HuhTheme())
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	return Result{Value: answer}, nil
}

func runCheckbox(t theme.Theme, spec Spec) (Result, error) {
	var answer []string
	opts := make([]huh.Option[string], len(spec.Options))
	for i, o := range spec.Options {
		opts[i] = huh.NewOption(o.Label, o.Value)
	}
	field := huh.NewMultiSelect[string]().
		Title(spec.Message).
		Options(opts...).
		Value(&answer)
	form := huh.NewForm(huh.NewGroup(field)).WithTheme(t.HuhTheme())
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	if answer == nil {
		answer = []string{}
	}
	return Result{Values: answer}, nil
}
