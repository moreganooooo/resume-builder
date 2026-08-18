import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from activity_heatmap import (
    get_daily_application_counts,
    render_heatmap_ascii,
)


class TestActivityHeatmap(unittest.TestCase):

    def test_get_daily_application_counts_default(self):
        counts = get_daily_application_counts(days=14, db_path="/nonexistent/data.db")
        self.assertEqual(len(counts), 14)
        self.assertTrue(all(v == 0 for v in counts.values()))

    def test_render_heatmap_ascii(self):
        counts = {f"2026-08-{i:02d}": i % 5 for i in range(1, 29)}
        chart = render_heatmap_ascii(counts)
        self.assertIn("Application Activity Heatmap", chart)
        self.assertIn("Legend:", chart)
        self.assertIn("Mon", chart)
        self.assertIn("Fri", chart)


if __name__ == "__main__":
    unittest.main()
