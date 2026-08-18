# Visual TUI Snapshot & Inspection Command

Run the automated headless TUI capture pipeline and inspect the rendered visual image for design, layout, contrast, and typography review.

## Steps to Execute:
1. Run the visual capture script:
   ```bash
   python3 scripts/capture_tui_visuals.py --out artifacts/tui_capture.png
   ```
2. Inspect the resulting image at `artifacts/tui_capture.png` using Claude's visual / image reading capabilities.
3. Review:
   - Visual hierarchy, font weights, and spacing rhythm
   - Catppuccin Mocha theme contrast compliance
   - Single-width Unicode ellipsis truncation and column alignment
   - Responsive geometry bounds (80x24 desktop, 35x12 mobile)
