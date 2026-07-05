import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import situational_roles  # noqa: E402


class TestDetectSituationalCandidates(unittest.TestCase):

    def test_no_match_on_ordinary_marketing_jd(self):
        jd_text = "We're hiring a Lifecycle Marketing Manager to own our email campaigns and CRM strategy."
        self.assertEqual(situational_roles.detect_situational_candidates(jd_text), [])

    def test_matches_humane_society_on_animal_welfare_language(self):
        jd_text = "Join our animal welfare team supporting shelter operations and adoption events."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("Humane Society of Greater Kansas City", candidates)

    def test_matches_unisource_on_print_production_language(self):
        jd_text = "Seeking a coordinator experienced in print production and document management workflows."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("Unisource Document Products", candidates)

    def test_matches_kansas_colloquies_on_journalism_language(self):
        jd_text = "We need a reporter for our newspaper's editorial team covering local news."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("Kansas Colloquies", candidates)

    def test_matches_ku_payroll_office_on_payroll_language(self):
        jd_text = "This role handles payroll processing and payroll administration for a mid-size firm."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("KU Payroll Office", candidates)

    def test_matches_dejoy_on_tax_accounting_language(self):
        jd_text = "Looking for a bookkeeping specialist to support tax preparation and audit readiness."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("DeJoy, Knauff & Blood", candidates)

    def test_matches_usitek_only_on_combined_clerical_and_design_language(self):
        jd_text = "This role blends administrative support with hands-on graphic design work for local retail clients."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("USitek", candidates)

    def test_does_not_match_usitek_on_design_language_alone(self):
        jd_text = "We're looking for a talented graphic designer to build our brand identity system."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertNotIn("USitek", candidates)

    def test_does_not_match_usitek_on_clerical_language_alone(self):
        jd_text = "This administrative support role handles scheduling, filing, and clerical correspondence."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertNotIn("USitek", candidates)

    def test_can_return_multiple_candidates(self):
        jd_text = "Reporter role covering local newspaper journalism, plus occasional payroll processing support."
        candidates = situational_roles.detect_situational_candidates(jd_text)
        self.assertIn("Kansas Colloquies", candidates)
        self.assertIn("KU Payroll Office", candidates)


class TestBankMinimumsFor(unittest.TestCase):

    def test_maps_display_names_to_bank_tags_with_minimum_of_2(self):
        minimums = situational_roles.bank_minimums_for(["KU Payroll Office", "DeJoy, Knauff & Blood"])
        self.assertEqual(minimums, {"Payroll": 2, "DeJoy": 2})

    def test_empty_candidates_returns_empty_dict(self):
        self.assertEqual(situational_roles.bank_minimums_for([]), {})
