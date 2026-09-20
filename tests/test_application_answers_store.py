import json
import os
import tempfile
import unittest
from unittest.mock import patch

from scripts import jd_manager


class TestApplicationAnswerStore(unittest.TestCase):
    def test_round_trip_allowlists_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "job.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"job_title": "Role", "company_name": "Acme"}, handle)
            with patch.object(jd_manager, "_sync_jd_to_db"):
                jd_manager.save_application_answers(
                    path,
                    {
                        "items": [
                            {
                                "question": "Why?",
                                "kind": "why_company",
                                "char_limit": 500,
                                "final": "Because.",
                                "history": [
                                    {
                                        "role": "assistant",
                                        "text": "Because.",
                                        "warnings": [],
                                        "created_at": "now",
                                        "secret": "drop",
                                    }
                                ],
                                "secret": "drop",
                            }
                        ],
                        "secret": "drop",
                    },
                )
            saved = jd_manager.read_application_answers(path)
            self.assertEqual(saved["items"][0]["question"], "Why?")
            self.assertNotIn("secret", json.dumps(saved))

    def test_jd_text_strips_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "job.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"job_title": "Role", "_application_answers": {"items": []}}, handle)
            self.assertNotIn("_application_answers", jd_manager.read_jd_text(path))

    def test_non_dict_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "job.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("[]")
            with patch.object(jd_manager, "_sync_jd_to_db") as sync:
                jd_manager.save_application_answers(path, {"items": []})
            sync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
