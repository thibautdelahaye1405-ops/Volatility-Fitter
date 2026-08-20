// Locks for the FilterTimeline geometry helpers (V3.9 item 7).
import { describe, expect, it } from "vitest";

import {
  bandPath,
  gainSeries,
  handleSeries,
  linePath,
  Q_KEYS,
  qStack,
  spansDays,
  stepLabel,
  stepMarkers,
  tickIndices,
  yDomain,
  zetaSeries,
  type FilterStepWire,
} from "./filterTimeline";

const step = (over: Partial<FilterStepWire>): FilterStepWire => ({
  ts: 1_760_000_000,
  dtDays: 0.02,
  prediction: [0.2, -0.3, 0.1],
  predictionStd: [0.01, 0.02, 0.05],
  observation: [0.21, -0.29, 0.12],
  observationStd: [0.005, 0.01, 0.02],
  innovation: [0.01, 0.01, 0.02],
  zeta: [0.9, 0.4, 0.3],
  gain: [0.8, 0.6, 0.4],
  posterior: [0.208, -0.292, 0.115],
  posteriorStd: [0.004, 0.009, 0.018],
  processBreakdown: { clock: [1e-6, 2e-6, 3e-6], spot: [4e-6, 0, 0] },
  transportDistance: 0.001,
  provenance: "update",
  resetReason: null,
  contaminated: false,
  ...over,
});

describe("handleSeries", () => {
  it("extracts prediction/observation bands and the posterior per handle", () => {
    const s = handleSeries([step({})], 0);
    expect(s.pred).toEqual([0.2]);
    expect(s.predLo[0]).toBeCloseTo(0.19);
    expect(s.predHi[0]).toBeCloseTo(0.21);
    expect(s.obsLo[0]).toBeCloseTo(0.205);
    expect(s.obsHi[0]).toBeCloseTo(0.215);
    expect(s.post).toEqual([0.208]);
  });

  it("yields NaN for short/missing arrays instead of throwing", () => {
    const s = handleSeries([step({ prediction: [], predictionStd: [] })], 2);
    expect(Number.isNaN(s.pred[0])).toBe(true);
    expect(Number.isNaN(s.predLo[0])).toBe(true);
  });
});

describe("zeta/gain series", () => {
  it("reads the selected handle and maps null zeta to NaN", () => {
    const steps = [step({}), step({ zeta: null })];
    expect(zetaSeries(steps, 1)).toEqual([0.4, NaN]);
    expect(gainSeries(steps, 2)).toEqual([0.4, 0.4]);
  });
});

describe("qStack", () => {
  it("stacks cumulatively in the fixed Q_KEYS order, zeros for missing keys", () => {
    const layers = qStack([step({})], 0);
    expect(layers.map((l) => l.key)).toEqual([...Q_KEYS]);
    expect(layers[0].lo[0]).toBe(0); // clock from the baseline
    expect(layers[0].hi[0]).toBeCloseTo(1e-6);
    expect(layers[1].lo[0]).toBeCloseTo(1e-6); // spot on top of clock
    expect(layers[1].hi[0]).toBeCloseTo(5e-6);
    // absent components (event/source/model/adaptive) are zero-thickness
    expect(layers[2].lo[0]).toBeCloseTo(5e-6);
    expect(layers[5].hi[0]).toBeCloseTo(5e-6);
  });

  it("clamps negative components to zero (variances by construction)", () => {
    const layers = qStack([step({ processBreakdown: { clock: [-1, 0, 0] } })], 0);
    expect(layers[0].hi[0]).toBe(0);
  });
});

describe("stepMarkers", () => {
  it("classifies seed vs reset vs contaminated, allowing both on one step", () => {
    const steps = [
      step({ resetReason: "first", provenance: "seed:today_fit" }),
      step({}),
      step({ resetReason: "quotes_edited", provenance: "seed:active_transported", contaminated: true }),
    ];
    const m = stepMarkers(steps);
    expect(m).toHaveLength(3);
    expect(m[0]).toMatchObject({ index: 0, kind: "seed" });
    expect(m[0].label).toContain("first");
    expect(m[1]).toMatchObject({ index: 2, kind: "reset" });
    expect(m[2]).toMatchObject({ index: 2, kind: "contaminated" });
  });
});

describe("yDomain", () => {
  it("pads the finite extent and ignores NaN", () => {
    const [lo, hi] = yDomain([1, 3, NaN], 0.1);
    expect(lo).toBeCloseTo(0.8);
    expect(hi).toBeCloseTo(3.2);
  });
  it("falls back on empty input and opens a flat domain", () => {
    expect(yDomain([])).toEqual([0, 1]);
    const [lo, hi] = yDomain([2, 2]);
    expect(lo).toBeLessThan(2);
    expect(hi).toBeGreaterThan(2);
  });
});

describe("SVG paths", () => {
  it("linePath restarts across non-finite points", () => {
    expect(linePath([0, 1, 2, 3], [5, NaN, 7, 8])).toBe("M0.0,5.0M2.0,7.0L3.0,8.0");
  });
  it("bandPath closes hi-forward / lo-back and drops bad indices", () => {
    expect(bandPath([0, 1, 2], [1, NaN, 1], [3, 4, 3])).toBe(
      "M0.0,3.0L2.0,3.0L2.0,1.0L0.0,1.0Z",
    );
    expect(bandPath([0], [1], [2])).toBe(""); // < 2 valid points
  });
});

describe("axis helpers", () => {
  it("stepLabel formats HH:MM intraday and MM-DD across days", () => {
    expect(stepLabel(1_760_000_000, false)).toMatch(/^\d{2}:\d{2}$/);
    expect(stepLabel(1_760_000_000, true)).toMatch(/^\d{2}-\d{2}$/);
  });
  it("spansDays detects multi-day rings", () => {
    const a = step({ ts: 1_760_000_000 });
    const b = step({ ts: 1_760_000_000 + 3600 });
    const c = step({ ts: 1_760_000_000 + 5 * 86400 });
    expect(spansDays([a, b])).toBe(false);
    expect(spansDays([a, c])).toBe(true);
    expect(spansDays([a])).toBe(false);
  });
  it("tickIndices always includes first and last, bounded by the target", () => {
    expect(tickIndices(0)).toEqual([]);
    expect(tickIndices(3)).toEqual([0, 1, 2]);
    const t = tickIndices(13, 6);
    expect(t[0]).toBe(0);
    expect(t[t.length - 1]).toBe(12);
    expect(t.length).toBeLessThanOrEqual(7);
  });
});
