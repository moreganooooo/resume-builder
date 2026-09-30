"""Reads the holistic critique back off an already-generated resume.

Every tailored resume is scored by `critique_resume.md` during its build --
fit, skills relevance, top-third, recruiter takeaway, ATS risks -- and those
scores scrolled past in the build log exactly once. They are persisted on the
document itself (`_critique`, alongside `_recommendation_actions` and
`_build_meta`), so this module is a READER: it opens no models and spends no
quota.

One thing it is careful to say out loud: the critique runs BEFORE Step 5.5
applies the critique's own recommendations, because the critique is what
produces them. So on a resume that was then edited, the stored scores are the
scores of the draft that was critiqued, not of the file on disk. Presenting
them as "final" would be a quiet lie, and a fit score the user cannot date is
worse than no fit score. `report_is_final()` is the distinction, and the
renderer leads with it.
"""

import datetime
import glob
import json
import os
import re

import cli_art
import profile_paths
import theme

RESUME_SUFFIX = "_Resume.json"

# The four headline numbers critique_resume.md returns, in the order the
# build log prints them -- a reader who saw the build should meet them in the
# same order here.
SCORE_FIELDS = [
    ("summary_alignment_score", "Summary alignment"),
    ("skills_relevance_score", "Skills relevance"),
    ("top_third_score", "Top third of page 1"),
    ("overall_fit_score", "Overall fit"),
]

# Critique list fields that describe something to IMPROVE, paired with the
# heading each is shown under. Kept separate from the strengths below because
# a viewer that mixes them reads as a wall of text rather than a work list.
OPPORTUNITY_FIELDS = [
    ("hard_failures_triggered", "Rubric hard failures"),
    ("flags", "Flags"),
    ("flat_sections", "Flat sections"),
    ("competing_narratives", "Competing narratives"),
    ("unsupported_positioning", "Unsupported positioning"),
    ("unsupported_skills", "Unsupported skills"),
    ("ungrouped_skills", "Ungrouped skills"),
    ("platform_parsing_risks", "Platform parsing risks"),
]

# Scores are 0-100. The bands are for COLOR only -- nothing branches on them.
STRONG_SCORE = 85
WEAK_SCORE = 70


def sample_jd_path() -> str:
    """The fixture `resume sample` builds against, profile-specific if one
    exists. Resolved through build_sample so the two can never disagree about
    which file that is."""
    try:
        import build_sample

        return build_sample._resolve_sample_jd_path()
    except Exception:
        return ""


def _sample_stem() -> str:
    """The output stem a sample build produces, derived rather than
    hardcoded: the fixture's own company and role decide it (currently
    "Content Strategist" @ "Abnormal AI"), and a profile with its own
    sample_jd.txt gets a different one."""
    try:
        import orchestrator

        path = sample_jd_path()
        return orchestrator._build_output_stem(path) if path else ""
    except Exception:
        return ""


def is_sample_resume(path: str, resume_data: dict | None = None) -> bool:
    """True for a document built from the sample-JD fixture.

    A sample resume is a QA smoke test re-run indefinitely against a fixed
    fixture -- its fit scores say something about the pipeline, not about a
    real application -- so it does not belong in a list of documents the user
    might send. Two tests, because they cover different eras: `_build_meta`
    names the JD outright, and for documents built before that key existed
    the stem is compared against what a sample build would produce.

    `resume sample` writes to output/<profile>/samples/ nowadays, so most
    samples never reach this directory at all; the ones that do are older
    builds, which is exactly why the stem fallback exists.
    """
    meta = (resume_data or {}).get("_build_meta") or {}
    jd = meta.get("jd_path") or ""
    if jd:
        # An explicit answer beats a guess: if the build recorded its JD,
        # believe it, and do NOT fall through to the stem heuristic.
        return os.path.basename(jd) == os.path.basename(sample_jd_path() or "?")
    stem = _sample_stem()
    return bool(stem) and os.path.basename(path).startswith(stem + "_")


def resume_json_dir() -> str:
    """Resolved per call, never at import.

    `polish.OUTPUT_JSON_DIR` is a module-level constant, which is the exact
    shape that made `JDTracker`'s `TRACKER_CSV` survive a profile switch and
    every test redirect. A viewer that reads another profile's documents is a
    privacy bug, not just a wrong list.
    """
    return profile_paths.output_resume_dir("json")


def resume_json_paths(include_samples: bool = False) -> list:
    """Every generated resume JSON for the active profile, newest first.

    Sample-fixture builds are excluded by default -- see is_sample_resume().
    """
    paths = [
        p
        for p in glob.glob(os.path.join(resume_json_dir(), f"*{RESUME_SUFFIX}"))
        if not p.endswith(".bak")
    ]
    if not include_samples:
        paths = [p for p in paths if not is_sample_resume(p, load_resume(p))]
    return sorted(paths, key=os.path.getmtime, reverse=True)


def describe_stem(path: str) -> str:
    """A readable role/company from the filename.

    The stem is `Name_Role_Company_Resume.json` with the words run together,
    so this splits on the underscores and re-spaces the CamelCase. Best
    effort by design -- `_build_meta.jd_path` is the authoritative answer and
    the renderer prefers it; this only has to beat showing a bare filename
    for documents built before that key existed.
    """
    stem = os.path.basename(path)
    if stem.endswith(RESUME_SUFFIX):
        stem = stem[: -len(RESUME_SUFFIX)]
    parts = stem.split("_")[1:] or [stem]
    return " / ".join(re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", p).strip() for p in parts)


def load_resume(path: str) -> dict:
    """The document, or {} if it cannot be read. Never raises: a viewer that
    dies on one unreadable file takes the whole list down with it."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def edits_after_critique(resume_data: dict) -> list:
    """Recommendations APPLIED after the critique was scored.

    Only `applied` counts. A skipped or deferred recommendation changed
    nothing, so it cannot have moved a score -- treating those as edits would
    mark almost every resume stale and make the distinction useless.
    """
    actions = resume_data.get("_recommendation_actions") or {}
    return list(actions.get("applied") or [])


def report_is_final(resume_data: dict) -> bool:
    """True when the stored scores describe the file as it now stands.

    A resume nothing was applied to was never changed after being scored, so
    its critique IS final. One applied edit and it is not.
    """
    critique = resume_data.get("_critique") or {}
    if not critique:
        return False
    # A re-score RECORDS that it ran against the current file, which beats
    # inferring vintage from the build's edit history -- those edits are
    # still listed, and still predate the new scores.
    if critique.get("_scored_at_stage") == RESCORED_STAGE:
        return True
    return not edits_after_critique(resume_data)


# How a critique recommendation ended up, and the mark each gets. Order is
# the order they are shown: what landed, then what still needs a person, then
# what nothing has been tried on.
OUTCOME_APPLIED = "applied"
OUTCOME_NEEDS_INPUT = "needs_input"
OUTCOME_DISCARDED = "discarded"
OUTCOME_NOT_AN_EDIT = "not_an_edit"
OUTCOME_UNATTEMPTED = "unattempted"

OUTCOME_ORDER = [
    OUTCOME_APPLIED,
    OUTCOME_NEEDS_INPUT,
    OUTCOME_DISCARDED,
    OUTCOME_NOT_AN_EDIT,
    OUTCOME_UNATTEMPTED,
]

OUTCOME_LABELS = {
    OUTCOME_APPLIED: "already in the resume",
    OUTCOME_NEEDS_INPUT: "needs your input",
    OUTCOME_DISCARDED: "tried, broke a validator rule",
    OUTCOME_NOT_AN_EDIT: "model called it not a document edit",
    OUTCOME_UNATTEMPTED: "not attempted",
}

OUTCOME_MARKS = {
    OUTCOME_APPLIED: "✓",
    OUTCOME_NEEDS_INPUT: "?",
    OUTCOME_DISCARDED: "✗",
    OUTCOME_NOT_AN_EDIT: "·",
    OUTCOME_UNATTEMPTED: "○",
}


def _strip_skip_annotation(text: str) -> str:
    """`skipped` entries may carry an appended reason -- "<rec> (attempted 3x,
    discarded: ...)" -- so the recommendation text has to be recovered before
    it can be matched against the critique's own list."""
    return re.sub(r"\s*\(attempted[^)]*\)\s*$", "", str(text)).strip()


def recommendation_outcomes(resume_data: dict) -> list:
    """Every critique recommendation paired with what became of it.

    Returns [(outcome, text)], one row per recommendation, ordered by
    OUTCOME_ORDER.

    Recommendations the apply loop filed as "not a resume-content edit" are
    included deliberately. That verdict is the model's, made in one pass, and
    it is wrong often enough to matter: plenty of them ARE document edits the
    model could not resolve or chose to pass on. Hiding them meant the one
    reader who can actually judge -- the candidate -- never saw them. They are
    marked rather than dropped, so a genuine "go network" suggestion still
    reads as noise at a glance without being censored.
    """
    critique = resume_data.get("_critique") or {}
    actions = resume_data.get("_recommendation_actions") or {}

    applied = {str(r).strip() for r in (actions.get("applied") or [])}
    needs_input = {str(r).strip() for r in (actions.get("needs_polish") or [])}
    discarded, not_an_edit = set(), set()
    for raw in actions.get("skipped") or []:
        text = _strip_skip_annotation(raw)
        if "discarded" in str(raw):
            discarded.add(text)
        else:
            not_an_edit.add(text)

    def classify(text: str) -> str:
        if text in applied:
            return OUTCOME_APPLIED
        if text in needs_input:
            return OUTCOME_NEEDS_INPUT
        if text in discarded:
            return OUTCOME_DISCARDED
        if text in not_an_edit:
            return OUTCOME_NOT_AN_EDIT
        return OUTCOME_UNATTEMPTED

    rows = [
        (classify(str(rec).strip()), str(rec).strip())
        for rec in (critique.get("recommendations") or [])
        if str(rec).strip()
    ]
    # An action recorded against a recommendation the critique no longer
    # lists (a re-score replaced the list) would otherwise vanish silently.
    known = {text for _, text in rows}
    for bucket, outcome in (
        (applied, OUTCOME_APPLIED),
        (needs_input, OUTCOME_NEEDS_INPUT),
        (discarded, OUTCOME_DISCARDED),
        (not_an_edit, OUTCOME_NOT_AN_EDIT),
    ):
        rows.extend((outcome, text) for text in sorted(bucket) if text not in known)

    return sorted(rows, key=lambda row: OUTCOME_ORDER.index(row[0]))


def critique_findings(resume_data: dict) -> list:
    """The critique's own quality findings, as (heading, [items]).

    Distinct from recommendations: these describe what is weak, where a
    recommendation names something to do about it.
    """
    critique = resume_data.get("_critique") or {}
    sections = []
    for key, heading in OPPORTUNITY_FIELDS:
        items = [str(i) for i in (critique.get(key) or []) if str(i).strip()]
        if items:
            sections.append((heading, items))
    return sections


def build_report(path: str) -> dict:
    """Everything the renderer needs, as plain data.

    Separated from rendering so the interesting logic -- vintage, which
    findings count as opportunities -- is testable without a terminal.
    """
    resume_data = load_resume(path)
    critique = resume_data.get("_critique") or {}
    meta = resume_data.get("_build_meta") or {}
    return {
        "path": path,
        "title": describe_stem(path),
        "jd_path": meta.get("jd_path") or "",
        "built_at": meta.get("built_at") or "",
        "has_critique": bool(critique),
        "is_final": report_is_final(resume_data),
        "edits_after": edits_after_critique(resume_data),
        "scores": [
            (label, critique.get(key))
            for key, label in SCORE_FIELDS
            if critique.get(key) is not None
        ],
        "primary_identity": critique.get("primary_identity") or "",
        "secondary_identity": critique.get("secondary_identity") or "",
        "tertiary_identity": critique.get("tertiary_identity") or "",
        "recruiter_takeaway": critique.get("recruiter_takeaway") or "",
        "strongest_alignment": critique.get("strongest_alignment") or "",
        "weakest_alignment": critique.get("weakest_alignment") or "",
        "weakest_ats_platform": critique.get("weakest_ats_platform") or "",
        "archetype_mismatch": bool(critique.get("archetype_mismatch")),
        "distinctive_moments": [
            str(m) for m in (critique.get("distinctive_moments") or []) if str(m)
        ],
        "findings": critique_findings(resume_data),
        "recommendations": recommendation_outcomes(resume_data),
    }


def _score_color(score) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return theme.MUTED
    if value >= STRONG_SCORE:
        return theme.SUCCESS
    if value < WEAK_SCORE:
        return theme.ERROR
    return theme.WARNING


def _outcome_color(outcome: str) -> str:
    if outcome == OUTCOME_APPLIED:
        return theme.SUCCESS
    if outcome == OUTCOME_DISCARDED:
        return theme.ERROR
    if outcome == OUTCOME_NOT_AN_EDIT:
        return theme.MUTED
    return theme.WARNING


def render_report(report: dict) -> None:
    """Prints one resume's report. Returns nothing; pure output."""
    cli_art.console.rule(
        f"[bold]{cli_art._escape_markup(report['title'])}[/bold]",
        style="dim",
        align="left",
    )
    if report["built_at"]:
        cli_art.print_literal(f"  Built     : {report['built_at']}")
    if report["jd_path"]:
        cli_art.print_literal(
            f"  From JD   : {cli_art._escape_markup(os.path.basename(report['jd_path']))}"
        )
    cli_art.print_literal(f"  File      : {cli_art._escape_markup(report['path'])}")
    cli_art.print_literal()

    if not report["has_critique"]:
        # Said plainly, because the likeliest cause is age rather than
        # breakage: builds before 2026-09-30 dropped `_critique` whenever a
        # recommendation was applied.
        cli_art.cli_info(
            "No stored critique on this resume. Resumes built before "
            "2026-09-30 lost their critique whenever a recommendation was "
            "applied; rebuild or re-polish this one to get scores."
        )
        return

    # The vintage comes FIRST. A reader who skims only the numbers should
    # have already been told what they are numbers about.
    if report["is_final"]:
        cli_art.console.print(
            f"  {theme.colorize_icon('success')} These scores are final -- "
            f"nothing was changed after the resume was scored.",
            soft_wrap=True,
        )
    else:
        count = len(report["edits_after"])
        cli_art.console.print(
            f"  {theme.colorize_icon('warning')} Scored BEFORE {count} "
            f"recommendation(s) were applied -- the file on disk is newer than "
            f"these numbers.",
            soft_wrap=True,
        )
    cli_art.print_literal()

    cli_art.print_literal("  Fit scores")
    for label, score in report["scores"]:
        cli_art.console.print(
            f"    {label:<22}[{_score_color(score)}]{score:>4}[/]/100", soft_wrap=True
        )
    cli_art.print_literal()

    identity = " / ".join(
        p
        for p in (
            report["primary_identity"],
            report["secondary_identity"],
            report["tertiary_identity"],
        )
        if p
    )
    if identity:
        cli_art.print_literal(f"  Reads as  : {cli_art._escape_markup(identity)}")
    if report["recruiter_takeaway"]:
        cli_art.print_literal(
            f"  Takeaway  : {cli_art._escape_markup(report['recruiter_takeaway'])}"
        )
    if report["strongest_alignment"]:
        cli_art.print_literal(
            f"  Strongest : {cli_art._escape_markup(report['strongest_alignment'])}"
        )
    if report["weakest_alignment"]:
        cli_art.print_literal(
            f"  Weakest   : {cli_art._escape_markup(report['weakest_alignment'])}"
        )
    if report["weakest_ats_platform"]:
        cli_art.print_literal(
            f"  Weakest ATS: {cli_art._escape_markup(report['weakest_ats_platform'])}"
        )
    if report["archetype_mismatch"]:
        cli_art.console.print(
            f"  {theme.colorize_icon('warning')} Archetype mismatch flagged.",
            soft_wrap=True,
        )
    cli_art.print_literal()

    if report["distinctive_moments"]:
        cli_art.print_literal("  Distinctive moments (protected from edits)")
        for moment in report["distinctive_moments"]:
            cli_art.print_literal(f"    - {cli_art._escape_markup(moment)}")
        cli_art.print_literal()

    if report["findings"]:
        cli_art.print_literal("  Critique findings")
        for heading, items in report["findings"]:
            cli_art.print_literal(f"    {heading}:")
            for item in items:
                cli_art.print_literal(f"      - {cli_art._escape_markup(item)}")
        cli_art.print_literal()

    if report["recommendations"]:
        cli_art.print_literal("  Recommendations")
        for outcome, text in report["recommendations"]:
            mark = OUTCOME_MARKS.get(outcome, "-")
            label = OUTCOME_LABELS.get(outcome, outcome)
            cli_art.console.print(
                f"    [{_outcome_color(outcome)}]{mark}[/] "
                f"{cli_art._escape_markup(text)}",
                soft_wrap=True,
            )
            cli_art.print_literal(f"        ({label})")
        cli_art.print_literal()
    else:
        cli_art.print_literal("  Recommendations: none recorded.")
        cli_art.print_literal()


# Written onto `_critique` by a re-score so the vintage question has a
# recorded answer instead of an inferred one. A build-time critique has no
# such key, which is what `report_is_final()` falls back to reading edits for.
RESCORED_STAGE = "rescore"


def rescore(path: str) -> dict:
    """Re-runs the holistic critique against the resume AS IT NOW STANDS.

    This is the only thing in this module that costs an API call, and it is
    the honest answer to "what are the FINAL scores": the build-time critique
    necessarily predates the edits it asked for, and no amount of reading can
    recover a number that was never computed.

    Scores only. It deliberately does not re-run Step 5.5's apply loop -- the
    fresh recommendations are reported as not-attempted rather than silently
    rewriting a document the user may already have sent somewhere.

    Returns {"ok": True, "report": ...} or {"ok": False, "error": "..."}.
    """
    resume_data = load_resume(path)
    if not resume_data:
        return {"ok": False, "error": f"Could not read {path}."}

    jd_path = (resume_data.get("_build_meta") or {}).get("jd_path") or ""
    if not jd_path:
        return {
            "ok": False,
            "error": (
                "This resume does not record which JD it was built from, so "
                "there is nothing to score it against. Resumes built from "
                "2026-09-30 onward carry that link; rebuild this one to "
                "re-score it."
            ),
        }
    if not os.path.exists(jd_path):
        return {
            "ok": False,
            "error": (
                f"The job description it was built from is gone "
                f"({os.path.basename(jd_path)}) -- it was likely archived or "
                f"purged. Scoring against a different posting would be "
                f"meaningless."
            ),
        }

    import jd_manager
    import orchestrator

    jd_text = jd_manager.read_jd_text(jd_path)
    if not jd_text.strip():
        return {"ok": False, "error": f"{os.path.basename(jd_path)} is empty."}

    engine = orchestrator.ResumeEngine()
    # job_key=None: this is not a build, and checkpointing a critique under a
    # finished job's key would make a later resumed build reuse a critique of
    # a different draft.
    engine._run_holistic_critique(
        checkpoint={},
        jd_text=jd_text,
        job_key=None,
        resume_data=resume_data,
        static_prefix=engine.build_audit_static_prefix(),
    )
    critique = resume_data.get("_critique")
    if not critique:
        return {"ok": False, "error": "The critique came back empty; nothing saved."}

    critique["_scored_at_stage"] = RESCORED_STAGE
    critique["_scored_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(resume_data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        return {"ok": False, "error": f"Scored, but could not save: {exc}"}
    return {"ok": True, "report": build_report(path)}


def _choice_label(path: str) -> str:
    """One picker row: the role, plus whether its scores are current."""
    report = build_report(path)
    if not report["has_critique"]:
        mark = "no scores"
    elif report["is_final"]:
        overall = dict(report["scores"]).get("Overall fit")
        mark = f"fit {overall}" if overall is not None else "scored"
    else:
        overall = dict(report["scores"]).get("Overall fit")
        mark = f"fit {overall} (pre-edit)" if overall is not None else "pre-edit"
    return f"{report['title']}  [{mark}]"


def _rescore_offer(report: dict) -> str:
    """Why re-scoring this particular resume is or isn't worth an API call."""
    if not report["jd_path"]:
        return ""
    if report["is_final"]:
        return "Re-score anyway (1 AI call) -- these scores are already current"
    return (
        f"Re-score against the current file (1 AI call) -- "
        f"{len(report['edits_after'])} edit(s) landed after these scores"
    )


def run() -> None:
    """Picker plus report, looping until the user backs out."""
    import questionary

    while True:
        paths = resume_json_paths()
        if not paths:
            cli_art.cli_info(
                "No generated resumes yet -- build one from Build Documents first."
            )
            return

        choices = [questionary.Choice(title=_choice_label(p), value=p) for p in paths]
        choices.append(questionary.Choice(title="Back", value="__back__"))
        selected = cli_art.select("Which resume?", choices)
        if not selected or selected == "__back__":
            return

        cli_art.print_literal()
        report = build_report(selected)
        render_report(report)

        offer = _rescore_offer(report)
        # Gated behind a confirm because it spends real quota, and stated in
        # the prompt rather than after the fact -- the same bar every other
        # paid action in this program is held to.
        if offer and cli_art.confirm(offer, default=not report["is_final"]):
            result = rescore(selected)
            cli_art.print_literal()
            if result.get("ok"):
                render_report(result["report"])
            else:
                cli_art.console.print(
                    f"  {theme.colorize_icon('warning')} "
                    f"{cli_art._escape_markup(result.get('error', 'Re-score failed.'))}",
                    soft_wrap=True,
                )
        if not cli_art.confirm("View another resume's report?", default=True):
            return


if __name__ == "__main__":
    run()
