package data

import (
	"errors"
	"fmt"
	"path/filepath"
	"strings"
)

// ErrPathTraversal is returned when a target path attempts to escape the root directory.
var ErrPathTraversal = errors.New("path traversal detected: target is outside allowed directory")

// SafePath joins baseDir with userPath (or cleans userPath if already absolute/relative)
// and guarantees that the resulting path remains strictly contained within baseDir.
func SafePath(baseDir, userPath string) (string, error) {
	if baseDir == "" {
		baseDir = "."
	}

	cleanBase, err := filepath.Abs(filepath.Clean(baseDir))
	if err != nil {
		return "", fmt.Errorf("failed to resolve base directory: %w", err)
	}

	var target string
	if filepath.IsAbs(userPath) {
		target = filepath.Clean(userPath)
	} else {
		target = filepath.Join(cleanBase, userPath)
	}

	cleanTarget, err := filepath.Abs(target)
	if err != nil {
		return "", fmt.Errorf("failed to resolve target path: %w", err)
	}

	rel, err := filepath.Rel(cleanBase, cleanTarget)
	if err != nil {
		return "", fmt.Errorf("failed to compute relative path: %w", err)
	}

	if rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", ErrPathTraversal
	}

	return cleanTarget, nil
}
