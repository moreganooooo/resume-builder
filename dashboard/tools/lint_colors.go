package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// literalPattern catches lipgloss.Color("#hex") / lipgloss.Color(#hex) --
// a color written directly at the call site instead of through a theme
// token.
var literalPattern = regexp.MustCompile(`lipgloss\.Color\("?#?[0-9a-fA-F]{3,6}"?\)`)

// identifierPattern catches lipgloss.Color(SomeIdentifier) -- the form
// literalPattern can't see, since the value isn't a literal hex string at
// the call site. This is exactly how the Main Menu's selection style and
// HoverStyle stayed hardcoded across all three themes (via the
// module-level BrandColor/AccentColor constants in tokens.go) while this
// linter reported a clean pass: neither issue was a literal hex string,
// and neither file was even under the walked root (see roots below).
var identifierPattern = regexp.MustCompile(`lipgloss\.Color\(([A-Za-z_][A-Za-z0-9_]*)\)`)

// themeConstructorFiles lists the files where literal hex (or the
// BrandColor/AccentColor/BaseColor/PrintColor constants) are the
// legitimate source of truth a token is built from -- the four theme
// constructors defining what each palette's colors actually are, plus
// tokens.go itself. Every other file should be consuming a theme.Theme
// field (t.Blue, t.Token.Mauve, ...) instead of a literal or a
// module-level color constant.
var themeConstructorFiles = map[string]bool{
	"internal/theme/tokens.go":           true,
	"internal/theme/resumebuilder.go":    true,
	"internal/theme/catppuccin.go":       true,
	"internal/theme/catppuccin_latte.go": true,
}

func main() {
	// internal/theme was previously excluded entirely -- the exact
	// package where hardcoded, non-token colors are most likely (and,
	// historically, actually did) slip in unnoticed.
	roots := []string{"internal/ui", "internal/theme"}

	hasErrors := false

	for _, root := range roots {
		err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}

			if info.IsDir() || filepath.Ext(path) != ".go" || strings.HasSuffix(path, "_test.go") {
				return nil
			}

			file, err := os.Open(path)
			if err != nil {
				return err
			}
			defer file.Close()

			scanner := bufio.NewScanner(file)
			lineNum := 1
			allowed := themeConstructorFiles[path]
			for scanner.Scan() {
				line := scanner.Text()
				if !allowed && literalPattern.MatchString(line) {
					fmt.Printf("Warning: Hard-coded color found in %s:%d\n", path, lineNum)
					fmt.Printf("  %s\n", line)
					fmt.Printf("  Please use theme.Token.* instead.\n\n")
					hasErrors = true
				}
				if !allowed {
					if m := identifierPattern.FindStringSubmatch(line); m != nil {
						fmt.Printf("Warning: Non-token color identifier found in %s:%d\n", path, lineNum)
						fmt.Printf("  %s\n", line)
						fmt.Printf("  lipgloss.Color(%s) bypasses the per-theme token system -- use a theme.Theme field (t.Blue, t.Token.Mauve, ...) instead.\n\n", m[1])
						hasErrors = true
					}
				}
				lineNum++
			}

			return scanner.Err()
		})

		if err != nil {
			fmt.Printf("Error walking through %s: %v\n", root, err)
			os.Exit(1)
		}
	}

	if hasErrors {
		os.Exit(1)
	} else {
		fmt.Println("Color linting passed: no hard-coded colors found.")
	}
}
