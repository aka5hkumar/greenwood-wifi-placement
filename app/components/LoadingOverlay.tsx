"use client";

import { useEffect, useState } from "react";

const PHASES = [
  { label: "Resolving boundary…", sub: "Pulling site topology from OpenStreetMap", ms: 0 },
  { label: "Fetching elevation…", sub: "Downloading USGS 3DEP elevation raster", ms: 4000 },
  { label: "Modeling terrain…", sub: "Ray-casting line-of-sight over trees and buildings", ms: 11000 },
  { label: "Checking solar viability…", sub: "NASA POWER irradiance + panel harvest model", ms: 20000 },
  { label: "Solving placement…", sub: "HiGHS ILP minimizing AP count via set cover", ms: 30000 },
  { label: "Finishing up…", sub: "Almost there — large sites can take up to a minute", ms: 48000 },
];

export default function LoadingOverlay() {
  const [phaseIdx, setPhaseIdx] = useState(0);

  useEffect(() => {
    const timers = PHASES.slice(1).map((phase, i) =>
      setTimeout(() => setPhaseIdx(i + 1), phase.ms)
    );
    return () => timers.forEach(clearTimeout);
  }, []);

  const phase = PHASES[phaseIdx];

  return (
    <div className="loading-overlay">
      <div className="spinner" />
      <div className="loading-phase">{phase.label}</div>
      <div className="loading-sub">{phase.sub}</div>
    </div>
  );
}
