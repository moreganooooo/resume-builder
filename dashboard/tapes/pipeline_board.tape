# VHS Tape: Pipeline board view (v cycles grouped -> flat -> board)
Output artifacts/tui_pipeline_board.gif

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
Type "1"
Wait+Screen@30s /Pipeline/
Sleep 500ms
# Two presses: v cycles grouped -> flat -> board, so the board is two hops
# from the screen's default, not one.
Type "v"
Sleep 500ms
Type "v"
Wait+Screen@30s /APPLIED|INTERVIEW|OFFER/
Sleep 1s
Screenshot artifacts/tui_pipeline_board.png
Sleep 1s
