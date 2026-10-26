"""Central registry of all hardcoded physical and operational constants.

Edit this file to adapt the tool to a different site, hardware, or design basis.
All values are used by importing from this module; none are duplicated elsewhere.
"""

# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------
FT_PER_M = 3.28084

# ---------------------------------------------------------------------------
# Grid generation
# ---------------------------------------------------------------------------
CANDIDATE_SPACING_M = 20   # AP candidate grid spacing (~66 ft)
TEST_SPACING_M = 10        # Fine test-point grid for coverage reporting (~33 ft)
ILP_TEST_SPACING_M = 20    # Coarser grid used inside the ILP solver — pole placement
                           # only needs ~1 m precision; 20 m matches the candidate
                           # spacing and cuts constraints ~4× vs the 10 m grid
PATH_BUFFER_M = 4.57       # 15 ft — radius around paths for "paths" coverage mode

# ---------------------------------------------------------------------------
# AP hardware geometry
# ---------------------------------------------------------------------------
AP_HEIGHT_M = 1.0          # Panel/antenna height above ground (metres)
RX_HEIGHT_M = 1.524        # 5 ft — device height (person holding a phone)

# ---------------------------------------------------------------------------
# Solar panel hardware (per node)
# ---------------------------------------------------------------------------
PANEL_RATED_W = 100.0      # Rated panel wattage
LOAD_W = 10.0              # Continuous AP load
BATTERY_WH = 50.0          # Battery capacity
DERATING = 0.80            # Temperature / wiring / soiling derating factor
DEMAND_WH_PER_DAY = LOAD_W * 24.0  # 240 Wh/day

# Solar panel orientation defaults
PANEL_TILT_DEG = 40.0      # Tilt from horizontal (≈ site latitude for max annual yield)
PANEL_AZIMUTH_DEG = 180.0  # Compass bearing the panel faces: 180 = true south (optimal
                            # for Northern Hemisphere); override per-site as needed.
                            # For this deployment the 4G uplink comes from the west,
                            # but panel orientation is kept south for energy yield;
                            # a west-facing panel would trade ~15 % annual yield for
                            # better afternoon harvest alignment.
PANEL_FACING = "south"     # Human-readable label written to outputs

# ---------------------------------------------------------------------------
# Solar viability thresholds
# ---------------------------------------------------------------------------
FREEZE_THRESHOLD_F = 34.0  # Average monthly temperature below which APs can't operate
MARGINAL_LOW = 0.80        # harvest / demand ratio below this → unviable
MARGINAL_HIGH = 1.10       # harvest / demand ratio above this → clearly viable

# ---------------------------------------------------------------------------
# RF propagation
# ---------------------------------------------------------------------------
# ITU-R P.833 specific vegetation attenuation coefficients (dB per metre)
VEG_DB_PER_M = {2.4: 0.12, 5.0: 0.18, 6.0: 0.22}

# ---------------------------------------------------------------------------
# Terrain model
# ---------------------------------------------------------------------------
DEFAULT_TREE_HEIGHT_M = 15.0    # Used when OSM height tag is absent
TREE_CANOPY_THRESHOLD_M = 2.0   # DSM − bare_earth > this is counted as canopy
SHADE_RADIUS_M = 50.0           # Radius used for solid-angle shade fraction check

# ---------------------------------------------------------------------------
# ILP optimiser
# ---------------------------------------------------------------------------
MARGINAL_PENALTY = 1.5     # Weight multiplier for marginal-solar candidates

# ---------------------------------------------------------------------------
# Default site (Green-Wood Cemetery, Brooklyn NY) — just the starting point
# for the demo. Any lat/lon can be passed at runtime (CLI flags or the API);
# the boundary is resolved generically via data.osm.fetch_boundary.
# ---------------------------------------------------------------------------
DEFAULT_SITE_NAME = "Green-Wood Cemetery"
DEFAULT_LAT = 40.651
DEFAULT_LON = -73.994

# Bounding box (south, west, north, east) — used by tests; the live boundary
# polygon is what's actually used for grid clipping and coverage reporting.
CEMETERY_BBOX = (40.644250, -74.002056, 40.659556, -73.980500)

# If you want to override the resolved boundary (e.g. to refine the perimeter,
# carve out a sub-area, or supply a user-drawn polygon from the web UI),
# populate this list with (lon, lat) tuples in order. When non-empty
# (≥ 3 points) it replaces the resolved boundary entirely.
BOUNDARY_OVERRIDE_POLYGON: list[tuple[float, float]] = []

# Area cap (m²) per metre of candidate-grid spacing, squared — keeps the
# candidate/ILP-test-point counts (which scale as area / spacing²) bounded
# for the live serverless compute path. See models/sizing.py. Calibrated
# against Green-Wood's real OSM boundary (~483 acres, spacing 61 m at its
# default 2000 ft range → area/spacing² ≈ 526) plus headroom, so the demo's
# own default site comfortably passes.
MAX_AREA_PER_SPACING2 = 700
