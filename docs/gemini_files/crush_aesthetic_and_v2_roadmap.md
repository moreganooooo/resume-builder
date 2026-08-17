# Crush Aesthetic Makeover & Charm v2 Migration Roadmap

This guide explores the design possibilities inspired by **Charm Crush** (the stunning new terminal AI coder) and provides a concrete roadmap for:
1. Running the entire Python CLI menu system in **Alt-Screen (full-screen) mode** so it matches the Go dashboard's immersive experience.
2. Infusing **Crush's high-end visual design system** into your job search cockpit.
3. Conducting a thorough technical evaluation of migrating your modules to **Bubble Tea v2 / Lip Gloss v2**.

---

## 🎬 Immersive Full-Screen Mode for Python CLI (`menu.py`)

Currently, your Go dashboard (`resume dashboard`) launches into full-screen (alt-screen) mode, but your main Python CLI menu (`scripts/menu.py`) runs inline in the scrolling shell terminal. This creates a disjointed experience where terminal history gets cluttered with menu repaints.

We can run the **entire Python menu in full alt-screen mode** with a simple ANSI escape wrapper. When the user launches `resume`, it will instantly take over the viewport; upon exit, the terminal is restored to exactly how it was, leaving zero visual clutter.

### The Python Implementation

Add this context manager directly in `scripts/menu.py` (or a helper file) to seamlessly wrap your interactive loop:

```python
import sys
import contextlib

@contextlib.contextmanager
def alternate_screen():
    """Switches the terminal to the alternate screen buffer and restores it at exit.
    
    Using \x1b[?1049h tells standard ANSI terminals to hide scrollback history,
    hide scrollbars, and open a clean fullscreen canvas. \x1b[?1049l restores
    the original terminal screen and preserves previous scrollback content intact.
    """
    # 1. Write the enter alt-screen sequence (\x1b[?1049h)
    # 2. Reset cursor position to home/top-left (\x1b[H)
    sys.stdout.write("\x1b[?1049h\x1b[H")
    sys.stdout.flush()
    try:
        yield
    finally:
        # Write the exit alt-screen sequence (\x1b[?1049l)
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()
```

### Hooking it Into Your Main Loop

In `scripts/menu.py`, wrap your interactive main loop inside `alternate_screen()`:

```python
def run_interactive_menu():
    session_stats = {"start_time": time.time(), "completed_count": 0}
    
    # Immersive alternate-screen wrapper
    with alternate_screen():
        display_main_banner()
        display_tip()
        
        while True:
            choice = cli_art.select("What would you like to do?", choices=_build_choices())
            if not choice or choice == "exit":
                break
                
            # If the choice is a submenu, it runs its own internal select loop
            if choice in _SUBMENUS:
                _SUBMENUS[choice](session_stats)
            else:
                _run_with_chain(choice, session_stats)
                
            display_breadcrumb()
            
    # Exit footer renders on standard screen once terminal is restored
    display_exit_footer()
```

Now, the entire pipeline is **100% immersive**, from command select to PDF render!

---

## 🎨 Borrowing the Visual DNA of "Crush"

**Charm Crush** is a masterclass in terminal-first interface design. By examining its interface elements, we can identify exactly how to bring its premium visual signature into `resume-builder`.

````carousel
![Crush Chat Interface](/Users/morganescott/.gemini/antigravity-cli/brain/6e724098-7f97-4f19-8e63-ef0ac578089e/crush-photos/command-line-agent-crush.webp)
<!-- slide -->
![Crush Repository Cockpit](/Users/morganescott/.gemini/antigravity-cli/brain/6e724098-7f97-4f19-8e63-ef0ac578089e/crush-photos/charm-crush-agency-repo.jpg)
<!-- slide -->
![Crush Interactive Setup](/Users/morganescott/.gemini/antigravity-cli/brain/6e724098-7f97-4f19-8e63-ef0ac578089e/crush-photos/charm-crush-install-3.jpg)
````

Here is our design blueprint to restructure your TUI to mirror Crush's premium aesthetics:

### 1. High-Contrast Status Badges (Pills)
Crush avoids plain text or basic foreground colored characters for badges. It uses high-contrast background colored blocks (pills) with bold black text.

**Before:**
```
[Applied]  2026-08-11 — Senior Systems Architect
```
**After (Crush Style):**
```
 APPLIED  2026-08-11 — Senior Systems Architect
```

**Go Lip Gloss Code:**
```go
appliedBadge := lipgloss.NewStyle().
    Background(t.Green).       // High-contrast Success Green
    Foreground(t.Base).        // Deep Midnight Base (#1e1e2e)
    Padding(0, 1).
    Bold(true).
    Render(" APPLIED ")
```

### 2. Dual-Column Sidebar Layouts with Single Borders
Crush uses a precise sidebar structure where list items have thin dividers, and active selections are highlighted using a colored left border line (`▎`) rather than full background fills. This preserves high readability while keeping the screen uncluttered.

**Go Lip Gloss Code:**
```go
activeRowStyle := lipgloss.NewStyle().
    Border(lipgloss.Border{Left: "┃"}, false, false, false, true).
    BorderForeground(t.Mauve).
    PaddingLeft(1).
    Foreground(t.Text)
```

### 3. Header Title Blocks
Rather than printing titles above a panel, Crush embeds the title directly into the panel's top border outline or aligns it cleanly alongside a custom key-value block.

```
┌─── SESSION: Morgan ──────────────────────────────────┐
│ Active Profile: Systems Architect                    │
└──────────────────────────────────────────────────────┘
```

**Go Lip Gloss Code:**
```go
panelStyle := lipgloss.NewStyle().
    Border(lipgloss.RoundedBorder()).
    BorderForeground(t.Overlay)

// Lip Gloss v1/v2 title embedding helper:
content := "Active Profile: Systems Architect"
rendered := panelStyle.Render(content)
```

---

## ⚙️ Charm v2 Migration: An Honest Assessment

You asked if there is value in upgrading to **Bubble Tea v2**, **Lip Gloss v2**, and **Bubbles v2**. Yes, the gains are architectural, but they come with breaking changes. Let's break down the impact on your dashboard:

### 🌟 Key Value Propositions

1. **Declarative Layouts (Bubble Tea v2):**
   In v1, you trigger alt-screen transitions and mouse tracking imperatively through commands (`tea.EnterAltScreen`) or launch arguments. In v2, you declare your layout settings directly inside your `View()` method inside a `tea.View` struct.
   
   *V1 (Imperative):*
   ```go
   p := tea.NewProgram(m, tea.WithAltScreen()) // Stiff launch-only setting
   ```
   *V2 (Declarative):*
   ```go
   func (m model) View() tea.View {
       v := tea.NewView(m.renderScreen())
       v.AltScreen = true // Can toggle alt-screen at runtime!
       return v
   }
   ```

2. **Deterministic & Stream-Safe Styling (Lip Gloss v2):**
   Lip Gloss v1 queries global terminal states (`os.Stdout`) directly. This is notorious for causing racing glitches, especially if you deploy your app over SSH (`wish`). Lip Gloss v2 isolates style context, meaning styling calculations are entirely stream-safe and 100% reliable during SSH sessions.

3. **Built-in Dark/Light Coordination:**
   V2 coordinates color downsampling and light/dark theme queries out of the box. Background queries are triggered cleanly via commands (`tea.RequestBackgroundColor`) and caught inside `Update` without blocking.

---

### ⚠️ Migration Effort & Breaking Changes

Upgrading your Go modules to `github.com/charmbracelet/bubbletea/v2` and `github.com/charmbracelet/lipgloss/v2` will require:

1. **Rewriting `View()` Returns:**
   All of your screen components (`PipelineModel`, `JobsModel`, etc.) must be updated from returning `string` to returning `tea.View` or standard strings wrapped in `tea.View`.

2. **Replacing `tea.WindowSizeMsg` Handling:**
   Size tracking in v2 is streamlined to bind to views more cleanly.

3. **Styling Adjustments:**
   V2 styles require an explicit terminal context for downsampling. While Lip Gloss v2 includes a `compat` package (`github.com/charmbracelet/lipgloss/v2/compat`) to ease the migration, full alignment requires updating how colors are resolved.

### 📊 Migration Recommendation

> [!IMPORTANT]
> **Keep your current stable v1 setup for immediate visual polish, but schedule a v2 migration before deploying your SSH server (`wish`).**
> 
> The visual redesign (Crush badges, dual-panes, title bars) is completely separate from the library version and can be fully implemented **today** in v1. Migrating to v2 is highly recommended if you expand into multi-user SSH clustering, as it eliminates global state color bugs entirely.
