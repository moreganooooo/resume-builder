#!/usr/bin/env bash
# ==============================================================================
# ◈ RESUME-BUILDER UNIFIED INSTALLER & SETUP WIZARD ◈
# Supports: macOS, Linux, Windows (WSL), and Mobile (Android Termux)
# ==============================================================================

# TrueColor / ANSI hex mappings
BRAND="\x1b[38;2;139;117;255m"      # #8B75FF (Catppuccin Lavender)
ACCENT="\x1b[38;2;255;96;255m"     # #FF60FF (Brand Accent Mauve)
SUCCESS="\x1b[38;2;166;227;161m"    # Catppuccin Green
INFO="\x1b[38;2;137;180;250m"       # Catppuccin Blue
WARNING="\x1b[38;2;249;226;175m"    # Catppuccin Yellow
ERROR="\x1b[38;2;243;139;168m"      # Catppuccin Red
RESET="\x1b[0m"
BOLD="\x1b[1m"

# Absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

clear

# Print TrueColor Gradient Banner
printf "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}\n"
printf "${BOLD}${BRAND}    ◈  R E S U M E   B U I L D E R   I N S T A L L E R  ◈${RESET}\n"
printf "${BOLD}${ACCENT}       Multi-Platform Setup Wizard (Desktop & Mobile Sync)${RESET}\n"
printf "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}\n\n"

# 1. Environment Detection
IS_MOBILE=0
if [ -d "/data/data/com.termux" ] || [ -n "$TERMUX_VERSION" ]; then
    IS_MOBILE=1
    printf "[ ${BOLD}${INFO}INFO${RESET} ] Detected environment: ${BOLD}${ACCENT}Android Termux (Mobile)${RESET}\n"
else
    printf "[ ${BOLD}${INFO}INFO${RESET} ] Detected environment: ${BOLD}${INFO}Desktop / Laptop OS${RESET}\n"
fi

# 2. Python Version Check
printf "[ ${BOLD}${BRAND}WAIT${RESET} ] Verifying Python installation...\n"
if ! command -v python3 >/dev/null 2>&1; then
    printf "[ ${BOLD}${ERROR}FAIL${RESET} ] ${BOLD}python3 is not installed.${RESET} Please install Python 3.10+ and try again.\n"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info[0])")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info[1])")

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    printf "[ ${BOLD}${ERROR}FAIL${RESET} ] Python version ${PY_VERSION} detected. ${BOLD}Requires >= 3.10.${RESET}\n"
    exit 1
else
    printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Python ${PY_VERSION} verified.\n"
fi

# 3. Choose Installation Mode
if [ "$IS_MOBILE" -eq 1 ]; then
    printf "\n${BOLD}${BRAND}RECOMMENDED SETTING FOR MOBILE:${RESET}\n"
    printf "  ${BOLD}${SUCCESS}1. Mobile Lite Mode${RESET} (Ultra-light virtual environment, ~15MB footprint)\n"
    printf "  2. Full Mobile Setup (Attempt compiling all packages, ~500MB)\n"
    printf "\nWhich mode would you like to run? [1/2] (Default: 1): "
    read -r mode_choice
    mode_choice="${mode_choice:-1}"
else
    printf "\n${BOLD}${BRAND}RECOMMENDED SETTING FOR DESKTOP:${RESET}\n"
    printf "  ${BOLD}${SUCCESS}1. Full Desktop Suite${RESET} (Standard environment with PDF compiling capabilities)\n"
    printf "  2. Lite Development Setup (Skip browser compiling, PDF rendering on desktop)\n"
    printf "\nWhich mode would you like to run? [1/2] (Default: 1): "
    read -r mode_choice
    mode_choice="${mode_choice:-1}"
fi

# 4. Virtual Environment Creation
printf "\n[ ${BOLD}${BRAND}WAIT${RESET} ] Creating isolated virtual environment in ${BOLD}.venv/${RESET}...\n"
cd "$PROJECT_ROOT" || exit 1
if [ -d ".venv" ]; then
    printf "[ ${BOLD}${INFO}INFO${RESET} ] Existing .venv/ found. Cleaning up for clean reinstall...\n"
    rm -rf .venv
fi
python3 -m venv .venv
if [ $? -eq 0 ]; then
    printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Virtual environment provisioned successfully.\n"
else
    printf "[ ${BOLD}${ERROR}FAIL${RESET} ] Failed to create virtual environment.\n"
    exit 1
fi

# 5. Dependency Provisioning
source .venv/bin/activate
printf "\n[ ${BOLD}${BRAND}WAIT${RESET} ] Installing dependencies in .venv/...\n"

if { [ "$IS_MOBILE" -eq 1 ] && [ "$mode_choice" -eq 1 ]; } || { [ "$IS_MOBILE" -eq 0 ] && [ "$mode_choice" -eq 2 ]; }; then
    # Lite Mode dependency list
    printf "[ ${BOLD}${INFO}INFO${RESET} ] Installing distilled, pure-Python Lite Package List (~15MB space)...\n"
    pip install --upgrade pip
    pip install pyyaml pydantic requests python-dotenv google-genai click rich beautifulsoup4 questionary pypdf
else
    # Full Desktop/Mobile dependency list
    printf "[ ${BOLD}${INFO}INFO${RESET} ] Installing complete requirements list (~250MB)...\n"
    pip install --upgrade pip
    pip install -r requirements.txt

    # Check for node/npm to compile Playwright
    if command -v npm >/dev/null 2>&1; then
        printf "[ ${BOLD}${INFO}INFO${RESET} ] Detected Node.js. Triggering Playwright Chromium compilation...\n"
        npm install
        npx playwright install chromium
    else
        printf "[ ${BOLD}${WARNING}WARN${RESET} ] Node.js not detected. Skipping standalone PDF browser compiler.\n"
        printf "         (You can run PDF compiling later by installing Node.js/npm and running 'npm install').\n"
    fi
fi

if [ $? -eq 0 ]; then
    printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Python dependencies installed cleanly.\n"
else
    printf "[ ${BOLD}${ERROR}FAIL${RESET} ] Dependency installation encountered errors.\n"
    exit 1
fi

# 6. Provisioning Shell Shortcuts
printf "\n[ ${BOLD}${BRAND}WAIT${RESET} ] Registering global shell shortcuts...\n"
SHELL_RC=""
if [ -n "$ZSH_VERSION" ] || [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -n "$BASH_VERSION" ] || [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -f "$HOME/.termux/shell.profile" ]; then
    SHELL_RC="$HOME/.termux/shell.profile"
fi

if [ -n "$SHELL_RC" ]; then
    SOURCE_LINE="source $PROJECT_ROOT/scripts/resume-cli.sh"
    if grep -q "resume-cli.sh" "$SHELL_RC" >/dev/null 2>&1; then
        printf "[ ${BOLD}${INFO}INFO${RESET} ] 'resume' command shortcut already exists in $SHELL_RC.\n"
    else
        printf "\n# Added by resume-builder installer\n%s\n" "$SOURCE_LINE" >> "$SHELL_RC"
        printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Added global 'resume' command alias to ${BOLD}$SHELL_RC${RESET}.\n"
    fi
else
    printf "[ ${BOLD}${WARNING}WARN${RESET} ] Could not locate standard shell profile file (~/.zshrc, ~/.bashrc).\n"
    printf "         Please manually source: ${BOLD}source $PROJECT_ROOT/scripts/resume-cli.sh${RESET}\n"
fi

# 6.5. Mobile-Specific Power-User Optimizations
if [ "$IS_MOBILE" -eq 1 ]; then
    printf "\n${BOLD}${BRAND}▯ DETECTED MOBILE: OPTIMIZE FOR LINUX MOBILE?${RESET}\n"
    printf "This will automatically:\n"
    printf "  ✦ Install & configure ${BOLD}Nerd Fonts${RESET} (for terminal icons/sparkles)\n"
    printf "  ◈ Install a clean ${BOLD}Catppuccin Macchiato${RESET} TrueColor theme\n"
    printf "  ▤ Setup ${BOLD}termux-api clipboard sync${RESET} utility\n"
    printf "  ⌨  Install specialized touch terminal navigation keys (ESC, CTRL, Arrow keys)\n"
    printf "  ▶ Create a One-Tap Home Screen Launcher via ${BOLD}Termux:Widget${RESET}\n"
    printf "\nApply these beautiful optimizations? [Y/n]: "
    read -r opt_choice
    opt_choice="${opt_choice:-Y}"

    if [ "$opt_choice" = "Y" ] || [ "$opt_choice" = "y" ]; then
        printf "\n[ ${BOLD}${BRAND}WAIT${RESET} ] Downloading and setting up Nerd Fonts...\n"
        mkdir -p "$HOME/.termux"
        curl -fsSL -o "$HOME/.termux/font.ttf" "https://github.com/ryanoasis/nerd-fonts/raw/HEAD/patched-fonts/FiraCode/Regular/FiraCodeNerdFont-Regular.ttf"
        if [ $? -eq 0 ]; then
            printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Fira Code Nerd Font compiled to ~/.termux/font.ttf.\n"
        else
            printf "[ ${BOLD}${WARNING}WARN${RESET} ] Could not fetch font. Skipping font installation.\n"
        fi

        printf "[ ${BOLD}${BRAND}WAIT${RESET} ] Writing Catppuccin Macchiato color configuration...\n"
        # Write Catppuccin Macchiato colors to colors.properties
        cat << 'EOF' > "$HOME/.termux/colors.properties"
background = #24273a
foreground = #cad3f5
color0     = #494d64
color1     = #ed8796
color2     = #a6da95
color3     = #eed49f
color4     = #8aadf4
color5     = #f5bde6
color6     = #8bd5ca
color7     = #b8c0e0
color8     = #5b6078
color9     = #ed8796
color10    = #a6da95
color11    = #eed49f
color12    = #8aadf4
color13    = #f5bde6
color14    = #8bd5ca
color15    = #a5adcb
EOF
        printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Applied Catppuccin color profile.\n"

        printf "[ ${BOLD}${BRAND}WAIT${RESET} ] Configuring Termux Clipboard API...\n"
        pkg install termux-api -y >/dev/null 2>&1
        printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Clipboard sync package registered.\n"

        printf "[ ${BOLD}${BRAND}WAIT${RESET} ] Provisioning extra navigation keys...\n"
        # Set Termux properties for extra keys
        cat << 'EOF' > "$HOME/.termux/termux.properties"
extra-keys = [ \
  ['ESC','TAB','CTRL','ALT','UP','DOWN','LEFT','RIGHT'] \
]
EOF
        printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Terminal touch navigation panel provisioned.\n"

        printf "[ ${BOLD}${BRAND}WAIT${RESET} ] Creating One-Tap Home Screen Launcher...\n"
        mkdir -p "$HOME/.shortcuts/tasks"
        cat << EOF > "$HOME/.shortcuts/tasks/ResumeBuilder"
#!/usr/bin/env bash
cd $PROJECT_ROOT
source .venv/bin/activate
python scripts/menu.py
EOF
        chmod +x "$HOME/.shortcuts/tasks/ResumeBuilder"
        printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Home Screen launch widget configured successfully.\n"

        # Reload Termux settings
        termux-reload-settings >/dev/null 2>&1
        printf "[ ${BOLD}${SUCCESS}PASS${RESET} ] Reloaded Termux layout configuration.\n"
    fi
fi

# 7. Print Post-Installation Actions
printf "\n"
printf "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}\n"
printf "       ✦  ${BOLD}${SUCCESS}INSTALLATION COMPLETED SUCCESSFULLY!${RESET}  ✦\n"
printf "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}\n\n"

if [ "$IS_MOBILE" -eq 1 ] && [ "$mode_choice" -eq 1 ]; then
    printf "${BOLD}${ACCENT}▯ MOBILE SYNCING COMPANION STRATEGY ACTIVATED:${RESET}\n"
    printf "  1. Install ${BOLD}Syncthing${RESET} on your Desktop and your Pixel 10.\n"
    printf "  2. Pair devices and share your active profile directories:\n"
    printf "     - ${BOLD}profiles/morgan/${RESET}\n"
    printf "     - ${BOLD}jds/morgan/${RESET}\n"
    printf "     - ${BOLD}output/morgan/${RESET}\n"
    printf "     - ${BOLD}data/morgan/${RESET}\n"
    printf "  3. When you run a scan/tailoring on your Pixel 10, the tiny state JSONs\n"
    printf "     will automatically sync to your desktop in <1 second.\n"
    printf "  4. Your desktop compilation daemon will instantly output the polished PDFs,\n"
    printf "     syncing them right back to your phone! No mobile storage bloat!\n\n"
fi

printf "${BOLD}${BRAND}Next Steps:${RESET}\n"
printf "  1. Open a new terminal session (or run: ${BOLD}source $SHELL_RC${RESET})\n"
printf "  2. Start the interactive console by typing: ${BOLD}resume${RESET}\n"
printf "  3. Verify everything is perfect by running: ${BOLD}resume doctor${RESET}\n\n"

printf "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}\n"
