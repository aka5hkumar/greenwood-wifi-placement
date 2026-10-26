"""Fetch a site boundary, trees, buildings, and paths from OpenStreetMap.

Works for any location, not just Green-Wood: fetch_boundary() resolves the
smallest enclosing park/cemetery/campus/nature-reserve feature around a
given point. fetch_trees/fetch_buildings/fetch_paths already only need a
boundary polygon and are location-agnostic.

Results are cached to data/cache/ as plain GeoJSON (keyed by `cache_key`, so
multiple locations don't collide) so Overpass is only hit once per site, or
when no_cache=True is passed. No API keys required; no geopandas/GDAL
dependency — geometries are plain shapely objects.
"""

import json
import os
import time

import overpy
import requests
from shapely.geometry import LineString, Point, Polygon, mapping, shape
from shapely.ops import unary_union

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")

class OverpassUnavailable(RuntimeError):
    """Every Overpass mirror refused or timed out.

    Public Overpass instances are frequently rate-limited or overloaded, so
    callers should treat this as an expected condition and degrade rather
    than abort — see run_pipeline's handling of trees/buildings/paths.
    """


# Overpass endpoints tried in order; first success wins.
_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Overpass usage policy expects an identifying User-Agent; overpass-api.de
# returns HTTP 406 without one.
_HTTP_HEADERS = {
    "User-Agent": os.environ.get(
        "OVERPASS_USER_AGENT",
        "greenwood-wifi-placement/1.0 (+https://github.com/aka5hkumar/greenwood-wifi-placement)",
    ),
}
_HTTP_TIMEOUT_S = 8.0   # 4 mirrors x 8s = 32s worst case, inside a 60s function budget
# Overpass mirrors are frequently rate-limited (HTTP 429) or slow. Retrying
# twice per endpoint with 3 s sleeps across three mirrors could burn ~25 s
# before raising — longer than the serverless budget, so the caller saw a
# timeout rather than a clean failure. One attempt per endpoint, no sleeps,
# fails over fast and still tries every mirror.
_RETRIES_PER_ENDPOINT = 1
_RETRY_DELAY_S = 0

# Tags that plausibly bound a walkable site worth covering with WiFi.
_SITE_TAG_FILTERS = [
    ('leisure', 'park|nature_reserve|garden|recreation_ground'),
    ('landuse', 'cemetery|recreation_ground|forest|religious'),
    ('amenity', 'grave_yard|university|college'),
    ('boundary', 'national_park|protected_area'),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _query(query: str, timeout_s: float = _HTTP_TIMEOUT_S):
    """Run an Overpass QL query with multi-endpoint fallback.

    The HTTP call is made directly rather than through overpy.query() so we
    can send a User-Agent — overpass-api.de rejects requests without one
    (HTTP 406) — and bound the per-endpoint timeout. overpy still does the
    JSON parsing, so callers get the usual Result object.
    """
    parser = overpy.Overpass()
    last_err = None
    for url in _ENDPOINTS:
        for attempt in range(_RETRIES_PER_ENDPOINT):
            try:
                resp = requests.post(
                    url, data={"data": query}, headers=_HTTP_HEADERS, timeout=timeout_s
                )
                if resp.status_code == 200:
                    return parser.parse_json(resp.text)
                # 429 = rate limited, 504 = server overloaded; both mean
                # "try another mirror" rather than "retry here".
                last_err = f"HTTP {resp.status_code}"
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
            if attempt < _RETRIES_PER_ENDPOINT - 1 and _RETRY_DELAY_S:
                time.sleep(_RETRY_DELAY_S)
        print(f"  Overpass {url} failed ({last_err}), trying next…")
    raise OverpassUnavailable(f"All Overpass endpoints failed. Last error: {last_err}")


def _bbox(boundary: Polygon) -> tuple[float, float, float, float]:
    """
    Return (south, west, north, east) for an Overpass bbox filter.
    shapely .bounds → (minx=west, miny=south, maxx=east, maxy=north)
    """
    west, south, east, north = boundary.bounds
    return south, west, north, east


def _boundary_cache_path(cache_key: str) -> str:
    return os.path.join(CACHE_DIR, f"osm_boundary_{cache_key}.json")


def _save_boundary(poly: Polygon, cache_key: str) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(_boundary_cache_path(cache_key), "w") as f:
        json.dump(list(poly.exterior.coords), f)


def _load_boundary(cache_key: str) -> Polygon | None:
    p = _boundary_cache_path(cache_key)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        coords = json.load(f)
    return Polygon(coords)


def _records_cache_path(cache_key: str, name: str) -> str:
    return os.path.join(CACHE_DIR, f"osm_{name}_{cache_key}.geojson")


def _save_records(records: list[dict], cache_key: str, name: str) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    features = []
    for rec in records:
        props = {k: v for k, v in rec.items() if k != "geometry"}
        features.append({"type": "Feature", "geometry": mapping(rec["geometry"]), "properties": props})
    with open(_records_cache_path(cache_key, name), "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f)


def _load_records(cache_key: str, name: str) -> list[dict] | None:
    p = _records_cache_path(cache_key, name)
    if not os.path.exists(p):
        return None
    with open(p) as f:
        fc = json.load(f)
    records = []
    for feat in fc["features"]:
        rec = dict(feat["properties"])
        rec["geometry"] = shape(feat["geometry"])
        records.append(rec)
    return records


def _ways_to_polygon(relation_result, relation) -> Polygon | None:
    """Convert OSM relation ways into a merged Shapely polygon."""
    way_nodes: dict = {}
    for way in relation_result.ways:
        coords = [(float(n.lon), float(n.lat)) for n in way.nodes]
        if len(coords) >= 3:
            way_nodes[way.id] = coords

    rings = []
    for member in relation.members:
        if hasattr(member, "ref") and member.ref in way_nodes:
            coords = way_nodes[member.ref]
            if coords[0] == coords[-1] and len(coords) >= 4:
                rings.append(Polygon(coords))

    if not rings:
        return None
    merged = unary_union(rings)
    if merged.geom_type == "MultiPolygon":
        return max(merged.geoms, key=lambda g: g.area)
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_boundary(
    lat: float,
    lon: float,
    no_cache: bool = False,
    cache_key: str = "default",
    override_polygon: list[tuple[float, float]] | None = None,
    search_radius_m: int = 1500,
) -> Polygon | None:
    """
    Resolve a site boundary polygon for an arbitrary point.

    Resolution order:
      1. override_polygon, if given (≥ 3 vertices) — e.g. a user-drawn
         boundary from the web UI, or a known fixture for a default demo site
      2. cached polygon for this cache_key (unless no_cache)
      3. live Overpass query for the smallest enclosing park/cemetery/campus/
         nature-reserve feature containing (lat, lon)

    Returns None if no enclosing feature is found — callers should fall back
    to a user-drawn polygon or a fixed-radius circle around the point.
    """
    if override_polygon and len(override_polygon) >= 3:
        print(f"Boundary from override polygon ({len(override_polygon)} vertices).")
        return Polygon(override_polygon)

    if not no_cache:
        cached = _load_boundary(cache_key)
        if cached is not None:
            print("Boundary loaded from cache.")
            return cached

    filters = "\n      ".join(
        f'way(around:{search_radius_m},{lat},{lon})["{tag}"~"^({pattern})$"];\n'
        f'      relation(around:{search_radius_m},{lat},{lon})["{tag}"~"^({pattern})$"];'
        for tag, pattern in _SITE_TAG_FILTERS
    )
    query = f"""
    [out:json][timeout:25];
    (
      {filters}
    );
    (._;>;);
    out body;
    """
    try:
        result = _query(query)
    except Exception as exc:
        print(f"Boundary lookup failed ({exc}).")
        return None

    point = Point(lon, lat)
    candidates = []

    for way in result.ways:
        try:
            coords = [(float(n.lon), float(n.lat)) for n in way.nodes]
        except Exception:
            continue
        if len(coords) >= 4 and coords[0] == coords[-1]:
            poly = Polygon(coords)
            if poly.is_valid and poly.contains(point):
                candidates.append(poly)

    for relation in result.relations:
        poly = _ways_to_polygon(result, relation)
        if poly and not poly.is_empty and poly.is_valid and poly.contains(point):
            candidates.append(poly)

    if not candidates:
        print("No enclosing park/cemetery/campus feature found near this point.")
        return None

    # Prefer the smallest enclosing feature — avoids grabbing a huge forest
    # or admin boundary when the point is inside a small garden within it.
    poly = min(candidates, key=lambda p: p.area)
    print(f"Boundary resolved: {poly.area:.6f} sq-deg")
    _save_boundary(poly, cache_key)
    return poly


def fetch_trees(boundary: Polygon, no_cache: bool = False, cache_key: str = "default") -> list[dict]:
    """Return OSM trees inside the boundary as [{"geometry": Point, "canopy_radius_m", "height_m"}, ...]."""
    if not no_cache:
        cached = _load_records(cache_key, "trees")
        if cached is not None:
            print(f"Trees loaded from cache: {len(cached)}")
            return cached

    s, w, n, e = _bbox(boundary)
    query = f"""
    [out:json][timeout:60];
    node["natural"="tree"]({s},{w},{n},{e});
    out body;
    """
    result = _query(query)

    records = []
    for node in result.nodes:
        pt = Point(float(node.lon), float(node.lat))
        if boundary.contains(pt):
            raw_h = node.tags.get("height", "0").rstrip("m ").strip()
            try:
                height_m = float(raw_h) if raw_h else 0.0
            except ValueError:
                height_m = 0.0
            if height_m <= 0:
                height_m = 0.0

            if "diameter_crown" in node.tags:
                canopy_r = float(node.tags["diameter_crown"]) / 2
            else:
                # Estimate from height: mature trees ≈ 0.4× height as crown radius.
                # Default height 15 m → 6 m crown radius.
                effective_h = height_m if height_m > 0 else 15.0
                canopy_r = max(3.0, effective_h * 0.4)

            records.append({
                "geometry": pt,
                "canopy_radius_m": canopy_r,
                "height_m": height_m if height_m > 0 else None,
            })

    print(f"Trees fetched: {len(records)}")
    _save_records(records, cache_key, "trees")
    return records


def fetch_buildings(boundary: Polygon, no_cache: bool = False, cache_key: str = "default") -> list[dict]:
    """Return OSM building footprints inside the boundary as [{"geometry": Polygon}, ...]."""
    if not no_cache:
        cached = _load_records(cache_key, "buildings")
        if cached is not None:
            print(f"Buildings loaded from cache: {len(cached)}")
            return cached

    s, w, n, e = _bbox(boundary)
    query = f"""
    [out:json][timeout:60];
    (
      way["building"]({s},{w},{n},{e});
      relation["building"]({s},{w},{n},{e});
    );
    (._;>;);
    out body;
    """
    result = _query(query)

    records = []
    for way in result.ways:
        try:
            coords = [(float(nd.lon), float(nd.lat)) for nd in way.nodes]
        except Exception:
            continue
        if len(coords) >= 3:
            poly = Polygon(coords)
            if poly.is_valid and boundary.intersects(poly):
                records.append({"geometry": poly})

    print(f"Buildings fetched: {len(records)}")
    _save_records(records, cache_key, "buildings")
    return records


def fetch_paths(boundary: Polygon, no_cache: bool = False, cache_key: str = "default") -> list[dict]:
    """Return OSM footway/path/road geometries inside the boundary as [{"geometry": LineString}, ...]."""
    if not no_cache:
        cached = _load_records(cache_key, "paths")
        if cached is not None:
            print(f"Paths loaded from cache: {len(cached)}")
            return cached

    s, w, n, e = _bbox(boundary)
    query = f"""
    [out:json][timeout:60];
    (
      way["highway"]({s},{w},{n},{e});
    );
    (._;>;);
    out body;
    """
    result = _query(query)

    records = []
    for way in result.ways:
        try:
            coords = [(float(nd.lon), float(nd.lat)) for nd in way.nodes]
        except Exception:
            continue
        if len(coords) >= 2:
            line = LineString(coords)
            if boundary.intersects(line):
                records.append({"geometry": line})

    print(f"Paths fetched: {len(records)}")
    _save_records(records, cache_key, "paths")
    return records
