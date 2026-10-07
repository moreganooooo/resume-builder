import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import orchestrator  # noqa: E402
import profile_paths  # noqa: E402
import validate_resume  # noqa: E402

RULES = {"skills_section": {"line_max_chars": 110, "widow_min_chars": 25}}


def _data(*lines):
    return {"SKILLS": list(lines)}


class JdPhraseAliasTests(unittest.TestCase):

    def setUp(self):
        # The hallucinated-tool guard reads the active profile's
        # verified_tools.json, which is gitignored: a fresh clone (CI) has
        # none, so every addition here was rejected there. Point the guard
        # at a ledger vouching for this file's fixture skills instead.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with open(os.path.join(tmp.name, "verified_tools.json"), "w") as f:
            json.dump(
                {
                    "tools": [
                        {"name": n}
                        for n in [
                            "Excel",
                            "Microsoft Excel",
                            "Data Entry",
                            "Data Input",
                            "Filing",
                            "Salesforce",
                        ]
                    ]
                },
                f,
            )
        patcher = mock.patch.object(profile_paths, "kb_dir", return_value=tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_adds_microsoft_excel_beside_excel(self):
        data = _data("**Data & Systems:** Excel, Data Entry")
        out, added = orchestrator._add_jd_phrase_aliases(
            data, {"tools": ["Microsoft Excel"]}, RULES
        )
        self.assertEqual(added, ["Microsoft Excel"])
        self.assertIn("Excel, Data Entry, Microsoft Excel", out["SKILLS"][0])
        self.assertIn("Excel, Data Entry", data["SKILLS"][0])
        self.assertNotIn("Microsoft", data["SKILLS"][0])

    def test_no_evidence_no_alias(self):
        data = _data("**CRM:** Salesforce, Outreach.io")
        out, added = orchestrator._add_jd_phrase_aliases(
            data, {"tools": ["Microsoft Excel"], "hard_skills": ["Data Input"]}, RULES
        )
        self.assertEqual(added, [])
        self.assertIs(out, data)

    def test_already_present_not_duplicated(self):
        data = _data("**Data:** Excel, Microsoft Excel")
        _, added = orchestrator._add_jd_phrase_aliases(
            data, {"tools": ["Microsoft Excel"]}, RULES
        )
        self.assertEqual(added, [])

    def test_lands_on_the_row_holding_the_synonym(self):
        data = _data("**CRM:** Salesforce", "**Admin:** Data Entry, Filing")
        out, added = orchestrator._add_jd_phrase_aliases(
            data, {"hard_skills": ["Data Input"]}, RULES
        )
        self.assertEqual(added, ["Data Input"])
        self.assertTrue(out["SKILLS"][1].endswith("Data Input"))
        self.assertEqual(out["SKILLS"][0], data["SKILLS"][0])

    def test_respects_line_limit(self):
        filler = ", ".join(f"Skill{i}" for i in range(12))
        data = _data(f"**Data:** Excel, {filler}")
        out, added = orchestrator._add_jd_phrase_aliases(
            data, {"tools": ["Microsoft Excel"]}, RULES
        )
        self.assertEqual(added, [])
        self.assertIs(out, data)


class TaskOnlyBulletTests(unittest.TestCase):
    def test_flags_task_only_and_passes_results(self):
        import validate_resume

        data = {
            "EXPERIENCE": [
                {
                    "company": "USitek",
                    "achievements": [
                        "Organized records and files for the office",
                        "Updated QuickBooks records, creating audit-ready files",
                        "Coordinated fulfillment across 200+ SKUs",
                    ],
                }
            ]
        }
        flagged = validate_resume.task_only_bullets(data)
        self.assertEqual(
            flagged, [("USitek", "Organized records and files for the office")]
        )


class VerbFitTests(unittest.TestCase):
    def test_executed_with_counted_team_is_flagged(self):
        import validate_resume

        def run(text):
            return validate_resume._check_verb_fit(
                {"EXPERIENCE": [{"achievements": [text]}]}
            )

        self.assertTrue(run("Executed a 12-member team following a promotion"))
        self.assertFalse(run("Executed email campaigns for a team of 5"))


class GuardTests(unittest.TestCase):
    def test_split_compound_fragments_dropped(self):
        line = "**CRM:** Salesforce, HubSpot, Research, Routing, Automation, Hygiene, Lead Scoring"
        drops = validate_resume.skills_fragment_items(line)
        for word in ("Research", "Routing", "Automation", "Hygiene"):
            self.assertIn(word, drops)

    def test_single_standalone_word_kept(self):
        line = "**Ops:** Salesforce, Automation, Lead Routing"
        self.assertEqual(validate_resume.skills_fragment_items(line), [])

    def test_mercor_fact_in_other_role_flagged(self):
        data = {
            "EXPERIENCE": [
                {
                    "company": "Treering Yearbooks",
                    "achievements": [
                        "Refined system prompts with subject matter experts"
                    ],
                },
                {
                    "company": "Mercor",
                    "achievements": [
                        "Refined system prompts with subject matter experts"
                    ],
                },
            ]
        }
        v = validate_resume._check_mercor_only_terms(data)
        self.assertEqual(len(v), 1)
        self.assertTrue(all("Treering" in x for x in v))

    def test_self_taught_recs_filtered(self):
        import json
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "vt.json")
            json.dump(
                {"tools": [{"name": "HubSpot", "employer": "Self / Profile"}]},
                open(path, "w"),
            )
            recs = [
                "Ensure the resume highlights HubSpot prominently in the skills and experience sections",
                "Add HubSpot to the skills section",
                "Tighten the summary",
            ]
            flagged = validate_resume.recommendations_claiming_self_taught(recs, path)
            self.assertEqual(flagged, [recs[0]])


if __name__ == "__main__":
    unittest.main()
