import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from bullet_bank_hash import bullets_sha  # noqa: E402


class TestBulletsSha(unittest.TestCase):

    def test_deterministic_across_calls(self):
        texts = ["Recovered $3M in pipeline", "Founded the Content Committee"]
        self.assertEqual(bullets_sha(texts), bullets_sha(list(texts)))

    def test_changes_if_a_single_bullet_edits(self):
        original = ["Recovered $3M in pipeline", "Founded the Content Committee"]
        edited = ["Recovered $4M in pipeline", "Founded the Content Committee"]
        self.assertNotEqual(bullets_sha(original), bullets_sha(edited))

    def test_changes_if_row_order_changes(self):
        a = ["First bullet", "Second bullet"]
        b = ["Second bullet", "First bullet"]
        self.assertNotEqual(bullets_sha(a), bullets_sha(b))

    def test_changes_if_a_row_is_added_or_removed(self):
        shorter = ["First bullet"]
        longer = ["First bullet", "Second bullet"]
        self.assertNotEqual(bullets_sha(shorter), bullets_sha(longer))

    def test_empty_list_does_not_raise(self):
        bullets_sha([])  # must not raise


if __name__ == "__main__":
    unittest.main()
