import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from cache_monitor import calculate_cache_efficiency, format_cache_report


class TestCacheMonitor(unittest.TestCase):
    def test_calculate_cache_efficiency_zero(self):
        stats = calculate_cache_efficiency(0, 0)
        self.assertEqual(stats["total_prompt_tokens"], 0)
        self.assertEqual(stats["cache_hit_rate"], 0.0)
        self.assertEqual(stats["savings_usd"], 0.0)

    def test_calculate_cache_efficiency_partial(self):
        # 1M total tokens, 800k cached (80% hit rate)
        stats = calculate_cache_efficiency(1_000_000, 800_000)
        self.assertEqual(stats["cache_hit_rate"], 80.0)
        self.assertGreater(stats["savings_usd"], 0.0)
        self.assertEqual(stats["savings_percentage"], 60.0)

    def test_format_cache_report(self):
        stats = calculate_cache_efficiency(500_000, 400_000)
        report = format_cache_report(stats)
        self.assertIn("GEMINI CONTEXT CACHE EFFICIENCY MONITOR", report)
        self.assertIn("80.0%", report)


if __name__ == "__main__":
    unittest.main()
