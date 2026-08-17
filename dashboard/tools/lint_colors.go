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

// adaptiveLiteralPattern catches a raw hex string inside a
// lipgloss.AdaptiveColor{Light: "#...", Dark: "#..."} literal -- a second
// way to hardcode a color that bypasses both literalPattern (no
// lipgloss.Color(...) call wraps it) and identifierPattern (no identifier
// argument at all). Matches on the field name + hex pair rather than the
// whole struct literal, since Light/Dark commonly land on separate lines.
var adaptiveLiteralPattern = regexp.MustCompile(`(?:Light|Dark):\s*"#[0-9a-fA-F]{3,6}"`)

// gradientLiteralPattern catches raw hex strings in RenderGradient calls --
// use theme.RenderColorGradient(text, c1, c2) with theme.Theme tokens instead.
var gradientLiteralPattern = regexp.MustCompile(`RenderGradient\([^,]+,\s*"#[0-9a-fA-F]{3,6}"`)

// identifierPattern catches lipgloss.Color(SomeIdentifier) -- the form
// literalPattern can't see, since the value isn't a literal hex string at
// the call site. This is exactly how the Main Menu's selection style and
// HoverStyle stayed hardcoded across all three themes (via the
// module-level BrandColor/AccentColor constants in tokens.go) while this
// linter reported a clean pass: neither issue was a literal hex string,
// and neither file was even under the walked root (see roots below).
//
// The identifier segment allows dots (package.Const, or a dotted field
// chain) -- the original bare-identifier-only version couldn't see
// lipgloss.Color(theme.AccentColor) either, which let viewer.go's link
// color hardcode that same module-level constant well after the Main
// Menu fix above. Theme fields (t.Blue, m.theme.Token.Mauve, ...) are
// already lipgloss.Color-typed and are never legitimately re-wrapped in
// another lipgloss.Color(...) call, so this widened pattern has no new
// false positives against real token usage -- every current match in the
// codebase outside themeConstructorFiles is exactly the bug class this
// linter exists to catch.
var identifierPattern = regexp.MustCompile(`lipgloss\.Color\(([A-Za-z_][A-Za-z0-9_.]*)\)`)

// themeConstructorFiles lists the files where literal hex (or the
// BrandColor/AccentColor module-level constants) are the legitimate
// source of truth a token is built from -- the three theme constructors
// defining what each palette's colors actually are, plus tokens.go
// itself. Every other file should be consuming a theme.Theme field
// (t.Blue, t.Token.Mauve, ...) instead of a literal or a module-level
// color constant.
var themeConstructorFiles = map[string]bool{
	"internal/theme/tokens.go":           true,
	"internal/theme/theme.go":            true,
	"internal/theme/resumebuilder.go":    true,
	"internal/theme/catppuccin.go":       true,
	"internal/theme/catppuccin_latte.go": true,
}

// lintFile scans one .go file for the three hardcoded-color patterns above,
// printing a warning per match. Shared between the directory walk and the
// standalone top-level files below so both paths apply the exact same
// checks -- a second, drifted copy of this logic was exactly how the
// walked-roots gap itself went unnoticed for as long as it did.
func lintFile(path, relPath string) (hasErrors bool, err error) {
	file, err := os.Open(path)
	if err != nil {
		return false, err
	}
	defer file.Close()

	scanner := bufio.NewScanner(file)
	lineNum := 1
	allowed := themeConstructorFiles[relPath]
	for scanner.Scan() {
		line := scanner.Text()
		if !allowed && literalPattern.MatchString(line) {
			fmt.Printf("Warning: Hard-coded color found in %s:%d\n", relPath, lineNum)
			fmt.Printf("  %s\n", line)
			fmt.Printf("  Please use theme.Token.* instead.\n\n")
			hasErrors = true
		}
		if !allowed {
			if m := identifierPattern.FindStringSubmatch(line); m != nil {
				fmt.Printf("Warning: Non-token color identifier found in %s:%d\n", relPath, lineNum)
				fmt.Printf("  %s\n", line)
				fmt.Printf("  lipgloss.Color(%s) bypasses the per-theme token system -- use a theme.Theme field (t.Blue, t.Token.Mauve, ...) instead.\n\n", m[1])
				hasErrors = true
			}
		}
		if !allowed && adaptiveLiteralPattern.MatchString(line) {
			fmt.Printf("Warning: Hard-coded color found in %s:%d\n", relPath, lineNum)
			fmt.Printf("  %s\n", line)
			fmt.Printf("  lipgloss.AdaptiveColor{...} with a raw hex literal bypasses the per-theme token system -- use a theme.Theme field instead.\n\n")
			hasErrors = true
		}
		if !allowed && gradientLiteralPattern.MatchString(line) {
			fmt.Printf("Warning: Hard-coded hex gradient found in %s:%d\n", relPath, lineNum)
			fmt.Printf("  %s\n", line)
			fmt.Printf("  RenderGradient with raw hex literal bypasses the per-theme token system -- use theme.RenderColorGradient(text, c1, c2) instead.\n\n")
			hasErrors = true
		}
		lineNum++
	}

	return hasErrors, scanner.Err()
}

func main() {
	// Auto-detect whether running from repo root or dashboard/ directory
	baseDir := "."
	if _, err := os.Stat("internal/ui"); err != nil {
		if _, err := os.Stat("dashboard/internal/ui"); err == nil {
			baseDir = "dashboard"
		}
	}

	roots := []string{"internal/ui", "internal/theme", "internal/model", "internal/data", "cmd"}
	standaloneFiles := []string{"main.go"}

	hasErrors := false

	for _, root := range roots {
		fullRoot := filepath.Join(baseDir, root)
		err := filepath.Walk(fullRoot, func(path string, info os.FileInfo, err error) error {
			if err != nil {
				return err
			}
			if info.IsDir() || filepath.Ext(path) != ".go" || strings.HasSuffix(path, "_test.go") {
				return nil
			}
			relPath, _ := filepath.Rel(baseDir, path)
			fileHasErrors, err := lintFile(path, relPath)
			if err != nil {
				return err
			}
			hasErrors = hasErrors || fileHasErrors
			return nil
		})

		if err != nil {
			fmt.Printf("Error walking through %s: %v\n", fullRoot, err)
			os.Exit(1)
		}
	}

	for _, relPath := range standaloneFiles {
		fullPath := filepath.Join(baseDir, relPath)
		fileHasErrors, err := lintFile(fullPath, relPath)
		if err != nil {
			fmt.Printf("Error reading %s: %v\n", fullPath, err)
			os.Exit(1)
		}
		hasErrors = hasErrors || fileHasErrors
	}

	if hasErrors {
		os.Exit(1)
	} else {
		fmt.Println("Color linting passed: no hard-coded colors found.")
	}
}
