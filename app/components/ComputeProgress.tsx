"use client";

import { useEffect, useState } from "react";

/**
 * Phases are time-estimated on the client, not reported by the server — the
 * compute is a single request with no streaming. They exist to tell the user
 * what the wait is for, not to claim precise progress.
 */
const PHASES: { label: string; at: number }[] = [
  { label: "Reading site topology", at: 0 },
  { label: "Sampling elevation", at: 5 },
  { label: "Modelling line-of-sight", at: 13 },
  { label: "Checking solar viability", at: 22 },
  { label: "Solving placement", at: 32 },
  { label: "Almost there", at: 50 },
];

/** Seconds a typical run takes; the ring eases toward — but never reaches —
 *  100% so it can't sit "complete" while still waiting. */
const EXPECTED_S = 55;

export function useComputeProgress(active: boolean) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsed(0);
      return;
    }
    const started = Date.now();
    const id = setInterval(() => setElapsed((Date.now() - started) / 1000), 250);
    return () => clearInterval(id);
  }, [active]);

  // Asymptotic: fast at first, never quite arrives.
  const fraction = 1 - Math.exp(-elapsed / (EXPECTED_S / 2.2));
  const phase = [...PHASES].reverse().find((p) => elapsed >= p.at) ?? PHASES[0];

  return { elapsed, fraction: Math.min(fraction, 0.97), phaseLabel: phase.label };
}

export function ProgressRing({
  fraction,
  size = 15,
  stroke = 2.5,
}: {
  fraction: number;
  size?: number;
  stroke?: number;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg
      className="progress-ring"
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      aria-hidden
      focusable="false"
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        strokeWidth={stroke}
        className="progress-ring-track"
      />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - fraction)}
        className="progress-ring-fill"
        /* Start at 12 o'clock and fill clockwise. */
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}
