"""Tests for scripts/jd_image_ingest.py -- converting a screenshot/PDF job
posting into a normal JSON JD file via Gemini's vision input.

All Gemini calls are mocked; nothing here reaches the real network.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import jd_image_ingest  # noqa: E402
import profile_paths  # noqa: E402


class TestMimeType(unittest.TestCase):
    def test_pdf(self):
        self.assertEqual(jd_image_ingest._mime_type("x.pdf"), "application/pdf")

    def test_png(self):
        self.assertEqual(jd_image_ingest._mime_type("x.png"), "image/png")

    def test_jpg_and_jpeg(self):
        self.assertEqual(jd_image_ingest._mime_type("x.jpg"), "image/jpeg")
        self.assertEqual(jd_image_ingest._mime_type("x.jpeg"), "image/jpeg")

    def test_case_insensitive(self):
        self.assertEqual(jd_image_ingest._mime_type("x.PDF"), "application/pdf")


class TestUnwrapImagePdf(unittest.TestCase):
    def _pdf_bytes(self, *images):
        import io

        buf = io.BytesIO()
        images[0].save(buf, format="PDF", save_all=True, append_images=list(images[1:]))
        return buf.getvalue()

    def test_single_image_page_becomes_png(self):
        from PIL import Image

        out = jd_image_ingest._unwrap_image_pdf(self._pdf_bytes(Image.new("RGB", (40, 90))))
        self.assertIsNotNone(out)
        self.assertEqual(out[1], "image/png")

    def test_multi_page_pdf_is_left_alone(self):
        from PIL import Image

        pdf = self._pdf_bytes(Image.new("RGB", (40, 90)), Image.new("RGB", (40, 90)))
        self.assertIsNone(jd_image_ingest._unwrap_image_pdf(pdf))

    def test_non_pdf_bytes_are_left_alone(self):
        self.assertIsNone(jd_image_ingest._unwrap_image_pdf(b"not a pdf"))


class TestDedupeStems(unittest.TestCase):
    def test_pdf_wins_over_png_for_same_stem(self):
        paths = ["/a/job.png", "/a/job.pdf"]
        self.assertEqual(jd_image_ingest._dedupe_stems(paths), ["/a/job.pdf"])

    def test_order_preserved_across_stems(self):
        paths = ["/a/one.png", "/a/two.pdf", "/a/one.pdf"]
        # "one" resolves to its .pdf, but keeps its FIRST-seen position
        self.assertEqual(
            jd_image_ingest._dedupe_stems(paths), ["/a/one.pdf", "/a/two.pdf"]
        )

    def test_no_collision_keeps_both(self):
        paths = ["/a/one.pdf", "/a/two.png"]
        self.assertEqual(jd_image_ingest._dedupe_stems(paths), paths)


class TestDiscoverFiles(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _touch(self, name):
        path = os.path.join(self.tmp_dir, name)
        with open(path, "w") as f:
            f.write("x")
        return path

    def test_scans_directory_non_recursively(self):
        self._touch("a.pdf")
        self._touch("b.png")
        self._touch("c.txt")  # unsupported, silently skipped for dir scans
        os.makedirs(os.path.join(self.tmp_dir, "nested"))
        with open(os.path.join(self.tmp_dir, "nested", "d.pdf"), "w") as f:
            f.write("x")
        found = jd_image_ingest.discover_files([self.tmp_dir])
        self.assertEqual(len(found), 2)
        self.assertTrue(all(f.endswith((".pdf", ".png")) for f in found))

    def test_explicit_unsupported_file_reports_error(self):
        path = self._touch("resume.docx")
        with patch("jd_image_ingest.cli_art.cli_error") as mock_error:
            found = jd_image_ingest.discover_files([path])
        self.assertEqual(found, [])
        mock_error.assert_called_once()

    def test_nonexistent_source_reports_error(self):
        with patch("jd_image_ingest.cli_art.cli_error") as mock_error:
            found = jd_image_ingest.discover_files(["/nonexistent/path"])
        self.assertEqual(found, [])
        mock_error.assert_called_once()


FAKE_EXTRACTION = {
    "job_title": "Data Analytics Engineer",
    "company_name": "Tesla",
    "location": "Buffalo, NY",
    "source_url": "",
    "is_remote": False,
    "description": "Full job posting body text.",
    "is_partial": False,
}


class TestExtractJdFromImage(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.image_path = os.path.join(self.tmp_dir, "job.png")
        with open(self.image_path, "wb") as f:
            f.write(b"\x89PNG fake bytes")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_happy_path_returns_job_dict_in_shared_shape(self):
        import orchestrator

        fake_engine = MagicMock()
        fake_engine.load_prompt.return_value = "prompt text"
        with patch.object(
            orchestrator.GeminiClient,
            "generate",
            return_value=(json.dumps(FAKE_EXTRACTION), {}),
        ) as mock_generate:
            job = jd_image_ingest.extract_jd_from_image(
                self.image_path, engine=fake_engine
            )

        self.assertNotIn("_ingest_error", job)
        self.assertEqual(job["job_title"], "Data Analytics Engineer")
        self.assertEqual(job["company_name"], "Tesla")
        self.assertEqual(job["source_platform"], "manual-screenshot")
        self.assertIsNone(job["source_job_id"])
        self.assertEqual(job["description"], "Full job posting body text.")
        self.assertNotIn("_ingest_partial", job)

        # inline_file must carry the real bytes and correct mime type
        kwargs = mock_generate.call_args.kwargs
        self.assertEqual(kwargs["inline_file"][1], "image/png")
        self.assertEqual(kwargs["inline_file"][0], b"\x89PNG fake bytes")

    def test_screencapture_pdf_is_sent_as_its_embedded_png(self):
        # A PDF page is rasterized at low resolution; the wrapped screenshot
        # at native size is what made a real Tesla posting's digits readable.
        import io

        import orchestrator
        from PIL import Image

        pdf_path = os.path.join(self.tmp_dir, "job.pdf")
        Image.new("RGB", (200, 300), "white").save(pdf_path, format="PDF")
        fake_engine = MagicMock()
        fake_engine.load_prompt.return_value = "prompt text"
        with patch.object(
            orchestrator.GeminiClient,
            "generate",
            return_value=(json.dumps(FAKE_EXTRACTION), {}),
        ) as mock_generate:
            jd_image_ingest.extract_jd_from_image(pdf_path, engine=fake_engine)

        sent_bytes, sent_mime = mock_generate.call_args.kwargs["inline_file"]
        self.assertEqual(sent_mime, "image/png")
        self.assertEqual(Image.open(io.BytesIO(sent_bytes)).size, (200, 300))

    def test_partial_flag_is_preserved(self):
        import orchestrator

        fake_engine = MagicMock()
        fake_engine.load_prompt.return_value = "prompt text"
        partial = dict(FAKE_EXTRACTION, is_partial=True)
        with patch.object(
            orchestrator.GeminiClient, "generate", return_value=(json.dumps(partial), {})
        ):
            job = jd_image_ingest.extract_jd_from_image(
                self.image_path, engine=fake_engine
            )
        self.assertTrue(job["_ingest_partial"])

    def test_gemini_failure_returns_ingest_error_not_raise(self):
        import orchestrator

        fake_engine = MagicMock()
        fake_engine.load_prompt.return_value = "prompt text"
        with patch.object(
            orchestrator.GeminiClient, "generate", side_effect=RuntimeError("blocked")
        ):
            job = jd_image_ingest.extract_jd_from_image(
                self.image_path, engine=fake_engine
            )
        self.assertIn("_ingest_error", job)
        self.assertIn("blocked", job["_ingest_error"])

    def test_empty_extraction_is_treated_as_an_error(self):
        import orchestrator

        fake_engine = MagicMock()
        fake_engine.load_prompt.return_value = "prompt text"
        empty = {
            "job_title": "",
            "company_name": "",
            "location": "",
            "source_url": "",
            "is_remote": None,
            "description": "",
            "is_partial": False,
        }
        with patch.object(
            orchestrator.GeminiClient, "generate", return_value=(json.dumps(empty), {})
        ):
            job = jd_image_ingest.extract_jd_from_image(
                self.image_path, engine=fake_engine
            )
        self.assertIn("_ingest_error", job)

    def test_unreadable_file_returns_ingest_error(self):
        job = jd_image_ingest.extract_jd_from_image("/nonexistent/x.png")
        self.assertIn("_ingest_error", job)


class TestIngestOne(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.sandbox = tempfile.mkdtemp()
        self.image_path = os.path.join(self.tmp_dir, "job.png")
        with open(self.image_path, "wb") as f:
            f.write(b"fake image bytes")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def test_writes_json_and_removes_source_on_success(self):
        with profile_paths.isolate_for_tests(self.sandbox):
            with patch.object(
                jd_image_ingest,
                "extract_jd_from_image",
                return_value=dict(FAKE_EXTRACTION, source_platform="manual-screenshot"),
            ):
                dest = jd_image_ingest.ingest_one(self.image_path, profile="alice")

            self.assertIsNotNone(dest)
            self.assertTrue(os.path.exists(dest))
            self.assertFalse(os.path.exists(self.image_path))
            with open(dest) as f:
                data = json.load(f)
            self.assertEqual(data["company_name"], "Tesla")
            self.assertIn(profile_paths.jds_dir("alice"), dest)

    def test_failure_leaves_source_file_in_place(self):
        with profile_paths.isolate_for_tests(self.sandbox):
            with patch.object(
                jd_image_ingest,
                "extract_jd_from_image",
                return_value={"_ingest_error": "boom", "_ingest_source": self.image_path},
            ):
                dest = jd_image_ingest.ingest_one(self.image_path, profile="alice")

            self.assertIsNone(dest)
            self.assertTrue(os.path.exists(self.image_path))

    def test_success_also_removes_same_stem_sibling(self):
        pdf_path = os.path.join(self.tmp_dir, "job.pdf")
        with open(pdf_path, "wb") as f:
            f.write(b"fake pdf bytes")
        with profile_paths.isolate_for_tests(self.sandbox):
            with patch.object(
                jd_image_ingest, "extract_jd_from_image", return_value=dict(FAKE_EXTRACTION)
            ):
                dest = jd_image_ingest.ingest_one(pdf_path, profile="alice")
        self.assertIsNotNone(dest)
        self.assertFalse(os.path.exists(pdf_path))
        self.assertFalse(os.path.exists(self.image_path))
        self.assertEqual(jd_image_ingest.discover_files([self.tmp_dir]), [])

    def test_filename_collision_gets_a_counter_suffix(self):
        with profile_paths.isolate_for_tests(self.sandbox):
            jds_dir = profile_paths.jds_dir("alice")
            os.makedirs(jds_dir, exist_ok=True)
            import datetime

            today = datetime.date.today().isoformat()
            existing = os.path.join(jds_dir, f"{today}_Tesla_DataAnalyticsEngineer.json")
            with open(existing, "w") as f:
                f.write("{}")

            with patch.object(
                jd_image_ingest, "extract_jd_from_image", return_value=dict(FAKE_EXTRACTION)
            ):
                dest = jd_image_ingest.ingest_one(self.image_path, profile="alice")

            self.assertIsNotNone(dest)
            self.assertNotEqual(dest, existing)
            self.assertTrue(os.path.exists(existing))  # original untouched


if __name__ == "__main__":
    unittest.main()
