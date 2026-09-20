import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import dedupe_verified_ledger as d  # noqa: E402


def _tools(*names):
    return [{"name": n, "employer": "Harbor Books"} for n in names]


class TestCategoryTokens(unittest.TestCase):
    def test_product_name_drops_category_word(self):
        merges = d.plan_tool_merges(_tools("Salesforce", "Salesforce CRM"))
        self.assertEqual(list(merges.values()), ["Salesforce CRM"])

    def test_general_skill_is_not_narrowed_into_a_crm_skill(self):
        self.assertEqual(
            d.plan_tool_merges(_tools("data quality", "CRM Data Quality")), {}
        )

    def test_vendor_prefix_still_merges(self):
        merges = d.plan_tool_merges(_tools("word", "Microsoft Word"))
        self.assertEqual(list(merges.values()), ["Microsoft Word"])


if __name__ == "__main__":
    unittest.main()
