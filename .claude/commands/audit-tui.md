# TUI Quality & Visual Audit Command

Runs the full Charm TUI test matrix, verifies responsive geometry bounds, and runs the visual capture suite.

## Steps to Execute:
1. Run the Go test suite with boundary and stress tests:
   ```bash
   cd dashboard && go test -v ./...
   ```
2. Run the visual capture tool:
   ```bash
   python3 scripts/capture_tui_visuals.py --out artifacts/tui_capture.png
   ```
3. Inspect `artifacts/tui_capture.png` to ensure:
   - Zero column drift or clipping
   - Borders and text alignments are intact
   - Status pills and category tabs render with correct Catppuccin palette tokens
