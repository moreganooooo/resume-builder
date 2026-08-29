"""profile_paths.py — the single source of truth for "which profile is
active" and every filesystem path derived from it. Every script that used
to hand-roll its own PROJECT_ROOT/resume-engine/knowledge_base (or
PROJECT_ROOT/jds, PROJECT_ROOT/output, PROJECT_ROOT/data) path routes
through here instead, so profiles/<name>/ becomes the one place a
profile's personalization data lives, and jds/<name>/, output/<name>/,
data/<name>/ become the one place a profile's operational data lives --
with zero risk of two profiles colliding in the same checkout.

RESUME_PROFILE unset resolves through _default_profile(), which reads what
is actually on disk: the only profile when there is exactly one, otherwise
the legacy name if present, else the first alphabetically. It used to
return a hardcoded "morgan" unconditionally, which silently handed anyone
whose profile is named something else a path to a directory that does not
exist on their machine.

RESUME_PROFILE set to a name with no matching profiles/<name>/ directory
is a hard failure, not a silent fallback -- silently reading the wrong
profile's data on a typo is exactly the bug this module exists to prevent.
The one accommodation is a case-insensitive match against the real
listing, since macOS and Linux disagree about whether profiles/Morgan and
profiles/morgan are the same directory.

Entry points should call preflight_profile() before importing anything
profile-scoped: jd_manager resolves its path constants at MODULE level, so
an unresolvable name otherwise aborts the process with a raw traceback
before any recovery flow can run.
"""

import importlib.util
import os

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# The four roots a profile's data lives under. These are separate module
# constants -- rather than joined off PROJECT_ROOT at call time -- because
# a test that isolates itself by patching PROFILES_DIR alone is only
# ONE-QUARTER isolated: profiles/ is redirected while jds/, output/, and
# data/ still resolve into the real checkout. create_new_profile() calls
# write_sync_ignore_files(), which os.makedirs() every one of these, so a
# half-patched test silently creates jds/<name>/, output/<name>/, and
# data/<name>/ in the developer's own tree. That is how jds/testprofile,
# jds/testuser, and friends accumulated there. Use isolate_for_tests()
# instead of patching any of these individually.
PROFILES_DIR = os.path.join(PROJECT_ROOT, "profiles")
JDS_ROOT = os.path.join(PROJECT_ROOT, "jds")
OUTPUT_ROOT = os.path.join(PROJECT_ROOT, "output")
DATA_ROOT = os.path.join(PROJECT_ROOT, "data")


def rename_profile(old: str, new: str) -> list:
    """Renames a profile across ALL FOUR of its sync roots.

    Centralized here, next to sync_roots(), so the rule "a profile is four
    directories" has one owner. The menu's inline version validated only
    that the new name was non-empty and not a duplicate -- so a name
    containing "/" or ".." reached os.rename() and could move a profile
    anywhere on disk. create_new_profile() has rejected those since it was
    written; rename had no such check.

    Returns [(label, old_path, new_path), ...] for what actually moved, so
    the caller can report it. Raises ValueError on a bad name and
    FileExistsError if any destination already exists -- checked for ALL
    roots BEFORE moving any of them, so a half-renamed profile is not
    possible.

    Callers must still tell the user about the two things this function
    cannot fix: Syncthing folder paths and git tracking. See
    rename_side_effects() for that text.
    """
    import bootstrap_bullet_bank

    if not bootstrap_bullet_bank._VALID_PROFILE_NAME.match(new or ""):
        raise ValueError(
            f"Invalid profile name {new!r} -- use only letters, digits, "
            "underscores, and hyphens."
        )
    if old == new:
        raise ValueError("The new name is the same as the old one.")

    planned = []
    for label, path in sync_roots(old):
        if not os.path.exists(path):
            continue
        new_path = os.path.join(os.path.dirname(path), new)
        # Case-insensitive filesystems (macOS) resolve profiles/morgan and
        # profiles/Morgan to the same directory, so a pure case change is
        # a legitimate rename whose destination "already exists".
        if os.path.exists(new_path) and old.lower() != new.lower():
            raise FileExistsError(
                f"{new_path} already exists -- refusing to overwrite it."
            )
        planned.append((label, path, new_path))

    for _label, path, new_path in planned:
        os.rename(path, new_path)
    return planned


def rename_side_effects(old: str, new: str) -> list:
    """The things a rename cannot do for the user, as (topic, text) pairs.

    Kept beside rename_profile() rather than inline in the menu because
    both are consequences of the same fact -- a profile is four real
    directories that other tools point at by absolute path."""
    return [
        (
            "Syncthing",
            "Each of this profile's four directories is a SEPARATE Syncthing "
            "folder, configured by absolute path on every paired device. "
            "Renaming them here does NOT rename them in Syncthing: the old "
            "paths are now missing, and Syncthing may treat that as a "
            "deletion and propagate it to your other machines. Before you "
            "let those devices sync, pause the four folders in Syncthing on "
            "every device, repoint each to the new path, then resume.",
        ),
        (
            "git",
            f"profiles/{new}/board_scanner/*.yml are tracked files. Git sees "
            f"this rename as deleting profiles/{old}/board_scanner/ and "
            "adding an untracked copy, so commit it with:\n"
            f"    git add -A profiles/{old} profiles/{new}",
        ),
        (
            "your shell",
            "RESUME_PROFILE is exported per terminal session by "
            "scripts/resume-cli.sh, so any OTHER open terminal still has the "
            f"old name. Run `export RESUME_PROFILE={new}` in those, or just "
            "open a new terminal.",
        ),
    ]


def isolate_for_tests(root: str):
    """Context manager redirecting ALL FOUR profile-data roots into
    `root`, for tests that create or write profiles.

    Use this instead of patching PROFILES_DIR by hand. Patching that one
    constant looks like isolation but leaves jds/, output/, and data/
    pointing at the real checkout, so create_new_profile() ->
    write_sync_ignore_files() quietly makedirs jds/<name>/,
    output/<name>/, and data/<name>/ in the developer's own tree. Every
    stray jds/testprofile, jds/testuser, output/temp_empty and friend in
    this repo got there that way.

    Yields the root so callers can assert against it:

        with profile_paths.isolate_for_tests(tmp) as sandbox:
            bootstrap_bullet_bank.create_new_profile("alice")
    """
    import contextlib
    import sys
    from unittest.mock import patch

    me = sys.modules[__name__]

    @contextlib.contextmanager
    def _cm():
        with (
            patch.object(me, "PROFILES_DIR", os.path.join(root, "profiles")),
            patch.object(me, "JDS_ROOT", os.path.join(root, "jds")),
            patch.object(me, "OUTPUT_ROOT", os.path.join(root, "output")),
            patch.object(me, "DATA_ROOT", os.path.join(root, "data")),
        ):
            os.makedirs(os.path.join(root, "profiles"), exist_ok=True)
            yield root

    return _cm()


def available_profiles() -> list:
    """Every profiles/<name>/ directory actually on disk, sorted."""
    if not os.path.isdir(PROFILES_DIR):
        return []
    return sorted(
        n
        for n in os.listdir(PROFILES_DIR)
        if os.path.isdir(os.path.join(PROFILES_DIR, n))
    )


#: Legacy default, kept only as the last resort when no profile exists at
#: all (a fresh clone). It is NOT an assumption that the operator is this
#: person -- see _default_profile().
_LEGACY_DEFAULT_PROFILE = "morgan"


def _default_profile() -> str:
    """Which profile to use when RESUME_PROFILE is unset.

    Returning a hardcoded "morgan" unconditionally meant that anyone whose
    profile is named anything else -- a second person sharing the checkout,
    or a stranger who cloned it from GitHub -- silently got paths pointing
    at a profile directory that does not exist on their machine. Nothing
    raised; every derived path was simply wrong.

    Resolution order:
      1. Exactly one profile on disk -- use it. Unambiguous for everyone,
         and the common case for a fresh single-user setup.
      2. Several profiles -- prefer the legacy default if it is one of
         them (so existing setups are untouched), else the first
         alphabetically, so the answer is at least deterministic. The
         shell wrapper already prompts in this situation; this only
         governs a direct `python scripts/...` invocation.
      3. No profiles at all -- the legacy name, so the "profiles/morgan/
         does not exist" message downstream still reads sensibly.
    """
    names = available_profiles()
    if len(names) == 1:
        return names[0]
    if names:
        by_lower = {n.lower(): n for n in names}
        return by_lower.get(_LEGACY_DEFAULT_PROFILE, sorted(names)[0])
    return _LEGACY_DEFAULT_PROFILE


def active_profile() -> str:
    name = os.environ.get("RESUME_PROFILE")
    if name is None:
        return _default_profile()
    if os.path.isdir(os.path.join(PROFILES_DIR, name)):
        return name
    # The name did not resolve as spelled. Before failing, try the real
    # on-disk listing case-insensitively: macOS resolves profiles/Morgan
    # and profiles/morgan to the same directory, so a name that works on
    # the machine a profile was created on can fail outright on a Linux
    # Syncthing peer whose checkout has the other spelling. This is the
    # same resolve-against-the-listing rule menu._confirm_active_profile()
    # already follows.
    #
    # Deliberately a FALLBACK, not the primary path: normalizing every
    # lookup to the directory's spelling would propagate whichever casing
    # one machine happens to have into every derived path, which is a
    # behaviour change for profiles that already resolve correctly.
    match = {n.lower(): n for n in available_profiles()}.get(name.lower())
    if match:
        return match
    raise ValueError(
        f"RESUME_PROFILE is set to {name!r}, but profiles/{name}/ does not exist. "
        "Check for a typo, or create it via the bootstrap 'New Profile' flow."
    )


def preflight_profile(stream=None) -> bool:
    """Entry-point guard: turns an unresolvable RESUME_PROFILE into an
    actionable message instead of an import-time traceback.

    jd_manager.py resolves JDS_DIR = jds_dir() at MODULE level, and
    cli_art imports jd_manager -- so a typo'd RESUME_PROFILE killed
    `resume`, the menu, and `resume doctor` with a raw ValueError before
    any gate, handler, or recovery flow could run. The old error text even
    pointed at the bootstrap 'New Profile' flow, which was unreachable by
    definition. Worse, resume-cli.sh EXPORTS the variable, so the broken
    state persisted for the whole terminal session.

    Call this before importing anything that touches profile paths.
    Returns True if the profile resolves (or is unset); False if the
    caller should stop. Never raises."""
    import sys

    out = stream or sys.stderr
    name = os.environ.get("RESUME_PROFILE")
    if name is None:
        return True
    try:
        active_profile()
        return True
    except ValueError:
        pass

    names = available_profiles()
    print(
        f"\n  RESUME_PROFILE is set to {name!r}, but profiles/{name}/ does not exist.",
        file=out,
    )
    if names:
        print(f"  Available profiles: {', '.join(names)}", file=out)
        print(f"\n  Fix it with one of:", file=out)
        print(f"    unset RESUME_PROFILE            # use the default", file=out)
        print(
            f"    export RESUME_PROFILE={names[0]}   # pick an existing one", file=out
        )
    else:
        print("  No profiles exist yet.", file=out)
        print("\n  Fix it with:", file=out)
        print(
            "    unset RESUME_PROFILE && resume    # then choose 'New User? Start Here!'",
            file=out,
        )
    print("", file=out)
    return False


# Modules that compute profile-scoped paths as module-level constants
# (resolved once at import time, per this project's existing SCRIPT_DIR/
# PROJECT_ROOT convention) rather than through this module's functions.
# cli.py and menu.py both import these -- and everything that in turn
# imports them (picker.py, scan.py, batch_evaluate.py, liveness.py all
# reference jd_manager.<CONSTANT> via attribute access, never `from
# jd_manager import X`) -- at their own top level, before any --profile
# flag or interactive gate can run. Switching RESUME_PROFILE mid-process
# without reloading these leaves them silently pointed at whichever
# profile was active when the long-running menu/CLI process first
# started, defeating the entire point of runtime profile-switching.
# bootstrap_bullet_bank/bootstrap_profile/bullet_bank_menu joined this list
# once bootstrap_menu.py started reading their KB_DIR-derived constants
# right after create_new_profile() + set_active_profile() -- the exact
# same-session "just created this profile, now act on it" sequence this
# list exists to make safe.
_RELOAD_ON_PROFILE_SWITCH = (
    "gemini_client",
    "jd_manager",
    "polish",
    "bootstrap_bullet_bank",
    "bootstrap_profile",
    "bullet_bank_menu",
)


def set_active_profile(name: str) -> None:
    """Sets RESUME_PROFILE and reloads every already-imported module whose
    profile-scoped path constants were resolved at their own import time
    -- use this instead of assigning os.environ["RESUME_PROFILE"] directly
    anywhere a profile switch needs to actually take effect for the rest
    of a running process (the interactive menu gate, the CLI --profile
    flag, bootstrap creating and switching to a new profile)."""
    import importlib
    import sys

    os.environ["RESUME_PROFILE"] = name
    for module_name in _RELOAD_ON_PROFILE_SWITCH:
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])


def profile_root(profile: str = None) -> str:
    return os.path.join(PROFILES_DIR, profile or active_profile())


def kb_dir(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "knowledge_base")


def board_scanner_dir(profile: str = None) -> str:
    """profiles/<name>/board_scanner/ -- tracked_companies.yml,
    search_queries.yml, and scan_filters.yml (scan_boards.py/scan_ats.py's
    config). 100% profile-specific data (Morgan's own curated target
    companies, search keywords, title/location filters) -- unlike
    board-scanners/providers/ (the Node scraper engine code itself, which
    stays shared/top-level, same split as engine code vs. profile data
    everywhere else in this project)."""
    return os.path.join(profile_root(profile), "board_scanner")


def situational_roles_path(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "situational_roles.yaml")


def company_locations_cache_path(profile: str = None) -> str:
    """profiles/<name>/company_locations.json -- cached geocoded employer points."""
    return os.path.join(profile_root(profile), "company_locations.json")


def fixed_content_module(profile: str = None):
    """Dynamically imports profiles/<profile>/fixed_content.py and returns
    the loaded module object -- the per-profile replacement for a static
    `import fixed_content`."""
    name = profile or active_profile()
    path = os.path.join(profile_root(name), "fixed_content.py")
    if not os.path.exists(path):
        raise ImportError(
            f"profiles/{name}/fixed_content.py not found -- has this profile "
            'been bootstrapped? Run `resume` -> "New User? Start Here!" '
            "(or `resume bootstrap`) to set this profile up."
        )
    spec = importlib.util.spec_from_file_location(f"fixed_content_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _fill_contact_info_from_profile_yaml(module, name)
    return module


# profile.yml's candidate block is the single source of truth for identity
# -- bootstrap_profile.run_profile_setup() writes it, and nothing has ever
# written fixed_content.py's CONTACT_INFO after create_new_profile()
# scaffolds it with five empty strings. Every bootstrapped profile
# therefore rendered a nameless resume until this mapping existed.
_CONTACT_INFO_FROM_CANDIDATE = {
    "NAME": "full_name",
    "PHONE": "phone",
    "EMAIL": "email",
    "LOCATION": "location",
    "LINKEDIN_DISPLAY": "linkedin",
}


def _fill_contact_info_from_profile_yaml(module, profile: str) -> None:
    """Fills any missing/blank CONTACT_INFO key from profile.yml's
    candidate block. Deliberately fill-only, never override: an
    explicitly-set value in fixed_content.py wins, because the two stores
    legitimately disagree on formatting -- an established profile's
    profile.yml may carry a fully-qualified '+1-XXX-XXX-XXXX' phone while
    every resume it has ever rendered shows the shorter CONTACT_INFO form.
    Overriding would silently change existing output; filling only blanks
    is a provable no-op for a populated profile and the entire fix for a
    freshly bootstrapped one.

    Also guarantees all five keys exist on the returned module:
    render_coverletter.py reads contact["NAME"]/["PHONE"]/["EMAIL"]/
    ["LINKEDIN_DISPLAY"]/["LOCATION"] by direct subscript, so a missing
    key is a KeyError mid-render rather than a blank line."""
    contact = dict(getattr(module, "CONTACT_INFO", None) or {})
    candidate = (profile_yaml(profile) or {}).get("candidate") or {}
    for key, candidate_key in _CONTACT_INFO_FROM_CANDIDATE.items():
        if str(contact.get(key) or "").strip():
            continue
        contact[key] = str(candidate.get(candidate_key) or "").strip()
    module.CONTACT_INFO = contact


def profile_yaml(profile: str = None) -> dict:
    """Loads and returns profiles/<profile>/knowledge_base/profile.yml as a
    dict -- shared by any caller that just needs one or two top-level
    fields (e.g. candidate.full_name) without pulling in orchestrator.py's
    ResumeEngine class."""
    name = profile or active_profile()
    path = os.path.join(kb_dir(name), "profile.yml")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def full_name(profile: str = None) -> str:
    """Reads candidate.full_name from profile.yml (e.g. "Alex Mercer")."""
    return (profile_yaml(profile).get("candidate") or {}).get("full_name", "")


def education_achievement_slots(profile: str = None) -> list:
    """Returns [(institution, achievement_options_dict), ...] in
    profile.yml's fixed_credentials.education order, for every entry that
    offers a pre-approved achievement-bullet choice (achievement_options:
    non-empty) -- entries with a single fixed bullet or no achievement
    concept at all (e.g. JCCC) are skipped. Both orchestrator.py (building
    the dynamic EDU_ACHIEVEMENT_KEY_<n> schema fields Gemini must answer)
    and normalize_resume.py (mapping those answers back to institutions
    for fixed_content.build_education()) call this exact function so the
    slot numbering can never drift between the two."""
    data = profile_yaml(profile)
    education = ((data.get("fixed_credentials") or {}).get("education")) or []
    return [
        (ed["institution"], ed["achievement_options"])
        for ed in education
        if ed.get("achievement_options")
    ]


def has_design_only_credentials(profile: str = None) -> bool:
    """True if profile.yml's fixed_credentials (certifications or
    education) has at least one entry marked design_only: true -- those
    are gated behind INCLUDE_DESIGN_CREDENTIALS (see tailor_resume.md)
    rather than always rendered, since they only read as credible when the
    JD has actual graphic-design responsibilities. Mirrors
    education_achievement_slots()'s pattern of returning an empty/false
    result for a profile with no such entries, so the schema field is
    only injected when there's something for it to gate."""
    credentials = (profile_yaml(profile).get("fixed_credentials")) or {}
    entries = (credentials.get("certifications") or []) + (
        credentials.get("education") or []
    )
    return any(entry.get("design_only") for entry in entries)


def tags(profile: str = None) -> list:
    """Returns profile.yml's tags: list -- each a dict with name/
    persona_description/keywords, generated once during bootstrap
    (bootstrap_extractors.generate_tag_taxonomy()) from this profile's own
    target roles and real achievement text. Replaces what used to be three
    separately-hardcoded, already-drifted-apart copies of the same
    marketing-specific taxonomy (orchestrator.py's TAG_CONTEXT +
    CLAIM_TAG_KEYWORDS, tag_bullet_bank.py's TAG_KEYWORDS, and
    rewrite_bullets.py's own copies of both) -- every consumer now reads
    this one list, so they can't drift apart again. Empty for a profile
    that hasn't generated one yet; callers should degrade gracefully
    (e.g. treat every bullet as belonging to no specific tag) rather than
    assume a non-empty list."""
    return profile_yaml(profile).get("tags") or []


def env_path(profile: str = None) -> str:
    """Path to this profile's own .env (GEMINI_API_KEY, JOBRIGHT_COOKIE_STRING,
    etc.) -- every script's load_dotenv() call points here instead of a
    single project-root .env, so two profiles sharing one checkout can
    each carry their own API key/cookie without colliding. Missing file is
    not an error here (load_dotenv() itself already handles that
    gracefully) -- callers surface their own clear error the first time
    they actually need a var that isn't set."""
    return os.path.join(profile_root(profile), ".env")


SIGNATURE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def signature_path(profile: str = None) -> str | None:
    """Path to this profile's own optional handwritten-style signature
    image (profiles/<name>/signature.{png,jpg,jpeg}), or None if the
    profile hasn't dropped one in -- render_coverletter() treats None as
    "render with no signature image," never an error. Checks each
    extension in SIGNATURE_EXTENSIONS in order, returns the first that
    exists."""
    root = profile_root(profile)
    for ext in SIGNATURE_EXTENSIONS:
        candidate = os.path.join(root, f"signature{ext}")
        if os.path.exists(candidate):
            return candidate
    return None


def jds_dir(profile: str = None) -> str:
    return os.path.join(JDS_ROOT, profile or active_profile())


def output_dir(profile: str = None) -> str:
    return os.path.join(OUTPUT_ROOT, profile or active_profile())


def checkpoints_dir(profile: str = None) -> str:
    return os.path.join(output_dir(profile), "checkpoints")


def data_dir(profile: str = None) -> str:
    return os.path.join(DATA_ROOT, profile or active_profile())


def applications_md_path(profile: str = None) -> str:
    return os.path.join(data_dir(profile), "applications.md")


def tracker_csv_path(profile: str = None) -> str:
    return os.path.join(jds_dir(profile), "jd_tracker_log.csv")


def sync_roots(profile: str = None) -> list:
    """Returns [(label, path), ...] for the profile-scoped directories a
    multi-computer sync tool (Syncthing) should be pointed at -- see
    CLAUDE.md's "Multi-computer sync" section for the full design. Kept
    as one place so write_sync_ignore_files() and any future sync
    tooling can't drift apart on what "this profile's synced data" means.
    Deliberately excludes nothing (not even .env or signature.*) --
    Syncthing is direct device-to-device and encrypted in transit, so the
    git-secrecy reason those are gitignored doesn't apply to it."""
    name = profile or active_profile()
    return [
        ("profile", profile_root(name)),
        ("jds", jds_dir(name)),
        ("output", output_dir(name)),
        ("data", data_dir(name)),
    ]


_SYNC_STIGNORE_CONTENT = (
    "// Syncthing per-folder ignore file -- machine-local cruft that should\n"
    "// never sync between devices. Secrets/PII are deliberately NOT\n"
    '// excluded here; see CLAUDE.md\'s "Multi-computer sync" section for why.\n'
    "data.db-wal\n"
    "data.db-shm\n"
    "*.lock\n"
    "__pycache__\n"
    "*.pyc\n"
    ".DS_Store\n"
)


def write_sync_ignore_files(profile: str = None) -> None:
    """Ensures every directory sync_roots() names exists and carries a
    .stignore, so a profile is ready for Syncthing to point at without
    the user hand-authoring config per profile. Called once from
    bootstrap_bullet_bank.create_new_profile() for every new profile.
    Idempotent and non-destructive -- never overwrites an already-present
    .stignore, so hand-customization survives re-runs."""
    for _label, path in sync_roots(profile):
        os.makedirs(path, exist_ok=True)
        stignore_path = os.path.join(path, ".stignore")
        if not os.path.exists(stignore_path):
            with open(stignore_path, "w", encoding="utf-8") as f:
                f.write(_SYNC_STIGNORE_CONTENT)


def kb_snapshot_dir(profile: str = None) -> str:
    """profiles/<name>/knowledge_base/ has no backup or recovery path of
    its own (see B13 -- it's fully gitignored on purpose, and Syncthing
    propagates corruption rather than guarding against it), so
    kb_snapshot.snapshot_kb() needs somewhere durable to keep rotating
    pre-run copies. data/<name>/ is already a sync_roots() member for
    this profile's operational data (see tracker_csv_path()/
    applications_md_path()), so snapshots live under it rather than
    adding a fifth sync root."""
    return os.path.join(data_dir(profile), "kb_snapshots")


def maintenance_log_path(profile: str = None) -> str:
    """Where the Maintenance submenu persists "when did this task last
    run" per background/administrative task (doctor script, etc.) --
    already covered by .gitignore's existing `*_log.json` pattern, no
    gitignore change needed."""
    return os.path.join(profile_root(profile), "maintenance_log.json")


def ui_config_path(profile: str = None) -> str:
    """Where per-profile terminal-UI preferences persist -- today just the
    Nerd Font vs. Unicode icon-set choice from the first-launch prompt
    (B33), so it's asked once per profile and never again. Already covered
    by .gitignore's blanket `profiles/*/` pattern, no gitignore change
    needed."""
    return os.path.join(profile_root(profile), "ui_config.json")
