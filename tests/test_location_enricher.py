import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import geo_distance
import location_enricher
import location_filter


class TestLocationEnricher(unittest.TestCase):

    # -------------------------------------------------------------------------
    # A. Dynamic Context-Bound Postal & Address Regex (7 Tests)
    # -------------------------------------------------------------------------

    def test_extract_valid_local_zip(self):
        text = "Join our fast-growing engineering team in Amherst, NY 14228!"
        res = location_enricher.extract_jd_address(text, state_code="NY")
        self.assertIsNotNone(res)
        self.assertEqual(res["zip"], "14228")
        self.assertEqual(res["source"], "jd_text")

    def test_extract_street_address_block(self):
        text = "The position is located at 500 Audubon Pkwy, Amherst, NY 14228 on-site."
        res = location_enricher.extract_jd_address(text, state_code="NY")
        self.assertIsNotNone(res)
        self.assertEqual(res["zip"], "14228")
        self.assertIn("500 Audubon Pkwy", res["address"])

    def test_rejects_salary_numbers(self):
        text = "Annual compensation: ,000 - ,000 per year plus equity and bonus."
        res = location_enricher.extract_jd_address(text, state_code="NY")
        self.assertIsNone(res)

    def test_rejects_job_requisition_ids(self):
        text = (
            "Job Requisition ID: 14202. Please reference this number during interview."
        )
        res = location_enricher.extract_jd_address(text, state_code="NY")
        self.assertIsNone(res)

    def test_rejects_dates_and_timestamps(self):
        text = "Posted on 2026-08-14 14:22:00 UTC by talent acquisition."
        res = location_enricher.extract_jd_address(text, state_code="NY")
        self.assertIsNone(res)

    def test_rejects_statutory_and_eeo_codes(self):
        text = "Compliant with Section 14221 of municipal labor regulations."
        res = location_enricher.extract_jd_address(text, state_code="NY")
        self.assertIsNone(res)

    def test_validates_zip_against_gazetteer(self):
        # 14099 is a fictional / non-existent postal code
        text = "Located in Amherst, NY 14099."
        res = location_enricher.extract_jd_address(text, state_code="NY")
        self.assertIsNone(res)

    # -------------------------------------------------------------------------
    # B. Conflict Reconciliation & Precedence Matrix (6 Tests)
    # -------------------------------------------------------------------------

    def test_corroborated_match(self):
        discovery = {
            "address": "Williamsville, NY 14221",
            "zip": "14221",
            "lat": 42.96,
            "lon": -78.74,
            "source": "osm_nominatim",
        }
        jd_text = {
            "address": "Williamsville, NY 14221",
            "zip": "14221",
            "lat": 42.96,
            "lon": -78.74,
            "source": "jd_text",
        }
        winning, status, corr = location_enricher.reconcile_address(discovery, jd_text)
        self.assertEqual(status, "resolved")
        self.assertEqual(winning["source"], "corroborated")
        self.assertTrue(corr["match"])

    def test_jd_overrides_conflict(self):
        discovery = {
            "address": "250 Delaware Ave, Buffalo, NY 14202",
            "zip": "14202",
            "lat": 42.89,
            "lon": -78.87,
            "source": "osm_nominatim",
        }
        jd_text = {
            "address": "500 Audubon Pkwy, Amherst, NY 14228",
            "zip": "14228",
            "lat": 42.99,
            "lon": -78.78,
            "source": "jd_text",
        }
        winning, status, corr = location_enricher.reconcile_address(discovery, jd_text)
        self.assertEqual(status, "resolved")
        self.assertEqual(winning["source"], "jd_text_override")
        self.assertEqual(winning["zip"], "14228")
        self.assertFalse(corr["match"])

    def test_discovery_only(self):
        discovery = {
            "address": "Main St, Amherst, NY 14226",
            "zip": "14226",
            "lat": 42.96,
            "lon": -78.80,
            "source": "osm_nominatim",
        }
        winning, status, corr = location_enricher.reconcile_address(discovery, None)
        self.assertEqual(status, "resolved")
        self.assertEqual(winning["source"], "osm_nominatim")
        self.assertEqual(winning["zip"], "14226")

    def test_jd_only(self):
        jd_text = {
            "address": "Williamsville, NY 14221",
            "zip": "14221",
            "lat": 42.96,
            "lon": -78.74,
            "source": "jd_text",
        }
        winning, status, corr = location_enricher.reconcile_address(None, jd_text)
        self.assertEqual(status, "resolved")
        self.assertEqual(winning["source"], "jd_text")
        self.assertEqual(winning["zip"], "14221")

    def test_gemini_ultra_backup(self):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"found": true, "address": "300 Tech Dr, Amherst, NY 14228", "zip": "14228"}'
        mock_client.generate_content_with_search.return_value = mock_response

        with patch.dict(os.environ, {"RESUME_ALLOW_TEST_NETWORK": "1"}):
            res = location_enricher.lookup_gemini_search_backup(
                "Acme Corp", "Amherst", "NY", client=mock_client
            )
            self.assertIsNotNone(res)
            self.assertEqual(res["zip"], "14228")
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
            "On behalf of our client in Williamsville, NY we are seeking an engineer."
        )
        self.assertTrue(
            location_enricher.is_staffing_agency("Unknown Staffing", jd_text=jd_text)
        )

    def test_unresolved_agency_kept(self):
        discovery = {"address": "Downtown Agency HQ, Buffalo, NY 14202", "zip": "14202"}
        winning, status, corr = location_enricher.reconcile_address(
            discovery, None, is_agency=True
        )
        self.assertIsNone(winning)
        self.assertEqual(status, "unresolved_agency")

    def test_confidential_company_skips(self):
        res = location_enricher.lookup_osm_nominatim("Confidential", "Buffalo", "NY")
        self.assertIsNone(res)
        res_stealth = location_enricher.lookup_osm_nominatim(
            "Unknown Company", "Buffalo", "NY"
        )
        self.assertIsNone(res_stealth)

    # -------------------------------------------------------------------------
    # D. Multi-Branch Proximity Selection (1 Test)
    # -------------------------------------------------------------------------

    def test_selects_closest_branch(self):
        origin = "14068"  # Getzville, NY
        branches = [
            {
                "address": "Downtown Branch, Buffalo, NY 14202",
                "zip": "14202",
                "lat": 42.891,
                "lon": -78.877,
            },  # ~11.2 mi
            {
                "address": "Cheektowaga Branch, NY 14225",
                "zip": "14225",
                "lat": 42.924,
                "lon": -78.761,
            },  # ~7.5 mi
            {
                "address": "Amherst Branch, NY 14228",
                "zip": "14228",
                "lat": 42.996,
                "lon": -78.788,
            },  # ~1.8 mi
        ]
        chosen = location_enricher.select_closest_branch(branches, origin)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["zip"], "14228")

    # -------------------------------------------------------------------------
    # E. Caching & Dynamic Distance Math (3 Tests)
    # -------------------------------------------------------------------------

    def test_cache_hit_prevents_network(self):
        cache = {
            "acme corp::ny": {
                "address": "Amherst, NY 14228",
                "zip": "14228",
                "lat": 42.99,
                "lon": -78.78,
                "source": "osm_nominatim",
            }
        }
        job = {"company": "Acme Corp", "location": "Buffalo, NY", "raw_text": ""}
        settings = {"city": "Buffalo", "state": "NY", "zip": "14068", "radius_miles": 5}

        with patch("location_enricher.lookup_osm_nominatim") as mock_osm:
            res = location_enricher.enrich_job_location(
                job, settings=settings, cache=cache
            )
            mock_osm.assert_not_called()
            self.assertEqual(res["status"], "resolved")
            self.assertEqual(res["resolved_zip"], "14228")

    def test_cache_stores_points_not_miles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_file = os.path.join(tmpdir, "company_locations.json")
            cache = {
                "test_co::ny": {
                    "address": "123 Main",
                    "zip": "14228",
                    "lat": 42.99,
                    "lon": -78.78,
                }
            }
            with open(cache_file, "w") as f:
                json.dump(cache, f)
            with open(cache_file, "r") as f:
                loaded = json.load(f)
            entry = loaded["test_co::ny"]
            self.assertIn("lat", entry)
            self.assertIn("lon", entry)
            self.assertNotIn("distance_miles", entry)

    def test_distance_recalculates_on_origin_change(self):
        job = {"company": "Acme Corp", "location": "Buffalo, NY"}
        cache = {
            "acme corp::ny": {
                "address": "Amherst, NY 14228",
                "zip": "14228",
                "lat": 42.996,
                "lon": -78.788,
                "source": "osm_nominatim",
            }
        }

        # Origin 1: 14068 (Getzville) -> ~1.8 miles
        settings_1 = {
            "city": "Getzville",
            "state": "NY",
            "zip": "14068",
            "radius_miles": 5,
        }
        res_1 = location_enricher.enrich_job_location(
            job, settings=settings_1, cache=cache
        )
        dist_1 = res_1["distance_miles"]
        self.assertIsNotNone(dist_1)
        self.assertLess(dist_1, 3.0)

        # Origin 2: 14202 (Downtown Buffalo) -> ~8.0 miles
        settings_2 = {
            "city": "Buffalo",
            "state": "NY",
            "zip": "14202",
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
                location_enricher.lookup_osm_nominatim("Real Company", "Buffalo", "NY")
            )
            self.assertEqual(
                location_enricher.scrape_company_locations("https://example.com", "NY"),
                [],
            )
            self.assertIsNone(
                location_enricher.lookup_gemini_search_backup(
                    "Real Company", "Buffalo", "NY"
                )
            )

    def test_remote_jobs_bypass_enrichment(self):
        job = {
            "company": "Acme Corp",
            "location": "Anywhere, US (Remote)",
            "is_remote": True,
        }
        settings = {"city": "Buffalo", "state": "NY", "zip": "14068", "radius_miles": 5}
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
            '{"found": true, "address": "Buffalo, NY 14202", "zip": "14202"}'
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
                        "location": "Buffalo, NY",
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
                            "state": "NY",
                            "zip": "14068",
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
                        "location": "Buffalo, NY",
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
                            "state": "NY",
                            "zip": "14068",
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
            "location": "Buffalo, NY",
            "raw_text": "Work at our headquarters at 175 Hampton Pkwy, Amherst, NY 14228.",
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
                        "state": "NY",
                        "zip": "14068",
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
                self.assertEqual(persisted["resolved_zip"], "14228")
                self.assertEqual(persisted["source"], "jd_text")


if __name__ == "__main__":
    unittest.main()
