import os
import unittest

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCORING_DIR = os.path.join(PROJECT_ROOT, "resume-engine", "scoring")


def _load(filename):
    with open(os.path.join(SCORING_DIR, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestSpecificityYamlIsEducationOnly(unittest.TestCase):

    def test_competencies_score_file_no_longer_exists(self):
        self.assertFalse(os.path.exists(os.path.join(SCORING_DIR, "competencies_score.yaml")))

    def test_specificity_yaml_has_no_project_criteria(self):
        data = _load("specificity.yaml")
        self.assertNotIn("project_description_specificity", data["criteria"])
        self.assertNotIn("project_tech_specificity", data["criteria"])
        self.assertIn("education_description_specificity", data["criteria"])

    def test_specificity_yaml_has_no_project_penalties_or_bonuses(self):
        data = _load("specificity.yaml")
        self.assertNotIn("generic_project_description", data["penalties"])
        self.assertNotIn("generic_project_tech", data["penalties"])
        self.assertNotIn("named_outcome", data.get("bonuses", {}))
        self.assertNotIn("named_system_or_stack", data.get("bonuses", {}))

    def test_education_score_file_no_longer_exists(self):
        self.assertFalse(os.path.exists(os.path.join(SCORING_DIR, "education_score.yaml")))


class TestFlagsBlocksParseAsLists(unittest.TestCase):
    """B47: `flags:` was written as a bare indented block with no `- ` markers,
    so yaml.safe_load returned a single space-joined scalar. summary_score and
    top_third_score are the only two scoring files attached to a live API call,
    and json.dumps() serialised that mangled string straight into the critique
    prompt -- the model was shown a run-on token string where a controlled flag
    vocabulary was intended. Checks every rubric, not just the known-bad ones,
    so a new file can't reintroduce the same shape."""

    def test_every_flags_block_is_a_list_of_nonempty_strings(self):
        offenders = []
        for filename in sorted(os.listdir(SCORING_DIR)):
            if not filename.endswith((".yaml", ".yml")):
                continue
            data = _load(filename)
            if not isinstance(data, dict) or "flags" not in data:
                continue
            flags = data["flags"]
            if not isinstance(flags, list) or not flags:
                offenders.append(f"{filename}: {type(flags).__name__}")
                continue
            for flag in flags:
                if not isinstance(flag, str) or not flag.strip() or " " in flag.strip():
                    offenders.append(f"{filename}: bad entry {flag!r}")
        self.assertEqual(offenders, [], f"flags blocks that don't parse as a flag list: {offenders}")

    def test_the_two_live_rubrics_expose_their_real_flag_vocabulary(self):
        # These two are what orchestrator.py actually attaches to the critique
        # call, so their shape is the one that reaches a model today.
        self.assertIn("generic_summary", _load("summary_score.yaml")["flags"])
        self.assertIn("unclear_identity", _load("top_third_score.yaml")["flags"])


if __name__ == "__main__":
    unittest.main()
