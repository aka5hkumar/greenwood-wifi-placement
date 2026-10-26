# WiFi AP Placement Optimizer

Calculates the minimum number of solar-powered WiFi access points needed to
cover a park, cemetery, or campus, and outputs their optimal locations. Built
originally for Green-Wood Cemetery in Brooklyn, NY — now generalized to work
anywhere.

**Live demo:** an interactive Next.js + Vercel-hosted version of this tool
lets you search for any location and see a live computed placement on a map
(see `/app` for the frontend, `/api` for the serverless compute route). This
README covers the underlying Python pipeline, which both the CLI and the web
app share.

## What it does

Given the rated range of an access point on each frequency band, the tool:

1. Resolves the site boundary — the smallest enclosing park/cemetery/campus/
   nature-reserve feature on OpenStreetMap around a given point (or a
   user-supplied polygon)
2. Fetches tree cover and building footprints from OpenStreetMap
3. Queries a bare-earth elevation grid from a free point-query API
4. Pulls multi-year monthly solar irradiance from NASA POWER
5. Models RF propagation using ITU-R P.833 vegetation attenuation
6. Checks solar viability for each candidate location (100 W panel, 10 W load,
   50 Wh battery)
7. Solves an Integer Linear Program (HiGHS, via scipy) to minimize AP count
8. Writes results as JSON, a Google Earth KML overlay, and a Markdown summary

**No API keys required.** All data sources are free and open.

## Hardware assumptions (per AP node)

| Parameter | Value |
|---|---|
| Solar panel | 100 W rated |
| Load | 10 W continuous |
| Battery | 50 Wh |
| Derating factor | 0.80 (temperature, wiring, soiling) |
| Design basis | Worst above-freezing month with sufficient sun |
| Thermal cutoff | Below ~34 °F average monthly temperature |

## Usage

### Web app (recommended)

```bash
npm install
npm run dev        # or: vercel dev — runs the Next.js frontend + Python API together
```

Open `http://localhost:3000`, search for a location, tune the AP range, and
run a live compute. Green-Wood loads instantly from a pre-baked result on
first visit; any other search runs the full pipeline live (can take up to
~60s depending on site size).

### CLI

```bash
# Quick start using Makefile (Green-Wood defaults)
make run

# Or with venv active:
python3 cli.py                                  # Green-Wood, default ranges
python3 cli.py --range-2g 500 --range-5g 260     # override ranges
python3 cli.py --range-6g 200                    # with 6 GHz tri-band AP
python3 cli.py --coverage paths                  # cover walkable paths only

# Any other location — pass a point inside the site
python3 cli.py --lat 37.7172 --lon -122.4212 --site-name "John McLaren Park"

# Supply an exact boundary instead of the auto-resolved OSM polygon
python3 cli.py --boundary-file my_site.geojson --site-name "My Park"

# Re-fetch all external data
python3 cli.py --no-cache
```

All range values are in **feet**.

### Outputs (CLI)

| File | Description |
|---|---|
| `output/ap_placement.json` | AP list with lat/lon and name |
| `output/ap_placement.kml` | Google Earth overlay — open directly |
| `output/summary.md` | AP count, solar-marginal sites, efficiency flags |

The KML pins are colour-coded: **green** = solar viable, **yellow** = marginal (may need a better-sited panel).

## Setup

```bash
# Python: one-time venv + deps
make venv
# Or manually:
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt pytest

# Frontend
npm install
```

## Running the tests

```bash
make test
# Or manually (with venv active):
python3 -m pytest tests/ -v
```

Tests cover coordinate ordering, grid transforms, RF physics, solar budget
logic, and the ILP optimizer — so porting to a new location catches
regressions immediately.

## Project structure

```
├── app/                     Next.js frontend (search, map, params, results)
├── api/                     Vercel Python serverless functions
│   ├── compute.py           Runs the full placement pipeline for a site
│   ├── geocode.py           Nominatim place-search proxy
│   └── boundary.py          Resolves/previews a site boundary before compute
├── data/
│   ├── osm.py               OSM boundary, trees, buildings, paths (cached, any location)
│   ├── elevation.py         Bare-earth elevation via a free point-query API (cached)
│   ├── solar_irradiance.py  NASA POWER monthly GHI + temperature (cached)
│   ├── interference.py      Optional WiGLE RF interference layer
│   └── fixtures/            Static boundary fixtures (e.g. Green-Wood's default)
├── models/
│   ├── terrain.py           DSM construction, vectorised LOS ray-casting
│   ├── rf.py                ITU-R P.833 vegetation attenuation model
│   ├── power.py              Solar harvest vs 240 Wh/day demand
│   └── sizing.py            Area-size guardrail for the live serverless path
├── optimize/
│   └── placer.py            HiGHS ILP set-cover optimizer
├── output/
│   └── writer.py             JSON, KML, and Markdown writers (CLI only)
├── tests/                    Unit tests (no network calls)
├── plans/                    Planning documents
├── public/demo/              Pre-baked Green-Wood result for instant first load
└── cli.py                    CLI entry point + run_pipeline() shared with api/compute.py
```

## Notes

- External data is cached in `data/cache/` after the first run, keyed per
  site — subsequent runs of the same site are fully offline. The live web app
  doesn't rely on this cache (serverless filesystems are ephemeral); it always
  computes live, gated by an area-size cap (see `models/sizing.py`) that keeps
  requests within the hosting platform's function-timeout budget.
- November and December (and similar shoulder months at other latitudes) can
  have insufficient sun for 24/7 operation even with a fully exposed panel;
  the tool flags these as shoulder months in the summary.
- The `--wigle-key`-style optional RF interference layer (`data/interference.py`)
  is not currently wired into the CLI or API — it's a free-standing module you
  can call directly if you have a WiGLE.net API key.
- The site is public but kept out of search indexes (`robots.txt` + a
  `noindex` meta tag) to cut down on bot/crawler traffic, since the live
  compute path depends on free, rate-limited upstream APIs (Nominatim,
  Overpass, Open-Topo-Data). `api/compute.py` also enforces a strict
  per-IP rate limit, the two read-mostly lookup routes (`geocode`,
  `boundary`) set `Cache-Control` headers so repeat queries are served from
  Vercel's edge cache, and all three check same-origin before doing any
  work. This is in-memory/best-effort (resets on cold start, not shared
  across concurrent instances) — fine for a portfolio demo; swap in Vercel
  KV/Upstash for anything higher-traffic.
