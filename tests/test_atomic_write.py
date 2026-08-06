import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

from atomic_write import atomic_write  # noqa: E402


class TestAtomicWrite(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_atomic_write")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.path = os.path.join(self.tmp_dir, "target.txt")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def test_creates_a_new_file(self):
        with atomic_write(self.path) as f:
            f.write("hello")
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "hello")

    def test_replaces_existing_content_on_success(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("old content, much longer than the new content")
        with atomic_write(self.path) as f:
            f.write("new")
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "new")

    def test_leaves_original_untouched_on_exception_mid_write(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("original")

        with self.assertRaises(RuntimeError):
            with atomic_write(self.path) as f:
                f.write("partial")
                raise RuntimeError("boom")

        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "original")

    def test_no_leftover_temp_file_after_success(self):
        with atomic_write(self.path) as f:
            f.write("hello")
        self.assertEqual(os.listdir(self.tmp_dir), ["target.txt"])

    def test_no_leftover_temp_file_after_failure(self):
        with self.assertRaises(RuntimeError):
            with atomic_write(self.path) as f:
                f.write("partial")
                raise RuntimeError("boom")
        self.assertEqual(os.listdir(self.tmp_dir), [])

    def test_never_leaves_a_zero_byte_file_behind_on_failure(self):
        # The exact bug B13 documents: open(path, "w") truncates at open,
        # before any write happens. atomic_write() must never expose that
        # window at the real path, even on failure.
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("original, not zero bytes")

        with self.assertRaises(RuntimeError):
            with atomic_write(self.path) as f:
                raise RuntimeError("boom before a single byte is written")

        self.assertGreater(os.path.getsize(self.path), 0)

    def test_supports_open_kwargs_like_newline_and_encoding(self):
        with atomic_write(self.path, newline="", encoding="utf-8") as f:
            f.write("a,b,c\r\n")
        with open(self.path, newline="", encoding="utf-8") as f:
            self.assertEqual(f.read(), "a,b,c\r\n")


if __name__ == "__main__":
    unittest.main()
