// The Series wire contract (SERIES ARC S4) — mirrors backend
// volfit/api/schemas_series.py (SeriesSpec / SeriesDoc / FrameDoc / LaneFitDoc /
// SeriesEstimate / FramePayload / StripPayload) and series_jobs.SeriesJobStatus.
// Field names are the backend's camelCase; keep the two in step by hand.
import type { QuoteBand } from "./mockData";

export type SeriesMode = "historical" | "live" | "import";
export type SeriesStep = "1m" | "5m" | "15m" | "30m" | "1h" | "session_close" | "daily" | "weekly";
export type LadderPolicy = "pinned" | "term" | "0dte";
export type LaneFamily = "lqd" | "svi" | "sigmoid" | "lv";
export type LaneSeed = "cold" | "warmup" | "live_prior";
export type SeriesStatus =
  | "draft" | "queued" | "harvesting" | "calibrating" | "paused" | "done" | "failed" | "cancelled";
export type FrameStatus = "pending" | "harvesting" | "ready" | "failed" | "skipped";
export type FitStatus = "pending" | "done" | "failed" | "skipped";
export type FitMode = "mid" | "bidask" | "haircut";

export const SERIES_STEPS: readonly SeriesStep[] = [
  "1m", "5m", "15m", "30m", "1h", "session_close", "daily", "weekly",
];
export const STEP_LABELS: Record<SeriesStep, string> = {
  "1m": "1 min", "5m": "5 min", "15m": "15 min", "30m": "30 min", "1h": "1 hour",
  session_close: "Session close", daily: "Daily", weekly: "Weekly",
};
export const LANE_PRESET_IDS = [
  "lqd_free", "lqd_prior", "lqd_prior_filter", "svi_free", "mcs_free", "lv_free", "lv_prior",
  "current",
] as const;
export type LanePresetId = (typeof LANE_PRESET_IDS)[number];

export interface SeriesClock {
  start?: string | null;
  end?: string | null;
  step: SeriesStep;
  count?: number | null;
  sessionOnly: boolean;
  timeOfDay: string;
  tz: string;
  warmupFrames: number;
}

export interface SeriesLadder {
  policy: LadderPolicy;
  expiries: string[];
  maxExpiries?: number | null;
}

export interface LaneSpec {
  id: string;
  name: string;
  family: LaneFamily;
  colour?: string | null;
  fitMode?: FitMode | null;
  patchFit: Record<string, unknown>;
  patchOptions: Record<string, unknown>;
  production: boolean;
  seed: LaneSeed;
}

export interface SeriesSpec {
  name: string;
  ticker: string;
  tickers?: string[];
  source?: string | null;
  mode: SeriesMode;
  clock: SeriesClock;
  ladder: SeriesLadder;
  fitMode: FitMode;
  lanes: LaneSpec[];
  note: string;
}

export interface SeriesProgress {
  status: SeriesStatus;
  framesTotal: number;
  framesReady: number;
  fitsTotal: number;
  fitsDone: number;
  current: string | null;
  error: string | null;
  startedTs: string | null;
  updatedTs: string | null;
}

export interface FrameDoc {
  idx: number;
  ts: string;
  snapshotId: number | null;
  spot: number | null;
  quoteKind: string | null;
  nQuotes: number;
  expiries: string[];
  warmup: boolean;
  status: FrameStatus;
  error: string | null;
  harvestedTs: string | null;
}

export interface SeriesDoc {
  id: string;
  createdTs: string;
  updatedTs: string;
  spec: SeriesSpec;
  baseFit: Record<string, unknown>;
  baseOptions: Record<string, unknown>;
  progress: SeriesProgress;
  frames: FrameDoc[];
}

export interface SeriesSummary {
  id: string;
  name: string;
  ticker: string;
  source: string | null;
  mode: SeriesMode;
  status: SeriesStatus;
  createdTs: string;
  nFrames: number;
  nFramesReady: number;
  nLanes: number;
}

export interface SeriesEstimate {
  instants: string[];
  servable: boolean[];
  nFrames: number;
  harvestSeconds: number;
  calibrateSeconds: number;
  perLaneSeconds: Record<string, number>;
  warnings: string[];
}

export interface SeriesJobStatus {
  seriesId: string | null;
  running: string | null;
  queue: string[];
  progress: SeriesProgress | null;
}

export interface ImportSource {
  kind: "captures" | "store" | "fixtures";
  path?: string | null;
  start?: string | null;
  end?: string | null;
  maxFrames?: number | null;
}

export interface SeriesImportRequest {
  name: string;
  ticker: string;
  source: ImportSource;
  lanes?: LaneSpec[] | null;
  presets?: string[];
  fitMode?: FitMode | null;
  ladder?: SeriesLadder | null;
  note?: string;
}

/** One expiry's market at a frame: the prepared quote bands the Smile chart
 *  draws, in the frame forward's moneyness. */
export interface FrameMarket {
  expiry: string;
  t: number;
  tau: number;
  forward: number;
  discount: number;
  spot: number;
  quotes: QuoteBand[];
}

export interface SliceCurveDoc {
  expiry: string;
  t: number;
  forward: number;
  k: number[];
  iv: number[];
  atmVol: number | null;
  skew: number | null;
  curvature: number | null;
  metrics: Record<string, unknown>;
}

export interface SurfaceGridDoc {
  k: number[];
  tau: number[];
  expiries: string[];
  sigma: number[][];
}

export interface TermPointDoc {
  expiry: string;
  t: number;
  atmVol: number | null;
  varSwapVol: number | null;
}

export interface LaneFrameDoc {
  laneId: string;
  slices: SliceCurveDoc[];
  surface: SurfaceGridDoc | null;
  term: TermPointDoc[];
  metrics: Record<string, unknown>;
  status: FitStatus;
}

export interface FramePayload {
  seriesId: string;
  idx: number;
  ts: string;
  quoteKind: string | null;
  spot: number | null;
  expiries: string[];
  forwards: Record<string, number>;
  market: Record<string, FrameMarket>;
  lanes: Record<string, LaneFrameDoc>;
}

/** The filmstrip: per frame scalars, per lane per metric one value per
 *  frame (null where the lane has no fit at that frame). */
export interface StripPayload {
  seriesId: string;
  idx: number[];
  ts: string[];
  spot: (number | null)[];
  atmVol: Record<string, (number | null)[]>;
  lanes: Record<string, Record<string, (number | null)[]>>;
}

/** Metric names the strip carries per lane (backend series_payload.STRIP_METRICS). */
export const STRIP_METRICS = [
  "rmsBp", "maxIvBp", "pullAtmBp", "zetaAtm", "fitMs", "skew", "curvature",
] as const;
export type StripMetric = (typeof STRIP_METRICS)[number];

/** GET /series/{id}/evidence — the Lanes stage's summary per lane over the
 *  ready frames of the shown expiry (backend series_payload.evidence_payload). */
export interface LaneEvidence {
  nFrames: number;
  nFailed: number;
  meanRmsBp: number | null;
  meanMaxIvBp: number | null;
  worstFrame: { idx: number; ts: string; rmsBp: number } | null;
  /** Mean |Δ σ_atm| between consecutive frames, in vol bp (the damping a prior
   *  or a filter buys, at the rms cost above). */
  roughnessAtmBp: number | null;
  /** Mean |Δ skew| between consecutive frames. */
  roughnessSkew: number | null;
  meanPullAtmBp: number | null;
  meanAbsPullAtmBp: number | null;
  meanFitMs: number | null;
  zetaAtmStd: number | null;
}

export interface EvidencePayload {
  seriesId: string;
  expiry: string | null;
  lanes: Record<string, LaneEvidence>;
}

/** GET /series/{id}/lanes/{lane}/filter — the expiries the lane keeps a
 *  filter ring for; /filter/{expiry} — that ring's steps in the
 *  FilterStepWire shape (empty when the lane runs no filter). */
export interface LaneFilterIndex {
  laneId: string;
  expiries: string[];
}

export interface LaneFilterPayload {
  laneId: string;
  expiry: string;
  steps: Record<string, unknown>[];
  /** Per step (same order): the series FRAME index the step was committed
   *  on — the Lanes stage's cursor matches steps to frames by this, never by
   *  clock (a step's `ts` is a local-clock epoch of a naive stamp). */
  frameIdx: (number | null)[];
}
