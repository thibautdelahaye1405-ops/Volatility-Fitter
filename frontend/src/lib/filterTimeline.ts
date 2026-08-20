// Pure geometry/series helpers for the FilterTimeline charts (V3.9 item 7).
// No React, no DOM — everything here is vitest-covered and consumed by
// components/FilterTimeline.tsx. Per-handle arrays follow the backend's
// FILTER_HANDLES order (ATM, skew, curvature).

/** One committed observation-filter step — the FilterStepOut wire shape of
 *  GET /smiles/{ticker}/{expiry}/filter/history (oldest first). */
export interface FilterStepWire {
  /** Snapshot epoch (seconds) the step committed at. */
  ts: number;
  /** Process-noise time the active clock charged (0 on a seed/reset). */
  dtDays: number;
  prediction: number[];
  predictionStd: number[];
  observation: number[];
  observationStd: number[];
  innovation: number[];
  /** Pre-inflation standardized innovation ν/√(P⁻+R); null when unavailable. */
  zeta: number[] | null;
  gain: number[];
  posterior: number[];
  posteriorStd: number[];
  /** Per-component Q variance vectors (clock/spot/… + "adaptive" when tripped). */
  processBreakdown: Record<string, number[]>;
  transportDistance: number | null;
  provenance: string;
  resetReason: string | null;
  contaminated: boolean;
}

/** Safe per-handle read: NaN when the array is short/absent (SVG paths skip it). */
const at = (a: number[] | null | undefined, i: number): number =>
  a != null && Number.isFinite(a[i]) ? a[i] : NaN;

/** Per-step series of one handle for the three-band chart. */
export interface HandleSeries {
  pred: number[];
  predLo: number[];
  predHi: number[];
  obs: number[];
  obsLo: number[];
  obsHi: number[];
  post: number[];
}

/** Extract the band-chart series for handle index `h`:
 *  prediction m⁻ ± σ, observation z ± σR, posterior m⁺. */
export function handleSeries(steps: FilterStepWire[], h: number): HandleSeries {
  const pred = steps.map((s) => at(s.prediction, h));
  const ps = steps.map((s) => at(s.predictionStd, h));
  const obs = steps.map((s) => at(s.observation, h));
  const os = steps.map((s) => at(s.observationStd, h));
  return {
    pred,
    predLo: pred.map((v, i) => v - ps[i]),
    predHi: pred.map((v, i) => v + ps[i]),
    obs,
    obsLo: obs.map((v, i) => v - os[i]),
    obsHi: obs.map((v, i) => v + os[i]),
    post: steps.map((s) => at(s.posterior, h)),
  };
}

/** ζ of one handle per step (NaN where a step carries no ζ, e.g. legacy rows). */
export function zetaSeries(steps: FilterStepWire[], h: number): number[] {
  return steps.map((s) => (s.zeta != null ? at(s.zeta, h) : NaN));
}

/** Kalman gain diagonal of one handle per step. */
export function gainSeries(steps: FilterStepWire[], h: number): number[] {
  return steps.map((s) => at(s.gain, h));
}

/** Fixed Q-component stack order — clock first (the baseline), the adaptive
 *  surprise component last (top of the stack, where spikes read). Colors are
 *  assigned to these KEYS in this order, never cycled. */
export const Q_KEYS = ["clock", "spot", "event", "source", "model", "adaptive"] as const;
export type QKey = (typeof Q_KEYS)[number];

/** One cumulative stacked layer: draw the band between lo and hi. */
export interface StackLayer {
  key: QKey;
  lo: number[];
  hi: number[];
}

/** Cumulative stacked Q-breakdown VARIANCE layers for handle `h` (Q_KEYS
 *  order). Missing components contribute zero; negatives are clamped to 0
 *  (variances by construction). */
export function qStack(steps: FilterStepWire[], h: number): StackLayer[] {
  const layers: StackLayer[] = [];
  let base = steps.map(() => 0);
  for (const key of Q_KEYS) {
    const vals = steps.map((s) => {
      const v = s.processBreakdown?.[key];
      return v != null && Number.isFinite(v[h]) ? Math.max(v[h], 0) : 0;
    });
    const hi = vals.map((v, i) => base[i] + v);
    layers.push({ key, lo: base, hi });
    base = hi;
  }
  return layers;
}

export type MarkerKind = "seed" | "reset" | "contaminated";

/** One vertical evidence tick on the timeline (hover title carries the why). */
export interface StepMarker {
  index: number;
  kind: MarkerKind;
  label: string;
}

/** Reset / seed / contamination markers. The very first seed ("first") is a
 *  seed; any later reseed is a reset; contamination is flagged independently
 *  (a step can carry both a reset and a contaminated measurement). */
export function stepMarkers(steps: FilterStepWire[]): StepMarker[] {
  const out: StepMarker[] = [];
  steps.forEach((s, i) => {
    if (s.resetReason !== null) {
      out.push({
        index: i,
        kind: s.resetReason === "first" ? "seed" : "reset",
        label: `${s.provenance} (${s.resetReason})`,
      });
    }
    if (s.contaminated) {
      out.push({
        index: i,
        kind: "contaminated",
        label: "measurement contaminated (persistence-anchored fit)",
      });
    }
  });
  return out;
}

/** Finite min/max of `values` padded by `padFrac`; [0, 1] when nothing is
 *  finite; a degenerate (flat) domain is opened symmetrically so the line
 *  never sits on the chart edge. */
export function yDomain(values: number[], padFrac = 0.08): [number, number] {
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of values) {
    if (!Number.isFinite(v)) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  if (!(lo <= hi)) return [0, 1];
  if (lo === hi) {
    const half = Math.max(Math.abs(lo) * 0.05, 1e-6);
    return [lo - half, hi + half];
  }
  const pad = (hi - lo) * padFrac;
  return [lo - pad, hi + pad];
}

/** SVG polyline path through (xs, ys), restarting on non-finite points. */
export function linePath(xs: number[], ys: number[]): string {
  let d = "";
  let started = false;
  for (let i = 0; i < xs.length; i++) {
    if (!Number.isFinite(xs[i]) || !Number.isFinite(ys[i])) {
      started = false;
      continue;
    }
    d += `${started ? "L" : "M"}${xs[i].toFixed(1)},${ys[i].toFixed(1)}`;
    started = true;
  }
  return d;
}

/** Closed band polygon between lo and hi (forward along hi, back along lo).
 *  Indices where either edge is non-finite are dropped; "" below 2 points. */
export function bandPath(xs: number[], lo: number[], hi: number[]): string {
  const keep: number[] = [];
  for (let i = 0; i < xs.length; i++) {
    if (Number.isFinite(xs[i]) && Number.isFinite(lo[i]) && Number.isFinite(hi[i])) {
      keep.push(i);
    }
  }
  if (keep.length < 2) return "";
  const fwd = keep.map((i, j) => `${j === 0 ? "M" : "L"}${xs[i].toFixed(1)},${hi[i].toFixed(1)}`);
  const back = [...keep].reverse().map((i) => `L${xs[i].toFixed(1)},${lo[i].toFixed(1)}`);
  return `${fwd.join("")}${back.join("")}Z`;
}

/** True when the ring spans more than one (local) calendar day. */
export function spansDays(steps: FilterStepWire[]): boolean {
  if (steps.length < 2) return false;
  const d0 = new Date(steps[0].ts * 1000);
  const d1 = new Date(steps[steps.length - 1].ts * 1000);
  return d0.toDateString() !== d1.toDateString();
}

/** Tick label for one step: HH:MM at intraday cadence, MM-DD across days. */
export function stepLabel(tsSec: number, multiDay: boolean): string {
  const d = new Date(tsSec * 1000);
  const p2 = (n: number) => String(n).padStart(2, "0");
  return multiDay
    ? `${p2(d.getMonth() + 1)}-${p2(d.getDate())}`
    : `${p2(d.getHours())}:${p2(d.getMinutes())}`;
}

/** Sparse x-tick indices: first + last + roughly every n/target-th step. */
export function tickIndices(n: number, target = 6): number[] {
  if (n <= 0) return [];
  if (n <= target) return Array.from({ length: n }, (_, i) => i);
  const stride = Math.ceil((n - 1) / (target - 1));
  const out: number[] = [];
  for (let i = 0; i < n - 1; i += stride) out.push(i);
  out.push(n - 1);
  return out;
}
