"use client";

import { useEffect, useRef } from "react";
import {
  Map as MLMap,
  Marker,
  Popup,
  NavigationControl,
  LngLatBounds,
  setWorkerUrl,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { AccessPoint } from "../types";

// CARTO's keyless basemaps. Match the basemap to the OS colour scheme so a
// light map never gets dropped into the dark theme.
const BASEMAP_LIGHT = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";
const BASEMAP_DARK = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";

function prefersDark(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches
  );
}

const SURVEY = {
  viable: "#8cbf6a",
  marginal: "#e3a53f",
  boundary: "#e3a53f",
};

// MapLibre resolves its worker relative to its own module URL, which breaks
// once Next bundles it into a hashed chunk — the worker 404s and the map
// renders as a blank grey canvas. scripts/copy-maplibre-worker.mjs puts the
// worker here at build time; point MapLibre at it explicitly.
setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

interface ResultMapProps {
  boundary: [number, number][] | null;
  aps: AccessPoint[];
  center?: [number, number];
}

export default function ResultMap({ boundary, aps, center }: ResultMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MLMap | null>(null);
  const markersRef = useRef<Marker[]>([]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const initialCenter: [number, number] =
      center ??
      (boundary && boundary.length > 0
        ? boundary[0]
        : aps.length > 0
          ? [aps[0].lon, aps[0].lat]
          : [-73.99, 40.65]);

    const map = new MLMap({
      container: containerRef.current,
      style: prefersDark() ? BASEMAP_DARK : BASEMAP_LIGHT,
      center: initialCenter,
      zoom: 14,
    });

    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    function render() {
      markersRef.current.forEach((m) => m.remove());
      markersRef.current = [];

      if (map!.getLayer("boundary-fill")) map!.removeLayer("boundary-fill");
      if (map!.getLayer("boundary-line")) map!.removeLayer("boundary-line");
      if (map!.getSource("boundary")) map!.removeSource("boundary");

      if (boundary && boundary.length > 2) {
        map!.addSource("boundary", {
          type: "geojson",
          data: {
            type: "Feature",
            properties: {},
            geometry: {
              type: "Polygon",
              coordinates: [boundary],
            },
          },
        });
        map!.addLayer({
          id: "boundary-fill",
          type: "fill",
          source: "boundary",
          paint: {
            "fill-color": SURVEY.boundary,
            "fill-opacity": 0.07,
          },
        });
        map!.addLayer({
          id: "boundary-line",
          type: "line",
          source: "boundary",
          paint: {
            "line-color": SURVEY.boundary,
            "line-width": 1.5,
            "line-dasharray": [4, 2],
          },
        });
      }

      aps.forEach((ap) => {
        // Viable reads as a solid disc, marginal as a hollow ring — the
        // distinction survives a colour-vision deficiency, where sage green
        // against amber would not.
        const viable = ap.solar_status === "viable";
        const el = document.createElement("div");
        el.style.width = "13px";
        el.style.height = "13px";
        el.style.borderRadius = "50%";
        el.style.boxSizing = "border-box";
        el.style.cursor = "pointer";
        el.style.border = `2px solid ${viable ? SURVEY.viable : SURVEY.marginal}`;
        el.style.background = viable ? SURVEY.viable : "transparent";
        el.style.boxShadow = "0 0 0 1.5px rgba(0,0,0,0.45)";
        el.title = `${ap.name} — ${ap.solar_status}`;

        const popupHtml = `
          <div style="font-size:12px; line-height:1.6;">
            <strong>${ap.name}</strong><br/>
            Bands: ${ap.bands.join(", ")}<br/>
            Solar: ${ap.solar_status}<br/>
            Harvest: ${ap.harvest_wh} Wh/day<br/>
            Coverage eff.: ${ap.coverage_efficiency_pct}%<br/>
            Panel facing: ${ap.panel_facing} (${ap.panel_azimuth_deg}&deg;, tilt ${ap.panel_tilt_deg}&deg;)
          </div>
        `;

        const marker = new Marker({ element: el })
          .setLngLat([ap.lon, ap.lat])
          .setPopup(new Popup({ offset: 10 }).setHTML(popupHtml))
          .addTo(map!);

        markersRef.current.push(marker);
      });

      const bounds = new LngLatBounds();
      let hasBounds = false;
      if (boundary) {
        boundary.forEach((c) => {
          bounds.extend(c as [number, number]);
          hasBounds = true;
        });
      }
      aps.forEach((ap) => {
        bounds.extend([ap.lon, ap.lat]);
        hasBounds = true;
      });
      if (hasBounds) {
        map!.fitBounds(bounds, { padding: 40, duration: 400, maxZoom: 17 });
      } else if (center) {
        map!.jumpTo({ center, zoom: 14 });
      }
    }

    if (map.isStyleLoaded()) {
      render();
    } else {
      map.once("load", render);
    }
  }, [boundary, aps, center]);

  return <div ref={containerRef} className="map-container" style={{ height: "100%" }} />;
}
