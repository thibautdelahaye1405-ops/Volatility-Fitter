// Locks the Term stage's helpers (SERIES ARC S5): a lane's term points
// (sorted, nulls, the slices fallback), the live endpoint's variance
// interpolation rule, and the production lane's chart shape.
import { describe, expect, it } from "vitest";
import {
  CURVE_POINTS,
  CURVE_T_MIN,
  CURVE_T_PAD,
  interpTotalVariance,
  laneTermSeries,
  productionTermChart,
} from "./seriesTerm";
import type { FramePayload, LaneFrameDoc, SliceCurveDoc, TermPointDoc } from "./seriesTypes";

const slice = (expiry: string, t: number, atmVol: number | null, metrics: Record<string, unknown> = {}): SliceCurveDoc =>
  ({ expiry, t, forward: 100, k: [0], iv: [atmVol ?? NaN], atmVol, skew: null, curvature: null, metrics });
const laneDoc = (laneId: string, term: TermPointDoc[], slices: SliceCurveDoc[] = []): LaneFrameDoc =>
  ({ laneId, slices, surface: null, term, metrics: {}, status: "done" });

const frame: FramePayload = {
  seriesId: "s", idx: 0, ts: "2026-09-08T15:45:00", quoteKind: "quotes", spot: 100,
  expiries: ["2026-09-18", "2026-10-16", "2026-12-18"], forwards: {}, market: {},
  lanes: {
    p: laneDoc("p", [
      { expiry: "2026-12-18", t: 0.28, atmVol: 0.2, varSwapVol: 0.21 },
      { expiry: "2026-09-18", t: 0.03, atmVol: 0.3, varSwapVol: null },
      { expiry: "2026-10-16", t: 0.1, atmVol: NaN, varSwapVol: 0.22 },
      { expiry: "bad", t: NaN, atmVol: 0.2, varSwapVol: 0.2 },
    ], [slice("2026-09-18", 0.03, 0.3, { maxIvBp: 12 })]),
    q: laneDoc("q", [], [slice("2026-10-16", 0.1, 0.22), slice("2026-09-18", 0.03, null)]),
    empty: laneDoc("empty", []),
  },
};

describe("laneTermSeries", () => {
  it("ascending in t, non-finite vols read null, a row without a finite t is dropped", () => {
    expect(laneTermSeries(frame, "p")).toEqual([
      { expiry: "2026-09-18", t: 0.03, atmVol: 0.3, varSwapVol: null },
      { expiry: "2026-10-16", t: 0.1, atmVol: null, varSwapVol: 0.22 },
      { expiry: "2026-12-18", t: 0.28, atmVol: 0.2, varSwapVol: 0.21 },
    ]);
  });
  it("falls back to the slices' ATM vols (no var-swap) when the lane carries no term rows", () => {
    expect(laneTermSeries(frame, "q")).toEqual([
      { expiry: "2026-09-18", t: 0.03, atmVol: null, varSwapVol: null },
      { expiry: "2026-10-16", t: 0.1, atmVol: 0.22, varSwapVol: null },
    ]);
    expect(laneTermSeries(frame, "empty")).toEqual([]);
    expect(laneTermSeries(frame, "zzz")).toEqual([]);
  });
});

describe("interpTotalVariance", () => {
  const tN = [0.1, 0.2];
  const wN = [0.004, 0.012];
  it("linear in t between nodes; the rate from the origin below; the last segment's rate above", () => {
    expect(interpTotalVariance(0.15, tN, wN)).toBeCloseTo(0.008, 12);
    expect(interpTotalVariance(0.1, tN, wN)).toBeCloseTo(0.004, 12);
    expect(interpTotalVariance(0.2, tN, wN)).toBeCloseTo(0.012, 12);
    expect(interpTotalVariance(0.05, tN, wN)).toBeCloseTo(0.002, 12);
    expect(interpTotalVariance(0.3, tN, wN)).toBeCloseTo(0.02, 12);
  });
  it("one node: its own rate on both sides; no node: zero", () => {
    expect(interpTotalVariance(0.2, [0.1], [0.004])).toBeCloseTo(0.008, 12);
    expect(interpTotalVariance(0.05, [0.1], [0.004])).toBeCloseTo(0.002, 12);
    expect(interpTotalVariance(0.1, [0.1], [0.004])).toBeCloseTo(0.004, 12);
    expect(interpTotalVariance(0.1, [], [])).toBe(0);
  });
});

describe("productionTermChart", () => {
  it("points in the live shape (τ = t, w0 = σ²t, var-swap falls back to ATM, worst error from the slice)", () => {
    const chart = productionTermChart(frame, "p")!;
    expect(chart.points.map((p) => p.expiry)).toEqual(["2026-09-18", "2026-12-18"]); // the NaN-ATM rung is not a point
    const [a, b] = chart.points;
    expect(a.tau).toBe(a.t);
    expect(a.w0).toBeCloseTo(0.09 * 0.03, 12);
    expect(a.varSwapVol).toBe(0.3);
    expect(a.maxIvErrorBp).toBe(12);
    expect(b.varSwapVol).toBe(0.21);
    expect(b.maxIvErrorBp).toBe(0);
  });
  it("the dense curve: the endpoint's grid, τ = t, vol = √(w/t), through the nodes", () => {
    const { curve, points } = productionTermChart(frame, "p")!;
    expect(curve.t.length).toBe(CURVE_POINTS);
    expect(curve.t[0]).toBeCloseTo(Math.min(CURVE_T_MIN, 0.03 / 2), 12);
    expect(curve.t[CURVE_POINTS - 1]).toBeCloseTo(CURVE_T_PAD * 0.28, 12);
    expect(curve.tau).toEqual(curve.t);
    curve.t.forEach((t, i) => expect(curve.vol[i]).toBeCloseTo(Math.sqrt(curve.w[i] / t), 12));
    for (let i = 1; i < curve.t.length; i++) expect(curve.t[i]).toBeGreaterThan(curve.t[i - 1]);
    const tN = points.map((p) => p.t);
    const wN = points.map((p) => p.w0);
    expect(interpTotalVariance(0.03, tN, wN)).toBeCloseTo(wN[0], 12);
    expect(interpTotalVariance(0.28, tN, wN)).toBeCloseTo(wN[1], 12);
  });
  it("null when the lane has no fitted expiry", () => {
    expect(productionTermChart(frame, "empty")).toBeNull();
    expect(productionTermChart(frame, "zzz")).toBeNull();
  });
});
