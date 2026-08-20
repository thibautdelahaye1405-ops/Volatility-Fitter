// Unit tests for the Compare view's pure logic (V3.2 item 12): series
// building from the wire payload, validity-chip states and null-metric
// formatting — the parts the chart/table components consume verbatim.
import { describe, expect, it } from "vitest";
import { getMockComparison } from "./mockData";
import type { CompareModelFit } from "./mockData";
import { MODEL_COLORS, MODEL_LABELS } from "./modelColor";
import {
  compareSeries,
  formatExp,
  formatFitMs,
  formatMetric,
  formatVolPct,
  validityChip,
} from "./modelCompare";

const baseFit = (over: Partial<CompareModelFit>): CompareModelFit => ({
  model: "svi",
  label: "SVI-JW",
  ok: true,
  curve: [
    { k: -0.1, vol: 0.22 },
    { k: 0.0, vol: 0.2 },
    { k: 0.1, vol: 0.21 },
  ],
  ...over,
});

describe("compareSeries", () => {
  it("builds one series per model in book order with the family colours", () => {
    const series = compareSeries(getMockComparison());
    expect(series.map((s) => s.label)).toEqual(["LQD", "SVI-JW", "MCS"]);
    expect(series.map((s) => s.color)).toEqual([
      MODEL_COLORS.lqd,
      MODEL_COLORS.svi,
      MODEL_COLORS.sigmoid,
    ]);
    for (const s of series) {
      expect(s.xs.length).toBe(s.ys.length);
      expect(s.xs.length).toBeGreaterThan(1);
    }
    expect(MODEL_LABELS.sigmoid).toBe("MCS"); // the book naming, not "Sigmoid"
  });

  it("skips failed rows and degenerate curves (table still lists them)", () => {
    const data = getMockComparison();
    data.models[1] = baseFit({ ok: false, error: "boom", curve: [] });
    data.models[2] = baseFit({ model: "sigmoid", label: "MCS", curve: [{ k: 0, vol: 0.2 }] });
    expect(compareSeries(data).map((s) => s.label)).toEqual(["LQD"]);
  });
});

describe("validityChip", () => {
  it("certified => green 'clean' naming the analytic quantity", () => {
    const chip = validityChip(
      baseFit({ validity: { kind: "g", minValue: 2.4e-4, certified: true } }),
    );
    expect(chip.certified).toBe(true);
    expect(chip.label).toBe("clean");
    expect(chip.title).toContain("Durrleman g");
  });

  it("breach => rose chip carrying the minimum value", () => {
    const chip = validityChip(
      baseFit({ validity: { kind: "g", minValue: -3.1e-4, certified: false } }),
    );
    expect(chip.certified).toBe(false);
    expect(chip.label).toContain("breach");
    expect(chip.label).toContain(formatExp(-3.1e-4));
  });

  it("density kind titles the LQD structural quantity", () => {
    const chip = validityChip(
      baseFit({ model: "lqd", validity: { kind: "density", minValue: 1e-6, certified: true } }),
    );
    expect(chip.title).toContain("density");
  });

  it("missing / recon validity => neutral n/a; failed fit => rose", () => {
    expect(validityChip(baseFit({ validity: null })).certified).toBeNull();
    expect(validityChip(baseFit({ validity: { kind: "recon", certified: null } })).label).toBe("n/a");
    const failed = validityChip(baseFit({ ok: false, error: "SolverError" }));
    expect(failed.certified).toBe(false);
    expect(failed.title).toBe("SolverError");
  });
});

describe("null-metric formatting", () => {
  it("em-dashes null / undefined / non-finite metrics", () => {
    expect(formatMetric(null)).toBe("—");
    expect(formatMetric(undefined)).toBe("—");
    expect(formatMetric(Number.NaN)).toBe("—");
    expect(formatMetric(18.44)).toBe("18.4");
    expect(formatMetric(-0.355, 3)).toBe("-0.355");
    expect(formatVolPct(null)).toBe("—");
    expect(formatVolPct(0.206)).toBe("20.60%");
  });

  it("labels reused committed fits 'cached', ad-hoc fits in ms", () => {
    expect(formatFitMs(baseFit({ reused: true, fitMs: null }))).toBe("cached");
    expect(formatFitMs(baseFit({ reused: false, fitMs: 41.8 }))).toBe("42 ms");
    expect(formatFitMs(baseFit({ reused: false, fitMs: null }))).toBe("—");
  });
});
