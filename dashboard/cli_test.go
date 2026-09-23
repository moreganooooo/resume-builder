package main

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCheckProfileNamesTheClosestMatch(t *testing.T) {
	root := t.TempDir()
	for _, n := range []string{"morgan", "dominick"} {
		if err := os.MkdirAll(filepath.Join(root, "profiles", n), 0o755); err != nil {
			t.Fatal(err)
		}
	}
	if err := checkProfile(root, "Morgan"); err != nil {
		t.Errorf("case-insensitive match should pass: %v", err)
	}
	err := checkProfile(root, "morgn")
	var fe fixError
	if !errors.As(err, &fe) || !strings.Contains(fe.fix, "Did you mean morgan?") {
		t.Fatalf("want a fix naming morgan, got %v", err)
	}
	if checkProfile(t.TempDir(), "anything") != nil {
		t.Error("a root with no profiles/ (career-ops) must not be refused")
	}
}
