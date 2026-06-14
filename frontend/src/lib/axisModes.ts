// Strike-axis display modes for the smile chart.
//
// The chart's internal geometry (brush window, quote hit-testing, zoom)
// always lives in log-moneyness k = ln(K/F); every mode below is a monotone
// map of k used ONLY to generate tick positions and tick / crosshair labels.
// Ticks are picked "nice" in display units and inverted back to k for
// positioning — analytically where possible, numerically by bisection for
// delta (which has no closed-form inverse but is monotone decreasing in k).
import { formatAxisNumber, niceTicks } from "./chartScale";

/** Supported strike-axis display modes. */
export type AxisMode =
  | "logmoneyness" // k = ln(K/F)
  | "strike" // K = F * exp(k)
  | "pctatm" // 100 * exp(k): strike as a percentage of the forward
  | "delta" // Black forward call delta N(d1) at the model vol
  | "normalized" // (K - F) / (sigma_ATM * F * sqrt(T)) = (e^k - 1)/(sigma sqrt(T))
  | "lognormalized"; // k / (sigma_ATM * sqrt(T))

/** Options for the axis-mode <select> in the chart-card header. */
export const AXIS_MODE_OPTIONS: { id: AxisMode; label: string }[] = [
  { id: "logmoneyness", label: "k = ln(K/F)" },
  { id: "strike", label: "Strike K" },
  { id: "pctatm", label: "% ATM" },
  { id: "delta", label: "Delta" },
  { id: "normalized", label: "(K−F)/σF√T" },
  { id: "lognormalized", label: "k/σ√T" },
];

/** Per-smile context the transforms need (forward, maturity, model curve). */
export interface AxisContext {
  forward: number;
  /** Year-fraction to expiry. */
  t: number;
  /** ATM implied vol (decimal), used by the normalized modes. */
  atmVol: number;
  /** Model implied vol at k (linear interp), used by delta mode. */
  volAt: (k: number) => number | null;
  /** k extent of the model curve: bisection bracket for delta inversion. */
  kRange: readonly [number, number];
}

/** Standard normal CDF (Abramowitz & Stegun 26.2.17, |err| < 7.5e-8). */
function normCdf(x: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);
  const poly =
    t *
    (0.31938153 +
      t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  const p = d * poly;
  return x >= 0 ? 1 - p : p;
}

/** sigma_ATM * sqrt(T), or 0 when the context is degenerate (mock edge). */
function sigmaRootT(ctx: AxisContext): number {
  const s = ctx.atmVol * Math.sqrt(Math.max(0, ctx.t));
  return Number.isFinite(s) && s > 0 ? s : 0;
}

/** Black forward call delta N(d1) at k, with w = sigma_model(k)^2 * T. */
function callDelta(k: number, ctx: AxisContext): number {
  const vol = ctx.volAt(k) ?? ctx.atmVol;
  const w = Math.max(1e-12, vol * vol * Math.max(1e-12, ctx.t));
  return normCdf((-k + w / 2) / Math.sqrt(w));
}

/** Map log-moneyness k to the display value of the given mode. */
export function axisTransform(mode: AxisMode, k: number, ctx: AxisContext): number {
  switch (mode) {
    case "strike":
      return ctx.forward * Math.exp(k);
    case "pctatm":
      return 100 * Math.exp(k);
    case "delta":
      return callDelta(k, ctx);
    case "normalized": {
      const s = sigmaRootT(ctx);
      return s > 0 ? (Math.exp(k) - 1) / s : k;
    }
    case "lognormalized": {
      const s = sigmaRootT(ctx);
      return s > 0 ? k / s : k;
    }
    default:
      return k;
  }
}

/** Numeric inverse of delta: bisection over the model-curve k range
 *  (call delta is monotone decreasing in k). Null when out of range. */
function invertDelta(target: number, ctx: AxisContext): number | null {
  let [lo, hi] = ctx.kRange;
  if (!(hi > lo)) return null;
  if (target > callDelta(lo, ctx) || target < callDelta(hi, ctx)) return null;
  for (let i = 0; i < 48; i++) {
    const mid = 0.5 * (lo + hi);
    if (callDelta(mid, ctx) >= target) lo = mid;
    else hi = mid;
  }
  return 0.5 * (lo + hi);
}

/** Map a display value back to k. Null when the value has no preimage. */
export function axisInvert(mode: AxisMode, v: number, ctx: AxisContext): number | null {
  switch (mode) {
    case "strike":
      return v > 0 && ctx.forward > 0 ? Math.log(v / ctx.forward) : null;
    case "pctatm":
      return v > 0 ? Math.log(v / 100) : null;
    case "delta":
      return invertDelta(v, ctx);
    case "normalized": {
      const s = sigmaRootT(ctx);
      if (s <= 0) return v; // degenerate context: transform fell back to k
      const m = 1 + v * s;
      return m > 0 ? Math.log(m) : null;
    }
    case "lognormalized": {
      const s = sigmaRootT(ctx);
      return s > 0 ? v * s : v;
    }
    default:
      return v;
  }
}

/** Compact tick label in display units. */
function tickLabel(mode: AxisMode, v: number): string {
  switch (mode) {
    case "pctatm":
      return `${formatAxisNumber(v)}%`;
    case "delta":
      return `${Math.round(v * 100)}Δ`;
    default:
      return formatAxisNumber(v);
  }
}

/** One axis tick: position in k-space + label in display units. */
export interface AxisTick {
  k: number;
  label: string;
}

/**
 * Generate ~`target` nice ticks for the visible window [kLo, kHi]:
 * pick round values in display units, then invert them back to k so the
 * chart can place them on its k-linear scale.
 */
export function axisTicks(
  mode: AxisMode,
  kLo: number,
  kHi: number,
  ctx: AxisContext,
  target = 6,
): AxisTick[] {
  const a = axisTransform(mode, kLo, ctx);
  const b = axisTransform(mode, kHi, ctx);
  const lo = Math.min(a, b);
  const hi = Math.max(a, b);
  // Delta ticks are picked nice in *percent* so labels land on 10Δ/25Δ-style values.
  const values =
    mode === "delta"
      ? niceTicks(lo * 100, hi * 100, target).map((v) => v / 100)
      : niceTicks(lo, hi, target);
  const eps = (kHi - kLo) * 1e-6;
  const ticks: AxisTick[] = [];
  for (const v of values) {
    const k = mode === "logmoneyness" ? v : axisInvert(mode, v, ctx);
    if (k === null || !Number.isFinite(k) || k < kLo - eps || k > kHi + eps) continue;
    ticks.push({ k, label: tickLabel(mode, v) });
  }
  return ticks;
}

/** One display-space tick: value in display units + its label. */
export interface DisplayTick {
  value: number;
  label: string;
}

/**
 * Nice ticks directly in display units, for charts that plot geometry in the
 * display coordinate (so the smile shape itself changes with the mode). Pass the
 * visible display-domain extent; delta ticks land on 10Δ/25Δ-style values.
 */
export function axisDisplayTicks(
  mode: AxisMode,
  lo: number,
  hi: number,
  target = 6,
): DisplayTick[] {
  const a = Math.min(lo, hi);
  const b = Math.max(lo, hi);
  const values =
    mode === "delta"
      ? niceTicks(a * 100, b * 100, target).map((v) => v / 100)
      : niceTicks(a, b, target);
  return values.map((v) => ({ value: v, label: tickLabel(mode, v) }));
}

/** Crosshair readout for a display value, e.g. "K 6150.00" or "25Δ". */
export function formatHoverValue(mode: AxisMode, v: number): string {
  switch (mode) {
    case "strike":
      return `K ${v.toFixed(2)}`;
    case "pctatm":
      return `${v.toFixed(1)}% ATM`;
    case "delta":
      return `${(v * 100).toFixed(0)}Δ`;
    case "normalized":
    case "lognormalized":
      return `z ${v.toFixed(2)}`;
    default:
      return `k ${v.toFixed(3)}`;
  }
}
