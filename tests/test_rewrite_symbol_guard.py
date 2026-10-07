import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import orchestrator  # noqa: E402


class RewriteSpellsOutSymbolsTests(unittest.TestCase):
    def test_flags_plus_sign_spelled_out(self):
        self.assertTrue(
            orchestrator.rewrite_spells_out_symbols(
                "Audited 2,933+ accounts", "Audited 2,933 plus accounts"
            )
        )

    def test_flags_apostrophe_spelled_out(self):
        self.assertTrue(
            orchestrator.rewrite_spells_out_symbols(
                "Corrected forms for Hill's Pet Nutrition",
                "Corrected forms for Hill plus s Pet Nutrition",
            )
        )

    def test_allows_plus_already_in_original(self):
        self.assertFalse(
            orchestrator.rewrite_spells_out_symbols(
                "Plus-tier upsell program", "Led the Plus-tier upsell program"
            )
        )

    def test_clean_rewrite_passes(self):
        self.assertFalse(
            orchestrator.rewrite_spells_out_symbols(
                "Audited 2,933+ accounts", "Audited 2,933+ accounts"
            )
        )

    def test_choose_audited_rewrite_keeps_original(self):
        crit = {"believability_score": 50}
        bullet, _ = orchestrator.ResumeEngine._choose_audited_rewrite(
            "Audited 2,933+ accounts",
            "Audited 2,933 plus accounts",
            crit,
            {"believability_score": 99},
            "Treering",
            "ops",
        )
        self.assertEqual(bullet, "Audited 2,933+ accounts")


if __name__ == "__main__":
    unittest.main()


class RewriteDropsMetricsTests(unittest.TestCase):
    def test_flags_dropped_percentage(self):
        self.assertEqual(
            orchestrator.rewrite_drops_metrics(
                "Digitized payroll records, reducing retrieval time by 75%",
                "Organized physical payroll records to maintain efficiency",
            ),
            ["75%"],
        )

    def test_kept_metric_passes_even_without_plus(self):
        self.assertEqual(
            orchestrator.rewrite_drops_metrics(
                "Streamlined fulfillment of 200+ SKUs with 100% on-time delivery",
                "Coordinated fulfillment across 200 SKUs, achieving 100% on-time delivery",
            ),
            [],
        )

    def test_choose_keeps_original_when_metric_dropped(self):
        crit = {"scores": {}}
        bullet = "Resolved 95% of payroll inquiries without escalation"
        got, _ = orchestrator.ResumeEngine._choose_audited_rewrite(
            bullet, "Resolved payroll inquiries securely", crit, crit, "KU", "[x]"
        )
        self.assertEqual(got, bullet)
