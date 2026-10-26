"use client";

import type { CoverageMode } from "../types";

interface ParamsPanelProps {
  range2g: number;
  range5g: number;
  range6g: number | null;
  coverage: CoverageMode;
  onChange: (next: {
    range2g?: number;
    range5g?: number;
    range6g?: number | null;
    coverage?: CoverageMode;
  }) => void;
  disabled?: boolean;
}

export default function ParamsPanel({
  range2g,
  range5g,
  range6g,
  coverage,
  onChange,
  disabled,
}: ParamsPanelProps) {
  return (
    <div className="card">
      <h3 className="section-title">Access point parameters</h3>

      <div className="field-group">
        <label className="field-label" htmlFor="range2g">
          <span>2.4 GHz range</span>
          <strong>{range2g.toLocaleString()} ft</strong>
        </label>
        <input
          id="range2g"
          type="range"
          min={200}
          max={3000}
          step={50}
          value={range2g}
          disabled={disabled}
          onChange={(e) => onChange({ range2g: Number(e.target.value) })}
        />
      </div>

      <div className="field-group">
        <label className="field-label" htmlFor="range5g">
          <span>5 GHz range</span>
          <strong>{range5g.toLocaleString()} ft</strong>
        </label>
        <input
          id="range5g"
          type="range"
          min={100}
          max={2000}
          step={25}
          value={range5g}
          disabled={disabled}
          onChange={(e) => onChange({ range5g: Number(e.target.value) })}
        />
      </div>

      <div className="field-group">
        <label className="field-label" htmlFor="range6g">
          <span>6 GHz range (optional, tri-band)</span>
          <strong>{range6g ? `${range6g.toLocaleString()} ft` : "off"}</strong>
        </label>
        <input
          id="range6g"
          type="range"
          min={0}
          max={500}
          step={10}
          value={range6g ?? 0}
          disabled={disabled}
          onChange={(e) => {
            const v = Number(e.target.value);
            onChange({ range6g: v === 0 ? null : v });
          }}
        />
      </div>

      <div className="field-group">
        <label className="field-label">
          <span>Coverage mode</span>
        </label>
        <div className="toggle-row">
          <button
            type="button"
            className={`toggle-btn${coverage === "full" ? " active" : ""}`}
            disabled={disabled}
            onClick={() => onChange({ coverage: "full" })}
          >
            Full grounds
          </button>
          <button
            type="button"
            className={`toggle-btn${coverage === "paths" ? " active" : ""}`}
            disabled={disabled}
            onClick={() => onChange({ coverage: "paths" })}
          >
            Paths only
          </button>
        </div>
      </div>
    </div>
  );
}
