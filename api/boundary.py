"""GET /api/boundary?lat=<f>&lon=<f> — resolve the enclosing site polygon.

Used by the frontend after a geocode search, before the user hits "compute":
lets the map show (and the user confirm/adjust) the boundary that will
actually be used, without running the full pipeline yet.

Response JSON: {"ok": true, "boundary": [[lon, lat], ...] | null}
boundary is null when no enclosing park/cemetery/campus feature was found —
the frontend should fall back to a user-drawn polygon or a radius circle.
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

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
from data.osm import fetch_boundary

_RATE_LIMIT = 20
_RATE_WINDOW_S = 60.0


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not allow(self, limit=_RATE_LIMIT, window_s=_RATE_WINDOW_S):
            respond(
                self, 429, {"ok": False, "error": "rate_limited", "message": "Too many requests — please slow down."},
                headers={"Retry-After": str(int(_RATE_WINDOW_S))},
            )
            return

        qs = parse_qs(urlparse(self.path).query)
        try:
            lat = float(qs["lat"][0])
            lon = float(qs["lon"][0])
        except (KeyError, ValueError, IndexError):
            respond(self, 400, {"ok": False, "error": "missing_params", "message": "lat and lon query params are required."})
            return

        cache_key = f"{lat:.4f}_{lon:.4f}"
        try:
            boundary = fetch_boundary(lat, lon, no_cache=False, cache_key=cache_key)
        except Exception as exc:
            respond(self, 502, {"ok": False, "error": "boundary_lookup_failed", "message": str(exc)})
            return

        cache_headers = {"Cache-Control": "public, max-age=3600"}

        if boundary is None:
            respond(self, 200, {"ok": True, "boundary": None}, headers=cache_headers)
            return

        coords = [[lon_, lat_] for lon_, lat_ in boundary.exterior.coords]
        respond(self, 200, {"ok": True, "boundary": coords}, headers=cache_headers)
