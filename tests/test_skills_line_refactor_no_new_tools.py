"""The skills-line dead-band fixer may trim or reword, but a rewrite that
introduces an unverified tool is rejected in favor of the original line --
it used to pad lines with tools the candidate never used, failing builds."""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402

LINE = "**Languages:** Python, SQL"


def _flag(resume_data):
    # Stand-in for the verified-tools check: anything named "Snowflake" is unverified.
    return [f"Hallucinated: {s}" for s in resume_data["SKILLS"] if "Snowflake" in s]


class TestSkillsLineRefactor(unittest.TestCase):
    def _run(self, rewrite):
        with (
            patch.object(
                orchestrator.GeminiClient, "generate", return_value=(rewrite, None)
            ),
            patch.object(
                orchestrator.validate_resume,
                "_check_hallucinated_tools",
                side_effect=_flag,
            ),
        ):
            return orchestrator._micro_refactor_skills_line(LINE, {})

    def test_rewrite_adding_an_unverified_tool_is_rejected(self):
        self.assertEqual(self._run("**Languages:** Python, SQL, Snowflake"), LINE)

    def test_rewrite_without_new_tools_is_kept(self):
        self.assertEqual(self._run("**Languages:** Python"), "**Languages:** Python")

    def test_empty_rewrite_keeps_the_original(self):
        self.assertEqual(self._run(""), LINE)


if __name__ == "__main__":
    unittest.main()
