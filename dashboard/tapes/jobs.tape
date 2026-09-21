# VHS Tape: Jobs triage screen (generated layout: hidden launch, wait on real UI text)
Output artifacts/tui_jobs.gif

Set FontSize 14
Set Width 1200
Set Height 750
Set Padding 20
Set Theme "Catppuccin Mocha"
Set FontFamily "JetBrainsMono Nerd Font, Menlo, monospace"
Env RESUME_BUILDER_ICONS "unicode"
Set TypingSpeed 0

# Launch off-camera so the recording starts on the rendered dashboard.
Hide
Type "clear && .venv/bin/python scripts/dashboard.py"
Enter
Wait+Screen@60s /Knowledge Base|Pipeline/
Sleep 500ms
Show
Sleep 500ms
Type "3"
Wait+Screen@30s /Jobs|filter/
Sleep 1s
Screenshot artifacts/tui_jobs.png
Sleep 1s
