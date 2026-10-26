"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import SearchBox from "./components/SearchBox";
import ParamsPanel from "./components/ParamsPanel";
import StatsPanel from "./components/StatsPanel";
import LoadingOverlay from "./components/LoadingOverlay";
import { circlePolygon } from "./lib/geo";
import type {
  ComputeError,
  ComputeResponse,
  ComputeResult,
  CoverageMode,
  GeocodeResult,
} from "./types";

const ResultMap = dynamic(() => import("./components/ResultMap"), { ssr: false });

type Stage = "idle" | "boundary-preview" | "loading" | "result" | "error";

interface PendingSite {
  lat: number;
  lon: number;
  displayName: string;
  boundary: [number, number][] | null;
  boundaryLookupFailed: boolean;
}

const DEFAULT_RANGE_2G = 2000;
const DEFAULT_RANGE_5G = 1250;

function PageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [stage, setStage] = useState<Stage>("idle");
  const [isDemo, setIsDemo] = useState(true);
  const [result, setResult] = useState<ComputeResult | null>(null);
  const [error, setError] = useState<ComputeError | null>(null);
  const [pending, setPending] = useState<PendingSite | null>(null);
  const [useCircle, setUseCircle] = useState(false);

  const [range2g, setRange2g] = useState(DEFAULT_RANGE_2G);
  const [range5g, setRange5g] = useState(DEFAULT_RANGE_5G);
  const [range6g, setRange6g] = useState<number | null>(null);
  const [coverage, setCoverage] = useState<CoverageMode>("full");

  const appliedUrlParams = useRef(false);

  // Load demo result on first mount (unless URL already specifies a location)
  useEffect(() => {
    const lat = searchParams.get("lat");
    const lon = searchParams.get("lon");
    if (lat && lon && !appliedUrlParams.current) {
      appliedUrlParams.current = true;
      const r2 = Number(searchParams.get("r2")) || DEFAULT_RANGE_2G;
      const r5 = Number(searchParams.get("r5")) || DEFAULT_RANGE_5G;
      const r6raw = searchParams.get("r6");
      const r6 = r6raw ? Number(r6raw) : null;
      const cov = (searchParams.get("cov") as CoverageMode) || "full";
      const site = searchParams.get("site") || "Custom Site";
      setRange2g(r2);
      setRange5g(r5);
      setRange6g(r6);
      setCoverage(cov);
      setIsDemo(false);
      runCompute(
        { lat: Number(lat), lon: Number(lon), site_name: site },
        { range2g: r2, range5g: r5, range6g: r6, coverage: cov },
        null
      );
      return;
    }

    fetch("/demo/greenwood.json")
      .then((res) => res.json())
      .then((data: ComputeResponse) => {
        if (data.ok) {
          setResult(data);
          setStage("result");
          setIsDemo(true);
        }
      })
      .catch(() => {
        /* demo file missing is non-fatal */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function syncUrl(site: {
    lat: number;
    lon: number;
    site_name: string;
  }) {
    const params = new URLSearchParams();
    params.set("lat", site.lat.toFixed(6));
    params.set("lon", site.lon.toFixed(6));
    params.set("site", site.site_name);
    params.set("r2", String(range2g));
    params.set("r5", String(range5g));
    if (range6g) params.set("r6", String(range6g));
    params.set("cov", coverage);
    router.replace(`/?${params.toString()}`, { scroll: false });
  }

  async function handleSelectLocation(geo: GeocodeResult) {
    setError(null);
    setIsDemo(false);
    try {
      const res = await fetch(`/api/boundary?lat=${geo.lat}&lon=${geo.lon}`);
      const data = await res.json();
      const boundary = data.ok ? data.boundary : null;
      setPending({
        lat: geo.lat,
        lon: geo.lon,
        displayName: geo.display_name,
        boundary,
        boundaryLookupFailed: !boundary,
      });
      setUseCircle(!boundary);
      setStage("boundary-preview");
    } catch {
      setPending({
        lat: geo.lat,
        lon: geo.lon,
        displayName: geo.display_name,
        boundary: null,
        boundaryLookupFailed: true,
      });
      setUseCircle(true);
      setStage("boundary-preview");
    }
  }

  const runCompute = useCallback(
    async (
      site: { lat: number; lon: number; site_name: string },
      params: {
        range2g: number;
        range5g: number;
        range6g: number | null;
        coverage: CoverageMode;
      },
      boundary: [number, number][] | null
    ) => {
      setStage("loading");
      setError(null);
      try {
        const res = await fetch("/api/compute", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            lat: site.lat,
            lon: site.lon,
            site_name: site.site_name,
            range_2g_ft: params.range2g,
            range_5g_ft: params.range5g,
            range_6g_ft: params.range6g,
            coverage: params.coverage,
            boundary,
            cache_key: null,
          }),
        });
        const data: ComputeResponse = await res.json();
        if (data.ok) {
          setResult(data);
          setStage("result");
          setIsDemo(false);
          syncUrl(site);
        } else {
          setError(data);
          setStage("error");
        }
      } catch (e) {
        setError({
          ok: false,
          error: "internal_error",
          message: e instanceof Error ? e.message : "Network error contacting the compute API.",
        });
        setStage("error");
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [range2g, range5g, range6g, coverage]
  );

  function handleRunCompute() {
    if (!pending) return;
    const boundary = useCircle ? circlePolygon(pending.lat, pending.lon, 300) : pending.boundary;
    runCompute(
      { lat: pending.lat, lon: pending.lon, site_name: pending.displayName },
      { range2g, range5g, range6g, coverage },
      boundary
    );
  }

  const previewBoundary = pending
    ? useCircle
      ? circlePolygon(pending.lat, pending.lon, 300)
      : pending.boundary
    : null;

  const mapBoundary = stage === "result" && result ? result.boundary_coords : previewBoundary;
  const mapAps = stage === "result" && result ? result.aps : [];
  const mapCenter: [number, number] | undefined = pending
    ? [pending.lon, pending.lat]
    : result
      ? [result.params_used.lon, result.params_used.lat]
      : undefined;

  const disabled = stage === "loading";

  return (
    <div>
      <SearchBox onSelect={handleSelectLocation} disabled={disabled} />

      {stage === "boundary-preview" && pending && (
        <div className="card boundary-confirm">
          <div>
            <strong>{pending.displayName}</strong>
            <div className="subtle">
              {pending.boundary
                ? "Boundary resolved from OpenStreetMap. Confirm below or use a simple radius instead."
                : "No OSM boundary polygon found for this point — falling back to a 300 m radius circle."}
            </div>
          </div>
          {pending.boundary && (
            <div className="toggle-row">
              <button
                type="button"
                className={`toggle-btn${!useCircle ? " active" : ""}`}
                onClick={() => setUseCircle(false)}
              >
                Use OSM boundary
              </button>
              <button
                type="button"
                className={`toggle-btn${useCircle ? " active" : ""}`}
                onClick={() => setUseCircle(true)}
              >
                Use 300m circle
              </button>
            </div>
          )}
          <button type="button" className="btn" onClick={handleRunCompute}>
            Run placement for this site
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setStage(result ? "result" : "idle");
              setPending(null);
            }}
          >
            Cancel
          </button>
        </div>
      )}

      {stage === "error" && error && (
        <div className="error-banner">
          {error.error === "area_too_large" ? (
            <>
              <strong>Site too large.</strong> This boundary covers {error.area_acres.toFixed(1)}{" "}
              acres, which exceeds the {error.max_area_acres.toFixed(1)}-acre limit for a live
              compute. Try a smaller site, or reduce 2.4/5 GHz range so fewer candidates are
              needed.
            </>
          ) : (
            <>
              <strong>{error.error}.</strong> {error.message}
            </>
          )}
        </div>
      )}

      <div className="tool-grid">
        <div className="panel-stack">
          <ParamsPanel
            range2g={range2g}
            range5g={range5g}
            range6g={range6g}
            coverage={coverage}
            disabled={disabled}
            onChange={(next) => {
              if (next.range2g !== undefined) setRange2g(next.range2g);
              if (next.range5g !== undefined) setRange5g(next.range5g);
              if (next.range6g !== undefined) setRange6g(next.range6g);
              if (next.coverage !== undefined) setCoverage(next.coverage);
            }}
          />

          {stage === "result" && result && (
            <>
              {isDemo && (
                <div className="badge">
                  <span className="badge-dot" />
                  Pre-computed result — search above for a live location
                </div>
              )}
              <StatsPanel stats={result.stats} siteName={result.site_name} />
              <div className="card">
                <h3 className="section-title">Access points ({result.aps.length})</h3>
                <div className="ap-list">
                  {result.aps.map((ap) => (
                    <div className="ap-row" key={ap.name}>
                      <span>{ap.name}</span>
                      <span className={`status-pill ${ap.solar_status}`}>{ap.solar_status}</span>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="map-container">
          <ResultMap boundary={mapBoundary} aps={mapAps} center={mapCenter} />
          {stage === "loading" && <LoadingOverlay />}
          {(mapBoundary || mapAps.length > 0) && (
            <div className="legend">
              <div className="legend-item">
                <span className="dot dot-viable" /> Solar viable
              </div>
              <div className="legend-item">
                <span className="dot dot-marginal" /> Marginal
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function Page() {
  // The hero text lives here, outside the Suspense boundary, so it is
  // server-rendered. PageInner calls useSearchParams(), which opts the whole
  // subtree out of SSR — without this the initial HTML carried almost no
  // text, and browser language detection would mis-identify the page and
  // offer to translate it.
  return (
    <div>
      <div className="hero">
        <h1>Solar WiFi Placement Optimizer</h1>
        <p>
          Computes the minimum number of solar-powered WiFi access points needed to cover any
          park, cemetery, or campus — using real OpenStreetMap topology, elevation-based
          line-of-sight, vegetation attenuation, solar viability, and an integer-linear-program
          set-cover solve. Search for a location below, or explore the pre-computed Green-Wood
          Cemetery example.
        </p>
      </div>

      <Suspense
        fallback={
          <div className="card subtle">
            Loading the interactive map and the pre-computed Green-Wood Cemetery example…
          </div>
        }
      >
        <PageInner />
      </Suspense>
    </div>
  );
}
