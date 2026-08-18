package data

import (
	"os"
	"path/filepath"
	"testing"
)

func TestWriteFileAtomic_Success(t *testing.T) {
	tmpDir := t.TempDir()
	targetPath := filepath.Join(tmpDir, "nested", "test.json")

	content := []byte(`{"status": "ok", "count": 42}`)
	err := WriteFileAtomic(targetPath, content, 0644)
	if err != nil {
		t.Fatalf("expected WriteFileAtomic to succeed, got: %v", err)
	}

	read, err := os.ReadFile(targetPath)
	if err != nil {
		t.Fatalf("failed reading target file: %v", err)
	}
	if string(read) != string(content) {
		t.Fatalf("expected content %q, got %q", string(content), string(read))
	}
}

func TestWriteFileAtomic_Overwrite(t *testing.T) {
	tmpDir := t.TempDir()
	targetPath := filepath.Join(tmpDir, "overwrite.txt")

	if err := os.WriteFile(targetPath, []byte("initial"), 0644); err != nil {
		t.Fatalf("failed writing initial file: %v", err)
	}

	newContent := []byte("updated content")
	if err := WriteFileAtomic(targetPath, newContent, 0644); err != nil {
		t.Fatalf("expected overwrite to succeed, got: %v", err)
	}

	read, err := os.ReadFile(targetPath)
	if err != nil {
		t.Fatalf("failed reading updated file: %v", err)
	}
	if string(read) != string(newContent) {
		t.Fatalf("expected content %q, got %q", string(newContent), string(read))
	}
}
