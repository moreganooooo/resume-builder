# VHS Tape: dashboard main menu, Catppuccin Latte theme
Output artifacts/tui_light.gif

Set FontSize 14
Set Width 1200
Set Height 750
Set Padding 20
Set Theme "Catppuccin Latte"
Set FontFamily "JetBrainsMono Nerd Font, Menlo, monospace"
Env RESUME_BUILDER_ICONS "unicode"
Set TypingSpeed 0

# Launch off-camera so the recording starts on the rendered UI.
Hide
Type "clear && .venv/bin/python scripts/dashboard.py --theme catppuccin-latte"
Enter
Wait+Screen@60s /Knowledge Base|Pipeline/
Sleep 500ms
Show
Sleep 500ms
Sleep 1s
Screenshot artifacts/tui_light.png
Sleep 1s
