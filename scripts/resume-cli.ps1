# resume-builder PowerShell shortcuts.
#
# Dot-source from your PowerShell $PROFILE (the installer does this automatically):
#   . "C:\path\to\resume-builder\scripts\resume-cli.ps1"
#
# Defines: resume (function), rb (alias), jobkit (alias)
# Mirrors scripts/resume-cli.sh -- same subcommands, same profile-selector logic.
#
# NOTE: If you get "running scripts is disabled", set execution policy once:
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# ── Project root (relative to this script: scripts/ → parent) ────────────────
$script:RB_DIR  = Split-Path -Parent $PSScriptRoot
$script:VENV_PY = Join-Path $script:RB_DIR '.venv\Scripts\python.exe'

# ── Enable VT/ANSI sequences (ConHost on Windows 10+) ────────────────────────
try {
    if (-not ([System.Management.Automation.PSTypeName]'RBCli.K32').Type) {
        $sig = @'
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int n);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint m);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint m);
'@
        Add-Type -MemberDefinition $sig -Name K32 -Namespace RBCli | Out-Null
    }
    $h = [RBCli.K32]::GetStdHandle(-11)
    $m = 0u
    if ([RBCli.K32]::GetConsoleMode($h, [ref]$m)) {
        [RBCli.K32]::SetConsoleMode($h, $m -bor 4u) | Out-Null
    }
} catch {}

[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$script:_ESC     = [char]27
$script:_BRAND   = "$($script:_ESC)[38;2;139;117;255m"
$script:_ACCENT  = "$($script:_ESC)[38;2;255;96;255m"
$script:_SUCCESS = "$($script:_ESC)[38;2;18;199;143m"
$script:_INFO    = "$($script:_ESC)[38;2;0;164;255m"
$script:_WARNING = "$($script:_ESC)[38;2;245;239;52m"
$script:_ERR     = "$($script:_ESC)[38;2;255;123;153m"
$script:_MUTED   = "$($script:_ESC)[38;2;163;163;163m"
$script:_BOLD    = "$($script:_ESC)[1m"
$script:_RESET   = "$($script:_ESC)[0m"

# ── Profile selector (mirrors _resume_ensure_profile in resume-cli.sh) ────────
function _RbEnsureProfile {
    if ($env:RESUME_PROFILE) { return }

    $profilesDir = Join-Path $script:RB_DIR 'profiles'
    if (-not (Test-Path $profilesDir)) { return }

    $names = @(Get-ChildItem -Path $profilesDir -Directory |
               Select-Object -ExpandProperty Name)
    if ($names.Count -eq 0) { return }
    if ($names.Count -eq 1) { $env:RESUME_PROFILE = $names[0]; return }

    $default = if ($names -icontains 'morgan') { 'morgan' } else { $names[0] }

    # Tier 1: precompiled Go Charm prompt binary (same binary the menu uses)
    $promptBin = Join-Path $script:RB_DIR 'dashboard\bin\prompt.exe'
    if (-not (Test-Path $promptBin)) {
        if (Get-Command go -ErrorAction SilentlyContinue) {
            $prevDir = Get-Location
            Set-Location (Join-Path $script:RB_DIR 'dashboard')
            & go build -o bin\prompt.exe .\cmd\prompt 2>$null
            Set-Location $prevDir
        }
    }

    $choice = $null
    if (Test-Path $promptBin) {
        $opts = ($names | ForEach-Object {
            "{`"label`":`"$_`",`"value`":`"$_`"}"
        }) -join ','
        $spec = "{`"type`":`"select`",`"message`":`"Which profile for this terminal session?`",`"options`":[$opts],`"default_value`":`"$default`"}"
        $out  = & $promptBin $spec 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            if ($out -match '"value"\s*:\s*"([^"]+)"') { $choice = $Matches[1] }
        }
    }

    # Tier 2: plain numbered text list fallback (no gum on Windows, skip Python inline)
    if (-not $choice) {
        $e = $script:_ESC
        $B = $script:_BRAND; $A = $script:_ACCENT
        $S = $script:_SUCCESS; $M = $script:_MUTED; $BO = $script:_BOLD; $R = $script:_RESET
        Write-Host ""
        Write-Host "${BO}${B}✦ ──────────────────────────────────────────────────── ✦${R}"
        Write-Host "  ${BO}${B}◈ RESUME-BUILDER PROFILE SELECTOR${R}"
        Write-Host "${BO}${B}✦ ──────────────────────────────────────────────────── ✦${R}"
        for ($i = 0; $i -lt $names.Count; $i++) {
            $n = $names[$i]
            if ($n -eq $default) {
                Write-Host "    $($i + 1). ${BO}${A}●${R} ${BO}$n${R} ${M}(default)${R}"
            } else {
                Write-Host "    $($i + 1). ${M}○${R} $n"
            }
        }
        $ans = Read-Host "`n  Which profile for this session? [$default]"
        if (-not $ans) {
            $choice = $default
        } elseif ($ans -match '^\d+$') {
            $idx = [int]$ans - 1
            $choice = if ($idx -ge 0 -and $idx -lt $names.Count) { $names[$idx] } else { $default }
        } elseif ($names -contains $ans) {
            $choice = $ans
        } else {
            $choice = $default
        }
    }

    $env:RESUME_PROFILE = $choice
    $S = $script:_SUCCESS; $A = $script:_ACCENT; $M = $script:_MUTED
    $BO = $script:_BOLD; $R = $script:_RESET
    Write-Host "  ${S}✓ Active profile:${R} ${BO}${A}$choice${R} ${M}(session only — set RESUME_PROFILE to persist)${R}`n"
}

# ── resume function ───────────────────────────────────────────────────────────
function resume {
    <#
    .SYNOPSIS
        Resume-builder command dispatcher. Mirrors the `resume` shell function in resume-cli.sh.
    .EXAMPLE
        resume                    # Launch interactive menu
        resume run                # Batch-process all pending JDs
        resume run jds\morgan\foo.txt  # Single-file mode
        resume test               # Full test suite
        resume doctor             # Environment health check
        resume activate           # Activate .venv in this shell
        resume help               # Subcommand reference
    #>

    _RbEnsureProfile

    $BO = $script:_BOLD; $B = $script:_BRAND; $A = $script:_ACCENT
    $S = $script:_SUCCESS; $INFO = $script:_INFO; $E = $script:_ERR
    $M = $script:_MUTED; $R = $script:_RESET

    if (-not (Test-Path $script:VENV_PY)) {
        Write-Host "  ${E}✗ Error:${R} virtual environment not found."
        Write-Host "    Run: ${BO}powershell -ExecutionPolicy Bypass -File `"$(Join-Path $script:RB_DIR 'scripts\install.ps1')`"${R}"
        return
    }

    $cmd  = if ($args.Count -gt 0) { $args[0] } else { '' }
    $rest = if ($args.Count -gt 1) { $args[1..($args.Count - 1)] } else { @() }

    switch ($cmd) {

        # ── activate: dot-sources venv into the caller's scope ──────────────
        # $env: variables are process-global, so PATH and VIRTUAL_ENV persist.
        'activate' {
            . (Join-Path $script:RB_DIR '.venv\Scripts\Activate.ps1')
            Set-Location $script:RB_DIR
            $active = if ($env:RESUME_PROFILE) { $env:RESUME_PROFILE } else { 'default' }
            Write-Host ""
            Write-Host "${BO}${B}✦ ──────────────────────────────────────────────────────────── ✦${R}"
            Write-Host "  ${BO}${S}✓ Python Virtual Environment Activated${R} ${M}(.venv)${R}"
            Write-Host "  ${BO}◰ Working Directory:${R} ${INFO}$($script:RB_DIR)${R}"
            Write-Host "  ${BO}◉ Active Profile:${R}    ${A}$active${R}"
            Write-Host "${BO}${B}✦ ──────────────────────────────────────────────────────────── ✦${R}"
            Write-Host ""
        }

        # ── cd: change into the project root ────────────────────────────────
        'cd' {
            Set-Location $script:RB_DIR
            Write-Host "  ${INFO}◰ $($script:RB_DIR)${R}"
        }

        # ── run / tailor ─────────────────────────────────────────────────────
        'run' {
            Push-Location $script:RB_DIR
            try {
                if ($rest.Count -gt 0 -and -not $rest[0].StartsWith('-')) {
                    & $script:VENV_PY scripts\cli.py tailor @rest
                } else {
                    & $script:VENV_PY scripts\cli.py run @rest
                }
            } finally { Pop-Location }
        }

        # ── direct cli.py passthroughs ───────────────────────────────────────
        { $_ -in 'coverletter','evaluate','scan','liveness','polish',
                 'dashboard','bootstrap','sample','doctor' } {
            Push-Location $script:RB_DIR
            try { & $script:VENV_PY scripts\cli.py $cmd @rest }
            finally { Pop-Location }
        }

        # ── test ─────────────────────────────────────────────────────────────
        'test' {
            Push-Location $script:RB_DIR
            try {
                switch ($rest[0]) {
                    '-vv'    { & $script:VENV_PY -m unittest discover -s tests -v }
                    '-v'     { & $script:VENV_PY -m unittest discover -s tests -v }
                    default  { & $script:VENV_PY -m unittest discover -s tests }
                }
            } finally { Pop-Location }
        }

        # ── help ─────────────────────────────────────────────────────────────
        'help' {
            Write-Host ""
            Write-Host "${BO}${B}✦ ──────────────────────────────────────────────────────────── ✦${R}"
            Write-Host "  ${BO}${B}◈  R E S U M E - B U I L D E R  ·  S H O R T C U T S${R}"
            Write-Host "${BO}${B}✦ ──────────────────────────────────────────────────────────── ✦${R}"
            Write-Host ""
            Write-Host "  ${BO}${A}resume${R}                 Launch the interactive menu"
            Write-Host "  ${BO}${A}resume run${R}             Batch-process all pending JDs"
            Write-Host "  ${BO}${A}resume run${R} <jd-path>   Single-file tailor mode"
            Write-Host "  ${BO}${A}resume coverletter${R}     Run cover-letter generation"
            Write-Host "  ${BO}${A}resume evaluate${R}        Evaluate pending JDs"
            Write-Host "  ${BO}${A}resume scan${R}            Scan job boards"
            Write-Host "  ${BO}${A}resume liveness${R}        Check liveness of saved JDs"
            Write-Host "  ${BO}${A}resume polish${R}          Polish the latest tailored resume"
            Write-Host "  ${BO}${A}resume dashboard${R}       Open the Browse & Manage Jobs TUI"
            Write-Host "  ${BO}${A}resume bootstrap${R}       Run the new-user setup wizard"
            Write-Host "  ${BO}${A}resume sample${R}          QA smoke test (sample_jd fixture)"
            Write-Host "  ${BO}${A}resume doctor${R}          Environment health check"
            Write-Host "  ${BO}${A}resume test${R}            Full test suite"
            Write-Host "  ${BO}${A}resume test -v${R}         Verbose test output"
            Write-Host "  ${BO}${A}resume activate${R}        Activate .venv in this shell"
            Write-Host "  ${BO}${A}resume cd${R}              cd into the project root"
            Write-Host ""
            Write-Host "  ${M}Aliases: ${BO}rb${R}${M}, ${BO}jobkit${R}${M} (both call resume)${R}"
            Write-Host ""
            Write-Host "${BO}${B}✦ ──────────────────────────────────────────────────────────── ✦${R}"
            Write-Host ""
        }

        # ── default: launch menu (no args) or pass unknown subcommand through
        default {
            Push-Location $script:RB_DIR
            try {
                if ($cmd) {
                    & $script:VENV_PY scripts\cli.py $cmd @rest
                } else {
                    & $script:VENV_PY scripts\cli.py
                }
            } finally { Pop-Location }
        }
    }
}

Set-Alias -Name rb      -Value resume -Scope Global -Force
Set-Alias -Name jobkit  -Value resume -Scope Global -Force
