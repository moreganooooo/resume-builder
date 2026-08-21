"""
build_geodata.py -- regenerates the bundled offline centroid indexes in
assets/geodata/ from GeoNames' public US postal-code export.

Run this only when the bundled data needs refreshing (ZIP codes change
slowly -- a few dozen a year). The output is committed, so a normal
checkout never needs network access to answer a distance question:

    python scripts/build_geodata.py

Sources, both GeoNames and both CC BY 4.0:

  export/zip/US.zip    postal codes -> ZIP centroids
  export/dump/US.zip   the gazetteer -> populated places

Two indexes are produced because job postings name locations two
different ways and both have to resolve:

  us_zipcodes.json.gz  "78701"     -> [lat, lon]
  us_cities.json.gz    "austin,tx" -> [lat, lon]

The city index merges BOTH sources, and it has to. The postal file's
place names are USPS-preferred mailing names, which omit a great many
real municipalities -- there is no "Amherst, NY" in it at all, despite
Amherst having ~130,000 residents, because its ZIPs are labeled
Buffalo/Williamsville. Deriving cities from ZIP labels alone therefore
silently fails to resolve entire suburbs, which is precisely where
commutable on-site jobs are.

The gazetteer supplies real municipality names and wins on conflict
(its centroid is the place itself, not the mean of mailing regions).
The postal names are kept as a second layer because the gazetteer is
filtered to populated places, which drops small unincorporated hamlets
that a posting -- or the candidate's own origin -- may still name.

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

GEONAMES_POSTAL_URL = "https://download.geonames.org/export/zip/US.zip"
GEONAMES_GAZETTEER_URL = "https://download.geonames.org/export/dump/US.zip"

# Gazetteer rows with no population are mostly unnamed physical
# localities; keeping administrative seats regardless preserves real
# places that simply have no population figure.
_ADMIN_FEATURE_CODES = {"PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC"}
ASSETS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "geodata"
)


def fetch_us_table(url: str) -> str:
    """Downloads a GeoNames US archive and returns US.txt's contents."""
    with urllib.request.urlopen(url, timeout=300) as resp:  # nosec B310
        payload = resp.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return archive.read("US.txt").decode("utf-8")


def parse_gazetteer(table: str) -> dict:
    """Populated places -> centroid, keyed "name,state".

    Where one state holds several places of the same name, the most
    populous wins -- a posting saying "Springfield, IL" means the city,
    not the hamlet.
    """
    best: dict = {}
    for line in table.splitlines():
        f = line.split("\t")
        if len(f) < 15 or f[6] != "P":
            continue
        state = f[10].strip().lower()
        if len(state) != 2:
            continue
        name = (f[2].strip() or f[1].strip()).lower()
        if not name:
            continue
        try:
            lat, lon = round(float(f[4]), 4), round(float(f[5]), 4)
            population = int(f[14] or 0)
        except ValueError:
            continue
        if population <= 0 and f[7] not in _ADMIN_FEATURE_CODES:
            continue
        key = f"{name},{state}"
        if key not in best or population > best[key][2]:
            best[key] = (lat, lon, population)
    return {key: [lat, lon] for key, (lat, lon, _) in best.items()}


def build_indexes(table: str) -> tuple[dict, dict]:
    """Parses the postal US.txt into (zip_centroids, usps_city_centroids)."""
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
    try:
        print(f"Fetching {GEONAMES_POSTAL_URL} ...")
        postal_table = fetch_us_table(GEONAMES_POSTAL_URL)
        print(f"Fetching {GEONAMES_GAZETTEER_URL} ...")
        gazetteer_table = fetch_us_table(GEONAMES_GAZETTEER_URL)
    except Exception as exc:  # pragma: no cover - network failure path
        print(f"Failed to fetch GeoNames export: {exc}", file=sys.stderr)
        sys.exit(1)

    zips, usps_cities = build_indexes(postal_table)
    gazetteer = parse_gazetteer(gazetteer_table)
    # Gazetteer wins; USPS names fill the gaps it filtered out.
    cities = dict(usps_cities)
    cities.update(gazetteer)
    print(
        f"  cities: {len(usps_cities):,} USPS + {len(gazetteer):,} gazetteer "
        f"-> {len(cities):,} merged"
    )
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
