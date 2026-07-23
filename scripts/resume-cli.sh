# resume-builder shell shortcuts.
# Source this from ~/.zshrc or ~/.bashrc (one line:
# `source /path/to/resume-builder/scripts/resume-cli.sh`) to get a `resume`
# command usable from anywhere in the terminal.
#
# Portable by design: resolves its own location at source time instead of a
# hardcoded path, so the same line works on any machine's clone of this repo.
# Works under both zsh and bash since the two shells expose the sourced
# file's path differently.

if [ -n "$ZSH_VERSION" ]; then
  _RESUME_BUILDER_DIR="$(cd "$(dirname "${(%):-%x}")/.." && pwd)"
else
  _RESUME_BUILDER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

resume() {
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
