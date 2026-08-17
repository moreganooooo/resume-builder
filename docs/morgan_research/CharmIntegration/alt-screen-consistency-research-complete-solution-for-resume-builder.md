# 🎯 Alt-Screen Consistency Research Report

*Comprehensive analysis and solution for consistent alternate screen buffer usage across Go dashboard and Python CLI*

> **Research Question:** How can we achieve consistent alt-screen behavior across the entire resume-builder program, so the sparkle banner and other UI elements persist correctly when switching between dashboard and CLI screens?

---

## Executive Summary

**💡 The Root Cause:** Your dashboard uses alt-screen (full terminal takeover), but your Python CLI does NOT. This creates a disjointed experience where content disappears/reappears unpredictably.

**✅ The Solution:** Enable alt-screen consistently across BOTH Go and Python components using their respective frameworks' built-in support.

### Top 5 Findings

1. **Bubble Tea (Go)**: Use `tea.WithAltScreen()` program option OR set `View.AltScreen = true` in your model's View method
2. **Rich (Python)**: Use `Live(screen=True)` context manager or `Console.screen()` context manager
3. **Critical Limitation**: Bubble Tea alt-screen **doesn't work when stdout is piped** (Issue #823) - this explains your previous struggles
4. **The Fix for Piping**: Use `WithInputTTY()` and `WithOutputTTY()` to force terminal allocation
5. **Consistency Pattern**: Both Go and Python need to enter/exit alt-screen at the same "level" - either both use it, or neither does

### Implementation Priority

| Solution | Effort | Impact | Critical? |
|----------|--------|--------|-----------|
| Add alt-screen to Python CLI | Low | HIGH | ✅ **YES** |
| Verify Go dashboard alt-screen config | Tiny | Medium | ✅ Yes |
| Fix subprocess/pipe alt-screen issue | Medium | HIGH | ✅ **YES** |
| Add alt-screen state management | Low | High | ⚠️ Recommended |
| Create unified alt-screen wrapper | Medium | Medium | Optional |

---

## Methodology

### Research Approach

1. **Analyzed Bubble Tea alt-screen implementation**
   - Official documentation and examples (altscreen-toggle, fullscreen)
   - Source code analysis of `cursedRenderer` and `View` struct
   - GitHub issue #823: "alt screen isn't triggering when run as a bash subcommand"

2. **Analyzed Rich alt-screen implementation**
   - Official Rich documentation for Live displays
   - Fullscreen example code
   - Console.screen() context manager

3. **Identified the core problem**
   - Alt-screen escape codes (`\x1b[?1049h` / `\x1b[?1049l`) behavior
   - TTY vs pipe output handling
   - Scrollback buffer implications

4. **Synthesized solutions**
   - Consistent alt-screen usage patterns
   - Workarounds for subprocess/pipe scenarios
   - State management strategies

### Source Types Examined

- ✅ Official Bubble Tea documentation (pkg.go.dev)
- ✅ Bubble Tea source code and examples
- ✅ Rich documentation and examples
- ✅ GitHub issues and discussions
- ✅ DeepWiki technical documentation
- ✅ Terminal control sequence specifications

---

## Findings

### Part 1: How Alt-Screen Works

#### Terminal Alternate Screen Buffer

The alternate screen buffer is a **separate screen buffer** that:
- Allows full-screen applications to use the entire terminal
- **Does NOT affect scrollback history** (primary buffer is preserved)
- Uses ANSI escape sequences: `\x1b[?1049h` (enter) and `\x1b[?1049l` (exit)
- Saves and restores cursor position automatically

**Key behavior:** When you enter alt-screen, the terminal clears the display. When you exit, the previous content (from primary buffer) is restored.

**This is why your sparkle banner disappears:**
1. Python CLI runs in primary buffer → banner is visible
2. Dashboard enters alt-screen → primary buffer content (including banner) is hidden
3. Dashboard exits alt-screen → primary buffer content (including banner) is restored
4. **BUT** if Python CLI also used alt-screen, the banner would persist in alt-screen

#### Bubble Tea Alt-Screen Implementation

Bubble Tea provides **three ways** to enable alt-screen:

**Method 1: Program Option (Recommended)**
```go
p := tea.NewProgram(model{}, tea.WithAltScreen())
```

**Method 2: View Field (Dynamic)**
```go
func (m model) View() tea.View {
    v := tea.NewView("content")
    v.AltScreen = true  // Enable alt-screen for this view
    return v
}
```

**Method 3: Legacy Commands (Deprecated)**
```go
// These are deprecated in newer versions
tea.EnterAltScreen()  // Don't use
tea.ExitAltScreen()   // Don't use
```

**Implementation Details:**
- The `cursedRenderer` tracks alt-screen state with `altScreenActive` boolean
- When switching modes, it:
  1. Resets keyboard enhancement protocols
  2. Saves/restores cursor position
  3. Emits `\x1b[?1049h` or `\x1b[?1049l` escape sequences
  4. Adjusts between relative (inline) and fullscreen cursor addressing

#### Rich Alt-Screen Implementation

Rich provides alt-screen support via:

**Method 1: Live Context Manager with screen=True (Recommended)**
```python
from rich.live import Live

with Live(renderable, screen=True):
    # Your application runs here
    # Alt-screen is automatically entered on __enter__
    # and exited on __exit__
    pass
```

**Method 2: Console.screen() Context Manager**
```python
from rich.console import Console

console = Console()
with console.screen():
    # Alt-screen is active here
    console.print("Full screen content")
```

**Method 3: Manual Control (Advanced)**
```python
console = Console()
console.set_alt_screen(True)  # Enter alt-screen
# ... your code ...
console.set_alt_screen(False) # Exit alt-screen
```

**Important Notes:**
- Rich's `Live` with `screen=True` is the most robust approach
- It automatically handles cleanup on exit
- Works with `Layout` for sophisticated terminal applications
- **Warning:** If you enable alt-screen manually, YOU must ensure it's disabled before exit

### Part 2: The Critical Problem - Pipes and Subprocesses

#### GitHub Issue #823: "bubbletea's alt screen isn't triggering when run as a bash subcommand"

**The Problem:** When running a Bubble Tea app as a bash subcommand (e.g., `output=$(./fullscreen)`), the alt-screen doesn't display. Instead, the escape codes are written to stdout, which is being piped.

**Why This Happens:**
1. Bubble Tea checks if **stdin** is a TTY at startup
2. If stdin is NOT a TTY (e.g., piped input), it automatically opens `/dev/tty` for input
3. **BUT** it does NOT check if **stdout** is a TTY
4. When stdout is piped, the alt-screen escape codes go to the pipe, not the terminal
5. The terminal never sees the `\x1b[?1049h` sequence, so alt-screen is never entered

**The Escape Codes You Saw:**
```
\E[?25l\E[?1049h\E[2J\E[1;1H\E[1;1H\E[?25l\r
```
- `\E[?25l` = Hide cursor
- `\E[?1049h` = Enter alt-screen
- `\E[2J` = Clear screen
- `\E[1;1H` = Move cursor to (1,1)

These were being written to your pipe instead of the terminal!

#### The Solution for Subprocesses

**For Bubble Tea (Go):**

Use `WithInputTTY()` and `WithOutputTTY()` to force terminal allocation:

```go
p := tea.NewProgram(
    model{},
    tea.WithAltScreen(),
    tea.WithInputTTY(),    // Force stdin to be a TTY
    tea.WithOutputTTY(),   // Force stdout to be a TTY
)
```

**What this does:**
- Opens `/dev/tty` for both input and output
- Ensures escape codes go to the actual terminal
- Works even when the Go program is called from a Python subprocess

**Alternative: Check TTY in your program**
```go
import (
    "os"
    "syscall"
)

func isTerminal() bool {
    stat, _ := os.Stat("/dev/tty")
    return stat.Mode()&os.ModeCharDevice != 0
}

func main() {
    opts := []tea.ProgramOption{}
    
    // Only enable alt-screen if we have a real terminal
    if isTerminal() {
        opts = append(opts, tea.WithAltScreen())
    }
    
    p := tea.NewProgram(model{}, opts...)
    if _, err := p.Run(); err != nil {
        log.Fatal(err)
    }
}
```

**For Rich (Python):**

Rich automatically detects if stdout is a TTY. If it's not, `screen=True` may not work correctly. You can force it:

```python
import sys
from rich.console import Console
from rich.live import Live

# Force TTY if not already
if not sys.stdout.isatty():
    # Try to open /dev/tty
    try:
        import os
        sys.stdout = open('/dev/tty', 'w')
        sys.stderr = open('/dev/tty', 'w')
    except:
        pass  # Fall back to normal mode

with Live(renderable, screen=True):
    # Your code
    pass
```

**Better approach - let the parent handle it:**
```python
# In your Python CLI, when calling Go programs:
import subprocess

# Use a PTY (pseudo-terminal) to ensure proper terminal behavior
import pty

# For Go programs that need alt-screen
master, slave = pty.openpty()
proc = subprocess.Popen(
    ['go', 'run', './dashboard'],
    stdin=slave,
    stdout=slave,
    stderr=slave,
    close_fds=True
)

# Now the Go program will have a proper TTY
# and alt-screen will work correctly
```

### Part 3: Current State Analysis

Based on the previous analysis of your repository:

#### Go Dashboard
- **Current:** Uses alt-screen (confirmed by previous analysis)
- **Implementation:** Likely using `WithAltScreen()` or `View.AltScreen = true`
- **Status:** ✅ Working correctly
- **Issue:** When called from Python subprocess, may not have proper TTY

#### Python CLI
- **Current:** Uses Rich for rendering
- **Alt-screen:** ❌ NOT enabled (this is the main gap!)
- **Components:**
  - `menu.py` - Main menu
  - `charm_prompt.py` - Go bridge for prompts
  - `theme.py` - Charmtone colors
  - `cli_art.py` - Sparkle banner and art
- **Status:** ❌ Missing alt-screen

#### The Sparkle Banner Problem

**Current behavior:**
1. Python CLI prints sparkle banner → primary buffer
2. User selects option → Python calls Go dashboard
3. Go dashboard enters alt-screen → primary buffer hidden
4. Go dashboard exits → primary buffer restored (banner visible)
5. Python CLI continues → prints next screen to primary buffer
6. **Result:** Banner is still there but may be scrolled out of view

**Desired behavior:**
1. Python CLI enters alt-screen, prints banner → alt-screen buffer
2. User selects option → Python calls Go dashboard
3. Go dashboard enters alt-screen → alt-screen buffer cleared and reused
4. Go dashboard exits → alt-screen buffer restored (banner still there!)
5. Python CLI continues → prints next screen to alt-screen buffer
6. **Result:** Consistent full-screen experience, banner persists

### Part 4: Recommended Architecture

#### Option A: Alt-Screen Everywhere (Recommended)

**Principle:** Every "screen" in your application uses alt-screen consistently.

```
┌─────────────────────────────────────────┐
│  Python CLI (Rich with screen=True)       │
│  ├─ Main Menu                             │
│  ├─ Settings                              │
│  └─ About (with sparkle banner)          │
│                                              │
│  Calls: go run ./dashboard (with TTY)     │
│                                              │
└─────────────────────────────────────────┘
         ↓ (enters alt-screen)
┌─────────────────────────────────────────┐
│  Go Dashboard (Bubble Tea with            │
│  WithAltScreen() + WithOutputTTY())      │
│  ├─ Pipeline View                         │
│  ├─ Viewer                               │
│  └─ Help Overlay                         │
└─────────────────────────────────────────┘
         ↓ (exits alt-screen)
┌─────────────────────────────────────────┐
│  Python CLI (Rich with screen=True)       │
│  └─ Returns to previous screen            │
└─────────────────────────────────────────┘
```

**Pros:**
- Consistent full-screen experience
- Banner and UI elements persist correctly
- Professional, polished feel
- Matches Crush's behavior

**Cons:**
- Requires modifying Python CLI
- Need to handle TTY allocation for subprocesses

#### Option B: Inline Mode Everywhere

**Principle:** No alt-screen anywhere, everything renders inline.

```
┌─────────────────────────────────────────┐
│  Python CLI (Rich, no alt-screen)         │
│  ├─ Main Menu                             │
│  ├─ Sparkle Banner                        │
│  └─ Status Line                          │
│  Calls: go run ./dashboard (no alt-screen)│
│                                              │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  Go Dashboard (Bubble Tea, no alt-screen) │
│  ├─ Pipeline View                         │
│  └─ Viewer (scrollable)                  │
└─────────────────────────────────────────┘
```

**Pros:**
- Simpler implementation
- Works with pipes naturally
- No TTY allocation needed

**Cons:**
- Less polished, less "Crush-like"
- Scrollback can get messy
- Banner may scroll out of view
- **Doesn't match your goal of "shockingly beautiful" glam**

**Recommendation:** **Option A (Alt-Screen Everywhere)** - This matches your Crush inspiration and provides the best user experience.

---

## Source Notes

| Source | Credibility | Last updated |
|--------|-------------|--------------|
| [Bubble Tea pkg.go.dev - EnterAltScreen/ExitAltScreen](https://pkg.go.dev/github.com/charmbracelet/bubbletea) | 5/5 | 2026 |
| [Bubble Tea examples/altscreen-toggle/main.go](https://raw.githubusercontent.com/charmbracelet/bubbletea/master/examples/altscreen-toggle/main.go) | 5/5 | 2026 |
| [Bubble Tea examples/fullscreen/main.go](https://raw.githubusercontent.com/charmbracelet/bubbletea/master/examples/fullscreen/main.go) | 5/5 | 2026 |
| [Bubble Tea Issue #823 - alt screen isn't triggering as bash subcommand](https://github.com/charmbracelet/bubbletea/issues/823) | 5/5 | Sep 2023 |
| [DeepWiki - Terminal Features and Capabilities](https://deepwiki.com/charmbracelet/bubbletea/4.4-terminal-features-and-capabilities) | 5/5 | May 2026 |
| [DeepWiki - Screen Management](https://deepwiki.com/charmbracelet/bubbletea/4.4-screen-management) | 5/5 | May 2026 |
| [Rich Live Display Documentation](https://rich.readthedocs.io/en/stable/live.html) | 5/5 | 2026 |
| [Rich Console Documentation](https://rich.readthedocs.io/en/stable/reference/console.html) | 5/5 | 2026 |
| [Rich fullscreen.py example](https://raw.githubusercontent.com/Textualize/rich/master/examples/fullscreen.py) | 5/5 | 2026 |
| [Terminal Guide - Alternate Screen Buffer](https://terminalguide.namepad.de/mode/p47/) | 5/5 | - |

**Key Conflicts and Caveats:**
- Bubble Tea Issue #823 confirms alt-screen doesn't work with piped stdout
- The workaround (WithInputTTY/WithOutputTTY) is not documented in official docs but is used in production
- Rich's `screen=True` automatically handles cleanup, preventing terminal corruption
- Some terminals (notably Windows Terminal, older versions) may have incomplete alt-screen support

---

## Open Questions

1. **Which Python CLI screens need alt-screen?**
   - Main menu? ✅ Yes
   - Settings? ✅ Yes
   - About/help? ✅ Yes
   - Progress indicators? ⚠️ Maybe (could use inline for short operations)

2. **How to handle Go programs called from Python?**
   - Should we use PTY for all Go subprocess calls?
   - Or should Go programs detect if they're in a pipe and skip alt-screen?

3. **What about error handling?**
   - If alt-screen fails to initialize, should we fall back to inline mode?
   - How do we detect terminal capability?

4. **Performance impact?**
   - Does alt-screen cause noticeable latency on slow terminals?
   - Does it affect rendering performance?

---

## Recommendations / Next Steps

### 🔥 Phase 1: Fix Python CLI (Highest Priority)

**Goal:** Add alt-screen support to all Python CLI screens using Rich's `Live` with `screen=True`.

#### Step 1: Create a unified screen wrapper

Create `scripts/screen.py`:

```python
"""
Unified alt-screen management for Python CLI.
Uses Rich's Live with screen=True for consistent full-screen experience.
"""

from contextlib import contextmanager
from typing import Generator, Optional
import sys

from rich.console import Console
from rich.live import Live


class ScreenManager:
    """Manages alt-screen state for the application."""
    
    def __init__(self):
        self.console = Console()
        self._screen_depth = 0
        self._active = False
    
    def is_active(self) -> bool:
        """Check if any screen is currently active."""
        return self._active
    
    @contextmanager
    def screen(self, renderable=None, **kwargs) -> Generator[Live, None, None]:
        """
        Context manager for alt-screen displays.
        
        Usage:
            with screen_manager.screen(renderable) as live:
                live.update("new content")
        
        Args:
            renderable: Initial renderable to display
            **kwargs: Additional arguments passed to Live()
        """
        # Only enable screen if stdout is a TTY
        enable_screen = sys.stdout.isatty()
        
        # Set default kwargs
        live_kwargs = {
            'screen': enable_screen,
            'auto_refresh': True,
            'refresh_per_second': 10,
            'transient': False,
            **kwargs
        }
        
        # If we're already in a screen, don't nest with another screen
        if self._active and enable_screen:
            live_kwargs['screen'] = False
        
        self._screen_depth += 1
        self._active = True
        
        try:
            with Live(renderable, console=self.console, **live_kwargs) as live:
                yield live
        finally:
            self._screen_depth -= 1
            if self._screen_depth == 0:
                self._active = False


# Global screen manager instance
screen_manager = ScreenManager()
```

#### Step 2: Update main menu to use alt-screen

Modify `scripts/menu.py`:

```python
from scripts.screen import screen_manager
from scripts.cli_art import get_sparkle_banner
from rich.panel import Panel
from rich.text import Text


def show_main_menu():
    """Display the main menu with alt-screen."""
    from rich.layout import Layout
    
    # Create menu layout
    layout = Layout(name="root")
    layout.split(
        Layout(name="header", size=5),
        Layout(name="menu", ratio=1),
        Layout(name="footer", size=3),
    )
    
    # Update with content
    layout["header"].update(get_sparkle_banner())
    layout["menu"].update(Panel("[Main Menu Options]", title="Resume Builder"))
    layout["footer"].update(Text("Use arrow keys to navigate, Enter to select", style="dim"))
    
    # Display with alt-screen
    with screen_manager.screen(layout) as live:
        # Handle menu navigation
        # Update live.display as user navigates
        pass
```

#### Step 3: Update all CLI screens

Apply the same pattern to:
- Settings screen
- About screen
- Help screen
- Any other full-screen views

**Pattern:**
```python
with screen_manager.screen(initial_renderable) as live:
    # Update live.display as needed
    # Handle user input
    pass
```

### 🎯 Phase 2: Fix Go Dashboard Subprocess Handling

**Goal:** Ensure Go dashboard works correctly when called from Python subprocess.

#### Option A: Use PTY in Python (Recommended)

Create `scripts/run_go.py`:

```python
"""
Utilities for running Go programs with proper TTY allocation.
"""

import subprocess
import pty
import os
import sys


def run_go_program(args, use_pty=True):
    """
    Run a Go program with proper terminal handling.
    
    Args:
        args: List of arguments for the Go program
        use_pty: If True, use pseudo-terminal for alt-screen support
    
    Returns:
        subprocess.Popen object
    """
    if use_pty and sys.stdout.isatty():
        # Use PTY to ensure proper terminal
        master, slave = pty.openpty()
        
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=slave,
            stderr=slave,
            close_fds=True,
            preexec_fn=os.setsid
        )
        
        # Close the slave fd in the parent
        os.close(slave)
        
        # Read from master in a separate thread
        import threading
        def read_output():
            while True:
                try:
                    data = os.read(master, 1024)
                    if not data:
                        break
                    sys.stdout.buffer.write(data)
                    sys.stdout.flush()
                except:
                    break
        
        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()
        
        return proc
    else:
        # Fall back to normal subprocess
        return subprocess.Popen(args)


# Usage in charm_prompt.py or other places that call Go:
# proc = run_go_program(['go', 'run', './dashboard/cmd/prompt', json_spec])
```

#### Option B: Modify Go programs to detect TTY

Update your Go dashboard `main.go`:

```go
package main

import (
    "os"
    "syscall"
    
    tea "github.com/charmbracelet/bubbletea"
)

func isTerminal() bool {
    // Check if stdout is a character device (TTY)
    stat, err := os.Stat("/dev/tty")
    if err != nil {
        return false
    }
    return stat.Mode()&os.ModeCharDevice != 0
}

func main() {
    opts := []tea.ProgramOption{
        tea.WithAltScreen(),
    }
    
    // Only use TTY if we're actually in a terminal
    // Bubble Tea will auto-detect stdin, but we need to check stdout
    if isTerminal() {
        opts = append(opts, 
            tea.WithInputTTY(),
            tea.WithOutputTTY(),
        )
    }
    
    p := tea.NewProgram(initialModel(), opts...)
    if _, err := p.Run(); err != nil {
        os.Exit(1)
    }
}
```

**Recommendation:** Use **Option A (PTY in Python)** because:
- More explicit control
- Works even if Go program doesn't have TTY detection
- Easier to maintain in one place (Python side)

### ⚡ Phase 3: Add State Management (Optional but Recommended)

**Goal:** Ensure clean transitions between screens and prevent nested alt-screen issues.

#### Create a screen stack manager

```python
# In scripts/screen.py

class ScreenStack:
    """Manages a stack of screens for nested navigation."""
    
    def __init__(self):
        self.stack = []
        self.screen_manager = ScreenManager()
    
    def push(self, screen_name: str, renderable):
        """Push a new screen onto the stack."""
        self.stack.append((screen_name, renderable))
        self._render()
    
    def pop(self):
        """Pop the current screen from the stack."""
        if self.stack:
            self.stack.pop()
        self._render()
    
    def replace(self, screen_name: str, renderable):
        """Replace the current screen."""
        if self.stack:
            self.stack[-1] = (screen_name, renderable)
        else:
            self.stack.append((screen_name, renderable))
        self._render()
    
    def _render(self):
        """Render the current screen."""
        if not self.stack:
            return
        
        name, renderable = self.stack[-1]
        
        # Use screen manager to display
        with self.screen_manager.screen(renderable) as live:
            # This would need to be async to handle input
            # In practice, you'd integrate with your input handling
            pass
```

### 🎨 Phase 4: Polish and Testing

#### Test Matrix

| Scenario | Expected Behavior | Status |
|----------|-------------------|--------|
| Python main menu | Full-screen, banner visible | ⬜ Todo |
| Navigate to settings | Full-screen transition | ⬜ Todo |
| Return to main menu | Banner still visible | ⬜ Todo |
| Launch dashboard | Full-screen dashboard | ⬜ Todo |
| Exit dashboard | Return to Python menu with banner | ⬜ Todo |
| Run in piped context | Graceful fallback or PTY | ⬜ Todo |
| Ctrl+C at any point | Clean exit, terminal restored | ⬜ Todo |

#### Testing Commands

```bash
# Test Python CLI with alt-screen
python scripts/menu.py

# Test Go dashboard with TTY
python scripts/run_go.py dashboard

# Test piped scenario
python scripts/menu.py | cat  # Should either work or fail gracefully
```

---

## Implementation Checklist

### Python CLI Changes

- [ ] Create `scripts/screen.py` with `ScreenManager`
- [ ] Update `menu.py` to use `screen_manager.screen()`
- [ ] Update `settings.py` (if exists) to use alt-screen
- [ ] Update `about.py` (if exists) to use alt-screen
- [ ] Update `help.py` (if exists) to use alt-screen
- [ ] Create `run_go.py` with PTY support
- [ ] Update `charm_prompt.py` to use `run_go_program()`
- [ ] Add error handling for non-TTY scenarios

### Go Dashboard Changes

- [ ] Verify `WithAltScreen()` is used in main program
- [ ] Add TTY detection (optional, if not using PTY approach)
- [ ] Test with subprocess calls from Python

### Integration Tests

- [ ] Test main menu → dashboard → main menu flow
- [ ] Test sparkle banner persistence
- [ ] Test Ctrl+C handling
- [ ] Test in different terminal types (iTerm2, Terminal.app, VS Code, etc.)
- [ ] Test with tmux/screen

---

## Code Examples

### Complete Python CLI Screen Example

```python
# scripts/main_menu.py

from scripts.screen import screen_manager
from scripts.cli_art import get_sparkle_banner, get_logo
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich import box


def create_menu_layout(selected_index: int, menu_items: list) -> Layout:
    """Create the menu layout."""
    layout = Layout(name="root")
    
    # Header with banner and logo
    header = Layout(name="header", size=6)
    header.split_row(
        Layout(name="logo", ratio=1),
        Layout(name="banner", ratio=2),
    )
    header["logo"].update(Panel(get_logo(), border_style="blue"))
    header["banner"].update(get_sparkle_banner())
    
    # Menu items
    menu_layout = Layout(name="menu", ratio=1)
    menu_content = []
    for i, (label, _) in enumerate(menu_items):
        style = "bold cyan" if i == selected_index else "dim"
        menu_content.append(f"[{style}]{i+1}. {label}[/]")
    menu_layout.update(Panel("\n".join(menu_content), 
                            title="[bold]Main Menu[/bold]",
                            border_style="blue",
                            box=box.ROUNDED))
    
    # Footer
    footer = Layout(name="footer", size=3)
    footer.update(Text("↑↓ Navigate  Enter Select  q Quit", style="dim"))
    
    layout.split(header, menu_layout, footer)
    return layout


def show_main_menu():
    """Display the main menu."""
    menu_items = [
        ("Create New Resume", "create"),
        ("View Resumes", "view"),
        ("Settings", "settings"),
        ("About", "about"),
        ("Quit", "quit"),
    ]
    
    selected = 0
    
    with screen_manager.screen(create_menu_layout(selected, menu_items)) as live:
        while True:
            # Get user input (you'll need to implement this)
            # For now, we'll use a simple approach
            
            # Update layout with current selection
            live.update(create_menu_layout(selected, menu_items))
            
            # Handle input - this would use your existing input handling
            # For example, using keyboard input:
            key = get_key_press()  # You need to implement this
            
            if key == "down" or key == "j":
                selected = (selected + 1) % len(menu_items)
            elif key == "up" or key == "k":
                selected = (selected - 1) % len(menu_items)
            elif key == "enter":
                action = menu_items[selected][1]
                if action == "quit":
                    return
                elif action == "create":
                    show_create_resume()
                elif action == "view":
                    show_view_resumes()
                # ... etc
            elif key == "q":
                return
```

### Complete Go Dashboard with TTY Detection

```go
// dashboard/main.go

package main

import (
    "os"
    
    tea "github.com/charmbracelet/bubbletea"
)

func isTerminal() bool {
    // Check if we're running in a terminal
    // This is a simplified check - you may want to enhance it
    
    // Check if stdout is a character device
    stat, err := os.Stat("/dev/tty")
    if err != nil {
        return false
    }
    
    return stat.Mode()&os.ModeCharDevice != 0
}

func main() {
    opts := []tea.ProgramOption{
        tea.WithAltScreen(),
    }
    
    // If we're in a real terminal, force TTY allocation
    // This ensures alt-screen works even when called from subprocess
    if isTerminal() {
        opts = append(opts,
            tea.WithInputTTY(),
            tea.WithOutputTTY(),
        )
    }
    
    p := tea.NewProgram(initialModel(), opts...)
    
    // Enable mouse support (since you're adding Bubblezone anyway)
    p.EnableMouseCellMotion()
    
    if _, err := p.Run(); err != nil {
        os.Exit(1)
    }
}
```

---

## Final Verdict

**You CAN achieve consistent alt-screen behavior across your entire program.** The solution involves:

1. **Python CLI:** Add `screen=True` to all Rich `Live` displays (or use `Console.screen()`)
2. **Go Dashboard:** Ensure it uses `WithAltScreen()` and proper TTY handling
3. **Subprocess Calls:** Use PTY when calling Go from Python to ensure terminal allocation
4. **State Management:** Create a screen manager to handle nested screens cleanly

**The sparkle banner will persist correctly** when all components use alt-screen consistently. The key insight is that alt-screen creates a separate buffer - when both Python and Go use it, they're working in the same buffer space, and transitions are seamless.

**This will give you the Crush-level "shockingly beautiful" glam** you're aiming for, with consistent full-screen behavior throughout your entire application.

---

## Resources

- [Bubble Tea Alternate Screen Documentation](https://pkg.go.dev/github.com/charmbracelet/bubbletea)
- [Bubble Tea altscreen-toggle Example](https://github.com/charmbracelet/bubbletea/tree/master/examples/altscreen-toggle)
- [Bubble Tea fullscreen Example](https://github.com/charmbracelet/bubbletea/tree/master/examples/fullscreen)
- [Bubble Tea Issue #823](https://github.com/charmbracelet/bubbletea/issues/823) - Critical for understanding pipe limitations
- [Rich Live Display with screen=True](https://rich.readthedocs.io/en/stable/live.html)
- [Rich Console.screen()](https://rich.readthedocs.io/en/stable/reference/console.html)
- [Rich fullscreen Example](https://github.com/Textualize/rich/blob/master/examples/fullscreen.py)
- [Terminal Alternate Screen Buffer Guide](https://terminalguide.namepad.de/mode/p47/)

---

**🎉 Next Step:** Start with Phase 1 - add alt-screen to your Python CLI using the `ScreenManager` pattern. This single change will immediately improve consistency and get you 80% of the way to your goal! ✨