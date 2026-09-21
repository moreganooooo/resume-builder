# VHS Tape: Progress help overlay
Output artifacts/tui_progress_help.gif

Set FontSize 14
Set Width 1200
Set Height 750
Set Padding 20
Set Theme "Catppuccin Mocha"
Set FontFamily "JetBrainsMono Nerd Font, Menlo, monospace"
Env RESUME_BUILDER_ICONS "unicode"
Set TypingSpeed 0

# Launch off-camera so the recording starts on the rendered UI.
Hide
Type "clear && .venv/bin/python scripts/dashboard.py"
Enter
Wait+Screen@60s /Knowledge Base|Pipeline/
Sleep 500ms
Show
Sleep 500ms
Type "2"
Wait+Screen@30s /SEARCH PROGRESS/
Sleep 500ms
Type "?"
Sleep 1s
Screenshot artifacts/tui_progress_help.png
Sleep 1s
