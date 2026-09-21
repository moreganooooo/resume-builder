# VHS Tape: Python CLI menu > Bullet Bank
Output artifacts/tui_cli_bullet_bank.gif

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
Type "clear && .venv/bin/python scripts/cli.py"
Enter
Wait+Screen@60s /What would you like to do/
Sleep 500ms
Show
Sleep 500ms
Down@200ms 2
Sleep 300ms
Enter
Sleep 6s
Screenshot artifacts/tui_cli_bullet_bank.png
Sleep 500ms
