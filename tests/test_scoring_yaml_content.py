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


if __name__ == "__main__":
    unittest.main()
