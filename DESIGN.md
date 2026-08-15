---
name: resume-builder
description: An end-to-end, LLM-powered job application management system.
colors:
  tui-base: "#1e1e2e"
  tui-surface: "#313244"
  tui-overlay: "#45475a"
  tui-text: "#cdd6f4"
  tui-subtext: "#a6adc8"
  tui-brand: "#4dabf7"
  tui-accent: "#b39ddb"
  tui-success: "#12C78F"
  tui-warning: "#F5EF34"
  tui-error: "#FF7B99"
  print-text: "#000000"
  print-bg: "#ffffff"
  print-divider: "#9aa3af"
typography:
  display:
    fontFamily: "'DM Serif Display', serif"
    fontWeight: 400
  body:
    fontFamily: "'DM Sans', sans-serif"
    fontWeight: 400
  headline:
    fontFamily: "'DM Sans', sans-serif"
    fontWeight: 800
components:
  tui-panel:
    backgroundColor: "{colors.tui-surface}"
    textColor: "{colors.tui-text}"
    padding: "16px"
  tui-active-panel:
    backgroundColor: "{colors.tui-surface}"
    textColor: "{colors.tui-text}"
  print-section:
    textColor: "{colors.print-text}"
    padding: "0 0 10px 0"
---

# Design System: resume-builder

## Overview

**Creative North Star: "The Command Center Editor"**

The visual system bridges two distinct worlds: a vibrant, powerful terminal dashboard and pristine, uncompromised print typography. The TUI draws inspiration from the *Charm* ecosystem (lipgloss/charm.land)—bursting with vibrant colors, rich data grids, and fluid tactile navigation, while avoiding overwhelming density. Conversely, the generated PDF output is completely restrained, serving as a strict editorial canvas that lets the typography and content shine.

**Key Characteristics:**
- **Vibrant & Tactile TUI:** Distinct panel surfaces, sharp contrast, clear borders, and strong active states.
- **Editorial Print Output:** High-contrast, black-and-white minimalist layout using strict page budgets.
- **Dual Identity:** Terminal neon meets classic serif typesetting.

## Colors

The system uses a split palette: vibrant, Charm-inspired neons for the TUI, and absolute monochrome for the print output.

### Primary TUI (Charm-Inspired Terminal)
- **TUI Base** (#1e1e2e): Deep Midnight workspace background.
- **TUI Surface** (#313244): Elevated panel backgrounds.
- **TUI Brand** (#4dabf7): Electric Sky for primary highlights and active elements.
- **TUI Accent** (#b39ddb): Vibrant Mauve for signature flourishes (Charm-like pop).

### Semantic TUI
- **Success** (#12C78F): High-visibility green.
- **Warning** (#F5EF34): Sharp amber.
- **Error** (#FF7B99): Lightened crimson.
- **Text** (#cdd6f4): Crisp terminal primary text.
- **Subtext** (#a6adc8): Dimmed contextual text.

**Why these three don't match a first guess at "green/amber/red":** each is
picked from Charmtone (the Charm ecosystem's own branded palette) and then
adjusted until it clears 4.5:1 WCAG AA contrast against *both* of the
dashboard's real backgrounds -- Base (#1e1e2e) and the lighter Surface
(#313244) that header/status/error bars render on top of. Surface is the
tighter constraint: an earlier Error value that measured fine against Base
(5.40:1) still failed AA against Surface (4.14:1) on the dashboard's own
error banner. Error above is that same Charmtone Coral, lightened until it
clears both (5.12:1 on Surface). See `scripts/theme.py`'s own top-of-file
comment for the full contrast math and the other three colors' (Brand/
Brand Accent/Info) identical story.

### Print/PDF Output
- **Print Text** (#000000): Absolute black for maximum contrast.
- **Print Background** (#ffffff): Pure white paper canvas.
- **Print Divider** (#9aa3af): Soft gray for structural lines without visual weight.

**The No-Bleed Rule.** Print colors never bleed into the TUI, and TUI neons never bleed into the print output. The boundary is absolute.

## Typography

**Display Font:** DM Serif Display (with serif fallback)
**Body Font:** DM Sans (with sans-serif fallback)

**Character:** The print output relies on the extreme contrast between the highly decorative *DM Serif Display* and the utilitarian, highly legible *DM Sans*. The TUI relies on the user's local terminal font (preferably a Nerd Font).

### Hierarchy (Print)
- **Display** (400, 36pt, 0.5625in line-height): The H1 hero name.
- **Headline** (400, 16pt, 1.2 line-height): Section titles, underlined by a 0.018cm gray divider.
- **Title** (800, 9.75pt, 1.2 line-height): Job titles, degree titles, and certification names.
- **Body** (400, 9.75pt, 1.2 line-height): Bullet points and summary text.
- **Tagline** (400, 15pt, 0.268in line-height): The primary role description immediately under the H1.

**The Strict Ligature Rule.** Ligatures must be explicitly disabled (`font-variant-ligatures: none; font-feature-settings: "liga" 0, "clig" 0;`) in the PDF to prevent ATS parsers from failing on joined glyphs (like "fi" or "fl").

## Layout

The TUI operates on an adaptive terminal grid using Go's Bubble Tea. It relies on explicit border rendering and flexible box layouts to pack dense but breathable data grids.

The Print output is strictly constrained to a 100% width, max 8.5in (US Letter) container. Margins and padding are tightly controlled (e.g., 10px bottom margin per section) to maximize the amount of content without triggering a page overflow.

## Elevation & Depth

**TUI:** Depth is achieved via bordered panels (Lip Gloss borders) and color contrast rather than shadows. Active panels use brighter borders (Electric Sky or Vibrant Mauve) to lift above inactive panels. Floating overlays (like modals) use the darker `#45475a` background.
**Print:** Absolutely flat. No shadows, no overlapping elements.

## Components

### TUI Panels / Dashboards
- **Shape:** Squared or subtly rounded terminal borders (using Unicode box-drawing characters).
- **Background:** `#313244` (Surface).
- **Active State:** Highlighted border (e.g., `#4dabf7` Brand) to indicate keyboard focus.

### Print Sections
- **Title Treatment:** 16pt DM Serif Display with a 0.018cm `#9aa3af` bottom border.
- **Spacing:** Tightly packed with 10px bottom margins to preserve the page budget.
- **Bullet Lists:** 16px left padding, no bolding inside bullets.

### Job/Education Entries (Print)
- **Header:** Bold title on top, followed by a pipe-separated meta line (Company | Size | Location | Dates) with a thin bottom divider.
- **Constraint:** `break-inside: avoid;` is strictly applied to prevent orphans/widows across page breaks.

## Do's and Don'ts

### Do:
- **Do** lean heavily into vibrant, Charm-like color palettes (magenta, cyan, neon green) when styling the TUI terminal interface.
- **Do** leverage the full Charm component ecosystem (`bubbles` for lists/spinners/paginators, `huh` for forms, `lipgloss` for styling) to build rich, tactile interfaces rapidly.
- **Do** ensure every interactive TUI panel clearly indicates focus via high-contrast border colors.
- **Do** adhere strictly to the `DM Serif Display` and `DM Sans` typographic hierarchy in the HTML templates.
- **Do** use `break-inside: avoid` on all major print blocks (jobs, education, certs) to control PDF pagination cleanly.

### Don't:
- **Don't** add any color to the generated resume PDF; it must remain strict black, white, and gray.
- **Don't** use bolding inside resume bullet points; keep them 400-weight to let the content breathe.
- **Don't** let the TUI dashboard become visually overwhelming; use empty space and muted subtext (`#a6adc8`) to balance the vibrant brand neons.
