"""build_recruiter_resume.py -- the `recruiter` command: builds ONE
role-agnostic resume for a staffing/employment agency, where there is no
specific position to tailor against.

An agency interview is a different problem from a job application. The
recruiter is not screening for one opening, they are deciding which of
their openings to put the candidate forward for -- so the resume has to
read strongly across the candidate's whole target range rather than
narrowing onto a single posting's keywords.

Two things this deliberately is NOT:

1. **Not `resume sample`.** That builds against a fixed fake JD
   (fixtures/sample_jd.txt) as a QA smoke test. A fake employer's
   keywords would steer the bullets toward an opening that does not
   exist, and the output would name a company the candidate is not
   meeting. Here the brief is synthesized from the candidate's OWN
   profile.yml (target_roles, archetypes, background_context) plus cv.md
   -- it describes the candidate's range, not an employer's ask.

2. **Not a build with company research.** It passes
   skip_company_research=True explicitly rather than letting research
   come back empty on its own. `research_company()`'s Tier 3 always falls
   back to the JD's own text, so a candidate-derived brief would be
   summarized into confident "company research" about the candidate
   themselves, and the resume's Why section would be addressed to a
   company that does not exist. SECTION_WHY/WHY_TEXT are optional in
   TemplateSchema, so with research skipped the section is simply
   omitted and validate_resume's Why checks stay dormant.

No cover letter is built, for the same reason there is no Why section:
a cover letter is addressed to an employer about a role, and here there
is neither.

The brief is written under output/<profile>/recruiter/, deliberately
OUTSIDE jds/<profile>/ -- the same reasoning that keeps
fixtures/sample_jd.txt out of there, so get_pending_jds() can never pick
it up during a batch `resume run` and treat it as a real application.
"""

import datetime
import logging
import os
import sys

import cli_art
import jd_manager
import orchestrator
import profile_paths
import theme

BRIEF_DIRNAME = "recruiter"
BRIEF_FILENAME = "recruiter_brief.txt"


def _as_list(value) -> list:
    """profile.yml fields are hand-edited, so a key that should hold a
    list routinely holds a bare string, None, or a list containing the
    empty-string placeholder the bootstrap scaffolding writes."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def build_target_brief(profile_data: dict, cv_text: str = "") -> str:
    """Synthesizes the role-agnostic brief the builder tailors against.

    Pure and side-effect free on purpose: this is the part worth testing
    directly, since everything downstream of it is a real Gemini build.

    Reads only what describes the candidate's RANGE -- target_roles
    (primary and secondary), archetypes, and background_context. It
    deliberately does not invent an employer, a location, or a
    requirements list: every heading here is about what the candidate
    brings, so nothing in the brief can be mistaken for a posting's ask.
    cv_text is appended as supporting evidence when available.
    """
    profile_data = profile_data or {}
    candidate = profile_data.get("candidate") or {}
    name = str(candidate.get("full_name") or "").strip() or "the candidate"

    targets = profile_data.get("target_roles") or {}
    primary = _as_list(targets.get("primary"))
    secondary = _as_list(targets.get("secondary"))

    lines = [
        "=== RECRUITER / STAFFING AGENCY BRIEF ===",
        "",
        "This is NOT a job posting. There is no specific opening, no employer,",
        f"and no company to address. {name} is meeting a staffing agency, which",
        "will decide which of ITS openings to put them forward for. Write the",
        "resume to read strongly across the whole range of roles below rather",
        "than narrowing onto any single one of them. Do not name or address a",
        "company anywhere in the output.",
        "",
    ]

    if primary:
        lines += ["ROLES TO PRESENT FOR (primary):"]
        lines += [f"  - {r}" for r in primary]
        lines.append("")
    if secondary:
        lines += [
            "ALSO PLACEABLE INTO (secondary -- the resume should not exclude these):"
        ]
        lines += [f"  - {r}" for r in secondary]
        lines.append("")

    archetypes = profile_data.get("archetypes")
    archetype_lines = []
    if isinstance(archetypes, list):
        for entry in archetypes:
            if not isinstance(entry, dict):
                continue
            entry_name = str(entry.get("name") or "").strip()
            if not entry_name:
                continue
            level = str(entry.get("level") or "").strip()
            notes = str(entry.get("notes") or "").strip()
            header = f"  - {entry_name}" + (f" ({level})" if level else "")
            archetype_lines.append(header)
            if notes:
                archetype_lines.append(f"      {notes}")
    if archetype_lines:
        lines += ["WHAT THEY BRING TO EACH:"] + archetype_lines + [""]

    background = str(profile_data.get("background_context") or "").strip()
    if background:
        lines += ["BACKGROUND:", f"  {background}", ""]

    cv_text = (cv_text or "").strip()
    if cv_text:
        lines += ["=== CANDIDATE CV (supporting evidence) ===", cv_text, ""]

    return "\n".join(lines).rstrip() + "\n"


def _load_profile_inputs() -> tuple[dict, str]:
    """Returns (profile_data, cv_text). A missing or unreadable cv.md is
    not fatal -- the brief's own sections carry the range, and the CV is
    supporting evidence; a missing profile.yml IS fatal and raises, since
    without it there is nothing to describe the candidate with."""
    profile_data = profile_paths.profile_yaml() or {}
    cv_text = ""
    try:
        cv_path = os.path.join(profile_paths.kb_dir(), "cv.md")
        if os.path.exists(cv_path):
            with open(cv_path, "r", encoding="utf-8") as f:
                cv_text = f.read()
    except Exception:
        cv_text = ""
    return profile_data, cv_text


def write_brief(brief_text: str) -> str:
    """Writes the brief under output/<profile>/recruiter/ and returns its
    path. Outside jds/<profile>/ deliberately -- see the module docstring."""
    brief_dir = os.path.join(profile_paths.output_dir(), BRIEF_DIRNAME)
    os.makedirs(brief_dir, exist_ok=True)
    brief_path = os.path.join(brief_dir, BRIEF_FILENAME)
    with open(brief_path, "w", encoding="utf-8") as f:
        f.write(brief_text)
    return brief_path


def _resolve_interactive(interactive: bool | None) -> bool:
    """Step 5.5's approval gate prompts through the Go/huh binary, which
    needs a real TTY: it aborts the whole build with "error opening TTY"
    when there isn't one. Hardcoding interactive=True therefore made this
    command work from a terminal and die at the last step everywhere else
    (a piped run, CI, a backgrounded shell) -- after paying for the entire
    pipeline, which is the worst possible place to fail. Resolved from the
    actual stream by default; an explicit True/False still wins, so the
    menu can demand the prompts and a test can force either branch."""
    if interactive is not None:
        return interactive
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except Exception:
        return False


def build_recruiter_resume(interactive: bool = None, fresh: bool = True) -> dict:
    """Builds one role-agnostic resume. Returns {"resume": {...}} -- the
    build_tailored_resume() return dict ({} on failure, or the real data
    plus an _output_paths key on success). No cover letter: there is no
    employer to address one to.

    fresh=False keeps any existing checkpoint instead of clearing it, so an
    interrupted run resumes rather than re-paying for every bullet audit and
    builder call it already made. Default stays True (a full rebuild) because
    the usual reason to re-run this is that the profile's targets changed,
    and a stale checkpoint would silently reuse bullets mined against the
    previous range."""
    logger = logging.getLogger("resume_pipeline")
    log_path = None
    import db as _db

    if not logger.handlers and not _db._is_unisolated_test_write():
        try:
            log_root = profile_paths.logs_dir()
            os.makedirs(log_root, exist_ok=True)
            timestamp = datetime.datetime.now().isoformat().replace(":", "-")
            log_path = os.path.join(log_root, f"pipeline_run_{timestamp}.log")
            handler = logging.FileHandler(log_path, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(levelname)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.info("Recruiter resume build started")
            cli_art.console.export_text(clear=True)  # discard stale transcript
        except Exception as e:
            cli_art.detail(f"Could not initialize logging: {e}", level=cli_art.NORMAL)
            log_path = None

    if log_path is None:
        for h in logger.handlers:
            if isinstance(h, logging.FileHandler):
                log_path = h.baseFilename
                break

    try:
        profile_data, cv_text = _load_profile_inputs()
    except Exception as e:
        cli_art.friendly_error(e, "reading this profile's knowledge base")
        return {"resume": {}}

    brief_text = build_target_brief(profile_data, cv_text)

    targets = (profile_data.get("target_roles") or {}) if profile_data else {}
    if not _as_list(targets.get("primary")) and not _as_list(targets.get("secondary")):
        # Without target roles the brief has no range to write across, and
        # the result would be a generic resume dressed up as a deliberate
        # one. Better to say so than to spend a full build finding out.
        cli_art.console.print(
            f"  {theme.colorize_icon('error')} No target_roles in this profile's "
            f"profile.yml -- a recruiter resume needs the range of roles to present for.",
            soft_wrap=True,
        )
        return {"resume": {}}

    brief_path = write_brief(brief_text)
    cli_art.print_literal(f"  Target brief written to: {brief_path}")

    job_key = jd_manager.compute_job_key(brief_path)
    if fresh:
        jd_manager.delete_checkpoint(job_key)
    else:
        cli_art.print_literal("  Resuming from the existing checkpoint.")

    engine = orchestrator.ResumeEngine()

    cli_art.console.rule("Building Recruiter Resume", style="dim")
    resume_result = engine.build_tailored_resume(
        jd_path=brief_path,
        master_resume={},
        # The recruiter resume is the role-agnostic one, so it claims the
        # plain "<Name>_Resume" name; every role-specific build carries its
        # title/company (or, failing that, its JD's basename -- see
        # _build_output_stem) and so can never collide with it.
        output_filename=f"{profile_paths.full_name().replace(' ', '')}_Resume.json",
        job_key=job_key,
        interactive=_resolve_interactive(interactive),
        skip_company_research=True,
    )

    if logger.handlers:
        logger.info(
            f"Recruiter resume build complete: "
            f"{'ok' if resume_result else 'failed'}"
        )
    if log_path:
        orchestrator.append_console_transcript(log_path)
    return {"resume": resume_result}


def main():
    result = build_recruiter_resume(fresh="--resume" not in sys.argv)
    if result["resume"]:
        cli_art.console.print(
            f"  {theme.colorize_icon('success')} Recruiter resume: "
            f"{result['resume']['_output_paths']['pdf']}",
            soft_wrap=True,
        )
    else:
        cli_art.console.print(
            f"  {theme.colorize_icon('error')} Recruiter resume build failed.",
            soft_wrap=True,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
