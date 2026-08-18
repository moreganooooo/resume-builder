---
name: tui-visual-auditor
description: Captures, renders, and visually audits Charm TUI terminal interfaces as images. Use when needing to review visual layouts, typography, padding, color balance, or mobile viewports via image inspection.
---

# TUI Visual Auditor

This skill provides procedures for capturing terminal screens into visual image artifacts (PNG) and inspecting them using `view_file` to evaluate layout aesthetics, contrast, and mobile reflow.

## Visual Inspection Workflow

1. **Capture Screen via VHS or Render Engine**:
   - Run a predefined VHS tape:
     ```bash
     vhs dashboard/tapes/menu.tape -o /tmp/menu_preview.png
     ```
   - Or use the python capture utility:
     ```bash
     python3 scripts/capture_tui_visuals.py --screen pipeline --out /tmp/pipeline_preview.png
     ```

2. **Inspect via `view_file`**:
   - Call `view_file(AbsolutePath="/tmp/menu_preview.png")` to visually examine:
     - Vertical rhythm and padding balance.
     - Color contrast and badge readability.
     - Truncation boundaries and header tracking.
     - Mobile portrait ($40\times24$) vs desktop ($120\times40$) scaling.

3. **Iterate and Refine**:
   - Make Lip Gloss style adjustments in `dashboard/internal/theme/` or screen models.
   - Re-render the capture and verify visual improvements.
