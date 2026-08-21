"""Tests for scripts/geo_distance.py -- offline centroid + haversine math."""

import math
import os
import sys
import unittest

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import geo_distance  # noqa: E402


class TestHaversine(unittest.TestCase):
    def test_identical_points_are_zero(self):
        self.assertEqual(
            geo_distance.haversine_distance_miles(30.27, -97.74, 30.27, -97.74), 0.0
        )

    def test_known_distance_kc_to_austin(self):
        # ~635 great-circle miles; allow a wide band since both endpoints
        # are city centroids, not landmarks.
        miles = geo_distance.haversine_distance_miles(39.10, -94.58, 30.27, -97.74)
        self.assertAlmostEqual(miles, 635, delta=25)

    def test_is_symmetric(self):
        a = geo_distance.haversine_distance_miles(39.10, -94.58, 30.27, -97.74)
        b = geo_distance.haversine_distance_miles(30.27, -97.74, 39.10, -94.58)
        self.assertAlmostEqual(a, b, places=6)

    def test_antipodal_points_do_not_raise(self):
        # Guards the sqrt domain: floating point can push `a` just past
        # 1.0 for opposite points, making asin() throw without the clamp.
        miles = geo_distance.haversine_distance_miles(0.0, 0.0, 0.0, 180.0)
        half_circumference = math.pi * geo_distance.EARTH_RADIUS_MILES
        self.assertAlmostEqual(miles, half_circumference, delta=1)


class TestZipCentroid(unittest.TestCase):
    def test_known_zip(self):
        self.assertIsNotNone(geo_distance.get_zip_centroid("78701"))

    def test_zip_plus_four(self):
        self.assertEqual(
            geo_distance.get_zip_centroid("78701-1234"),
            geo_distance.get_zip_centroid("78701"),
        )

    def test_unknown_zip_is_none(self):
        self.assertIsNone(geo_distance.get_zip_centroid("00000"))

    def test_empty_is_none(self):
        self.assertIsNone(geo_distance.get_zip_centroid(""))
        self.assertIsNone(geo_distance.get_zip_centroid(None))


class TestCityCentroid(unittest.TestCase):
    def test_state_code_and_full_name_agree(self):
        self.assertEqual(
            geo_distance.get_city_centroid("Austin", "TX"),
            geo_distance.get_city_centroid("Austin", "Texas"),
        )

    def test_case_insensitive(self):
        self.assertEqual(
            geo_distance.get_city_centroid("AUSTIN", "tx"),
            geo_distance.get_city_centroid("Austin", "TX"),
        )

    def test_non_us_state_is_none(self):
        self.assertIsNone(geo_distance.get_city_centroid("London", "UK"))
        self.assertIsNone(geo_distance.get_city_centroid("Toronto", "ON"))

    def test_missing_parts_are_none(self):
        self.assertIsNone(geo_distance.get_city_centroid("", "TX"))
        self.assertIsNone(geo_distance.get_city_centroid("Austin", ""))


class TestResolveLocation(unittest.TestCase):
    def test_bare_zip(self):
        self.assertEqual(
            geo_distance.resolve_location("78701"),
            geo_distance.get_zip_centroid("78701"),
        )

    def test_city_state(self):
        self.assertEqual(
            geo_distance.resolve_location("Austin, TX"),
            geo_distance.get_city_centroid("Austin", "TX"),
        )

    def test_zip_wins_over_city_when_both_present(self):
        # The ZIP is the more precise token, so it should be preferred.
        self.assertEqual(
            geo_distance.resolve_location("Austin, TX 78701"),
            geo_distance.get_zip_centroid("78701"),
        )

    def test_trailing_country_token(self):
        self.assertEqual(
            geo_distance.resolve_location("Austin, TX, USA"),
            geo_distance.get_city_centroid("Austin", "TX"),
        )

    def test_leading_qualifier(self):
        self.assertEqual(
            geo_distance.resolve_location("Downtown, Austin, TX"),
            geo_distance.get_city_centroid("Austin", "TX"),
        )

    def test_international_is_none(self):
        for value in ("London, UK", "Toronto, ON", "Berlin, Germany"):
            with self.subTest(value=value):
                self.assertIsNone(geo_distance.resolve_location(value))

    def test_non_places_are_none(self):
        # "Unknown" must never be silently rendered as a distance.
        for value in ("Remote", "Anywhere", "", "   ", None, "Greater Austin Area"):
            with self.subTest(value=value):
                self.assertIsNone(geo_distance.resolve_location(value))

    def test_bare_city_without_state_is_none(self):
        # Ambiguous by design: there are Austins in several states.
        self.assertIsNone(geo_distance.resolve_location("Austin"))


class TestDistanceBetween(unittest.TestCase):
    def test_nearby_cities(self):
        miles = geo_distance.distance_between("San Francisco, CA", "Sunnyvale, CA")
        self.assertLess(miles, 45)

    def test_distant_cities(self):
        miles = geo_distance.distance_between("Kansas City, MO", "Austin, TX")
        self.assertGreater(miles, 500)

    def test_unresolvable_endpoint_is_none(self):
        self.assertIsNone(geo_distance.distance_between("Austin, TX", "Remote"))
        self.assertIsNone(geo_distance.distance_between("Remote", "Austin, TX"))


class TestBundledData(unittest.TestCase):
    def test_indexes_are_populated(self):
        # A corrupt or missing asset degrades to {}, which would silently
        # make every location unresolvable rather than failing loudly.
        self.assertGreater(len(geo_distance._zip_index()), 30000)
        self.assertGreater(len(geo_distance._city_index()), 20000)


if __name__ == "__main__":
    unittest.main()
