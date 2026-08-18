package data

import (
	"errors"
	"os"
	"path/filepath"
	"testing"
)

func TestSafePath(t *testing.T) {
	tmpDir := t.TempDir()

	// Create a subfolder inside tmpDir
	subDir := filepath.Join(tmpDir, "reports")
	if err := os.MkdirAll(subDir, 0755); err != nil {
		t.Fatalf("failed to create subdir: %v", err)
	}

	tests := []struct {
		name        string
		baseDir     string
		userPath    string
		expectError bool
		targetErr   error
	}{
		{
			name:        "valid relative path inside baseDir",
			baseDir:     tmpDir,
			userPath:    "reports/report.md",
			expectError: false,
		},
		{
			name:        "valid nested path with dot components",
			baseDir:     tmpDir,
			userPath:    "./reports/sub/../report.md",
			expectError: false,
		},
		{
			name:        "path traversal using parent directory",
			baseDir:     subDir,
			userPath:    "../secret.txt",
			expectError: true,
			targetErr:   ErrPathTraversal,
		},
		{
			name:        "deep path traversal escaping baseDir",
			baseDir:     subDir,
			userPath:    "../../../../etc/passwd",
			expectError: true,
			targetErr:   ErrPathTraversal,
		},
		{
			name:        "absolute path outside baseDir",
			baseDir:     subDir,
			userPath:    "/etc/shadow",
			expectError: true,
			targetErr:   ErrPathTraversal,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := SafePath(tc.baseDir, tc.userPath)
			if tc.expectError {
				if err == nil {
					t.Fatalf("expected error for path %q in base %q, got nil (result: %q)", tc.userPath, tc.baseDir, got)
				}
				if tc.targetErr != nil && !errors.Is(err, tc.targetErr) {
					t.Errorf("expected error %v, got %v", tc.targetErr, err)
				}
			} else {
				if err != nil {
					t.Fatalf("unexpected error: %v", err)
				}
				if got == "" {
					t.Errorf("expected non-empty path result")
				}
			}
		})
	}
}
