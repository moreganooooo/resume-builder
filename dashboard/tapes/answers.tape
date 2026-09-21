# VHS Tape: Application-question answers view
# NOTE: submitting the question makes one real Gemini call per capture.
Output artifacts/tui_answers.gif

Set FontSize 14
Set Width 1200
Set Height 750
Set Padding 20
Set Theme "Catppuccin Mocha"
Set FontFamily "JetBrainsMono Nerd Font, Menlo, monospace"
Env RESUME_BUILDER_ICONS "unicode"
Set TypingSpeed 0

Hide
Type "clear && .venv/bin/python scripts/dashboard.py --view answers --job fixtures/sample_jd.txt"
Enter
Wait+Screen@60s /Paste an application question/
Sleep 500ms
Show
Sleep 500ms
Set TypingSpeed 40ms
Type "Why do you want this role?"
Sleep 500ms
Enter
Wait+Screen@120s /Answer ready|Error:/
Sleep 1s
Screenshot artifacts/tui_answers.png
Sleep 1s
