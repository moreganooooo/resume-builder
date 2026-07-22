"""profile_paths.py — the single source of truth for "which profile is
active" and every filesystem path derived from it. Every script that used
to hand-roll its own PROJECT_ROOT/resume-engine/knowledge_base (or
PROJECT_ROOT/jds, PROJECT_ROOT/output, PROJECT_ROOT/data) path routes
through here instead, so profiles/<name>/ becomes the one place a
profile's personalization data lives, and jds/<name>/, output/<name>/,
data/<name>/ become the one place a profile's operational data lives --
with zero risk of two profiles colliding in the same checkout.

RESUME_PROFILE unset defaults to "morgan" (backward compatible with every
existing workflow). RESUME_PROFILE set to a name with no matching
profiles/<name>/ directory is a hard failure, not a silent fallback --
silently reading the wrong profile's data on a typo is exactly the bug
this module exists to prevent.
"""

import importlib.util
import os

import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
PROFILES_DIR = os.path.join(PROJECT_ROOT, "profiles")


def active_profile() -> str:
    name = os.environ.get("RESUME_PROFILE")
    if name is None:
        return "morgan"
    if not os.path.isdir(os.path.join(PROFILES_DIR, name)):
        raise ValueError(
            f"RESUME_PROFILE is set to {name!r}, but profiles/{name}/ does not exist. "
            "Check for a typo, or create it via the bootstrap 'New Profile' flow."
        )
    return name


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
_RELOAD_ON_PROFILE_SWITCH = ("jd_manager", "polish")


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


def situational_roles_path(profile: str = None) -> str:
    return os.path.join(profile_root(profile), "situational_roles.yaml")


def fixed_content_module(profile: str = None):
    """Dynamically imports profiles/<profile>/fixed_content.py and returns
    the loaded module object -- the per-profile replacement for a static
    `import fixed_content`."""
    name = profile or active_profile()
    path = os.path.join(profile_root(name), "fixed_content.py")
    if not os.path.exists(path):
        raise ImportError(
            f"profiles/{name}/fixed_content.py not found -- has this profile been bootstrapped?"
        )
    spec = importlib.util.spec_from_file_location(f"fixed_content_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def profile_yaml(profile: str = None) -> dict:
    """Loads and returns profiles/<profile>/knowledge_base/profile.yml as a
    dict -- shared by any caller that just needs one or two top-level
    fields (e.g. candidate.full_name) without pulling in orchestrator.py's
    ResumeEngine class."""
    path = os.path.join(kb_dir(profile), "profile.yml")
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def full_name(profile: str = None) -> str:
    """Reads candidate.full_name from profile.yml (e.g. "Morgan Escott")."""
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
    return os.path.join(PROJECT_ROOT, "jds", profile or active_profile())


def output_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "output", profile or active_profile())


def checkpoints_dir(profile: str = None) -> str:
    return os.path.join(output_dir(profile), "checkpoints")


def data_dir(profile: str = None) -> str:
    return os.path.join(PROJECT_ROOT, "data", profile or active_profile())


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
    "// excluded here; see CLAUDE.md's \"Multi-computer sync\" section for why.\n"
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


def maintenance_log_path(profile: str = None) -> str:
    """Where the Maintenance submenu persists "when did this task last
    run" per background/administrative task (doctor script, etc.) --
    already covered by .gitignore's existing `*_log.json` pattern, no
    gitignore change needed."""
    return os.path.join(profile_root(profile), "maintenance_log.json")
