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
    *)
      echo "resume-builder shortcuts:"
      echo "  resume activate        cd into the project and activate the venv (stays active in this shell)"
      echo "  resume cd              just cd into the project"
      echo "  resume run             tailor+render every pending JD in jds/ (batch mode)"
      echo "  resume run jds/x.txt   tailor+render one specific JD file"
      echo "  resume coverletter jds/x.txt   generate + render a cover letter for one JD"
      echo "  resume evaluate jds/x.txt   score a JD's fit (go/no-go) without building a resume"
      echo "  resume scan             pull new postings from all configured sources into jds/"
      echo "  resume scan --source jobright   pull from just one source (jobright, linkedin)"
      echo "  resume liveness         check every pending JD's posting URL, move expired ones out"
      echo "  resume test            run the full test suite (compact: dots + summary)"
      echo "  resume test -v         same, but lists every test by name"
      echo "  resume test -vv        same, but shows the app's own logging too"
      ;;
  esac
}
