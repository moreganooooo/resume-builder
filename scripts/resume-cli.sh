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

if [ "$_RESUME_DIRECT_RUN" -eq 1 ]; then
  local_path="${BASH_SOURCE[0]:-$0}"
  abs_path="$(cd "$(dirname "$local_path")" && pwd)/$(basename "$local_path")"
  echo "--------------------------------------------------------"
  echo "  ✦  RESUME-BUILDER SHELL SHORTCUTS  ✦"
  echo "--------------------------------------------------------"
  echo "You executed this script directly instead of sourcing it."
  echo "To use the 'resume' command from anywhere in your shell,"
  echo "please SOURCE this file instead of running it."
  echo ""
  echo "Run this command to activate it for your current session:"
  echo "  source $abs_path"
  echo ""
  echo "Or add it to your profile (~/.zshrc or ~/.bashrc) permanently:"
  echo "  echo \"source $abs_path\" >> ~/.zshrc"
  echo "--------------------------------------------------------"
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
    choice="$(printf '%s\n' "$names" | gum choose --header "Which profile for this terminal session?")"
  else
    echo "Multiple resume-builder profiles found:"
    while IFS= read -r name; do
      printf '  %s\n' "$name"
    done <<< "$names"
    printf "Which profile for this terminal session? [%s]: " "$default"
    read -r choice
  fi
  choice="${choice:-$default}"
  export RESUME_PROFILE="$choice"
  echo "Using profile: $RESUME_PROFILE (set for this terminal session only)"
}

resume() {
  type _resume_ensure_profile >/dev/null 2>&1 && _resume_ensure_profile
  local cmd="$1"
  local all_args=("$@")
  if [ $# -gt 0 ]; then shift; fi

  case "$cmd" in
    activate)
      cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate
      ;;
    cd)
      cd "$_RESUME_BUILDER_DIR"
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
