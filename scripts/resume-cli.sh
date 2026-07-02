# resume-builder shell shortcuts.
# Source this from ~/.zshrc (one line: `source /path/to/resume-builder/scripts/resume-cli.sh`)
# to get a `resume` command usable from anywhere in the terminal.
#
# Portable by design: resolves its own location at source time instead of a
# hardcoded path, so the same line works on any machine's clone of this repo.

_RESUME_BUILDER_DIR="$(cd "$(dirname "${(%):-%x}")/.." && pwd)"

resume() {
  local cmd="$1"
  if [ $# -gt 0 ]; then shift; fi

  case "$cmd" in
    activate)
      cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate
      ;;
    cd)
      cd "$_RESUME_BUILDER_DIR"
      ;;
    run)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python scripts/orchestrator.py "$@" )
      ;;
    test)
      ( cd "$_RESUME_BUILDER_DIR" && source .venv/bin/activate && python -m unittest discover -s tests -v )
      ;;
    *)
      echo "resume-builder shortcuts:"
      echo "  resume activate        cd into the project and activate the venv (stays active in this shell)"
      echo "  resume cd              just cd into the project"
      echo "  resume run             run orchestrator.py in batch mode (processes every pending JD)"
      echo "  resume run jds/x.txt   run orchestrator.py in single-file mode"
      echo "  resume test            run the full test suite"
      ;;
  esac
}
