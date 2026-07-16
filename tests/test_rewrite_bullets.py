import os
import sys
import unittest

import pandas as pd

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from rewrite_bullets import filter_claims_by_tags  # noqa: E402


def _claims_df():
    return pd.DataFrame({
        "Claim / Finding": [
            "Built 62+ email sequences",
            "Managed Salesforce CRM data hygiene",
            "Led content committee governance",
            "Sourced $1M+ in revenue",
            "Designed brand identity for Element 8",
        ],
        "Metric(s)": ["62 sequences", "2000+ accounts", "100+ assets", "$1M+", "N/A"],
        "Confidence": ["High", "High", "High", "High", "High"],
        "Evidence / Detail": ["", "", "", "", ""],
    })


class TestFilterClaimsByTagsMaxRows(unittest.TestCase):

    def test_default_max_rows_matches_existing_constant(self):
        df = pd.concat([_claims_df()] * 5, ignore_index=True)  # 25 rows, all [email]-matchable
        filtered = filter_claims_by_tags(df, "[email]")
        self.assertLessEqual(len(filtered), 12)  # MAX_CLAIMS_ROWS default unchanged

    def test_custom_max_rows_caps_tighter(self):
        df = pd.concat([_claims_df()] * 5, ignore_index=True)
        filtered = filter_claims_by_tags(df, "[email]", max_rows=5)
        self.assertLessEqual(len(filtered), 5)


if __name__ == "__main__":
    unittest.main()
