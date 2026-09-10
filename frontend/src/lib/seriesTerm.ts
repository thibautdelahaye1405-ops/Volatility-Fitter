// Term-structure helpers of the Series lens's TERM stage (SERIES ARC S5,
// roadmap §3.4): a lane's per-expiry ATM / var-swap vols at a frame, and
// the PRODUCTION lane's points + dense curve in the live Term chart's own
// shape (state/useTerm TermPoint / TermCurve). A series carries no event
// calendar, so τ = t everywhere and the curve accrues total variance
// linearly in calendar time between the expiries — the live endpoint's rule
// (backend analytics.py: CURVE_POINTS samples from CURVE_T_MIN to
// CURVE_T_PAD × the last expiry; calib/weighted_time.interp_total_variance).
// Pure — no React; unit-tested in seriesTerm.test.ts.
import { laneSlice, sliceMetric } from "./seriesLanes";
import type { FramePayload } from "./seriesTypes";
import type { TermCurve, TermPoint } from "../state/useTerm";

/** One expiry of a lane's term structure at a frame (null = not fitted). */
export interface LaneTermPoint {
  expiry: string;
  t: number;
  atmVol: number | null;
  varSwapVol: number | null;
}

/** The live Term endpoint's dense-curve constants (backend analytics.py). */
export const CURVE_POINTS = 80;
export const CURVE_T_MIN = 0.02;
export const CURVE_T_PAD = 1.05;

const finiteOrNull = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** The lane's term points at a frame, ascending in t: its `term` rows, else
 *  (an older payload) its slices' ATM vols; a non-finite vol reads null and
 *  a row without a finite positive t is dropped; [] for an unknown lane. */
export function laneTermSeries(frame: FramePayload, laneId: string): LaneTermPoint[] {
  const lane = frame.lanes[laneId];
  if (!lane) return [];
  const rows: LaneTermPoint[] = lane.term.length > 0
    ? lane.term.map((p) => ({
        expiry: p.expiry, t: p.t, atmVol: finiteOrNull(p.atmVol), varSwapVol: finiteOrNull(p.varSwapVol),
      }))
    : lane.slices.map((s) => ({ expiry: s.expiry, t: s.t, atmVol: finiteOrNull(s.atmVol), varSwapVol: null }));
  return rows.filter((p) => Number.isFinite(p.t) && p.t > 0).sort((a, b) => a.t - b.t);
}

/** Total variance at t, linear in t between ASCENDING nodes; below the
 *  first node the variance RATE from the origin, above the last the last
 *  segment's rate (one node: its own rate) — interp_total_variance, τ = t. */
export function interpTotalVariance(t: number, tNodes: readonly number[], wNodes: readonly number[]): number {
  const n = Math.min(tNodes.length, wNodes.length);
  if (n === 0) return 0;
  if (t < tNodes[0]) return tNodes[0] > 0 ? (wNodes[0] * t) / tNodes[0] : wNodes[0];
  if (t > tNodes[n - 1]) {
    const dt = n > 1 ? tNodes[n - 1] - tNodes[n - 2] : tNodes[n - 1];
    const dw = n > 1 ? wNodes[n - 1] - wNodes[n - 2] : wNodes[n - 1];
    return wNodes[n - 1] + (dt > 0 ? dw / dt : 0) * (t - tNodes[n - 1]);
  }
  for (let i = 1; i < n; i++) {
    if (t <= tNodes[i]) {
      const dt = tNodes[i] - tNodes[i - 1];
      const f = dt > 0 ? (t - tNodes[i - 1]) / dt : 1;
      return wNodes[i - 1] + f * (wNodes[i] - wNodes[i - 1]);
    }
  }
  return wNodes[n - 1];
}

/** The production lane's term structure in the live chart's shape: one
 *  TermPoint per fitted expiry (τ = t, w0 = σ²t, the lane's var-swap vol —
 *  the ATM vol when it carries none, so the chart's diamond sits under the
 *  ATM marker — and the slice's worst error) plus the dense curve. The
 *  curve starts at CURVE_T_MIN, or half the first expiry when that is
 *  shorter (a 0DTE ladder), and ends at CURVE_T_PAD × the last expiry.
 *  Null when the lane has no fitted expiry. */
export function productionTermChart(
  frame: FramePayload,
  laneId: string,
): { points: TermPoint[]; curve: TermCurve } | null {
  const points: TermPoint[] = [];
  for (const p of laneTermSeries(frame, laneId)) {
    if (p.atmVol === null) continue;
    points.push({
      expiry: p.expiry, t: p.t, tau: p.t, atmVol: p.atmVol, w0: p.atmVol * p.atmVol * p.t,
      varSwapVol: p.varSwapVol ?? p.atmVol,
      maxIvErrorBp: sliceMetric(laneSlice(frame, laneId, p.expiry), "maxIvBp") ?? 0,
    });
  }
  if (points.length === 0) return null;
  const tNodes = points.map((p) => p.t);
  const wNodes = points.map((p) => p.w0);
  const t0 = Math.min(CURVE_T_MIN, tNodes[0] * 0.5);
  const t1 = CURVE_T_PAD * tNodes[tNodes.length - 1];
  const t: number[] = [];
  const w: number[] = [];
  const vol: number[] = [];
  for (let i = 0; i < CURVE_POINTS; i++) {
    const ti = t0 + ((t1 - t0) * i) / (CURVE_POINTS - 1);
    const wi = interpTotalVariance(ti, tNodes, wNodes);
    t.push(ti);
    w.push(wi);
    vol.push(Math.sqrt(Math.max(wi, 0) / ti));
  }
  return { points, curve: { t, tau: [...t], w, vol } };
}
