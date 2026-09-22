// Package prompt renders a single interactive prompt (select, confirm, or
// checkbox) from a JSON spec and returns the answer. Generalizes the
// one-off dashboard/cmd/bootstrap pattern (a bespoke Go/huh binary per
// prompt) into a single reusable binary driven by data instead of code,
// so scripts/menu.py's remaining questionary call sites can move to Charm
// without a new Go binary per prompt.
package prompt

import (
	"fmt"
	"os"

	tea "charm.land/bubbletea/v2"
	"charm.land/huh/v2"
	"github.com/charmbracelet/colorprofile"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
)

// newForm builds a huh.Form with this app's theme and a forced TrueColor
// profile. Color-profile detection (like isDark in theme.HuhTheme) reads
// TERM/COLORTERM from the subprocess environment rather than doing an
// async terminal round trip, but it's just as unreliable in practice
// through this Python-subprocess invocation -- COLORTERM doesn't always
// survive being inherited down from a real terminal through a shell
// through subprocess.run(), so the profile can silently downgrade to
// ANSI/no-color, which is indistinguishable from "no color set" (default
// foreground, often black) for anything this app didn't explicitly give
// a background too. Forcing TrueColor sidesteps that the same way
// HuhTheme() sidesteps the isDark detection.
//
// WithProgramOptions *replaces* Form.teaOptions rather than appending to
// it, so tea.WithOutput(os.Stderr) -- the default NewForm() sets, and the
// whole reason rendering ever reaches the real terminal instead of the
// piped stdout Python captures for the JSON answer -- must be repeated
// here explicitly or this call silently undoes that fix.
func newForm(t theme.Theme, group *huh.Group) *huh.Form {
	return huh.NewForm(group).
		WithTheme(t.HuhTheme()).
		WithProgramOptions(
			tea.WithOutput(os.Stderr),
			tea.WithColorProfile(colorprofile.TrueColor),
		)
}

// Option is one selectable item in a select or checkbox prompt.
type Option struct {
	Label string `json:"label"`
	Value string `json:"value"`
	// Heading marks a non-selectable section title (select only).
	Heading bool `json:"heading,omitempty"`
	// Description is a supporting line rendered under the label, dimmer
	// than it (select only). It carries what used to be an inline
	// parenthetical on the label itself: at a glance the menu is then six
	// short names rather than six sentences, and the explanation is still
	// right there for anyone who needs it.
	Description string `json:"description,omitempty"`
}

// Spec describes the prompt to render, decoded from the CLI argument JSON.
// Default is used by "confirm"; DefaultValue is used by "select" and
// "text" (the pre-filled/editable starting value) -- kept as separate
// fields since they're different JSON types, not a shared "default" key.
// CurrentDirectory/AllowedTypes are used only by "filepicker".
type Spec struct {
	Type             string   `json:"type"` // "select", "confirm", "checkbox", "text", or "filepicker"
	Message          string   `json:"message"`
	Options          []Option `json:"options,omitempty"`
	Default          bool     `json:"default,omitempty"`
	DefaultValue     string   `json:"default_value,omitempty"`
	CurrentDirectory string   `json:"current_directory,omitempty"`
	AllowedTypes     []string `json:"allowed_types,omitempty"`
	// Masked, "text"-only, renders the input with huh's password EchoMode
	// (dots instead of the typed characters) -- for secrets like an API
	// key, where echoing the raw paste back to the terminal both leaks it
	// over-the-shoulder and, in a screen-recorded onboarding session,
	// into the recording.
	Masked bool `json:"masked,omitempty"`
}

// Result is the answer, encoded to stdout JSON. Exactly one field is
// meaningful, matching Spec.Type: Confirmed for "confirm", Value for
// "select"/"text"/"filepicker", Values for "checkbox". Value deliberately
// has NO omitempty: an empty string is a legitimate answer (e.g. a user
// skipping an optional text prompt with a blank line), and omitempty on a
// string drops the key entirely rather than emitting "". Python's
// charm_prompt.text()/select() index data["value"] unconditionally, so a
// missing key -- not just an empty one -- crashed with a KeyError the
// first time a real user actually skipped a text prompt (observed
// 2026-09-06, confirm_missing_coverage_keywords_interactively's optional
// note field).
type Result struct {
	Value     string   `json:"value"`
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
		if needsSectionModel(spec) {
			return runSections(t, spec)
		}
		return runSelect(t, spec)
	case "checkbox":
		return runCheckbox(t, spec)
	case "grid":
		return runGrid(t, spec)
	case "text":
		return runText(t, spec)
	case "filepicker":
		return runFilePicker(t, spec)
	default:
		return Result{}, fmt.Errorf("unknown prompt type %q", spec.Type)
	}
}

func runConfirm(t theme.Theme, spec Spec) (Result, error) {
	answer := spec.Default
	field := huh.NewConfirm().
		Title(spec.Message).
		Value(&answer)
	form := newForm(t, huh.NewGroup(field))
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
	form := newForm(t, huh.NewGroup(field))
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	return Result{Value: answer}, nil
}

// runText renders a free-text input field -- the one prompt type
// scripts/charm_prompt.py never got a Go counterpart for (see its own
// module docstring), so cli_art.text()'s two call sites (menu.py's Stale
// Sweep age-threshold prompt, cli.py's GEMINI_API_KEY entry) stayed on
// raw questionary.text() long after confirm/select/checkbox migrated.
// That mattered beyond just visual consistency: menu.py's
// _run_with_chain() sets a DECSTBM scroll region around every leaf
// action's banner, and prompt_toolkit (questionary's renderer) doesn't
// understand a clamped scroll region -- Stale Sweep's prompt rendered
// nothing at all under it, the same dead-end evaluate_all's confirm had
// before it was routed through huh. See picker.should_proceed()'s
// docstring for the fuller writeup of that conflict.
func runText(t theme.Theme, spec Spec) (Result, error) {
	answer := spec.DefaultValue
	field := huh.NewInput().
		Title(spec.Message).
		Value(&answer)
	if spec.Masked {
		field = field.EchoMode(huh.EchoModePassword)
	}
	form := newForm(t, huh.NewGroup(field))
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	return Result{Value: answer}, nil
}

// runFilePicker renders huh's single-file picker. There is no multi-file
// picker in this huh version (confirmed via `go doc`), so multi-file intake
// is handled Python-side as a pick-one-then-loop-and-confirm-another UX
// rather than here.
func runFilePicker(t theme.Theme, spec Spec) (Result, error) {
	var answer string
	field := huh.NewFilePicker().
		Title(spec.Message).
		// huh's own keybindings aren't discoverable from the picker itself
		// (arrows just move the highlighted row; entering a folder needs
		// -> or l, not Enter) -- this was reported as "arrows show
		// confusing unrecognized options" by a brand-new user. Spelling
		// it out here is cheaper than retraining muscle memory.
		Description("↑↓ move · → or l open folder · ← or h go up · Enter select file").
		FileAllowed(true).
		DirAllowed(false).
		ShowSize(true).
		Value(&answer)
	if spec.CurrentDirectory != "" {
		field = field.CurrentDirectory(spec.CurrentDirectory)
	}
	if len(spec.AllowedTypes) > 0 {
		field = field.AllowedTypes(spec.AllowedTypes)
	}
	form := newForm(t, huh.NewGroup(field))
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	return Result{Value: answer}, nil
}

// checkboxViewportHeight bounds how many options huh renders/lays out at
// once. Unbounded, a long checkbox (e.g. skill_gap_scan.py's pending-
// pipeline skill list, which can run into the hundreds) redraws every
// option on every keystroke -- this turns it into a fixed scrollable
// window instead, which is also what makes Filterable's live re-filtering
// stay responsive on a large list. Raised from 14 to 24 (2026-09-08, per
// direct user request for a bigger viewable window) -- still a fixed
// constant rather than a real-terminal-size read, since huh's own
// Bubbletea render runs independent of the DECSTBM scroll region
// menu.py's _run_with_chain sets around it; a much larger value risks
// overflowing a short terminal window.
const checkboxViewportHeight = 24

func runCheckbox(t theme.Theme, spec Spec) (Result, error) {
	var answer []string
	opts := make([]huh.Option[string], len(spec.Options))
	for i, o := range spec.Options {
		opts[i] = huh.NewOption(o.Label, o.Value)
	}
	field := huh.NewMultiSelect[string]().
		Title(spec.Message).
		Options(opts...).
		Filterable(true).
		Height(checkboxViewportHeight).
		Value(&answer)
	form := newForm(t, huh.NewGroup(field))
	if err := form.Run(); err != nil {
		return Result{}, err
	}
	if answer == nil {
		answer = []string{}
	}
	return Result{Values: answer}, nil
}
