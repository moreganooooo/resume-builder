<#
.SYNOPSIS
    Resume-Builder installer for Windows (native PowerShell).

.DESCRIPTION
    Mirrors scripts/install.sh for machines without WSL. Sets up the Python
    virtual environment, installs dependencies, optionally installs Node.js /
    Playwright, and registers the `resume` command in your PowerShell profile.

.NOTES
    Requires PowerShell 5.1+ (ships with Windows 10/11) or PowerShell 7+.
    Run once from an elevated or normal PowerShell window:

        powershell -ExecutionPolicy Bypass -File scripts\install.ps1

    If you see "running scripts is disabled", set execution policy for your
    user account permanently:

        Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

    Python 3.10-3.12 must be installed before running this script.
    Python 3.13+ is NOT supported (numpy wheel constraint -- see comment below).
#>

#Requires -Version 5.1
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Enable VT/ANSI sequences (ConHost on Windows 10+) ────────────────────────
# Windows Terminal and VS Code handle this automatically; ConHost (the default
# terminal on older Win10 builds) needs it explicitly enabled.
try {
    if (-not ([System.Management.Automation.PSTypeName]'RBInstall.K32').Type) {
        $sig = @'
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int n);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint m);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint m);
'@
        Add-Type -MemberDefinition $sig -Name K32 -Namespace RBInstall | Out-Null
    }
    $h = [RBInstall.K32]::GetStdHandle(-11)   # STD_OUTPUT_HANDLE
    $m = 0u
    if ([RBInstall.K32]::GetConsoleMode($h, [ref]$m)) {
        [RBInstall.K32]::SetConsoleMode($h, $m -bor 4u) | Out-Null  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    }
} catch { <# Non-fatal -- colors degrade gracefully on very old consoles. #> }

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$ESC     = [char]27
$BRAND   = "$ESC[38;2;139;117;255m"
$ACCENT  = "$ESC[38;2;255;96;255m"
$SUCCESS = "$ESC[38;2;18;199;143m"
$INFO    = "$ESC[38;2;0;164;255m"
$WARNING = "$ESC[38;2;245;239;52m"
$ERR     = "$ESC[38;2;255;123;153m"
$BOLD    = "$ESC[1m"
$RESET   = "$ESC[0m"

$SCRIPT_DIR   = $PSScriptRoot
$PROJECT_ROOT = Split-Path -Parent $SCRIPT_DIR

Clear-Host

Write-Host "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}"
Write-Host "${BOLD}${BRAND}    ◈  R E S U M E   B U I L D E R   I N S T A L L E R  ◈${RESET}"
Write-Host "${BOLD}${ACCENT}       Windows Setup Wizard (Native PowerShell)${RESET}"
Write-Host "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}"
Write-Host ""

# ── 1. Python version check ───────────────────────────────────────────────────
Write-Host "[ ${BOLD}${BRAND}WAIT${RESET} ] Verifying Python installation..."

$pyCmd = $null
foreach ($candidate in @('python3', 'python', 'py')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $pyCmd = $candidate
        break
    }
}

if (-not $pyCmd) {
    Write-Host "[ ${BOLD}${ERR}FAIL${RESET} ] ${BOLD}Python not found.${RESET} Install Python 3.10-3.12 from https://python.org"
    Write-Host "         then re-run this script."
    exit 1
}

$pyMajor = [int](& $pyCmd -c "import sys; print(sys.version_info[0])")
$pyMinor = [int](& $pyCmd -c "import sys; print(sys.version_info[1])")
$pyVer   = & $pyCmd -c "import sys; print('.'.join(map(str, sys.version_info[:2])))"

if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 10)) {
    Write-Host "[ ${BOLD}${ERR}FAIL${RESET} ] Python $pyVer detected. ${BOLD}Requires 3.10-3.12.${RESET}"
    exit 1
} elseif ($pyMajor -eq 3 -and $pyMinor -gt 12) {
    Write-Host "[ ${BOLD}${ERR}FAIL${RESET} ] Python $pyVer detected. ${BOLD}Requires 3.10-3.12.${RESET}"
    Write-Host "         A dependency (python-jobspy) pins numpy==1.26.3, which has no"
    Write-Host "         wheel for Python 3.13+ and cannot be built against it."
    Write-Host "         Install Python 3.12 from https://python.org, then re-run, e.g.:"
    Write-Host "           ${BOLD}winget install Python.Python.3.12${RESET}"
    exit 1
} else {
    Write-Host "[ ${BOLD}${SUCCESS}PASS${RESET} ] Python $pyVer verified."
}

# ── 2. Installation mode ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "${BOLD}${BRAND}RECOMMENDED SETTING FOR DESKTOP:${RESET}"
Write-Host "  ${BOLD}${SUCCESS}1. Full Desktop Suite${RESET} (Standard environment with PDF compiling capabilities)"
Write-Host "  2. Lite Development Setup (Skip browser compiling, faster install)"
Write-Host ""
$modeChoice = Read-Host "Which mode would you like to run? [1/2] (Default: 1)"
if (-not $modeChoice) { $modeChoice = '1' }

# ── 3. Virtual environment ────────────────────────────────────────────────────
Write-Host ""
Write-Host "[ ${BOLD}${BRAND}WAIT${RESET} ] Creating virtual environment in ${BOLD}.venv\${RESET}..."
Set-Location $PROJECT_ROOT

if (Test-Path '.venv') {
    Write-Host "[ ${BOLD}${WARNING}WARN${RESET} ] An existing ${BOLD}.venv\${RESET} was found."
    Write-Host "  ${BOLD}1. Keep it${RESET} and install/upgrade packages into it (recommended)"
    Write-Host "  2. Delete and rebuild from scratch"
    $venvChoice = Read-Host "Which would you like? [1/2] (Default: 1)"
    if (-not $venvChoice) { $venvChoice = '1' }
    if ($venvChoice -eq '2') {
        Write-Host "[ ${BOLD}${INFO}INFO${RESET} ] Removing existing .venv\ for a clean rebuild..."
        Remove-Item -Recurse -Force '.venv'
    } else {
        Write-Host "[ ${BOLD}${INFO}INFO${RESET} ] Keeping existing .venv\."
    }
}

if (-not (Test-Path '.venv')) {
    & $pyCmd -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ ${BOLD}${ERR}FAIL${RESET} ] Failed to create virtual environment."
        exit 1
    }
}
Write-Host "[ ${BOLD}${SUCCESS}PASS${RESET} ] Virtual environment provisioned successfully."

# ── 4. Dependencies ───────────────────────────────────────────────────────────
$venvPip = Join-Path $PROJECT_ROOT '.venv\Scripts\pip.exe'

Write-Host ""
Write-Host "[ ${BOLD}${BRAND}WAIT${RESET} ] Installing dependencies in .venv\..."

& $venvPip install --upgrade pip | Out-Null

if ($modeChoice -eq '2') {
    Write-Host "[ ${BOLD}${INFO}INFO${RESET} ] Installing Lite Package List (~15 MB)..."
    & $venvPip install -r requirements-lite.txt
    $pipRc = $LASTEXITCODE
    Write-Host "[ ${BOLD}${INFO}INFO${RESET} ] Lite Mode installed. Onboarding and tailoring work;"
    Write-Host "         local PDF rendering, LinkedIn/Indeed scanning, and the extra export"
    Write-Host "         formats need Full mode (see requirements-lite.txt for the split)."
} else {
    Write-Host "[ ${BOLD}${INFO}INFO${RESET} ] Installing complete requirements list (~250 MB)..."
    & $venvPip install -r requirements.txt
    $pipRc = $LASTEXITCODE

    if ($pipRc -eq 0) {
        if (Get-Command npm -ErrorAction SilentlyContinue) {
            Write-Host "[ ${BOLD}${INFO}INFO${RESET} ] Detected Node.js. Installing npm packages and Playwright Chromium..."
            npm install
            npx playwright install chromium
        } else {
            Write-Host "[ ${BOLD}${WARNING}WARN${RESET} ] Node.js not found. Skipping PDF browser compiler."
            Write-Host "         Install Node.js from https://nodejs.org, then run from the project root:"
            Write-Host "           ${BOLD}npm install${RESET}"
            Write-Host "           ${BOLD}npx playwright install chromium${RESET}"
        }
    }
}

if ($pipRc -ne 0) {
    Write-Host "[ ${BOLD}${ERR}FAIL${RESET} ] Dependency installation failed (pip exit code $pipRc)."
    Write-Host "         Activate .venv\ and run pip install by hand to see the full error:"
    Write-Host "           ${BOLD}.\.venv\Scripts\Activate.ps1${RESET}"
    Write-Host "           ${BOLD}pip install -r requirements.txt${RESET}"
    exit 1
}
Write-Host "[ ${BOLD}${SUCCESS}PASS${RESET} ] Python dependencies installed cleanly."

# ── 5. PowerShell profile (resume shortcut) ───────────────────────────────────
Write-Host ""
Write-Host "[ ${BOLD}${BRAND}WAIT${RESET} ] Registering 'resume' command in PowerShell profile..."

$cliScript  = Join-Path $SCRIPT_DIR 'resume-cli.ps1'
$sourceLine = ". `"$cliScript`""

# Ensure the profile directory and file exist.
$profileDir = Split-Path -Parent $PROFILE
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}
if (-not (Test-Path $PROFILE)) {
    New-Item -ItemType File -Path $PROFILE -Force | Out-Null
}

$profileContent = Get-Content $PROFILE -Raw -ErrorAction SilentlyContinue
if ($profileContent -and $profileContent -match 'resume-cli\.ps1') {
    Write-Host "[ ${BOLD}${INFO}INFO${RESET} ] 'resume' shortcut already exists in `$PROFILE."
} else {
    Add-Content -Path $PROFILE -Value "`n# Added by resume-builder installer`n$sourceLine"
    Write-Host "[ ${BOLD}${SUCCESS}PASS${RESET} ] Added 'resume' command to ${BOLD}`$PROFILE${RESET}."
    Write-Host "         ($PROFILE)"
}

# ── 6. Summary ────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}"
Write-Host "       ✦  ${BOLD}${SUCCESS}INSTALLATION COMPLETED SUCCESSFULLY!${RESET}  ✦"
Write-Host "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}"
Write-Host ""
Write-Host "${BOLD}${BRAND}Next Steps:${RESET}"
Write-Host "  1. Open a new PowerShell window  (or reload: ${BOLD}. `$PROFILE${RESET})"
Write-Host "  2. Start the interactive console: ${BOLD}resume${RESET}"
Write-Host "  3. Choose ${BOLD}${ACCENT}`"--> New User? Start Here!`"${RESET} to create your profile"
Write-Host "     and load your resume. You'll need a free Gemini API key from"
Write-Host "     Google AI Studio (aistudio.google.com)."
Write-Host "  4. Verify everything is set up:  ${BOLD}resume doctor${RESET}"
Write-Host ""
Write-Host "${BOLD}${BRAND}✦ ────────────────────────────────────────────────────────────── ✦${RESET}"
