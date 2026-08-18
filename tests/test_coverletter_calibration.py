"""Unit tests for coverletter_calibration.py."""

import unittest

from coverletter_calibration import (
    detect_company_scale,
    detect_role_seniority,
    get_calibration_parameters,
)


class TestCoverletterCalibration(unittest.TestCase):

    def test_detect_role_seniority(self):
        self.assertEqual(detect_role_seniority("VP of Engineering"), "executive")
        self.assertEqual(detect_role_seniority("Staff Software Engineer"), "lead")
        self.assertEqual(detect_role_seniority("Senior Frontend Developer"), "senior")
        self.assertEqual(detect_role_seniority("Software Engineer"), "standard")

    def test_detect_company_scale(self):
        self.assertEqual(
            detect_company_scale("Acme", "Seed stage fast-growing startup"),
            "startup",
        )
        self.assertEqual(
            detect_company_scale("MegaCorp", "Fortune 500 enterprise leader"),
            "enterprise",
        )
        self.assertEqual(detect_company_scale("Stripe"), "growth")

    def test_get_calibration_parameters(self):
        exec_params = get_calibration_parameters(
            "Head of Product", "MegaCorp", "Fortune 500"
        )
        self.assertEqual(exec_params["seniority"], "executive")
        self.assertEqual(exec_params["recommended_paragraphs"], 2)
        self.assertLessEqual(exec_params["target_word_count"], 200)

        senior_params = get_calibration_parameters(
            "Senior Backend Engineer", "Acme", "Series A startup"
        )
        self.assertEqual(senior_params["seniority"], "senior")
        self.assertEqual(senior_params["recommended_paragraphs"], 3)


if __name__ == "__main__":
    unittest.main()
