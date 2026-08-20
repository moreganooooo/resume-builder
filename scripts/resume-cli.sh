# resume-builder shell shortcuts.
# Source this from ~/.zshrc or ~/.bashrc (one line:
# `source /path/to/resume-builder/scripts/resume-cli.sh`) to get a `resume`
# command usable from anywhere in the terminal.
#
# Portable by design: resolves its own location at source time instead of a
# hardcoded path, so the same line works on any machine's clone of this repo.
# Works under both zsh and bash since the two shells expose the sourced
# file's path differently.

# Check if script is being run directly instead of sourced
_RESUME_DIRECT_RUN=0
if [ -n "$ZSH_VERSION" ]; then
  if [[ "$ZSH_EVAL_CONTEXT" == "toplevel"* ]]; then
    _RESUME_DIRECT_RUN=1
  fi
elif [ -n "$BASH_VERSION" ]; then
  if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    _RESUME_DIRECT_RUN=1
  fi
fi

# TrueColor / ANSI hex mappings matching theme.py tokens
_RB_BRAND="\033[38;2;139;117;255m"      # #8B75FF (Charmtone Hazy / Lavender)
_RB_ACCENT="\033[38;2;255;96;255m"     # #FF60FF (Charmtone Dolly / Brand Accent)
_RB_SUCCESS="\033[38;2;18;199;143m"    # #12C78F (Charmtone Guac / Green)
_RB_INFO="\033[38;2;0;164;255m"        # #00A4FF (Charmtone Malibu / Blue)
_RB_WARNING="\033[38;2;245;239;52m"    # #F5EF34 (Charmtone Mustard / Yellow)
_RB_ERROR="\033[38;2;255;123;153m"     # #FF7B99 (Charmtone Coral / Red)
_RB_MUTED="\033[38;2;163;163;163m"     # #A3A3A3 (Muted Gray)
_RB_BOLD="\033[1m"
_RB_RESET="\033[0m"

if [ "$_RESUME_DIRECT_RUN" -eq 1 ]; then
  local_path="${BASH_SOURCE[0]:-$0}"
  abs_path="$(cd "$(dirname "$local_path")" && pwd)/$(basename "$local_path")"
  printf "\n${_RB_BOLD}${_RB_BRAND}✦ ────────────────────────────────────────────────────────────── ✦${_RB_RESET}\n"
  printf "  ${_RB_BOLD}${_RB_BRAND}✦  RESUME-BUILDER SHELL SHORTCUTS  ✦${_RB_RESET}\n"
  printf "${_RB_BOLD}${_RB_BRAND}✦ ────────────────────────────────────────────────────────────── ✦${_RB_RESET}\n"
  printf "  ${_RB_WARNING}⚠  You executed this script directly instead of sourcing it.${_RB_RESET}\n"
  printf "  ${_RB_MUTED}To use the${_RB_RESET} ${_RB_BOLD}${_RB_ACCENT}resume${_RB_RESET} ${_RB_MUTED}command from anywhere in your shell, source it:${_RB_RESET}\n\n"
  printf "  ${_RB_BOLD}${_RB_SUCCESS}source %s${_RB_RESET}\n\n" "$abs_path"
  printf "  ${_RB_MUTED}Or add it to your profile (~/.zshrc or ~/.bashrc) permanently:${_RB_RESET}\n"
  printf "  ${_RB_INFO}echo \"source %s\" >> ~/.zshrc${_RB_RESET}\n" "$abs_path"
  printf "${_RB_BOLD}${_RB_BRAND}✦ ────────────────────────────────────────────────────────────── ✦${_RB_RESET}\n\n"
  exit 1
fi

if [ -n "$ZSH_VERSION" ]; then
  _RESUME_BUILDER_DIR="$(cd "$(dirname "${(%):-%x}")/.." && pwd)"
else
  _RESUME_BUILDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

# When multiple people share one login (no per-user RESUME_PROFILE default
# to inherit), ask once per terminal session which profile this session is
# for, then export it so every `resume` call after that just works. Only
# fires when RESUME_PROFILE is unset and more than one profiles/<name>/
# directory exists -- a single-profile checkout never prompts, and
# profile_paths.py's own "morgan" default still applies if this is skipped.
_resume_ensure_profile() {
  [ -n "$RESUME_PROFILE" ] && return
  local profiles_dir="$_RESUME_BUILDER_DIR/profiles"
  [ -d "$profiles_dir" ] || return
  local names
  names="$(cd "$profiles_dir" && ls -d */ 2>/dev/null | sed 's#/$##')"
  local count
  count="$(printf '%s\n' "$names" | grep -c .)"
  [ "$count" -gt 1 ] || return

  local default
  default="$(printf '%s\n' "$names" | head -1)"
  local choice
  if command -v gum >/dev/null 2>&1; then
    choice="$(printf '%s\n' "$names" | gum choose --header "✦ Which profile for this terminal session?")"
  else
    printf "\n${_RB_BOLD}${_RB_BRAND}✦ ────────────────────────────────────────────────────────────── ✦${_RB_RESET}\n"
    printf "  ${_RB_BOLD}${_RB_BRAND}◈ RESUME-BUILDER PROFILE SELECTOR${_RB_RESET}\n"
    printf "${_RB_BOLD}${_RB_BRAND}✦ ────────────────────────────────────────────────────────────── ✦${_RB_RESET}\n"
    printf "  ${_RB_MUTED}Multiple profiles found in${_RB_RESET} ${_RB_INFO}profiles/${_RB_RESET}:\n"
    while IFS= read -r name; do
      if [ "$name" = "$default" ]; then
        printf "    ${_RB_ACCENT}●${_RB_RESET} ${_RB_BOLD}%s${_RB_RESET} ${_RB_MUTED}(default)${_RB_RESET}\n" "$name"
      else
        printf "    ${_RB_MUTED}○${_RB_RESET} %s\n" "$name"
      fi
    done <<< "$names"
    printf "\n  ${_RB_BOLD}Which profile for this session?${_RB_RESET} [${_RB_ACCENT}%s${_RB_RESET}]: " "$default"
    read -r choice
  fi
  choice="${choice:-$default}"
  export RESUME_PROFILE="$choice"
  printf "  ${_RB_SUCCESS}✓ Active profile:${_RB_RESET} ${_RB_BOLD}${_RB_ACCENT}%s${_RB_RESET} ${_RB_MUTED}(session only)${_RB_RESET}\n\n" "$RESUME_PROFILE"
}

resume() {
  type _resume_ensure_profile >/dev/null 2>&1 && _resume_ensure_profile
  local cmd="$1"
  local all_args=("$@")
  if [ $# -gt 0 ]; then shift; fi

  case "$cmd" in
    activate)
      cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate
      local active_prof="${RESUME_PROFILE:-default}"
      printf "\n${_RB_BOLD}${_RB_BRAND}✦ ────────────────────────────────────────────────────────────── ✦${_RB_RESET}\n"
      printf "  ${_RB_BOLD}${_RB_SUCCESS}✓ Python Virtual Environment Activated${_RB_RESET} ${_RB_MUTED}(.venv)${_RB_RESET}\n"
      printf "  ${_RB_BOLD}◰ Working Directory:${_RB_RESET} ${_RB_INFO}%s${_RB_RESET}\n" "$_RESUME_BUILDER_DIR"
      printf "  ${_RB_BOLD}◉ Active Profile:${_RB_RESET}    ${_RB_ACCENT}%s${_RB_RESET}\n" "$active_prof"
      printf "${_RB_BOLD}${_RB_BRAND}✦ ────────────────────────────────────────────────────────────── ✦${_RB_RESET}\n\n"
      ;;
    cd)
      cd "$_RESUME_BUILDER_DIR"
      printf "  ${_RB_INFO}◰ %s${_RB_RESET}\n" "$_RESUME_BUILDER_DIR"
      ;;
    run)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate
        if [ $# -gt 0 ] && [ "${1#-}" = "$1" ]; then
          python scripts/cli.py tailor "$@"
        else
          python scripts/cli.py run "$@"
        fi )
      ;;
    coverletter)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py coverletter "$@" )
      ;;
    evaluate)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py evaluate "$@" )
      ;;
    scan)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py scan "$@" )
      ;;
    liveness)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py liveness "$@" )
      ;;
    polish)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py polish "$@" )
      ;;
    dashboard)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py dashboard "$@" )
      ;;
    bootstrap)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py bootstrap "$@" )
      ;;
    sample)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py sample "$@" )
      ;;
    doctor)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py doctor "$@" )
      ;;
    test)
      # unittest's own pass/fail reporting goes to stderr; the app code under
      # test prints a lot of its own operational logging (Step 1/2/3..., batch
      # summaries, etc.) to stdout. Discarding stdout here keeps the actual
      # test results clean and readable without touching any test code.
      #   resume test        -- one dot per passing test, full detail only on failure
      #   resume test -v     -- one line per test (name + ok/FAIL), still no app noise
      #   resume test -vv    -- everything, including the app's own logging
      case "$1" in
        -vv)
          ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python -m unittest discover -s tests -v )
          ;;
        -v|verbose)
          ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python -m unittest discover -s tests -v 1>/dev/null )
          ;;
        *)
          ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python -m unittest discover -s tests 1>/dev/null )
          ;;
      esac
      ;;
    help)
      # Delegates to `python scripts/cli.py help` (cli_art.display_help(),
      # sourced from cli_art.HELP_ENTRIES) instead of a second hardcoded
      # copy of this text, so there's exactly one place to update it --
      # this is also what the interactive menu's own Help entry renders.
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py help )
      ;;
    *)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/cli.py "${all_args[@]}" )
      ;;
  esac
}

# CLI Aliases
alias rb="resume"
alias jobkit="resume"

