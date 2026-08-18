# VHS Tape: Mobile Termux Screen (40x24)
Output artifacts/tui_mobile.png
Output artifacts/tui_mobile.gif

Set FontSize 16
Set Width 420
Set Height 720
Set Padding 10
Set Theme "Catppuccin Mocha"
Set FontFamily "JetBrainsMono Nerd Font"
Env RESUME_BUILDER_MOBILE "1"

Type "python3 scripts/dashboard.py"
Enter
Sleep 1.5s
Screenshot artifacts/tui_mobile.png
Sleep 2s
