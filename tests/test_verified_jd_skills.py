import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402


class TestVerifiedJdSkills(unittest.TestCase):
    def test_keeps_only_verified_tools_and_skills_in_jd_order(self):
        keywords = {
            "tools": ["Widgetron", "S3", "Gizmo Pro"],
            "hard_skills": ["Forecasting", "s3"],
            "core_functions": ["Forecasting Programs"],
        }
        ledger = ["AWS S3", "Forecasting", "Widgetron"]
        self.assertEqual(
            orchestrator.verified_jd_skills(keywords, ledger),
            ["Widgetron", "S3", "Forecasting"],
        )

    def test_empty_inputs(self):
        self.assertEqual(orchestrator.verified_jd_skills(None, ["X"]), [])
        self.assertEqual(orchestrator.verified_jd_skills({"tools": ["X"]}, []), [])


if __name__ == "__main__":
    unittest.main()
