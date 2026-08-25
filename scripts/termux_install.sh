#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# ◈ RESUME-BUILDER ONE-COMMAND TERMUX (MOBILE) INSTALLER ◈
# Optimized for Google Pixel / Android Termux touch environments.
# ==============================================================================

set -e

BRAND="\033[38;2;139;117;255m"      # #8B75FF
ACCENT="\033[38;2;255;96;255m"     # #FF60FF
SUCCESS="\033[38;2;18;199;143m"    # #12C78F
INFO="\033[38;2;0;164;255m"        # #00A4FF
WARNING="\033[38;2;245;239;52m"    # #F5EF34
ERROR="\033[38;2;255;123;153m"     # #FF7B99
RESET="\033[0m"
BOLD="\033[1m"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}"
echo -e "${BOLD}${BRAND}    ◈  R E S U M E   B U I L D E R   M O B I L E   S E T U P  ◈${RESET}"
echo -e "${BOLD}${ACCENT}       Termux Lite Mode Bootstrapper for Android / Pixel${RESET}"
echo -e "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}\n"

# 1. Termux package requirements check
echo -e "[ ${BOLD}${INFO}INFO${RESET} ] Checking Termux environment packages..."
if command -v pkg >/dev/null 2>&1; then
    pkg update -y || true
    pkg install -y python git termux-api nodejs || true
fi

# 2. Python verification
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "[ ${BOLD}${ERROR}FAIL${RESET} ] Python 3 is not installed. Please run: pkg install python"
    exit 1
fi

PY_VER=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
echo -e "[ ${BOLD}${SUCCESS}PASS${RESET} ] Python ${PY_VER} verified."

# 3. Create Lite Virtual Environment
cd "$PROJECT_ROOT"
if [ ! -d ".venv" ]; then
    echo -e "[ ${BOLD}${INFO}INFO${RESET} ] Creating isolated mobile virtual environment (.venv)..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo -e "[ ${BOLD}${INFO}INFO${RESET} ] Upgrading pip and wheel..."
pip install --upgrade pip wheel setuptools --quiet

echo -e "[ ${BOLD}${INFO}INFO${RESET} ] Installing mobile lite requirements (requirements-lite.txt)..."
if [ -f "requirements-lite.txt" ]; then
    pip install -r requirements-lite.txt --quiet
else
    pip install click rich pyyaml pydantic requests --quiet
fi

# 4. Configure global alias in bashrc / zshrc
CLI_WRAPPER="$PROJECT_ROOT/scripts/resume-cli.sh"
ALIAS_LINE="source \"$CLI_WRAPPER\""

for RC_FILE in "$HOME/.bashrc" "$HOME/.zshrc"; do
    if [ -f "$RC_FILE" ] || [ "$RC_FILE" = "$HOME/.bashrc" ]; then
        touch "$RC_FILE"
        if ! grep -Fq "resume-cli.sh" "$RC_FILE"; then
            echo -e "\n# Resume Builder CLI\n$ALIAS_LINE" >> "$RC_FILE"
            echo -e "[ ${BOLD}${SUCCESS}PASS${RESET} ] Registered 'resume' shortcut in ${RC_FILE}"
        fi
    fi
done

# 5. Run Syncthing and environment verification
echo -e "\n[ ${BOLD}${BRAND}DIAG${RESET} ] Running Syncthing and directory diagnostics..."
python3 scripts/verify_syncthing.py || true

echo -e "\n${BOLD}${SUCCESS}✓ Mobile Termux setup completed successfully!${RESET}"
echo -e "You can now run ${BOLD}${ACCENT}resume menu${RESET} or ${BOLD}${ACCENT}resume doctor${RESET} from any directory.\n"
