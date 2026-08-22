# ✦ Mobile Termux & Visual Inspection Guide ✧

**Repository**: `moreganooooo/resume-builder`
**Date**: August 18, 2026

---

## 1. Visual Terminal Inspection & Review

Antigravity can visually "see" and review terminal layouts, typography tracking, padding balance, and Catppuccin color schemes using our headless screenshot pipeline and Charm `vhs`.

### Automated Screenshot Tool

Run the visual capture utility from the repo root:

```bash
# Capture full high-DPI retina PNG snapshot
python3 scripts/capture_tui_visuals.py --out artifacts/tui_capture.png
```

* **How it works**:
  1. The headless Go capture engine executes `dashboard/cmd/rendercapture` to generate ANSI terminal frames.
  2. The parser translates ANSI 24-bit RGB escape codes into HTML with Catppuccin Mocha styling.
  3. Playwright renders a pixel-perfect retina screenshot to `artifacts/tui_capture.png`.
  4. The AI directly inspects the resulting image via multimodal `view_file` to review layout alignment, contrast ratios, and visual rhythm.

### Optional: Charm VHS Tape Recordings

For interactive animated GIFs and video recordings of terminal sessions, install Charm's `vhs`:

```bash
# On macOS
brew install charmbracelet/tap/vhs ttyd ffmpeg
```

Run any pre-built tape in `dashboard/tapes/`:

```bash
vhs dashboard/tapes/menu.tape       # Main menu animation
vhs dashboard/tapes/pipeline.tape   # Career pipeline screen
vhs dashboard/tapes/jobs.tape       # Jobs triage accordion
vhs dashboard/tapes/kb_view.tape    # Knowledge Base explorer
vhs dashboard/tapes/mobile.tape     # Mobile Termux portrait view (40x24)
```

---

## 2. Android / Termux Mobile Optimization

Resume Builder includes native optimizations for running on Android devices via [Termux](https://termux.dev/).

### Mobile-Specific Features
1. **Auto-Detection**: Automatically detects Termux environments (`TERMUX_VERSION`) and relaxes minimum terminal size constraints from $80\times24$ to $35\times12$.
2. **Touch & Tap Navigation**: Uses Bubble Tea cell motion (`tea.WithMouseCellMotion()`) so screen taps on Android register as mouse clicks on list items, menu rows, and category tabs.
3. **Ergonomic Hotkeys**: Full navigation with single-character keys (`1`–`5`, `Space`, `Enter`, `q`, `u`) eliminating the need for complex `Ctrl`/`Alt` combos on mobile keyboards.
4. **Battery & CPU Conservation**: Automatically throttles continuous 20fps background animation loops to maintain 0% CPU utilization when idle.

---

## 3. Manual Setup Instructions for Android (Termux)

Follow these steps to run the Resume Builder dashboard directly on your Android phone or tablet:

### Step 1: Install Termux
* Download and install **Termux** from [F-Droid](https://f-droid.org/packages/com.termux/) (do not use the obsolete Google Play Store build).

### Step 2: Set Up Packages in Termux
Open Termux and run:
```bash
pkg update -y && pkg upgrade -y
pkg install -y git golang python
```

### Step 3: Clone or Copy Your Resume Builder
```bash
git clone https://github.com/moreganooooo/resume-builder.git
cd resume-builder
```

### Step 4: Run the TUI Dashboard
You can run directly using Go:
```bash
cd dashboard
go run .
```

Or build a standalone, ultra-fast native ARM64 binary:
```bash
cd dashboard
CGO_ENABLED=0 go build -ldflags="-s -w" -o dashboard-arm64 .
./dashboard-arm64
```

### Optional: Cross-Compiling from your Mac
To compile for your Android device from macOS, run:
```bash
./scripts/build_mobile.sh
```
The compiled static ARM64 binary will be located in `dist/mobile/dashboard-linux-arm64`. You can transfer this single file to your Android device (via Syncthing, SSH, or cloud storage) and execute it directly.

---

## 4. Antigravity Workspace Customizations (`.agents/`)

The workspace now contains:
* **`.agents/rules/tui_standards.md`**: Enforces Lip Gloss v2 color tokens, WCAG AA contrast, and single-width ellipsis rune truncation.
* **`.agents/rules/mobile_termux.md`**: Defines mobile layout requirements, thumb ergonomics, and power efficiency rules.
* **`.agents/skills/tui-visual-auditor/SKILL.md`**: Provides the standardized procedure for capturing and auditing visual screenshots of terminal interfaces.
