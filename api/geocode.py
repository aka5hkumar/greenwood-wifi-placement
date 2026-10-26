"""GET /api/geocode?q=<place name> — free, keyless place search via Nominatim.

Response JSON: {"ok": true, "results": [{"display_name", "lat", "lon", "boundingbox"}, ...]}
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import requests

# Vercel loads this file as a module without putting its own directory on
# sys.path, so both the api/ dir (for the _respond / _ratelimit helpers) and
# the repo root (for cli / data / models) have to be added explicitly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from _respond import respond
from _ratelimit import allow

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_RATE_LIMIT = 30
_RATE_WINDOW_S = 60.0

# Nominatim returns the feature's real outline alongside the search hit, so
# the UI can show the true site boundary immediately. Overpass is the only
# other source for this and it is frequently rate-limited or slow enough to
# blow a serverless function's budget, so it is now a fallback rather than
# the primary path.
_MAX_BOUNDARY_POINTS = 400


def _ring_area(ring: list) -> float:
    """Unsigned shoelace area, used only to pick the biggest ring."""
    a = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[i + 1][0], ring[i + 1][1]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def _decimate(ring: list) -> list:
    """Cap vertex count so a huge coastline polygon can't bloat the payload."""
    if len(ring) <= _MAX_BOUNDARY_POINTS:
        return ring
    step = len(ring) // _MAX_BOUNDARY_POINTS + 1
    thinned = ring[::step]
    if thinned[0] != thinned[-1]:
        thinned.append(thinned[0])
    return thinned


def _boundary_from_geojson(geom: dict | None) -> list | None:
    """Extract a single outer ring as [[lon, lat], ...] from Nominatim geojson."""
    if not geom:
        return None
    gtype, coords = geom.get("type"), geom.get("coordinates")
    if not coords:
        return None
    if gtype == "Polygon":
        ring = coords[0]
    elif gtype == "MultiPolygon":
        # Largest component — e.g. a park split by a road into several pieces.
        ring = max((p[0] for p in coords if p), key=_ring_area, default=None)
    else:
        return None  # Point/LineString results have no usable area.
    if not ring or len(ring) < 4:
        return None
    return [[float(x), float(y)] for x, y in _decimate(ring)]
# Nominatim's usage policy requires an identifying User-Agent — override via
# env var if you fork this for your own deployment.
USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "greenwood-wifi-placement-demo (contact: akash@nycmesh.net)",
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not allow(self, limit=_RATE_LIMIT, window_s=_RATE_WINDOW_S):
            respond(
                self, 429, {"ok": False, "error": "rate_limited", "message": "Too many searches — please slow down."},
                headers={"Retry-After": str(int(_RATE_WINDOW_S))},
            )
            return

        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get("q") or [""])[0].strip()
        if not q:
            respond(self, 400, {"ok": False, "error": "missing_query"})
            return

        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={
                    "q": q,
                    "format": "jsonv2",
                    "limit": 5,
                    "polygon_geojson": 1,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            respond(self, 502, {"ok": False, "error": "geocode_failed", "message": str(exc)})
            return

        results = [
            {
                "display_name": r.get("display_name"),
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "boundingbox": [float(x) for x in r.get("boundingbox", [])],
                "boundary": _boundary_from_geojson(r.get("geojson")),
            }
            for r in data
        ]
        # Identical searches get served from Vercel's edge cache instead of
        # hitting Nominatim again — cuts real load against its free tier.
        respond(self, 200, {"ok": True, "results": results}, headers={"Cache-Control": "public, max-age=3600"})
