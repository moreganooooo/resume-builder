"""End-to-end guard for the new-user bootstrap path.

Written after the 2026-08-23 bootstrap audit, which found four defects
that each independently broke a new user's first run. Three of them were
invisible to the existing suite because every test either ran against
Morgan's own fully-populated profile or stubbed the identity layer
outright. This module bootstraps a throwaway profile into a temp
directory and asserts on what a real new user would actually get.

The single most important assertion here is
test_no_previous_users_identity_leaks_into_a_new_profile: for the entire
life of the project, profile_paths carried ~250 lines of one specific
person's real contact details and career history as an import-time
fallback, guarded by `if name == "morgan" or profile is None`. Every one
of the nine call sites used the zero-arg form, so `profile is None` was
always true and the guard never fired -- a brand-new user's rendered
resume and cover letter carried someone else's name, phone, and email.

Isolation goes through profile_paths.isolate_for_tests(), which redirects
all FOUR profile-data roots at once. Patching PROFILES_DIR alone -- the
obvious move, and what this file did first -- leaves jds/, output/ and
data/ pointing at the real checkout, so create_new_profile() quietly
creates jds/<name>/ and data/<name>/ in the developer's tree. This module
did exactly that before the helper existed.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import profile_paths  # noqa: E402


def _capture_prior_user_markers():
    """Identity fragments that must never appear in a DIFFERENT profile's
    rendered output.

    Captured ONCE at import, before any test enters a sandbox -- inside a
    sandbox the "active profile" is the persona, whose values legitimately
    do appear in the output under test.

    Read from the real profile rather than written down here.
    Hardcoding them would put one person's real name, phone and home town
    into tracked source -- which is the exact thing this module exists to
    prevent, and would leave the check meaningless for anyone else. Falls
    back to an empty list when no profile is configured; the assertions
    that use it then trivially pass, which is correct: with no other
    profile on the machine there is nothing that could leak.
    """
    candidate = (profile_paths.profile_yaml() or {}).get("candidate") or {}
    markers = []
    for key in ("full_name", "email", "phone", "location", "linkedin"):
        value = str(candidate.get(key) or "").strip()
        if len(value) >= 5:
            markers.append(value)
    return markers


# Bound at import time: see the docstring above for why this cannot be
# evaluated lazily inside a test.
_PRIOR_USER_MARKERS = _capture_prior_user_markers()


class BootstrapFirstRunTest(unittest.TestCase):
    """Each test gets a clean profiles/ root containing nothing at all --
    the true starting state of a fresh clone for a person who is not the
    project's original author."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_env = os.environ.get("RESUME_PROFILE")
        # isolate_for_tests, not a bare PROFILES_DIR patch: create_new_profile()
        # calls write_sync_ignore_files(), which makedirs all four sync roots.
        # Patching only PROFILES_DIR left jds/, output/, and data/ pointing at
        # the real checkout -- this very test created jds/alice and data/alice
        # in the developer's tree before the helper existed.
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self.profiles_dir = profile_paths.PROFILES_DIR
        os.environ["RESUME_PROFILE"] = "alice"

    def tearDown(self):
        self._iso.__exit__(None, None, None)
        if self._orig_env is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig_env
        self._tmp.cleanup()

    def _create(self, name="alice"):
        return bootstrap_bullet_bank.create_new_profile(name)

    def _write_profile_yml(self, name, candidate):
        kb = profile_paths.kb_dir(name)
        os.makedirs(kb, exist_ok=True)
        import yaml

        with open(os.path.join(kb, "profile.yml"), "w", encoding="utf-8") as f:
            yaml.safe_dump({"candidate": candidate}, f)

    # -- scaffolding ----------------------------------------------------

    def test_create_new_profile_scaffolds_the_files_a_first_run_needs(self):
        root = self._create()
        for rel in (
            "fixed_content.py",
            "situational_roles.yaml",
            os.path.join("board_scanner", "tracked_companies.yml"),
            os.path.join("board_scanner", "search_queries.yml"),
            os.path.join("board_scanner", "scan_filters.yml"),
            os.path.join("knowledge_base", "bootstrap", "source_documents"),
        ):
            self.assertTrue(
                os.path.exists(os.path.join(root, rel)),
                f"new profile is missing {rel}",
            )

    def test_profile_name_with_path_traversal_is_rejected(self):
        for bad in ("../escape", "a/b", ".."):
            with self.assertRaises(ValueError):
                self._create(bad)

    def test_creating_an_existing_profile_raises_rather_than_overwriting(self):
        self._create()
        with self.assertRaises(FileExistsError):
            self._create()

    def test_creating_a_profile_writes_nothing_outside_the_sandbox(self):
        """create_new_profile() -> write_sync_ignore_files() makedirs all
        four sync roots. Three of them (jds/, output/, data/) derived from
        PROJECT_ROOT, which no test patched -- so every test that created a
        profile silently made jds/<name>/ and data/<name>/ in the real
        checkout. This asserts the isolation is total, not one-quarter."""
        real_root = profile_paths.PROJECT_ROOT
        self._create("sandboxcheck")
        for sub in ("jds", "output", "data", "profiles"):
            stray = os.path.join(real_root, sub, "sandboxcheck")
            self.assertFalse(
                os.path.exists(stray),
                f"test leaked {stray} into the real checkout",
            )
        # ...and the sandbox really did get them, so this is not vacuous.
        self.assertTrue(
            os.path.isdir(os.path.join(self._tmp.name, "jds", "sandboxcheck"))
        )

    # -- the PII regression --------------------------------------------

    def test_unbootstrapped_profile_raises_instead_of_falling_back(self):
        """A profile with no fixed_content.py must fail loudly. It used to
        silently return the original author's real identity."""
        os.makedirs(os.path.join(self.profiles_dir, "alice"))
        with self.assertRaises(ImportError):
            profile_paths.fixed_content_module()

    def test_missing_profile_yaml_returns_empty_not_someone_elses_data(self):
        os.makedirs(os.path.join(self.profiles_dir, "alice"))
        self.assertEqual(profile_paths.profile_yaml(), {})

    def test_no_previous_users_identity_leaks_into_a_new_profile(self):
        """The permanent guard against the fallback-PII class of bug."""
        self._create()
        self._write_profile_yml(
            "alice",
            {
                "full_name": "Alice Rivera",
                "email": "alice@example.com",
                "phone": "555-0100",
                "location": "Portland, OR",
                "linkedin": "linkedin.com/in/alicerivera",
            },
        )
        contact = profile_paths.fixed_content_module().CONTACT_INFO
        blob = repr(contact)
        for marker in _PRIOR_USER_MARKERS:
            self.assertNotIn(
                marker,
                blob,
                f"another user's identity ({marker!r}) leaked into alice's contact block",
            )

    # -- identity derivation (F3) --------------------------------------

    def test_contact_info_is_populated_from_profile_yaml(self):
        """create_new_profile scaffolds CONTACT_INFO as five empty strings
        and run_profile_setup() writes profile.yml but never
        fixed_content.py -- so without derivation every bootstrapped user
        rendered a nameless resume."""
        self._create()
        self._write_profile_yml(
            "alice",
            {
                "full_name": "Alice Rivera",
                "email": "alice@example.com",
                "phone": "555-0100",
                "location": "Portland, OR",
                "linkedin": "linkedin.com/in/alicerivera",
            },
        )
        contact = profile_paths.fixed_content_module().CONTACT_INFO
        self.assertEqual(contact["NAME"], "Alice Rivera")
        self.assertEqual(contact["EMAIL"], "alice@example.com")
        self.assertEqual(contact["PHONE"], "555-0100")
        self.assertEqual(contact["LOCATION"], "Portland, OR")
        self.assertEqual(contact["LINKEDIN_DISPLAY"], "linkedin.com/in/alicerivera")

    def test_all_five_contact_keys_always_exist(self):
        """render_coverletter.py reads contact["NAME"]/["PHONE"]/["EMAIL"]/
        ["LINKEDIN_DISPLAY"]/["LOCATION"] by direct subscript, so a missing
        key is a KeyError mid-render, not a blank line."""
        self._create()  # no profile.yml written at all
        contact = profile_paths.fixed_content_module().CONTACT_INFO
        for key in ("NAME", "PHONE", "EMAIL", "LOCATION", "LINKEDIN_DISPLAY"):
            self.assertIn(key, contact)

    def test_explicit_fixed_content_wins_over_profile_yaml(self):
        """Derivation fills blanks; it must never override. The two stores
        legitimately disagree on formatting (a fully-qualified phone in
        profile.yml vs. the shorter rendered form), and overriding would
        silently change an established profile's output."""
        root = self._create()
        with open(os.path.join(root, "fixed_content.py"), "a", encoding="utf-8") as f:
            f.write('\nCONTACT_INFO["PHONE"] = "555-0100"\n')
        self._write_profile_yml(
            "alice", {"full_name": "Alice Rivera", "phone": "+1-555-0100"}
        )
        contact = profile_paths.fixed_content_module().CONTACT_INFO
        self.assertEqual(contact["PHONE"], "555-0100")  # explicit value kept
        self.assertEqual(contact["NAME"], "Alice Rivera")  # blank still filled


class GoBootstrapWizardTest(unittest.TestCase):
    """The Go wizard's module lives in dashboard/, not the project root.
    Invoking it from the root failed with "cannot find main module" on
    every machine that had Go installed -- and the questionary fallback
    was gated on Go being ABSENT, so having Go guaranteed the broken path
    and never the working one."""

    def test_wizard_is_invoked_from_a_directory_containing_a_go_module(self):
        import menu

        captured = {}

        def fake_run(cmd, cwd=None, **kwargs):
            captured["cwd"] = cwd

            class R:
                returncode = 1
                stdout = ""
                stderr = ""

            return R()

        with (
            patch("subprocess.run", side_effect=fake_run),
            patch("shutil.which", return_value="/usr/local/bin/go"),
        ):
            menu._run_go_bootstrap_wizard()

        self.assertIn("cwd", captured, "wizard was never invoked")
        self.assertTrue(
            os.path.exists(os.path.join(captured["cwd"], "go.mod")),
            f"wizard invoked from {captured['cwd']!r}, which has no go.mod -- "
            "this is the exact failure that broke New User Setup",
        )

    def test_wizard_failure_falls_back_instead_of_dead_ending(self):
        import menu

        class R:
            returncode = 1
            stdout = ""
            stderr = "boom"

        with (
            patch("subprocess.run", return_value=R()),
            patch("shutil.which", return_value="/usr/local/bin/go"),
        ):
            ok, data = menu._run_go_bootstrap_wizard()
        self.assertFalse(ok, "a wizard failure must hand off to the fallback wizard")
        self.assertIsNone(data)

    def test_user_cancellation_is_distinguished_from_failure(self):
        import menu

        class R:
            returncode = 130  # huh.ErrUserAborted
            stdout = ""
            stderr = ""

        with (
            patch("subprocess.run", return_value=R()),
            patch("shutil.which", return_value="/usr/local/bin/go"),
            patch("os.path.exists", return_value=True),
        ):
            ok, data = menu._run_go_bootstrap_wizard()
        self.assertTrue(ok, "cancelling is not an error")
        self.assertIsNone(data, "cancelling must not run setup")


class ProfilePreflightTest(unittest.TestCase):
    """jd_manager.py resolves JDS_DIR at module level and cli_art imports
    it, so an unresolvable RESUME_PROFILE killed `resume`, the menu, AND
    `resume doctor` with a raw traceback -- the error text pointed at a
    recovery flow that was unreachable by definition."""

    def setUp(self):
        self._orig = os.environ.get("RESUME_PROFILE")

    def tearDown(self):
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig

    def test_preflight_passes_when_profile_is_unset(self):
        os.environ.pop("RESUME_PROFILE", None)
        self.assertTrue(profile_paths.preflight_profile(stream=_Sink()))

    def test_preflight_reports_instead_of_raising_on_a_bad_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "real"))
            with patch.object(profile_paths, "PROFILES_DIR", tmp):
                os.environ["RESUME_PROFILE"] = "typo"
                sink = _Sink()
                self.assertFalse(profile_paths.preflight_profile(stream=sink))
                self.assertIn("typo", sink.text)
                self.assertIn("real", sink.text, "must list what IS available")

    def test_preflight_never_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(profile_paths, "PROFILES_DIR", tmp):
                os.environ["RESUME_PROFILE"] = "nope"
                try:
                    profile_paths.preflight_profile(stream=_Sink())
                except Exception as exc:  # pragma: no cover
                    self.fail(f"preflight must never raise, got {exc!r}")


class _Sink:
    def __init__(self):
        self.text = ""

    def write(self, s):
        self.text += s

    def flush(self):
        pass


if __name__ == "__main__":
    unittest.main()


class GeminiTestNetworkGuardTest(unittest.TestCase):
    """The suite made 78 live calls to generativelanguage.googleapis.com on
    every full run -- real spend, real 429s, and a wall-clock that swung
    between 127s and 274s depending on rate limiting. websearch_ddg.py
    already had this guard; gemini_client.py never got one."""

    def setUp(self):
        import gemini_client

        self.gc = gemini_client
        self._orig = os.environ.get(gemini_client._TEST_NETWORK_ENV)
        os.environ.pop(gemini_client._TEST_NETWORK_ENV, None)

    def tearDown(self):
        if self._orig is None:
            os.environ.pop(self.gc._TEST_NETWORK_ENV, None)
        else:
            os.environ[self.gc._TEST_NETWORK_ENV] = self._orig

    def test_auth_headers_refuse_to_build_under_unittest(self):
        with self.assertRaises(self.gc.TestNetworkBlockedError):
            self.gc._get_auth_headers()

    def test_guard_fails_closed_rather_than_returning_a_canned_value(self):
        """A guard that returned empty headers would let these tests stay
        green while asserting nothing -- strictly worse than the bug."""
        try:
            self.gc._get_auth_headers()
        except self.gc.TestNetworkBlockedError:
            return
        self.fail("guard must raise, not degrade")

    def test_opt_in_env_var_restores_real_behaviour(self):
        os.environ[self.gc._TEST_NETWORK_ENV] = "1"
        headers = self.gc._get_auth_headers()
        self.assertIn("x-goog-api-key", headers)


class ProfileIsSetUpTest(unittest.TestCase):
    """create_new_profile() makes knowledge_base/ the moment a profile is
    named, so a brand-new empty profile reported "set up" -- which lifted
    the guest-mode guard and offered tailoring against an empty bullet
    bank."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self._orig = os.environ.get("RESUME_PROFILE")

    def tearDown(self):
        self._iso.__exit__(None, None, None)
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig
        self._tmp.cleanup()

    def test_freshly_scaffolded_profile_is_not_yet_set_up(self):
        import menu

        bootstrap_bullet_bank.create_new_profile("alice")
        self.assertFalse(menu._profile_is_set_up("alice"))

    def test_profile_with_real_knowledge_base_content_is_set_up(self):
        """Deliberately broad: a profile restored from a Syncthing peer or
        assembled by hand is as set up as a bootstrapped one."""
        import menu

        bootstrap_bullet_bank.create_new_profile("alice")
        kb = profile_paths.kb_dir("alice")
        os.makedirs(kb, exist_ok=True)
        with open(os.path.join(kb, "profile.yml"), "w", encoding="utf-8") as f:
            f.write("candidate: {full_name: Alice Rivera}\n")
        self.assertTrue(menu._profile_is_set_up("alice"))

    def test_missing_profile_is_not_set_up(self):
        import menu

        self.assertFalse(menu._profile_is_set_up("nobody"))


class RenameProfileTest(unittest.TestCase):
    """A profile is four directories, and rename has to move all of them.
    The menu's inline version validated only non-empty/non-duplicate, so a
    name containing "/" or ".." reached os.rename()."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._iso = profile_paths.isolate_for_tests(self._tmp.name)
        self._iso.__enter__()
        self._orig = os.environ.get("RESUME_PROFILE")
        bootstrap_bullet_bank.create_new_profile("alice")

    def tearDown(self):
        self._iso.__exit__(None, None, None)
        if self._orig is None:
            os.environ.pop("RESUME_PROFILE", None)
        else:
            os.environ["RESUME_PROFILE"] = self._orig
        self._tmp.cleanup()

    def test_rename_moves_all_four_sync_roots(self):
        profile_paths.rename_profile("alice", "bob")
        for label, path in profile_paths.sync_roots("bob"):
            self.assertTrue(os.path.isdir(path), f"{label} did not move")
        for label, path in profile_paths.sync_roots("alice"):
            self.assertFalse(os.path.exists(path), f"old {label} left behind")

    def test_rename_rejects_path_traversal(self):
        for bad in ("../escape", "a/b", "..", "with space", ""):
            with self.assertRaises(ValueError):
                profile_paths.rename_profile("alice", bad)
        # ...and the profile is untouched after each refusal.
        self.assertTrue(os.path.isdir(profile_paths.profile_root("alice")))

    def test_rename_refuses_to_overwrite_an_existing_profile(self):
        bootstrap_bullet_bank.create_new_profile("bob")
        with self.assertRaises(FileExistsError):
            profile_paths.rename_profile("alice", "bob")

    def test_nothing_moves_when_any_destination_is_taken(self):
        """Destinations are checked for ALL roots before ANY are moved, so
        a collision cannot leave a half-renamed profile."""
        bootstrap_bullet_bank.create_new_profile("bob")
        with self.assertRaises(FileExistsError):
            profile_paths.rename_profile("alice", "bob")
        for label, path in profile_paths.sync_roots("alice"):
            self.assertTrue(os.path.isdir(path), f"{label} moved despite the error")

    def test_side_effects_name_syncthing_git_and_the_shell(self):
        topics = [t for t, _ in profile_paths.rename_side_effects("alice", "bob")]
        self.assertIn("Syncthing", topics)
        self.assertIn("git", topics)
        self.assertIn("your shell", topics)
