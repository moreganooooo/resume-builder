// Command prompt renders a single interactive prompt (select, confirm, or
// checkbox) described by a JSON spec passed as the program's one CLI
// argument, and writes the answer as JSON to stdout. The spec travels as
// an argument rather than stdin because huh's form needs real stdin for
// keystrokes -- piping the spec through stdin would consume the same
// channel a live terminal session needs.
//
// Generalizes dashboard/cmd/bootstrap's one-off pattern so
// scripts/charm_prompt.py can invoke this same binary for every
// questionary call site being migrated in scripts/menu.py, instead of a
// new Go binary per prompt.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"

	"github.com/charmbracelet/huh"
	"github.com/moreganooooo/resume-builder/dashboard/internal/theme"
	"github.com/moreganooooo/resume-builder/dashboard/internal/ui/prompt"
)

// cancelExitCode matches the shell SIGINT convention (128 + SIGINT's 2),
// distinguishing "user backed out" from any other failure so
// scripts/charm_prompt.py can map it to None instead of raising.
const cancelExitCode = 130

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "prompt: expected exactly one argument, a JSON prompt spec")
		os.Exit(1)
	}

	var spec prompt.Spec
	if err := json.Unmarshal([]byte(os.Args[1]), &spec); err != nil {
		fmt.Fprintf(os.Stderr, "prompt: invalid spec JSON: %v\n", err)
		os.Exit(1)
	}

	t := theme.NewTheme("")
	result, err := prompt.Run(t, spec)
	if err != nil {
		if errors.Is(err, huh.ErrUserAborted) {
			os.Exit(cancelExitCode)
		}
		fmt.Fprintf(os.Stderr, "prompt: %v\n", err)
		os.Exit(1)
	}

	out, err := json.Marshal(result)
	if err != nil {
		fmt.Fprintf(os.Stderr, "prompt: failed to encode result: %v\n", err)
		os.Exit(1)
	}
	fmt.Println(string(out))
}
