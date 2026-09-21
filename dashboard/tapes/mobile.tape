# VHS Tape: Mobile screen (generated layout: hidden launch, wait on real UI text)
Output artifacts/tui_mobile.gif

Set FontSize 13
Set Width 460
Set Height 820
Set Padding 20
Set Theme "Catppuccin Mocha"
Set FontFamily "JetBrainsMono Nerd Font, Menlo, monospace"
Env RESUME_BUILDER_ICONS "unicode"
Set TypingSpeed 0
Env RESUME_BUILDER_MOBILE "1"

# Launch off-camera so the recording starts on the rendered dashboard.
Hide
Type "clear && .venv/bin/python scripts/dashboard.py"
Enter
Wait+Screen@60s /Knowledge Base|Pipeline/
Sleep 500ms
Show
Sleep 1s
Screenshot artifacts/tui_mobile.png
Sleep 1s
