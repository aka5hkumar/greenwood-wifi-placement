"use client";

import type { Stats } from "../types";

export default function StatsPanel({ stats, siteName }: { stats: Stats; siteName: string }) {
  return (
    <div className="card">
      <h3 className="section-title">{siteName}</h3>
      <div className="stats-grid">
        <div className="stat-tile">
          <div className="stat-value">{stats.ap_count}</div>
          <div className="stat-label">Access points</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{stats.coverage_pct.toFixed(1)}%</div>
          <div className="stat-label">Coverage</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{stats.area_acres.toFixed(1)}</div>
          <div className="stat-label">Acres</div>
        </div>
        <div className="stat-tile">
          <div className="stat-value">{stats.design_month}</div>
          <div className="stat-label">Design month</div>
        </div>
      </div>
      <div className="subtle" style={{ marginTop: "0.75rem" }}>
        {stats.total_covered.toLocaleString()} / {stats.report_point_count.toLocaleString()} report points covered
        &middot; {stats.viable_candidate_count}/{stats.candidate_count} candidates solar-viable
        &middot; design GHI {stats.design_ghi_wh_m2_day.toLocaleString()} Wh/m²/day
      </div>
      {stats.shoulder_months.length > 0 && (
        <div className="subtle" style={{ marginTop: "0.35rem" }}>
          Shoulder months (insufficient sun for 24/7 operation): {stats.shoulder_months.join(", ")}
        </div>
      )}
    </div>
  );
}
