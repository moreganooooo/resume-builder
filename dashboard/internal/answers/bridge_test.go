package answers

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	tea "charm.land/bubbletea/v2"
)

func TestTurnReadsAnswerEvent(t *testing.T) {
	dir := t.TempDir()
	scripts := filepath.Join(dir, "scripts")
	if err := os.Mkdir(scripts, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(scripts, "application_answers.py"), []byte("import sys\nprint('{\"type\":\"status\",\"message\":\"working\"}')\nprint('{\"type\":\"answer\",\"text\":\"hello\",\"kind\":\"general\",\"warnings\":[]}')\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	msg := Turn(context.Background(), "python3", dir, TurnRequest{Job: "job", Question: "question"})()
	answer, ok := msg.(AnswerMsg)
	if !ok || answer.Answer != "hello" {
		t.Fatalf("unexpected result: %#v", msg)
	}
}

func TestTurnReturnsStderrOnFailure(t *testing.T) {
	dir := t.TempDir()
	script := filepath.Join(dir, "fake.py")
	if err := os.WriteFile(script, []byte("import sys\nsys.stderr.write('broken\\n')\nsys.exit(1)\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	// The bridge invokes application_answers.py relative to projectRoot, so
	// provide the expected path and use the interpreter directly.
	scripts := filepath.Join(dir, "scripts")
	if err := os.Mkdir(scripts, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(script, filepath.Join(scripts, "application_answers.py")); err != nil {
		t.Fatal(err)
	}
	msg := Turn(context.Background(), "python3", dir, TurnRequest{})()
	errMsg, ok := msg.(ErrorMsg)
	if !ok || errMsg.Err.Error() != "broken" {
		t.Fatalf("unexpected error: %#v", msg)
	}
}

func TestTurnCanBeCancelled(t *testing.T) {
	dir := t.TempDir()
	scripts := filepath.Join(dir, "scripts")
	if err := os.Mkdir(scripts, 0o700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(scripts, "application_answers.py"), []byte("import time\ntime.sleep(10)\n"), 0o700); err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan tea.Msg, 1)
	go func() { done <- Turn(ctx, "python3", dir, TurnRequest{})() }()
	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("cancelled command did not return")
	}
}
