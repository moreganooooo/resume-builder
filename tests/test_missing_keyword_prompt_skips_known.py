import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402
import skills_menu  # noqa: E402


class TestMissingKeywordPromptSkipsKnown(unittest.TestCase):
    def test_ledger_skills_are_never_asked_again(self):
        ledger = {"tools": [{"name": "Process documentation"}]}
        asked = []
        with (
            patch.object(
                orchestrator.sys,
                "modules",
                {k: v for k, v in sys.modules.items() if k != "unittest"},
            ),
            patch.object(orchestrator.sys.stdin, "isatty", return_value=True),
            patch.object(skills_menu, "_load_verified_tools", return_value=ledger),
            patch.object(skills_menu, "_save_verified_tools") as save,
            patch.object(
                orchestrator.cli_art,
                "confirm",
                side_effect=lambda q, **k: asked.append(q) or False,
            ),
            patch.object(orchestrator.cli_art, "detail"),
        ):
            result = orchestrator.confirm_missing_coverage_keywords_interactively(
                ["Process  Documentation", "Harbor CMS"]
            )
        self.assertEqual(result, [])
        self.assertEqual(len(asked), 1)
        self.assertIn("Harbor CMS", asked[0])
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
