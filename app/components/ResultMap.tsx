"use client";

import { useEffect, useRef } from "react";
import { Map as MLMap, Marker, Popup, NavigationControl, LngLatBounds } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { AccessPoint } from "../types";

const BASEMAP_STYLE = "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

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
      style: BASEMAP_STYLE,
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
            "fill-color": "#3fb8af",
            "fill-opacity": 0.08,
          },
        });
        map!.addLayer({
          id: "boundary-line",
          type: "line",
          source: "boundary",
          paint: {
            "line-color": "#3fb8af",
            "line-width": 2,
          },
        });
      }

      aps.forEach((ap) => {
        const el = document.createElement("div");
        el.style.width = "14px";
        el.style.height = "14px";
        el.style.borderRadius = "50%";
        el.style.border = "2px solid rgba(0,0,0,0.35)";
        el.style.background = ap.solar_status === "viable" ? "#3ecf6a" : "#e0b63f";
        el.style.cursor = "pointer";

        const popupHtml = `
          <div style="font-size:12px; line-height:1.5; color:#111;">
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
