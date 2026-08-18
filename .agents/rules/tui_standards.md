# TUI & Charm Coding Standards for Resume Builder

## Visual Hierarchy & Styling Rules
1. **Never Hardcode ANSI / Hex Colors**:
   - Always reference the centralized theme tokens in `dashboard/internal/theme/theme.go` (`t.Mauve`, `t.Peach`, `t.Surface`, `t.Overlay`, `t.Subtext`, `t.Text`, etc.).
   - Verify every new component by running `go run ./tools/lint_colors.go`.

2. **Contrast & Accessibility (WCAG AA)**:
   - Ensure text over badge overlays maintains at least 4.5:1 contrast.
   - Respect `RESUME_BUILDER_MOTION=reduced` by halting physics springs and continuous background timer ticks.
   - Respect `RESUME_BUILDER_ICONS=unicode` for terminals without Nerd Font glyphs.

3. **String Truncation & Column Alignment**:
   - Never use standard 3-character ASCII `"..."` for width-sensitive truncation.
   - Always use `ansi.Truncate(str, maxWidth, "…")` or single-rune Unicode `"…"`.

4. **Responsive Reflow & Geometry**:
   - All models must support dynamic terminal resizing (`tea.WindowSizeMsg`).
   - Check inner widths before slice allocations (`if innerWidth <= 0 { ... }`) to prevent panic on ultra-compact screens.
