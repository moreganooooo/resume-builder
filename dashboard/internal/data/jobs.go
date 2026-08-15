package data

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/moreganooooo/resume-builder/dashboard/internal/model"
)

// LoadJobs reads the JD evaluation export written by
// scripts/dashboard.py (picker.list_all_evaluated_jds()) at path and
// decodes it into JobRows.
func LoadJobs(path string) ([]model.JobRow, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading jobs export %s: %w", path, err)
	}
	var rows []model.JobRow
	if err := json.Unmarshal(raw, &rows); err != nil {
		return nil, fmt.Errorf("parsing jobs export %s: %w", path, err)
	}
	return rows, nil
}
