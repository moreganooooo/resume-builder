#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# ◈ RESUME-BUILDER ONE-COMMAND TERMUX (MOBILE) UPDATER ◈
# Safely pulls the latest updates, ensures dependencies are fresh, and runs doctor.
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
echo -e "${BOLD}${BRAND}    ◈  R E S U M E   B U I L D E R   M O B I L E   U P D A T E  ◈${RESET}"
echo -e "${BOLD}${ACCENT}       Termux Update & Health Check Wizard${RESET}"
echo -e "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}\n"

cd "$PROJECT_ROOT"

# 1. Pull latest git commits
echo -e "[ ${BOLD}${INFO}INFO${RESET} ] Fetching latest updates from git repository..."
if [ -d ".git" ]; then
    git pull --rebase || {
        echo -e "[ ${BOLD}${WARNING}WARN${RESET} ] git pull encountered conflicts or offline state. Continuing with local version."
    }
fi

# 2. Virtual environment dependency sync
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo -e "[ ${BOLD}${INFO}INFO${RESET} ] Verifying python dependencies..."
    if [ -f "requirements-lite.txt" ]; then
        pip install -r requirements-lite.txt --quiet
    fi
else
    echo -e "[ ${BOLD}${WARNING}WARN${RESET} ] .venv not found. Running installer..."
    bash scripts/termux_install.sh
    exit 0
fi

# 3. Syncthing & Doctor verification
echo -e "\n[ ${BOLD}${BRAND}DIAG${RESET} ] Checking Syncthing sync integrity..."
python3 scripts/verify_syncthing.py || true

echo -e "\n[ ${BOLD}${BRAND}DIAG${RESET} ] Running resume doctor checks..."
python3 scripts/doctor.py --skip-tests || true

echo -e "\n${BOLD}${SUCCESS}✓ Mobile installation is up to date and verified!${RESET}\n"
