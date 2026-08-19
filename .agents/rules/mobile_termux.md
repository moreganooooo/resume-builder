---
paths:
  - "dashboard/**/*.go"
  - "scripts/build_mobile.sh"
  - "scripts/capture_tui_visuals.py"
---

# Mobile & Termux Guidelines for Resume Builder

## Mobile Screen Geometries & Ergonomics
1. **Viewport Constraints**:
   - Mobile portrait viewports typically range from 36 to 55 columns wide and 16 to 24 lines high.
   - When running under Termux (`TERMUX_VERSION` set) or with `RESUME_BUILDER_MOBILE=1`, relax desktop minimum size guards down to 35x12.

2. **Thumb & Touch Navigation**:
   - Pass `tea.WithMouseCellMotion()` so Android touch events map to mouse clicks.
   - Design primary navigation around numeric jumps (`1`–`5`), `Space` (primary action), `Enter` (select), and `Esc`/`q` (back).
   - Avoid requiring complex multi-key combinations (`Ctrl+Alt+X`) on mobile virtual keyboards.

3. **Battery & Resource Conservation**:
   - In mobile mode, disable idle 20fps background animation loops (starfield, continuous shimmers) to keep CPU utilization near 0% when idle.
   - Use compiled native ARM64 binaries (`dashboard-linux-arm64`) for instant < 5ms startup and minimal memory footprint.
