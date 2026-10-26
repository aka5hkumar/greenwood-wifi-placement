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

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from _respond import respond
from data.osm import fetch_boundary


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
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

        if boundary is None:
            respond(self, 200, {"ok": True, "boundary": None})
            return

        coords = [[lon_, lat_] for lon_, lat_ in boundary.exterior.coords]
        respond(self, 200, {"ok": True, "boundary": coords})
