package main

import (
	"bufio"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
)

func main() {
	pattern := regexp.MustCompile(`lipgloss\.Color\("?#?[0-9a-fA-F]{3,6}"?\)`)
	
	// Assuming this is run from the dashboard directory
	root := "internal/ui"
	
	hasErrors := false

	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		
		if info.IsDir() || filepath.Ext(path) != ".go" {
			return nil
		}

		file, err := os.Open(path)
		if err != nil {
			return err
		}
		defer file.Close()

		scanner := bufio.NewScanner(file)
		lineNum := 1
		for scanner.Scan() {
			line := scanner.Text()
			if pattern.MatchString(line) {
				fmt.Printf("Warning: Hard-coded color found in %s:%d\n", path, lineNum)
				fmt.Printf("  %s\n", line)
				fmt.Printf("  Please use theme.Token.* instead.\n\n")
				hasErrors = true
			}
			lineNum++
		}

		return scanner.Err()
	})

	if err != nil {
		fmt.Printf("Error walking through %s: %v\n", root, err)
		os.Exit(1)
	}

	if hasErrors {
		os.Exit(1)
	} else {
		fmt.Println("Color linting passed: no hard-coded colors found.")
	}
}
