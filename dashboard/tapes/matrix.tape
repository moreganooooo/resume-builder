# VHS Tape: Jobs skills-gap matrix (top job; scrolls the detail pane)
# Shows a STORED matrix only -- pressing m would compute one (API/embedding cost).
Output artifacts/tui_matrix.gif

Set FontSize 14
Set Width 1200
Set Height 750
Set Padding 20
Set Theme "Catppuccin Mocha"
Set FontFamily "JetBrainsMono Nerd Font, Menlo, monospace"
Env RESUME_BUILDER_ICONS "unicode"
Set TypingSpeed 0

Hide
Type "clear && .venv/bin/python scripts/dashboard.py"
Enter
Wait+Screen@60s /Knowledge Base|Pipeline/
Sleep 500ms
Show
Sleep 500ms
Type "4"
Wait+Screen@30s /JOBS/
Sleep 500ms
Type@80ms "JJJJJJJJJJJJJJJJJJJJJJJJJJJJJJ"
Wait+Screen@30s /Skills Gap Matrix/
Sleep 1s
Screenshot artifacts/tui_matrix.png
Sleep 1s
