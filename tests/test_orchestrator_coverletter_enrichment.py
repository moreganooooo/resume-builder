import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import profile_paths  # noqa: E402


class TestCoverLetterSchemaNewFields(unittest.TestCase):

    def test_contact_fields_default_to_empty_string(self):
        model = orchestrator.CoverLetterSchema(
            company_name="Acme", greeting="Dear Acme Corp Hiring Team,",
            body_paragraphs=["p1", "p2"], sign_off="Sincerely,",
        )
        self.assertEqual(model.contact_name, "")
        self.assertEqual(model.contact_title, "")


if __name__ == "__main__":
    unittest.main()
