"""Area-size guardrail for the live serverless compute path.

Candidate/ILP-test-point counts scale as area / spacing**2, where
spacing = max(floor, range_m / 10) (see the adaptive-spacing formula shared
by cli.py and api/compute.py). Keeping that ratio bounded keeps the
coverage-matrix build + ILP solve within a serverless function's time budget
instead of growing unboundedly with the chosen site's area.
"""

from constants import CANDIDATE_SPACING_M, MAX_AREA_PER_SPACING2

M2_PER_ACRE = 4046.8564224


def adaptive_spacing_m(primary_range_m: float, floor_m: float = CANDIDATE_SPACING_M) -> float:
    return max(floor_m, primary_range_m / 10)


def max_area_m2(primary_range_m: float) -> float:
    """Largest boundary area (m²) considered safe for a live serverless run
    at the given primary (2.4 GHz) AP range."""
    spacing = adaptive_spacing_m(primary_range_m)
    return MAX_AREA_PER_SPACING2 * spacing ** 2


def check_area(boundary_area_m2: float, primary_range_m: float) -> tuple[bool, dict]:
    """
    Returns (ok, info). info always has area/cap in both m² and acres, so
    callers (CLI or API) can render a friendly "shrink the area or increase
    AP range" message without recomputing anything.
    """
    cap_m2 = max_area_m2(primary_range_m)
    info = {
        "area_m2": boundary_area_m2,
        "max_area_m2": cap_m2,
        "area_acres": boundary_area_m2 / M2_PER_ACRE,
        "max_area_acres": cap_m2 / M2_PER_ACRE,
    }
    return boundary_area_m2 <= cap_m2, info
