"""Fetch a bare-earth elevation grid via a free, keyless point-query API.

No GDAL/rasterio dependency — Open-Topo-Data's bulk endpoint (100 points per
request, no API key) is queried over the same lat/lon grid schema the old
USGS-raster path produced, so downstream code (models/terrain.py) needs no
changes. Point OPENTOPODATA_URL at a self-hosted instance
(https://www.opentopodata.org/#host-your-own) for faster/higher-volume use.
"""

import json
import os
import time

import numpy as np
import requests
from shapely.geometry import Polygon

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")

OPENTOPODATA_URL = os.environ.get(
    "OPENTOPODATA_URL", "https://api.opentopodata.org/v1/aster30m"
)
_BATCH_SIZE = 100
_REQUEST_DELAY_S = 1.0   # respect the public demo server's ~1 req/s rate limit

# Coarser than a typical USGS DEM — keeps point-query counts serverless-
# friendly while still resolving tree/building-scale terrain features at
# park/cemetery scale.
RESOLUTION_M = 15.0
BBOX_PAD_DEG = 0.002

# Hard cap on grid points per site. The public endpoint accepts 100 points
# per request and asks for ~1 req/s, so cost is roughly
# (points / 100) seconds — a 357-acre park at a flat 15 m spacing needs
# ~9,300 points, i.e. 90+ seconds of rate-limited calls, far beyond a
# serverless request budget. Coarsening the grid for large sites keeps the
# fetch bounded; terrain is a gentler signal than canopy at park scale, so
# the loss of detail is acceptable where the alternative is no result.
MAX_SAMPLE_POINTS = 1200


def _elevation_cache_paths(cache_key: str) -> tuple[str, str]:
    return (
        os.path.join(CACHE_DIR, f"elevation_{cache_key}.npy"),
        os.path.join(CACHE_DIR, f"elevation_transform_{cache_key}.json"),
    )


def _query_elevations(points: list[tuple[float, float]]) -> list[float]:
    """points: list of (lat, lon). Returns elevation in metres (NaN on failure)."""
    out: list[float] = []
    for i in range(0, len(points), _BATCH_SIZE):
        batch = points[i : i + _BATCH_SIZE]
        locations = "|".join(f"{lat},{lon}" for lat, lon in batch)
        try:
            resp = requests.get(
                OPENTOPODATA_URL, params={"locations": locations}, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            for r in data.get("results", []):
                e = r.get("elevation")
                out.append(float(e) if e is not None else float("nan"))
        except Exception as exc:
            print(f"  Elevation batch {i // _BATCH_SIZE} failed ({exc}), using fallback.")
            out.extend([float("nan")] * len(batch))
        if i + _BATCH_SIZE < len(points):
            time.sleep(_REQUEST_DELAY_S)
    return out


def fetch_elevation_raster(
    boundary: Polygon, no_cache: bool = False, cache_key: str = "default"
) -> tuple[np.ndarray, dict]:
    """
    Build a bare-earth elevation grid by point-querying a free elevation API.

    Returns (elevation_m, transform) with the same schema the previous
    USGS-raster path produced: transform describes the grid origin/cell size
    in degrees so any lat/lon maps to a (row, col) index via latlon_to_grid.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    elev_cache, transform_cache = _elevation_cache_paths(cache_key)

    if not no_cache and os.path.exists(elev_cache) and os.path.exists(transform_cache):
        print("Loading elevation from cache...")
        elev = np.load(elev_cache)
        with open(transform_cache) as f:
            transform = json.load(f)
        return elev, transform

    minx, miny, maxx, maxy = boundary.bounds
    minx -= BBOX_PAD_DEG
    miny -= BBOX_PAD_DEG
    maxx += BBOX_PAD_DEG
    maxy += BBOX_PAD_DEG

    mid_lat = (miny + maxy) / 2
    lat_m_per_deg = 111_320.0
    lon_m_per_deg = 111_320.0 * np.cos(np.radians(mid_lat))

    height_m = (maxy - miny) * lat_m_per_deg
    width_m = (maxx - minx) * lon_m_per_deg

    # Coarsen uniformly until the grid fits inside MAX_SAMPLE_POINTS.
    resolution_m = RESOLUTION_M
    if (height_m * width_m) / (resolution_m ** 2) > MAX_SAMPLE_POINTS:
        resolution_m = ((height_m * width_m) / MAX_SAMPLE_POINTS) ** 0.5

    nrows = max(20, int(height_m / resolution_m))
    ncols = max(20, int(width_m / resolution_m))

    transform = {
        "origin_lon": minx,
        "origin_lat": maxy,
        "cell_lon": (maxx - minx) / ncols,
        "cell_lat": -((maxy - miny) / nrows),
        "nrows": nrows,
        "ncols": ncols,
        "resolution_m": resolution_m,
    }

    print(
        f"Querying elevation grid ({ncols}×{nrows} px at {resolution_m:.0f} m, "
        f"{nrows * ncols:,} points)..."
    )

    lats = maxy + np.arange(nrows) * transform["cell_lat"]
    lons = minx + np.arange(ncols) * transform["cell_lon"]
    points = [(lat, lon) for lat in lats for lon in lons]

    elevations = _query_elevations(points)
    elev = np.array(elevations, dtype=np.float32).reshape(nrows, ncols)

    # Fill any failed/no-data points from the grid mean so NaNs never reach
    # the LOS raycasting (a flat local fallback is safer than propagating NaN).
    if np.isnan(elev).any():
        valid_mean = float(np.nanmean(elev)) if not np.all(np.isnan(elev)) else 0.0
        elev = np.nan_to_num(elev, nan=valid_mean)

    np.save(elev_cache, elev)
    with open(transform_cache, "w") as f:
        json.dump(transform, f, indent=2)

    print(f"Elevation grid: min={elev.min():.1f} m, max={elev.max():.1f} m")
    return elev, transform


def latlon_to_grid(lat, lon, transform: dict):
    """Convert lat/lon (scalar or array) to fractional (row, col) grid indices."""
    row = (lat - transform["origin_lat"]) / transform["cell_lat"]
    col = (lon - transform["origin_lon"]) / transform["cell_lon"]
    return row, col


def grid_to_latlon(row, col, transform: dict):
    """Convert (row, col) grid indices to (lat, lon)."""
    lat = transform["origin_lat"] + row * transform["cell_lat"]
    lon = transform["origin_lon"] + col * transform["cell_lon"]
    return lat, lon
