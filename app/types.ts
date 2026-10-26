export type SolarStatus = "viable" | "marginal";

export interface AccessPoint {
  name: string;
  lat: number;
  lon: number;
  bands: string[];
  solar_status: SolarStatus;
  harvest_wh: number;
  shade_pct: number;
  coverage_efficiency_pct: number;
  overlap_pct: number;
  panel_facing: string;
  panel_azimuth_deg: number;
  panel_tilt_deg: number;
  panel_sky_score: number;
}

export interface ParamsUsed {
  lat: number;
  lon: number;
  range_2g_ft: number;
  range_5g_ft: number;
  range_6g_ft: number | null;
  coverage: CoverageMode;
}

export interface Stats {
  design_month: string;
  design_ghi_wh_m2_day: number;
  shoulder_months: string[];
  area_acres: number;
  candidate_count: number;
  viable_candidate_count: number;
  report_point_count: number;
  total_covered: number;
  coverage_pct: number;
  ap_count: number;
}

export interface ComputeResult {
  ok: true;
  site_name: string;
  boundary_coords: [number, number][];
  aps: AccessPoint[];
  params_used: ParamsUsed;
  stats: Stats;
}

export interface ComputeErrorAreaTooLarge {
  ok: false;
  error: "area_too_large";
  message: string;
  area_m2: number;
  max_area_m2: number;
  area_acres: number;
  max_area_acres: number;
}

export interface ComputeErrorGeneric {
  ok: false;
  error: "NoBoundaryError" | "NoViableCandidatesError" | "NoSolutionError" | "internal_error";
  message: string;
}

export type ComputeError = ComputeErrorAreaTooLarge | ComputeErrorGeneric;
export type ComputeResponse = ComputeResult | ComputeError;

export type CoverageMode = "full" | "paths";

export interface GeocodeResult {
  display_name: string;
  lat: number;
  lon: number;
  boundingbox: [number, number, number, number];
}

export interface GeocodeResponse {
  ok: boolean;
  results: GeocodeResult[];
}

export interface BoundaryResponse {
  ok: boolean;
  boundary: [number, number][] | null;
}

export interface ComputeParams {
  lat: number;
  lon: number;
  site_name: string;
  range_2g_ft: number;
  range_5g_ft: number;
  range_6g_ft: number | null;
  coverage: CoverageMode;
  boundary: [number, number][] | null;
  cache_key: string | null;
}
