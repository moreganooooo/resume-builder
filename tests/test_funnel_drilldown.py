"""
test_funnel_drilldown.py — Unit tests for recruitment funnel drilldown and bottleneck diagnostics.
"""

import os
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import db
import funnel_drilldown
import profile_paths
from rich.console import Console


class TestFunnelDrilldown(unittest.TestCase):
    def test_compute_funnel_metrics_isolated_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            profile_paths.isolate_for_tests(tmpdir)
            conn = db.get_db("test_user")
            try:
                conn.execute("DELETE FROM jobs;")
                # Discovered / Evaluated
                conn.execute(
                    "INSERT INTO jobs (id, company, title, raw_text, final_score, status) VALUES "
                    "('job-1', 'Acme', 'Lead', 'raw 1', 4.2, 'applied'),"
                    "('job-2', 'Beta', 'Senior', 'raw 2', 4.6, 'interview'),"
                    "('job-3', 'Gamma', 'Manager', 'raw 3', 3.2, 'pending'),"
                    "('job-4', 'Delta', 'Director', 'raw 4', NULL, 'pending');"
                )
                conn.commit()
            finally:
                conn.close()

            metrics = funnel_drilldown.compute_funnel_metrics(profile="test_user")
            self.assertEqual(metrics["stages"]["discovered"], 4)
            self.assertEqual(metrics["stages"]["evaluated"], 3)
            self.assertEqual(metrics["stages"]["high_fit"], 2)
            self.assertEqual(metrics["stages"]["applied"], 2)
            self.assertEqual(metrics["stages"]["interview"], 1)

            # Test render output
            c = Console(record=True)
            funnel_drilldown.render_funnel_drilldown(metrics, console=c)
            rendered = c.export_text()
            self.assertIn("APPLICATION FUNNEL DRILL-DOWN", rendered)
            self.assertIn("Discovered", rendered)


if __name__ == "__main__":
    unittest.main()
