"use client";

import type { Stats } from "../types";

/**
 * Every figure here is paired with the unit and the thing it is a fraction
 * of, because the raw pipeline vocabulary ("design month", "report points",
 * "GHI") means nothing without the model behind it.
 */
export default function StatsPanel({ stats, siteName }: { stats: Stats; siteName: string }) {
  const operating = stats.operating_months_label;
  const shoulder = stats.shoulder_months_label;
  const freezing = stats.freezing_months_label;

  // Older/pre-baked payloads may not carry the window; fall back to the
  // single design month rather than rendering an empty tile.
  const windowValue = operating ?? stats.design_month;
  const yearRound = operating === "year-round";

  const sunHours =
    stats.design_peak_sun_hours ?? Math.round((stats.design_ghi_wh_m2_day / 1000) * 10) / 10;

  return (
    <div className="card">
      <h3 className="section-title">{siteName}</h3>

      <div className="stats-grid">
        <div className="stat-tile">
          <div className="stat-value">{stats.ap_count}</div>
          <div className="stat-label">Access points needed</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{stats.coverage_pct.toFixed(1)}%</div>
          <div className="stat-label">Of site within range</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{stats.area_acres.toFixed(0)}</div>
          <div className="stat-label">Acres surveyed</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{windowValue}</div>
          <div className="stat-label">Runs 24/7</div>
        </div>
      </div>

      <dl className="readout">
        <div className="readout-row">
          <dt>Coverage</dt>
          <dd>
            {stats.total_covered.toLocaleString()} of{" "}
            {stats.report_point_count.toLocaleString()} sample points across the grounds can
            reach at least one access point.
          </dd>
        </div>

        <div className="readout-row">
          <dt>Siting</dt>
          <dd>
            {stats.viable_candidate_count?.toLocaleString() ?? "—"} of{" "}
            {stats.candidate_count?.toLocaleString() ?? "—"} possible mounting spots get enough
            sunlight to power a node; the rest are too shaded by trees or buildings.
          </dd>
        </div>

        <div className="readout-row">
          <dt>Power</dt>
          <dd>
            {yearRound ? (
              <>
                Sunlight is sufficient all year. The worst month still delivers {sunHours} hours
                of full-sun equivalent, enough for a 100 W panel to run a 10 W node around the
                clock.
              </>
            ) : (
              <>
                Each node runs 24/7 from <strong>{operating ?? stats.design_month}</strong>, sized
                against the weakest of those months ({sunHours} hours of full-sun equivalent per
                day).
                {shoulder && shoulder !== "none" && (
                  <>
                    {" "}
                    In <strong>{shoulder}</strong> there is too little sun for round-the-clock
                    operation — those months run daytime and early evening only.
                  </>
                )}
                {freezing && freezing !== "none" && (
                  <>
                    {" "}
                    <strong>{freezing}</strong> averages below freezing, where the battery hits
                    its thermal cutoff.
                  </>
                )}
              </>
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}
