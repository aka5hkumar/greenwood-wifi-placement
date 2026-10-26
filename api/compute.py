"""POST /api/compute — run the live placement pipeline for an arbitrary site.

Request JSON body:
    {
      "lat": float, "lon": float,            # a point inside the site
      "site_name": str,                      # optional, for labeling
      "range_2g_ft": float, "range_5g_ft": float, "range_6g_ft": float|null,
      "coverage": "full" | "paths",
      "boundary": [[lon, lat], ...] | null,  # optional user-drawn override
      "cache_key": str | null                # optional explicit cache key
    }

Response JSON (200): the same schema as output/ap_placement.json plus
boundary/params/stats — see cli.run_pipeline()'s return value.

Response JSON (422): {"ok": false, "error": "...", "message": "..."} for
known, user-fixable failure conditions (area too large, no boundary found,
no viable candidates, no ILP solution).
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler

# Vercel loads this file as a module without putting its own directory on
# sys.path, so both the api/ dir (for the _respond / _ratelimit helpers) and
# the repo root (for cli / data / models) have to be added explicitly.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_HERE, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from _respond import respond
from _ratelimit import allow, same_origin
from cli import (
    run_pipeline,
    AreaTooLargeError,
    NoBoundaryError,
    NoViableCandidatesError,
    NoSolutionError,
)

_KNOWN_ERRORS = (NoBoundaryError, NoViableCandidatesError, NoSolutionError)

# This is by far the most expensive route (real OSM/elevation/solar fetches +
# an ILP solve per call) and the one most worth protecting — a handful of
# live runs per IP per window is plenty for a demo, and keeps the free
# upstream elevation/OSM APIs from getting hammered by a scraper or bot.
_RATE_LIMIT = 6
_RATE_WINDOW_S = 600.0


def _clean(result: dict) -> dict:
    """Drop internal/non-JSON-safe fields (numpy arrays) meant only for the CLI."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if not same_origin(self):
            respond(self, 403, {"ok": False, "error": "forbidden", "message": "Cross-origin requests to this API are not allowed."})
            return
        if not allow(self, limit=_RATE_LIMIT, window_s=_RATE_WINDOW_S):
            respond(
                self, 429,
                {"ok": False, "error": "rate_limited", "message": "Too many live computes from this address — please wait a bit and try again."},
                headers={"Retry-After": str(int(_RATE_WINDOW_S))},
            )
            return

        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            params = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            respond(self, 400, {"ok": False, "error": "bad_request", "message": "Invalid JSON body."})
            return

        try:
            lat = float(params.get("lat", 40.651))
            lon = float(params.get("lon", -73.994))
        except (TypeError, ValueError):
            respond(self, 400, {"ok": False, "error": "bad_request", "message": "lat/lon must be numbers."})
            return

        boundary_override = params.get("boundary")
        if boundary_override:
            boundary_override = [(float(c[0]), float(c[1])) for c in boundary_override]

        cache_key = params.get("cache_key") or f"{lat:.4f}_{lon:.4f}"

        range_6g = params.get("range_6g_ft")

        try:
            result = run_pipeline(
                lat=lat,
                lon=lon,
                site_name=params.get("site_name") or "Custom Site",
                range_2g_ft=float(params.get("range_2g_ft", 2000.0)),
                range_5g_ft=float(params.get("range_5g_ft", 1250.0)),
                range_6g_ft=float(range_6g) if range_6g else None,
                coverage=params.get("coverage", "full"),
                no_cache=False,
                cache_key=cache_key,
                boundary_override=boundary_override,
                parallel=False,
                enforce_area_cap=True,
            )
        except AreaTooLargeError as exc:
            respond(self, 422, {"ok": False, "error": "area_too_large", "message": str(exc), **exc.info})
            return
        except _KNOWN_ERRORS as exc:
            respond(self, 422, {"ok": False, "error": type(exc).__name__, "message": str(exc)})
            return
        except Exception as exc:
            respond(self, 500, {"ok": False, "error": "internal_error", "message": str(exc)})
            return

        respond(self, 200, _clean(result))
