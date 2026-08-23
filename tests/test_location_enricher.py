import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# This module used to import geo_distance/location_* with no path setup of
# its own, so it only worked when some OTHER test module happened to be
# imported first and inserted scripts/. That made it unimportable in
# isolation (`python -m unittest tests.test_location_enricher`).
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import geo_distance  # noqa: E402
import location_enricher
import location_filter


class TestLocationEnricher(unittest.TestCase):

    # -------------------------------------------------------------------------
    # A. Dynamic Context-Bound Postal & Address Regex (7 Tests)
    # -------------------------------------------------------------------------

    def test_extract_valid_local_zip(self):
        text = "Join our fast-growing engineering team in Springfield, IL 62702!"
        res = location_enricher.extract_jd_address(text, state_code="IL")
        self.assertIsNotNone(res)
        self.assertEqual(res["zip"], "62702")
        self.assertEqual(res["source"], "jd_text")

    def test_extract_street_address_block(self):
        text = (
            "The position is located at 500 Monroe St, Springfield, IL 62702 on-site."
        )
        res = location_enricher.extract_jd_address(text, state_code="IL")
        self.assertIsNotNone(res)
        self.assertEqual(res["zip"], "62702")
        self.assertIn("500 Monroe St", res["address"])

    def test_rejects_salary_numbers(self):
        text = "Annual compensation: ,000 - ,000 per year plus equity and bonus."
        res = location_enricher.extract_jd_address(text, state_code="IL")
        self.assertIsNone(res)

    def test_rejects_job_requisition_ids(self):
        text = (
            "Job Requisition ID: 62704. Please reference this number during interview."
        )
        res = location_enricher.extract_jd_address(text, state_code="IL")
        self.assertIsNone(res)

    def test_rejects_dates_and_timestamps(self):
        text = "Posted on 2026-08-14 14:22:00 UTC by talent acquisition."
        res = location_enricher.extract_jd_address(text, state_code="IL")
        self.assertIsNone(res)

    def test_rejects_statutory_and_eeo_codes(self):
        text = "Compliant with Section 62703 of municipal labor regulations."
        res = location_enricher.extract_jd_address(text, state_code="IL")
        self.assertIsNone(res)

    def test_validates_zip_against_gazetteer(self):
        # 14099 is a fictional / non-existent postal code
        text = "Located in Springfield, IL 99999."
        res = location_enricher.extract_jd_address(text, state_code="IL")
        self.assertIsNone(res)

    # -------------------------------------------------------------------------
    # B. Conflict Reconciliation & Precedence Matrix (6 Tests)
    # -------------------------------------------------------------------------

    def test_corroborated_match(self):
        discovery = {
            "address": "Springfield, IL 62702",
            "zip": "62703",
            "lat": 39.736,
            "lon": -89.6363,
            "source": "osm_nominatim",
        }
        jd_text = {
            "address": "Springfield, IL 62702",
            "zip": "62703",
            "lat": 39.736,
            "lon": -89.6363,
            "source": "jd_text",
        }
        winning, status, corr = location_enricher.reconcile_address(discovery, jd_text)
        self.assertEqual(status, "resolved")
        self.assertEqual(winning["source"], "corroborated")
        self.assertTrue(corr["match"])

    def test_jd_overrides_conflict(self):
        discovery = {
            "address": "250 Delaware Ave, Williamsville, IL 62704",
            "zip": "62704",
            "lat": 39.666,
            "lon": -89.7663,
            "source": "osm_nominatim",
        }
        jd_text = {
            "address": "500 Monroe St, Springfield, IL 62702",
            "zip": "62702",
            "lat": 39.766,
            "lon": -89.6763,
            "source": "jd_text",
        }
        winning, status, corr = location_enricher.reconcile_address(discovery, jd_text)
        self.assertEqual(status, "resolved")
        self.assertEqual(winning["source"], "jd_text_override")
        self.assertEqual(winning["zip"], "62702")
        self.assertFalse(corr["match"])

    def test_discovery_only(self):
        discovery = {
            "address": "Main St, Springfield, IL 62704",
            "zip": "62704",
            "lat": 39.736,
            "lon": -89.6963,
            "source": "osm_nominatim",
        }
        winning, status, corr = location_enricher.reconcile_address(discovery, None)
        self.assertEqual(status, "resolved")
        self.assertEqual(winning["source"], "osm_nominatim")
        self.assertEqual(winning["zip"], "62704")

    def test_jd_only(self):
        jd_text = {
            "address": "Springfield, IL 62702",
            "zip": "62703",
            "lat": 39.736,
            "lon": -89.6363,
            "source": "jd_text",
        }
        winning, status, corr = location_enricher.reconcile_address(None, jd_text)
        self.assertEqual(status, "resolved")
        self.assertEqual(winning["source"], "jd_text")
        self.assertEqual(winning["zip"], "62703")

    def test_gemini_ultra_backup(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"found": true, "address": "300 Tech Dr, Springfield, IL 62702", "zip": "62702"}'
        mock_client.generate_content_with_search.return_value = mock_response

        with patch.dict(os.environ, {"RESUME_ALLOW_TEST_NETWORK": "1"}):
            res = location_enricher.lookup_gemini_search_backup(
                "Acme Corp", "Springfield", "IL", client=mock_client
            )
            self.assertIsNotNone(res)
            self.assertEqual(res["zip"], "62702")
            self.assertEqual(res["source"], "gemini_search")

    def test_unresolved_graceful_fallback(self):
        winning, status, corr = location_enricher.reconcile_address(None, None)
        self.assertIsNone(winning)
        self.assertEqual(status, "unresolved")

    # -------------------------------------------------------------------------
    # C. Staffing Agency & Stealth Employer Guards (4 Tests)
    # -------------------------------------------------------------------------

    def test_known_agency_skips_discovery(self):
        self.assertTrue(location_enricher.is_staffing_agency("Russell Tobin"))
        self.assertTrue(location_enricher.is_staffing_agency("Apex Systems LLC"))

    def test_client_mention_skips_discovery(self):
        jd_text = (
            "On behalf of our client in Williamsville, IL we are seeking an engineer."
        )
        self.assertTrue(
            location_enricher.is_staffing_agency("Unknown Staffing", jd_text=jd_text)
        )

    def test_unresolved_agency_kept(self):
        discovery = {
            "address": "Downtown Agency HQ, Williamsville, IL 62704",
            "zip": "62704",
        }
        winning, status, corr = location_enricher.reconcile_address(
            discovery, None, is_agency=True
        )
        self.assertIsNone(winning)
        self.assertEqual(status, "unresolved_agency")

    def test_confidential_company_skips(self):
        res = location_enricher.lookup_osm_nominatim(
            "Confidential", "Springfield", "IL"
        )
        self.assertIsNone(res)
        res_stealth = location_enricher.lookup_osm_nominatim(
            "Unknown Company", "Springfield", "IL"
        )
        self.assertIsNone(res_stealth)

    # -------------------------------------------------------------------------
    # D. Multi-Branch Proximity Selection (1 Test)
    # -------------------------------------------------------------------------

    def test_selects_closest_branch(self):
        origin = "62701"  # Springfield, IL
        branches = [
            {
                "address": "Downtown Branch, Williamsville, IL 62704",
                "zip": "62704",
                "lat": 39.667,
                "lon": -89.7733,
            },  # ~11.2 mi
            {
                "address": "Cheektowaga Branch, IL 62703",
                "zip": "62703",
                "lat": 39.7,
                "lon": -89.6573,
            },  # ~7.5 mi
            {
                "address": "Amherst Branch, IL 62702",
                "zip": "62702",
                "lat": 39.772,
                "lon": -89.6843,
            },  # ~1.8 mi
        ]
        chosen = location_enricher.select_closest_branch(branches, origin)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["zip"], "62702")

    # -------------------------------------------------------------------------
    # E. Caching & Dynamic Distance Math (3 Tests)
    # -------------------------------------------------------------------------

    def test_cache_hit_prevents_network(self):
        cache = {
            "acme corp::il": {
                "address": "Springfield, IL 62702",
                "zip": "62702",
                "lat": 39.766,
                "lon": -89.6763,
                "source": "osm_nominatim",
            }
        }
        job = {"company": "Acme Corp", "location": "Williamsville, IL", "raw_text": ""}
        settings = {
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "radius_miles": 5,
        }

        with patch("location_enricher.lookup_osm_nominatim") as mock_osm:
            res = location_enricher.enrich_job_location(
                job, settings=settings, cache=cache
            )
            mock_osm.assert_not_called()
            self.assertEqual(res["status"], "resolved")
            self.assertEqual(res["resolved_zip"], "62702")

    def test_cache_stores_points_not_miles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "company_locations.json")
            cache = {
                "test_co::il": {
                    "address": "123 Main",
                    "zip": "62702",
                    "lat": 39.766,
                    "lon": -89.6763,
                }
            }
            with open(cache_file, "w") as f:
                json.dump(cache, f)
            with open(cache_file, "r") as f:
                loaded = json.load(f)
            entry = loaded["test_co::il"]
            self.assertIn("lat", entry)
            self.assertIn("lon", entry)
            self.assertNotIn("distance_miles", entry)

    def test_distance_recalculates_on_origin_change(self):
        job = {"company": "Acme Corp", "location": "Williamsville, IL"}
        cache = {
            "acme corp::il": {
                "address": "Springfield, IL 62702",
                "zip": "62702",
                "lat": 39.8317,
                "lon": -89.6465,
                "source": "osm_nominatim",
            }
        }

        # Origin 1: 62701 (downtown Springfield) -> ~2.2 miles
        settings_1 = {
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "radius_miles": 5,
        }
        res_1 = location_enricher.enrich_job_location(
            job, settings=settings_1, cache=cache
        )
        dist_1 = res_1["distance_miles"]
        self.assertIsNotNone(dist_1)
        self.assertLess(dist_1, 3.0)

        # Origin 2: a nearby town, same cached job point -> ~8.3 miles.
        # The point of the test is that the distance is recomputed from the
        # CURRENT origin rather than cached alongside the address.
        settings_2 = {
            "city": "Rochester",
            "state": "IL",
            "zip": "62563",
            "radius_miles": 15,
        }
        res_2 = location_enricher.enrich_job_location(
            job, settings=settings_2, cache=cache
        )
        dist_2 = res_2["distance_miles"]
        self.assertIsNotNone(dist_2)
        self.assertGreater(dist_2, 6.0)

    # -------------------------------------------------------------------------
    # F. Guardrails & Test Isolation (3 Tests)
    # -------------------------------------------------------------------------

    def test_blocked_under_tests_guard(self):
        # Without RESUME_ALLOW_TEST_NETWORK, network lookups return None/empty
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(location_enricher._blocked_under_tests())
            self.assertIsNone(
                location_enricher.lookup_osm_nominatim(
                    "Real Company", "Springfield", "IL"
                )
            )
            self.assertEqual(
                location_enricher.scrape_company_locations("https://example.com", "NY"),
                [],
            )
            self.assertIsNone(
                location_enricher.lookup_gemini_search_backup(
                    "Real Company", "Springfield", "IL"
                )
            )

    def test_remote_jobs_bypass_enrichment(self):
        job = {
            "company": "Acme Corp",
            "location": "Anywhere, US (Remote)",
            "is_remote": True,
        }
        settings = {
            "city": "Springfield",
            "state": "IL",
            "zip": "62701",
            "radius_miles": 5,
        }
        with patch("location_enricher.lookup_osm_nominatim") as mock_osm:
            res = location_enricher.enrich_job_location(job, settings=settings)
            mock_osm.assert_not_called()
            self.assertEqual(res["status"], "bypassed_remote")
            self.assertIsNone(res["distance_miles"])

    def test_gemini_quota_cap(self):
        # Simulates batch execution capping at max_search_calls on success
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = (
            '{"found": true, "address": "Williamsville, IL 62704", "zip": "62704"}'
        )
        mock_client.generate_content_with_search.return_value = mock_response

        with patch.dict(os.environ, {"RESUME_ALLOW_TEST_NETWORK": "1"}):
            with (
                patch("db.get_db") as mock_db,
                patch("db.checkpoint"),
                patch("jd_manager.get_pending_jds", return_value=[]),
                patch("jd_manager.get_completed_jds", return_value=[]),
            ):
                conn = MagicMock()
                # 15 unresolvable jobs in db
                rows = [
                    {
                        "id": f"job_{i}",
                        "title": "Eng",
                        "company": f"Co_{i}",
                        "location": "Williamsville, IL",
                        "raw_text": "",
                        "metadata_json": "{}",
                    }
                    for i in range(15)
                ]
                conn.execute.return_value.fetchall.return_value = rows
                mock_db.return_value = conn

                with (
                    patch("location_enricher.lookup_osm_nominatim", return_value=None),
                    patch("location_enricher.load_locations_cache", return_value={}),
                    patch("location_enricher.save_locations_cache"),
                    patch("gemini_client.GeminiClient", return_value=mock_client),
                    patch(
                        "location_settings.read_settings",
                        return_value={
                            "city": "Buffalo",
                            "state": "IL",
                            "zip": "62701",
                            "radius_miles": 5,
                        },
                    ),
                ):

                    summary = location_enricher.enrich_profile_locations(
                        statuses=["pending"],
                        allow_search_backup=True,
                        max_search_calls=10,
                    )
                    self.assertEqual(summary["search_calls_used"], 10)
                    self.assertEqual(
                        mock_client.generate_content_with_search.call_count, 10
                    )

    def test_gemini_quota_cap_counts_failed_attempts(self):
        # Simulates batch execution where Gemini fails/returns found=false; attempts MUST still count against quota
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"found": false}'
        mock_client.generate_content_with_search.return_value = mock_response

        with patch.dict(os.environ, {"RESUME_ALLOW_TEST_NETWORK": "1"}):
            with (
                patch("db.get_db") as mock_db,
                patch("db.checkpoint"),
                patch("jd_manager.get_pending_jds", return_value=[]),
                patch("jd_manager.get_completed_jds", return_value=[]),
            ):
                conn = MagicMock()
                # 15 unresolvable jobs in db
                rows = [
                    {
                        "id": f"job_fail_{i}",
                        "title": "Eng",
                        "company": f"ObscureCo_{i}",
                        "location": "Williamsville, IL",
                        "raw_text": "",
                        "metadata_json": "{}",
                    }
                    for i in range(15)
                ]
                conn.execute.return_value.fetchall.return_value = rows
                mock_db.return_value = conn

                with (
                    patch("location_enricher.lookup_osm_nominatim", return_value=None),
                    patch("location_enricher.load_locations_cache", return_value={}),
                    patch("location_enricher.save_locations_cache"),
                    patch("gemini_client.GeminiClient", return_value=mock_client),
                    patch(
                        "location_settings.read_settings",
                        return_value={
                            "city": "Buffalo",
                            "state": "IL",
                            "zip": "62701",
                            "radius_miles": 5,
                        },
                    ),
                ):

                    summary = location_enricher.enrich_profile_locations(
                        statuses=["pending"],
                        allow_search_backup=True,
                        max_search_calls=10,
                    )
                    self.assertEqual(summary["search_calls_used"], 10)
                    self.assertEqual(
                        mock_client.generate_content_with_search.call_count, 10
                    )
                    self.assertEqual(summary["resolved"], 0)

    def test_file_based_jd_enrichment_persistence(self):
        # Verify enrich_profile_locations writes _location_enrichment to the file on disk
        import shutil
        import tempfile

        import jd_manager

        tmp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp_dir, ignore_errors=True)
        jd_file = os.path.join(tmp_dir, "test_job.json")
        data = {
            "title": "Software Engineer",
            "company": "Local Innovators",
            "location": "Williamsville, IL",
            "raw_text": "Work at our headquarters at 175 Hampton Pkwy, Springfield, IL 62702.",
        }
        with open(jd_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        with patch("db.get_db") as mock_db, patch("db.checkpoint"):
            conn = MagicMock()
            conn.execute.return_value.fetchall.return_value = []
            mock_db.return_value = conn

            with (
                patch("location_enricher.load_locations_cache", return_value={}),
                patch("location_enricher.save_locations_cache"),
                patch("jd_manager.get_pending_jds", return_value=[jd_file]),
                patch("jd_manager.get_completed_jds", return_value=[]),
                patch(
                    "location_settings.read_settings",
                    return_value={
                        "city": "Buffalo",
                        "state": "IL",
                        "zip": "62701",
                        "radius_miles": 5,
                    },
                ),
            ):

                summary = location_enricher.enrich_profile_locations(
                    statuses=["pending"]
                )
                self.assertEqual(summary["total_processed"], 1)
                self.assertEqual(summary["resolved"], 1)

                persisted = jd_manager.read_location_enrichment(jd_file)
                self.assertIsNotNone(persisted)
                self.assertEqual(persisted["status"], "resolved")
                self.assertEqual(persisted["resolved_zip"], "62702")
                self.assertEqual(persisted["source"], "jd_text")


if __name__ == "__main__":
    unittest.main()
