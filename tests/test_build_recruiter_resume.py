"""Unit tests for scripts/build_recruiter_resume.py.

Everything here exercises the pure brief-building half and the guards
around the build -- never the build itself, which is real Gemini calls.
"""

import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import build_recruiter_resume  # noqa: E402

PROFILE = {
    "candidate": {"full_name": "Ada Fictional"},
    "target_roles": {
        "primary": ["Data Scientist", "Machine Learning Engineer"],
        "secondary": ["Data Analyst"],
    },
    "archetypes": [
        {
            "name": "Data Scientist (Time Series)",
            "level": "Mid",
            "notes": "Anomaly detection on sensor data.",
        },
        "a malformed entry that is not a dict",
    ],
    "background_context": "Trained as a chemist, moved into industry ML.",
}


class TestBuildTargetBrief(unittest.TestCase):
    def test_includes_primary_and_secondary_roles(self):
        brief = build_recruiter_resume.build_target_brief(PROFILE)
        for role in ("Data Scientist", "Machine Learning Engineer", "Data Analyst"):
            self.assertIn(role, brief)

    def test_states_there_is_no_posting_or_company(self):
        """The whole point of this build: the model must not tailor to,
        or address, an employer that does not exist."""
        brief = build_recruiter_resume.build_target_brief(PROFILE)
        self.assertIn("NOT a job posting", brief)
        self.assertIn("Ada Fictional", brief)

    def test_includes_archetype_notes_and_background(self):
        brief = build_recruiter_resume.build_target_brief(PROFILE)
        self.assertIn("Anomaly detection on sensor data.", brief)
        self.assertIn("Trained as a chemist", brief)

    def test_survives_malformed_archetype_entries(self):
        """profile.yml is hand-edited; a non-dict entry must not crash a
        build the user is running two days before an interview."""
        brief = build_recruiter_resume.build_target_brief(PROFILE)
        self.assertIn("Data Scientist (Time Series)", brief)

    def test_appends_cv_text_when_present(self):
        brief = build_recruiter_resume.build_target_brief(PROFILE, "## Experience\nfoo")
        self.assertIn("CANDIDATE CV", brief)
        self.assertIn("## Experience", brief)

    def test_omits_cv_section_when_absent(self):
        brief = build_recruiter_resume.build_target_brief(PROFILE, "")
        self.assertNotIn("CANDIDATE CV", brief)

    def test_empty_profile_does_not_raise(self):
        self.assertIsInstance(build_recruiter_resume.build_target_brief({}), str)
        self.assertIsInstance(build_recruiter_resume.build_target_brief(None), str)

    def test_bootstrap_placeholder_strings_are_dropped(self):
        """create_new_profile() scaffolds list fields as [""] -- a blank
        bullet in the brief reads as a role with no name."""
        brief = build_recruiter_resume.build_target_brief(
            {"target_roles": {"primary": ["Data Scientist", "", "   "]}}
        )
        self.assertNotIn("  - \n", brief)


class TestWriteBrief(unittest.TestCase):
    """The brief must land outside jds/<profile>/, or get_pending_jds()
    would pick it up in a batch run and treat it as a real application."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_writes_under_output_not_jds(self):
        with patch(
            "build_recruiter_resume.profile_paths.output_dir",
            return_value=self.tmp_dir,
        ):
            path = build_recruiter_resume.write_brief("hello")
        self.assertTrue(path.startswith(self.tmp_dir))
        self.assertNotIn(os.sep + "jds" + os.sep, path)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "hello")


class TestResolveInteractive(unittest.TestCase):
    """Step 5.5's approval gate prompts through the Go/huh binary, which
    aborts the entire build with "error opening TTY" when there is no
    terminal -- after the whole pipeline has already been paid for."""

    def test_explicit_value_wins_over_the_stream(self):
        self.assertTrue(build_recruiter_resume._resolve_interactive(True))
        self.assertFalse(build_recruiter_resume._resolve_interactive(False))

    def test_defaults_to_false_without_a_tty(self):
        class _NoTTY:
            def isatty(self):
                return False

        with patch.object(build_recruiter_resume.sys, "stdin", _NoTTY()):
            self.assertFalse(build_recruiter_resume._resolve_interactive(None))

    def test_defaults_to_true_with_a_tty(self):
        class _TTY:
            def isatty(self):
                return True

        with patch.object(build_recruiter_resume.sys, "stdin", _TTY()):
            self.assertTrue(build_recruiter_resume._resolve_interactive(None))

    def test_survives_a_stdin_that_raises(self):
        class _Broken:
            def isatty(self):
                raise ValueError("detached")

        with patch.object(build_recruiter_resume.sys, "stdin", _Broken()):
            self.assertFalse(build_recruiter_resume._resolve_interactive(None))


class TestBuildGuards(unittest.TestCase):
    def test_bails_out_when_profile_has_no_target_roles(self):
        """Without a range to write across, the result would be a generic
        resume dressed up as a deliberate one -- and a full build is a lot
        of API spend to discover that."""
        with patch.object(
            build_recruiter_resume,
            "_load_profile_inputs",
            return_value=({"candidate": {"full_name": "Ada"}}, ""),
        ), patch.object(build_recruiter_resume, "write_brief") as mock_write, patch(
            "build_recruiter_resume.orchestrator.ResumeEngine"
        ) as mock_engine:
            result = build_recruiter_resume.build_recruiter_resume()
        self.assertEqual(result, {"resume": {}})
        mock_write.assert_not_called()
        mock_engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
