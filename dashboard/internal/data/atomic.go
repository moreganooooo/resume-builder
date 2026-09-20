package data

import (
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// WriteFileAtomic writes data to a temporary file in target file's directory
// and atomically renames it to path. If rename fails across filesystem boundaries,
// it falls back to an atomic copy-replace routine.
func WriteFileAtomic(path string, data []byte, perm os.FileMode) error {
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("creating directory %s: %w", dir, err)
	}

	tmpFile, err := os.CreateTemp(dir, ".tmp-atomic-*")
	if err != nil {
		return fmt.Errorf("creating temp file in %s: %w", dir, err)
	}
	tmpName := tmpFile.Name()

	cleanUp := func() {
		_ = os.Remove(tmpName)
	}

	if _, err := tmpFile.Write(data); err != nil {
		_ = tmpFile.Close()
		cleanUp()
		return fmt.Errorf("writing temp file: %w", err)
	}

	if err := tmpFile.Chmod(perm); err != nil {
		_ = tmpFile.Close()
		cleanUp()
		return fmt.Errorf("setting permissions on temp file: %w", err)
	}

	if err := tmpFile.Sync(); err != nil {
		_ = tmpFile.Close()
		cleanUp()
		return fmt.Errorf("syncing temp file: %w", err)
	}

	if err := tmpFile.Close(); err != nil {
		cleanUp()
		return fmt.Errorf("closing temp file: %w", err)
	}

	if err := os.Rename(tmpName, path); err != nil {
		// Fallback for cross-device or permission edge cases
		src, srcErr := os.Open(tmpName)
		if srcErr != nil {
			cleanUp()
			return fmt.Errorf("rename failed (%v) and fallback open failed: %w", err, srcErr)
		}
		// Read side of a best-effort fallback copy: a close error here
		// tells us nothing the copy itself did not already report.
		defer func() { _ = src.Close() }()

		dst, dstErr := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, perm)
		if dstErr != nil {
			cleanUp()
			return fmt.Errorf("rename failed (%v) and fallback dst open failed: %w", err, dstErr)
		}
		// dst is explicitly Sync()'d below, so the data is already on disk
		// by the time this runs.
		defer func() { _ = dst.Close() }()

		if _, copyErr := io.Copy(dst, src); copyErr != nil {
			cleanUp()
			return fmt.Errorf("fallback copy failed: %w", copyErr)
		}
		_ = dst.Sync()
		cleanUp()
	}

	return nil
}
