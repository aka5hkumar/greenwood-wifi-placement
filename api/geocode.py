"""GET /api/geocode?q=<place name> — free, keyless place search via Nominatim.

Response JSON: {"ok": true, "results": [{"display_name", "lat", "lon", "boundingbox"}, ...]}
"""

import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _respond import respond

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires an identifying User-Agent — override via
# env var if you fork this for your own deployment.
USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "greenwood-wifi-placement-demo (contact: akash@nycmesh.net)",
)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get("q") or [""])[0].strip()
        if not q:
            respond(self, 400, {"ok": False, "error": "missing_query"})
            return

        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": q, "format": "jsonv2", "limit": 5},
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
            }
            for r in data
        ]
        respond(self, 200, {"ok": True, "results": results})
