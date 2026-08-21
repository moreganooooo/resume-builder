"""
build_geodata.py -- regenerates the bundled offline centroid indexes in
assets/geodata/ from GeoNames' public US postal-code export.

Run this only when the bundled data needs refreshing (ZIP codes change
slowly -- a few dozen a year). The output is committed, so a normal
checkout never needs network access to answer a distance question:

    python scripts/build_geodata.py

Source: https://download.geonames.org/export/zip/US.zip (CC BY 4.0).
The upstream file is tab-separated; we use columns 1 (postal code),
2 (place name), 4 (state code), 9 (latitude), and 10 (longitude).

Two indexes are produced because job postings name locations two
different ways and both have to resolve:

  us_zipcodes.json.gz  "78701"     -> [lat, lon]
  us_cities.json.gz    "austin,tx" -> [lat, lon]

A city's centroid is the mean of its ZIP centroids, which is close
enough for radius filtering -- we are answering "is this commutable",
not surveying a property line.

Both are gzipped (2.1 MB -> ~700 KB) and read lazily by
scripts/geo_distance.py, which decompresses once per process.
Coordinates are rounded to 4 decimals (~11 m), far finer than any
question a mileage radius can ask, and it measurably shrinks the file.

Note that assets/ is deliberately NOT data/ -- data/ is profile-scoped
(data/<profile>/) and is one of the four Syncthing roots from
profile_paths.sync_roots(). This is shared, read-only, machine-agnostic
reference data; it has no business syncing between devices.
"""

import collections
import gzip
import io
import json
import os
import sys
import urllib.request
import zipfile

GEONAMES_URL = "https://download.geonames.org/export/zip/US.zip"
ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "geodata"
)


def fetch_us_table() -> str:
    """Downloads the GeoNames US archive and returns US.txt's contents."""
    with urllib.request.urlopen(GEONAMES_URL, timeout=120) as resp:  # nosec B310
        payload = resp.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return archive.read("US.txt").decode("utf-8")


def build_indexes(table: str) -> tuple[dict, dict]:
    """Parses US.txt into (zip_centroids, city_centroids)."""
    zips: dict = {}
    city_points = collections.defaultdict(list)

    for line in table.splitlines():
        fields = line.split("\t")
        if len(fields) < 11:
            continue
        postal, place, state = fields[1], fields[2], fields[4]
        try:
            lat = round(float(fields[9]), 4)
            lon = round(float(fields[10]), 4)
        except ValueError:
            # A handful of upstream rows carry empty coordinates.
            continue

        zips[postal] = [lat, lon]
        if place and state:
            city_points[f"{place.lower()},{state.lower()}"].append((lat, lon))

    cities = {
        key: [
            round(sum(lat for lat, _ in pts) / len(pts), 4),
            round(sum(lon for _, lon in pts) / len(pts), 4),
        ]
        for key, pts in city_points.items()
    }
    return zips, cities


def write_index(payload: dict, filename: str) -> None:
    path = os.path.join(ASSETS_DIR, filename)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, separators=(",", ":"), sort_keys=True)
    size_kb = os.path.getsize(path) / 1024
    print(f"  wrote {filename}  ({len(payload):,} entries, {size_kb:,.0f} KB)")


def main() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)
    print(f"Fetching {GEONAMES_URL} ...")
    try:
        table = fetch_us_table()
    except Exception as exc:  # pragma: no cover - network failure path
        print(f"Failed to fetch GeoNames export: {exc}", file=sys.stderr)
        sys.exit(1)

    zips, cities = build_indexes(table)
    if len(zips) < 30000:
        # A truncated or restructured upstream file should not silently
        # replace a good bundled index with a partial one.
        print(
            f"Refusing to write: parsed only {len(zips)} ZIPs, expected ~41,000. "
            "The upstream format may have changed.",
            file=sys.stderr,
        )
        sys.exit(1)

    write_index(zips, "us_zipcodes.json.gz")
    write_index(cities, "us_cities.json.gz")
    print("Done.")


if __name__ == "__main__":
    main()
