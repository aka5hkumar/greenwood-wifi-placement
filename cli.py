"""WiFi AP placement optimizer — works for any park/cemetery/campus, not just
Green-Wood.

Usage
-----
    python cli.py                                   # Green-Wood defaults
    python cli.py --range-2g 2000 --range-5g 1250
    python cli.py --lat 37.7694 --lon -122.4862      # Golden Gate Park
    python cli.py --range-2g 2000 --range-5g 1250 --range-6g 800 --coverage paths
    python cli.py --help

The core pipeline (run_pipeline()) is shared with the Vercel API route in
api/compute.py — this module is just the CLI wrapper that adds the
multi-core/fork speedups suited to a long-lived local process and writes the
JSON/KML/Markdown files.
"""

import argparse
import json
import multiprocessing as mp
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Point, Polygon
from shapely.ops import transform as shapely_transform

from data.osm import fetch_boundary, fetch_trees, fetch_buildings, fetch_paths
from data.elevation import fetch_elevation_raster
from data.solar_irradiance import (
    fetch_solar_and_temperature,
    get_design_month,
    shoulder_months,
    classify_months,
    format_month_span,
    MONTH_NAMES,
)
from models.terrain import TerrainModel, to_utm, to_wgs84, configure_projection, current_epsg
from models.rf import effective_range_m
from models.power import (
    daily_harvest_wh, solar_status, best_panel_azimuth, facing_label,
)
from models.sizing import check_area
from optimize.placer import optimize_placement
from output.writer import write_placement_json, write_summary, write_kml
from constants import (
    FT_PER_M, DEFAULT_LAT, DEFAULT_LON, DEFAULT_SITE_NAME,
    CANDIDATE_SPACING_M, TEST_SPACING_M, ILP_TEST_SPACING_M, PATH_BUFFER_M,
    PANEL_TILT_DEG,
)

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "data", "fixtures")
GREENWOOD_FIXTURE = os.path.join(FIXTURE_DIR, "greenwood_boundary.geojson")


class AreaTooLargeError(Exception):
    """Raised when enforce_area_cap=True and the boundary is too big for a
    live serverless run at the chosen AP range."""
    def __init__(self, info: dict):
        self.info = info
        super().__init__(
            f"Boundary area ({info['area_acres']:.1f} acres) exceeds the live-compute "
            f"cap ({info['max_area_acres']:.1f} acres) at this AP range. "
            "Shrink the area or increase the 2.4 GHz range."
        )


class NoBoundaryError(Exception):
    """Raised when no enclosing site polygon could be resolved and none was supplied."""


class NoViableCandidatesError(Exception):
    """Raised when every candidate location is too shaded for solar viability."""


class NoSolutionError(Exception):
    """Raised when the ILP (and the greedy fallback) found no covering set."""


# ---------------------------------------------------------------------------
# Coverage matrix — fork-based process pool with shared state (CLI only)
# ---------------------------------------------------------------------------
# These are set before the ProcessPoolExecutor is created (or before the
# sequential in-process fallback is used). fork() copies the parent's address
# space (copy-on-write), so child processes inherit these without any
# serialisation overhead.
_mp_terrain = None
_mp_ilp_lats = _mp_ilp_lons = _mp_ilp_utm = None
_mp_ap_lats = _mp_ap_lons = _mp_ap_utms = None
_mp_all_nearby = _mp_bands_m = None


def _coverage_chunk(start_i: int, end_i: int):
    """Process candidates[start_i:end_i] using the module-level globals above."""
    results = []
    for i in range(start_i, end_i):
        nearby_raw = _mp_all_nearby[i]
        if not nearby_raw:
            results.append((i, np.array([], dtype=int), np.array([], dtype=bool)))
            continue
        nearby_idx = np.array(nearby_raw, dtype=int)
        ap_utm = _mp_ap_utms[i]

        nl = _mp_ilp_lats[nearby_idx]
        no = _mp_ilp_lons[nearby_idx]
        los_clear, veg_path = _mp_terrain.batch_los(
            _mp_ap_lats[i], _mp_ap_lons[i], nl, no
        )
        distances_m = np.linalg.norm(_mp_ilp_utm[nearby_idx] - ap_utm, axis=1)

        covered = np.zeros(len(nearby_idx), dtype=bool)
        for freq, rated_m in _mp_bands_m:
            eff_range = effective_range_m(rated_m, freq, veg_path)
            covered |= los_clear & (distances_m <= eff_range)

        results.append((i, nearby_idx, covered))
    return results


def _candidate_coverage(
    i, ap_lat, ap_lon, nearby_idx, test_lats, test_lons,
    test_utm, ap_utm, bands_m, terrain,
):
    """Single-candidate helper used for the post-ILP fine-grid pass."""
    if len(nearby_idx) == 0:
        return i, nearby_idx, np.array([], dtype=bool)
    nl = test_lats[nearby_idx]
    no = test_lons[nearby_idx]
    los_clear, veg_path = terrain.batch_los(ap_lat, ap_lon, nl, no)
    distances_m = np.linalg.norm(test_utm[nearby_idx] - ap_utm, axis=1)
    covered = np.zeros(len(nearby_idx), dtype=bool)
    for freq, rated_m in bands_m:
        eff_range = effective_range_m(rated_m, freq, veg_path)
        covered |= los_clear & (distances_m <= eff_range)
    return i, nearby_idx, covered


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def _epsg_transformers():
    epsg = current_epsg()
    fwd = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    inv = Transformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
    return fwd, inv


def generate_grid(boundary_wgs84, spacing_m: float) -> list[tuple[float, float]]:
    """Return (lat, lon) tuples on a metric grid clipped to the WGS84 boundary."""
    fwd, inv = _epsg_transformers()

    boundary_utm = shapely_transform(fwd.transform, boundary_wgs84)
    minx, miny, maxx, maxy = boundary_utm.bounds

    xs = np.arange(minx, maxx, spacing_m)
    ys = np.arange(miny, maxy, spacing_m)

    points = []
    for x in xs:
        for y in ys:
            lon, lat = inv.transform(x, y)
            if boundary_wgs84.contains(Point(lon, lat)):
                points.append((lat, lon))
    return points


def generate_path_grid(paths: list[dict], boundary_wgs84, spacing_m: float) -> list[tuple[float, float]]:
    """Return grid points within PATH_BUFFER_M of any path, inside the boundary."""
    if not paths:
        return generate_grid(boundary_wgs84, spacing_m)

    from shapely.ops import unary_union
    buffered = unary_union([p["geometry"].buffer(PATH_BUFFER_M / 111_320) for p in paths])
    buffered = buffered.intersection(boundary_wgs84)

    fwd, inv = _epsg_transformers()
    boundary_utm = shapely_transform(fwd.transform, boundary_wgs84)
    minx, miny, maxx, maxy = boundary_utm.bounds
    xs = np.arange(minx, maxx, spacing_m)
    ys = np.arange(miny, maxy, spacing_m)

    points = []
    for x in xs:
        for y in ys:
            lon, lat = inv.transform(x, y)
            pt = Point(lon, lat)
            if buffered.contains(pt):
                points.append((lat, lon))
    return points


def _load_fixture_polygon(path: str) -> list[tuple[float, float]]:
    with open(path) as f:
        gj = json.load(f)
    geom = gj["geometry"] if "geometry" in gj else gj
    return [(lon, lat) for lon, lat in geom["coordinates"][0]]


# ---------------------------------------------------------------------------
# Shared pipeline — used by both the CLI (below) and api/compute.py
# ---------------------------------------------------------------------------

def run_pipeline(
    lat: float = DEFAULT_LAT,
    lon: float = DEFAULT_LON,
    site_name: str = DEFAULT_SITE_NAME,
    range_2g_ft: float = 2000.0,
    range_5g_ft: float = 1250.0,
    range_6g_ft: float | None = None,
    coverage: str = "full",
    no_cache: bool = False,
    cache_key: str = "default",
    boundary_override: list[tuple[float, float]] | None = None,
    parallel: bool = True,
    enforce_area_cap: bool = False,
) -> dict:
    """
    Run the full placement pipeline for an arbitrary site and return a dict
    with the AP list, resolved boundary, and summary stats.

    Raises AreaTooLargeError / NoBoundaryError / NoViableCandidatesError /
    NoSolutionError on known failure conditions so callers (CLI or the API
    route) can render a friendly message instead of a stack trace.
    """
    bands_ft = [(2.4, range_2g_ft), (5.0, range_5g_ft)]
    if range_6g_ft:
        bands_ft.append((6.0, range_6g_ft))
    bands_m = [(freq, rng / FT_PER_M) for freq, rng in bands_ft]
    primary_freq, primary_range_m = bands_m[0]   # 2.4 GHz — longest range
    primary_range_ft = primary_range_m * FT_PER_M

    # At large ranges the constraint matrix becomes dense (density ≈ π·r²/area).
    # Increasing grid spacing reduces problem size as spacing², keeping IPM tractable.
    adaptive_cand_m = max(CANDIDATE_SPACING_M, primary_range_m / 10)
    adaptive_ilp_m  = max(ILP_TEST_SPACING_M,  primary_range_m / 10)

    print(f"\n=== WiFi Placement Optimizer: {site_name} ===")
    print(f"Bands: {[(f'{f} GHz', f'{r:.0f} ft') for f, r in bands_ft]}")
    print(f"Coverage mode: {coverage}\n")

    # ------------------------------------------------------------------
    # 1. Fetch data
    # ------------------------------------------------------------------
    print("=== Fetching OSM Data ===")
    boundary = fetch_boundary(
        lat, lon, no_cache=no_cache, cache_key=cache_key, override_polygon=boundary_override,
    )
    if boundary is None:
        raise NoBoundaryError(
            "No enclosing park/cemetery/campus boundary found near this point. "
            "Draw a boundary manually or try a nearby landmark."
        )
    configure_projection(*boundary.centroid.coords[0])

    # Check the size guardrail BEFORE any of the expensive fetches below.
    # Those calls (Overpass for trees/buildings/paths, the elevation grid)
    # are the slowest part of the run, so an over-cap site must be rejected
    # here rather than after burning the whole serverless time budget.
    boundary_utm = Polygon(
        [to_utm(lon_, lat_) for lon_, lat_ in boundary.exterior.coords],
        holes=[
            [to_utm(lon_, lat_) for lon_, lat_ in interior.coords]
            for interior in boundary.interiors
        ],
    )
    ok, area_info = check_area(boundary_utm.area, primary_range_m)
    if enforce_area_cap and not ok:
        raise AreaTooLargeError(area_info)

    trees = fetch_trees(boundary, no_cache=no_cache, cache_key=cache_key)
    buildings = fetch_buildings(boundary, no_cache=no_cache, cache_key=cache_key)
    paths = fetch_paths(boundary, no_cache=no_cache, cache_key=cache_key)

    print("\n=== Fetching Elevation ===")
    elevation, elev_transform = fetch_elevation_raster(boundary, no_cache=no_cache, cache_key=cache_key)

    print("\n=== Fetching Solar Data ===")
    centroid_lon, centroid_lat = boundary.centroid.coords[0]
    solar_data = fetch_solar_and_temperature(
        lat=centroid_lat, lon=centroid_lon, no_cache=no_cache, cache_key=cache_key,
    )
    design_month, design_ghi = get_design_month(solar_data)
    off_season = shoulder_months(solar_data)
    month_classes = classify_months(solar_data)
    print(
        f"Design month: {MONTH_NAMES[design_month]} "
        f"(GHI {design_ghi:.0f} Wh/m²/day, "
        f"avg temp {solar_data[str(design_month)]['avg_temp_f']:.1f} °F)"
    )
    if off_season:
        print(f"Shoulder months (limited solar, daytime-only): {', '.join(off_season)}")

    # ------------------------------------------------------------------
    # 2. Build terrain model  (area guardrail already applied above)
    # ------------------------------------------------------------------
    print("\n=== Building Terrain Model ===")
    terrain = TerrainModel(elevation, elev_transform, trees, buildings)

    # ------------------------------------------------------------------
    # 3. Generate candidate and test-point grids
    # ------------------------------------------------------------------
    print("\n=== Generating Grids ===")
    candidates = generate_grid(boundary, adaptive_cand_m)

    if coverage == "paths":
        report_points = generate_path_grid(paths, boundary, TEST_SPACING_M)
        ilp_points    = generate_path_grid(paths, boundary, adaptive_ilp_m)
    else:
        report_points = generate_grid(boundary, TEST_SPACING_M)
        ilp_points    = generate_grid(boundary, adaptive_ilp_m)

    print(f"Grid spacing : candidates {adaptive_cand_m:.0f} m  "
          f"ILP {adaptive_ilp_m:.0f} m  report {TEST_SPACING_M} m")
    print(f"Candidates: {len(candidates):,}  "
          f"ILP test grid: {len(ilp_points):,}  "
          f"Report grid: {len(report_points):,}")

    # ------------------------------------------------------------------
    # 4. Solar viability per candidate
    # ------------------------------------------------------------------
    print("\n=== Computing Solar Viability ===")
    t_solar = time.time()
    candidate_meta = []
    for clat, clon in candidates:
        dir_shade = terrain.shade_by_azimuth(clat, clon)
        shade = float(min(dir_shade.sum(), 1.0))
        harvest = daily_harvest_wh(design_ghi, shade)
        status = solar_status(harvest)
        azimuth, sky_score = best_panel_azimuth(dir_shade, latitude_deg=clat)
        candidate_meta.append({
            "shade": shade,
            "harvest": harvest,
            "status": status,
            "panel_azimuth_deg": round(azimuth, 1),
            "panel_sky_score": round(sky_score, 3),
        })

    viable_idx = [i for i, m in enumerate(candidate_meta) if m["status"] != "unviable"]
    viable_candidates = [candidates[i] for i in viable_idx]
    viable_meta = [candidate_meta[i] for i in viable_idx]

    n_unviable = len(candidates) - len(viable_candidates)
    n_marginal = sum(1 for m in viable_meta if m["status"] == "marginal")
    print(
        f"Viable: {len(viable_candidates) - n_marginal}  "
        f"Marginal: {n_marginal}  "
        f"Unviable (too shaded): {n_unviable}  "
        f"({time.time()-t_solar:.1f}s)"
    )

    if not viable_candidates:
        raise NoViableCandidatesError(
            "No viable candidate locations found — every candidate is too shaded. "
            "Check that the site has open-sky areas."
        )

    # ------------------------------------------------------------------
    # 5. Build coverage matrix
    # ------------------------------------------------------------------
    print("\n=== Computing Coverage Matrix ===")
    t_cov = time.time()

    ilp_lats = np.array([p[0] for p in ilp_points])
    ilp_lons = np.array([p[1] for p in ilp_points])
    ilp_utm  = np.column_stack(to_utm(ilp_lons, ilp_lats))
    ilp_kdtree = cKDTree(ilp_utm)

    ap_lats = np.array([p[0] for p in viable_candidates])
    ap_lons = np.array([p[1] for p in viable_candidates])
    ap_utms = np.column_stack(to_utm(ap_lons, ap_lats))

    all_nearby = ilp_kdtree.query_ball_point(ap_utms, primary_range_m * 1.05)

    global _mp_terrain, _mp_ilp_lats, _mp_ilp_lons, _mp_ilp_utm
    global _mp_ap_lats, _mp_ap_lons, _mp_ap_utms, _mp_all_nearby, _mp_bands_m
    _mp_terrain   = terrain
    _mp_ilp_lats  = ilp_lats
    _mp_ilp_lons  = ilp_lons
    _mp_ilp_utm   = ilp_utm
    _mp_ap_lats   = ap_lats
    _mp_ap_lons   = ap_lons
    _mp_ap_utms   = ap_utms
    _mp_all_nearby = all_nearby
    _mp_bands_m   = bands_m

    n_cands = len(viable_candidates)
    coverage_matrix = np.zeros((n_cands, len(ilp_points)), dtype=bool)

    if parallel:
        # Fork-based process pool — only safe/useful for a long-lived local
        # process with multiple cores (the CLI). Not used on serverless,
        # where a single invocation usually gets one vCPU.
        n_workers = os.cpu_count() or 4
        chunk_size = max(1, n_cands // (n_workers * 8))
        chunks = [(i, min(i + chunk_size, n_cands))
                  for i in range(0, n_cands, chunk_size)]

        print(f"  {n_cands:,} candidates × {len(ilp_points):,} ILP points  "
              f"({n_workers} processes, {len(chunks)} chunks of ~{chunk_size})")

        done_count = 0
        ctx = mp.get_context("fork")
        pool = ProcessPoolExecutor(max_workers=n_workers, mp_context=ctx)
        try:
            futures = {pool.submit(_coverage_chunk, s, e): (s, e) for s, e in chunks}
            for future in as_completed(futures):
                for i, nearby_idx, covered in future.result():
                    if len(nearby_idx):
                        coverage_matrix[i, nearby_idx] = covered
                    done_count += 1
                if done_count % max(chunk_size, 200) < chunk_size or done_count == n_cands:
                    elapsed = time.time() - t_cov
                    rate = done_count / elapsed if elapsed > 0 else 1
                    eta = (n_cands - done_count) / rate
                    print(
                        f"  {done_count:,}/{n_cands:,} candidates  "
                        f"({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)    ",
                        end="\r",
                    )
        except KeyboardInterrupt:
            pool.shutdown(wait=False, cancel_futures=True)
            print("\nInterrupted.")
            raise SystemExit(1)
        else:
            pool.shutdown(wait=False)
    else:
        # Sequential, in-process — used by the serverless API route, where
        # spawning extra processes offers no benefit on a single vCPU and
        # adds overhead/memory the function may not have room for.
        print(f"  {n_cands:,} candidates × {len(ilp_points):,} ILP points  (sequential)")
        for i, nearby_idx, covered in _coverage_chunk(0, n_cands):
            if len(nearby_idx):
                coverage_matrix[i, nearby_idx] = covered

    print(f"\n  Coverage matrix: {coverage_matrix.sum():,} covered pairs  "
          f"({time.time()-t_cov:.1f}s total)")

    # ------------------------------------------------------------------
    # 6. ILP optimisation
    # ------------------------------------------------------------------
    print("\n=== Running ILP Optimiser ===")
    statuses = [m["status"] for m in viable_meta]
    selected_idx = optimize_placement(coverage_matrix, statuses, parallel=parallel)

    if not selected_idx:
        raise NoSolutionError("No solution found — try increasing range values.")

    # ------------------------------------------------------------------
    # 7. Fine-grid coverage for selected APs (stats + summary)
    # ------------------------------------------------------------------
    print("\n=== Computing Fine Coverage for Selected APs ===")
    rep_lats = np.array([p[0] for p in report_points])
    rep_lons = np.array([p[1] for p in report_points])
    rep_utm  = np.column_stack(to_utm(rep_lons, rep_lats))
    rep_kdtree = cKDTree(rep_utm)

    n_sel = len(selected_idx)
    sel_lats = ap_lats[selected_idx]
    sel_lons = ap_lons[selected_idx]
    sel_utms = ap_utms[selected_idx]
    sel_nearby = rep_kdtree.query_ball_point(sel_utms, primary_range_m * 1.05)

    selected_coverage = np.zeros((n_sel, len(report_points)), dtype=bool)
    for rank in range(n_sel):
        nearby_idx = np.array(sel_nearby[rank], dtype=int) if sel_nearby[rank] else np.array([], dtype=int)
        if len(nearby_idx):
            _, near, cov = _candidate_coverage(
                rank, sel_lats[rank], sel_lons[rank],
                nearby_idx, rep_lats, rep_lons, rep_utm, sel_utms[rank],
                bands_m, terrain,
            )
            selected_coverage[rank, near] = cov

    site_prefix = "".join(w[0] for w in site_name.split()[:3]).upper() or "AP"
    aps = []
    for rank, idx in enumerate(selected_idx):
        ap_lat, ap_lon = viable_candidates[idx]
        name = f"{site_prefix}-AP-{rank + 1:02d}"
        meta = viable_meta[idx]

        ap_cov = selected_coverage[rank]
        n_covered = int(ap_cov.sum())

        others = [r for r in range(n_sel) if r != rank]
        if others:
            other_cov = selected_coverage[others].any(axis=0)
            overlap = int((ap_cov & other_cov).sum())
        else:
            overlap = 0
        overlap_pct = 100.0 * overlap / n_covered if n_covered else 0.0

        ap_circle_utm = Point(*ap_utms[idx]).buffer(primary_range_m)
        rated_area_m2 = ap_circle_utm.intersection(boundary_utm).area
        rated_circle_area_ft2 = max(rated_area_m2 * (FT_PER_M ** 2), 1.0)
        covered_area_ft2 = n_covered * (TEST_SPACING_M * FT_PER_M) ** 2
        efficiency_pct = min(100.0, 100.0 * covered_area_ft2 / rated_circle_area_ft2)

        ap_azimuth = meta["panel_azimuth_deg"]
        aps.append({
            "name": name,
            "lat": round(ap_lat, 6),
            "lon": round(ap_lon, 6),
            "bands": [f"{f:.4g}GHz" for f, _ in bands_ft],
            "solar_status": meta["status"],
            "harvest_wh": round(meta["harvest"], 1),
            "shade_pct": round(meta["shade"] * 100.0, 1),
            "coverage_efficiency_pct": round(efficiency_pct, 1),
            "overlap_pct": round(overlap_pct, 1),
            "panel_facing": facing_label(ap_azimuth),
            "panel_azimuth_deg": ap_azimuth,
            "panel_tilt_deg": PANEL_TILT_DEG,
            "panel_sky_score": meta["panel_sky_score"],
        })

    total_covered = int(selected_coverage.any(axis=0).sum())
    coverage_pct = 100.0 * total_covered / len(report_points) if report_points else 0.0

    return {
        "ok": True,
        "site_name": site_name,
        "boundary_coords": [[lon_, lat_] for lon_, lat_ in boundary.exterior.coords],
        "aps": aps,
        "params_used": {
            "lat": lat, "lon": lon,
            "range_2g_ft": range_2g_ft, "range_5g_ft": range_5g_ft, "range_6g_ft": range_6g_ft,
            "coverage": coverage,
        },
        "stats": {
            "design_month": MONTH_NAMES[design_month],
            "design_ghi_wh_m2_day": round(design_ghi, 0),
            # Peak sun-hours is the intuitive form of GHI: 3,000 Wh/m²/day at
            # 1000 W/m² reference irradiance ≈ 3.0 hours of full sun.
            "design_peak_sun_hours": round(design_ghi / 1000.0, 1),
            "operating_months_label": format_month_span(month_classes["operating"]),
            "shoulder_months_label": format_month_span(month_classes["shoulder"]),
            "freezing_months_label": format_month_span(month_classes["freezing"]),
            "shoulder_months": off_season,
            "area_acres": round(area_info["area_acres"], 1),
            "candidate_count": len(candidates),
            "viable_candidate_count": len(viable_candidates),
            "report_point_count": len(report_points),
            "total_covered": total_covered,
            "coverage_pct": round(coverage_pct, 1),
            "ap_count": len(aps),
        },
        # Internal, non-JSON-safe fields used only by the CLI for KML/summary.
        "_selected_coverage": selected_coverage,
        "_report_point_count": len(report_points),
        "_primary_range_ft": primary_range_ft,
        "_off_season": off_season,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Outputs optimal solar-powered WiFi AP placement for any park, cemetery, or campus.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
outputs:
  output/ap_placement.json   Machine-readable AP list (lat/lon/name)
  output/ap_placement.kml    Google Earth overlay — open directly in Google Earth
  output/summary.md          AP count, solar-marginal sites, range suggestions
        """,
    )

    parser.add_argument(
        "--lat", type=float, default=DEFAULT_LAT, metavar="DEG",
        help=f"Latitude of a point inside the site (default: {DEFAULT_LAT}, Green-Wood Cemetery)",
    )
    parser.add_argument(
        "--lon", type=float, default=DEFAULT_LON, metavar="DEG",
        help=f"Longitude of a point inside the site (default: {DEFAULT_LON}, Green-Wood Cemetery)",
    )
    parser.add_argument(
        "--site-name", default=DEFAULT_SITE_NAME, metavar="NAME",
        help="Human-readable site name used in output file labels",
    )
    parser.add_argument(
        "--boundary-file", default=None, metavar="PATH",
        help="Path to a GeoJSON Polygon to use as the site boundary override "
             "(skips OSM boundary lookup entirely)",
    )
    parser.add_argument(
        "--range-2g", type=float, default=2000.0, metavar="FT",
        help="Rated range of the AP on 2.4 GHz in feet (default: 2000)",
    )
    parser.add_argument(
        "--range-5g", type=float, default=1250.0, metavar="FT",
        help="Rated range of the AP on 5 GHz in feet (default: 1250)",
    )
    parser.add_argument(
        "--range-6g", type=float, default=None, metavar="FT",
        help=(
            "Rated range of the AP on 6 GHz in feet. "
            "Omit this flag entirely if the AP does not support 6 GHz."
        ),
    )
    parser.add_argument(
        "--coverage", choices=["full", "paths"], default="full",
        help=(
            "Coverage target for the optimiser. "
            "'full' — every point inside the site boundary (default). "
            "'paths' — only areas within 15 ft of walkable paths."
        ),
    )
    parser.add_argument(
        "--no-cache", action="store_true",
        help="Re-download all external data even if a local cache exists.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.no_cache:
        cache_dir = os.path.join("data", "cache")
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir)
            print("Cache cleared.")

    is_default_site = (
        args.boundary_file is None
        and args.lat == DEFAULT_LAT
        and args.lon == DEFAULT_LON
    )
    if args.boundary_file:
        boundary_override = _load_fixture_polygon(args.boundary_file)
    elif is_default_site and os.path.exists(GREENWOOD_FIXTURE):
        # Zero-config `python cli.py` keeps working without an Overpass
        # boundary search — this is the same crude 6-vertex polygon the
        # tool has always shipped with for Green-Wood.
        boundary_override = _load_fixture_polygon(GREENWOOD_FIXTURE)
    else:
        boundary_override = None

    cache_key = "greenwood" if is_default_site else f"{args.lat:.4f}_{args.lon:.4f}"

    try:
        result = run_pipeline(
            lat=args.lat,
            lon=args.lon,
            site_name=args.site_name,
            range_2g_ft=args.range_2g,
            range_5g_ft=args.range_5g,
            range_6g_ft=args.range_6g,
            coverage=args.coverage,
            no_cache=args.no_cache,
            cache_key=cache_key,
            boundary_override=boundary_override,
            parallel=True,
            enforce_area_cap=False,
        )
    except (AreaTooLargeError, NoBoundaryError, NoViableCandidatesError, NoSolutionError) as exc:
        print(f"\nERROR: {exc}")
        return

    print("\n=== Writing Output ===")
    os.makedirs("output", exist_ok=True)
    write_placement_json(result["aps"], "output/ap_placement.json")
    write_kml(result["aps"], "output/ap_placement.kml")
    write_summary(
        result["aps"],
        result["_selected_coverage"],
        result["_report_point_count"],
        result["_primary_range_ft"],
        "output/summary.md",
        shoulder_months_list=result["_off_season"],
    )

    stats = result["stats"]
    print(
        f"\nDone! {stats['ap_count']} APs placed, "
        f"{stats['total_covered']:,}/{stats['report_point_count']:,} test points covered "
        f"({stats['coverage_pct']:.1f}%)."
    )
    print("  output/ap_placement.json")
    print("  output/ap_placement.kml  ← open in Google Earth")
    print("  output/summary.md")


if __name__ == "__main__":
    main()
