// Weight-strip binning/alignment helpers (V3.4 item 5; series redefined
// 2026-09-09: target shape vs the weight the fit sums, plus the multiplier).
import { describe, expect, it } from "vitest";
import { buildWeightBars, mockWeightEntries, targetLabel } from "./weightStrip";
import type { WeightEntry } from "./weightStrip";

function entry(over: Partial<WeightEntry> & { index: number; k: number }): WeightEntry {
  return { spacing: 0.1, weightRaw: 1, weight: 1, excluded: false, ...over };
}

describe("buildWeightBars", () => {
  it("normalizes the target and the weight each to max 1 over the included entries", () => {
    const bars = buildWeightBars(
      [
        entry({ index: 0, k: -0.1, spacing: 0.1, weightRaw: 0.2, weight: 0.5 }),
        entry({ index: 1, k: 0.0, spacing: 0.05, weightRaw: 0.4, weight: 2.0 }), // peak target + heaviest
        entry({ index: 2, k: 0.1, spacing: 0.2, weightRaw: 0.1, weight: 1.0 }),
      ],
      { scheme: "vega_density", maxMult: 10 },
    );
    expect(bars[1].target).toBe(1); // 0.4 is the max target
    expect(bars[1].weightNorm).toBe(1); // weight 2.0 is the max
    expect(bars[0].target).toBeCloseTo(0.5, 12); // 0.2 / 0.4
    expect(bars[2].target).toBeCloseTo(0.25, 12);
    expect(bars[0].weightNorm).toBeCloseTo(0.25, 12);
    expect(bars[2].weightNorm).toBeCloseTo(0.5, 12);
    expect(bars[2].weight).toBe(1.0); // the actual mean-1 value survives
    expect(bars[2].targetRaw).toBe(0.1); // and so does the raw target
  });

  it("reports the capped Voronoi multiplier s_i / s̄ the density schemes applied", () => {
    // s̄ = (0.1 + 0.05 + 0.2) / 3 = 0.35 / 3
    const bars = buildWeightBars(
      [
        entry({ index: 0, k: -0.1, spacing: 0.1 }),
        entry({ index: 1, k: 0.0, spacing: 0.05 }), // crowded: multiplier < 1
        entry({ index: 2, k: 0.1, spacing: 0.2 }), // isolated: multiplier > 1
      ],
      { scheme: "uniform_density", maxMult: 10 },
    );
    const sBar = 0.35 / 3;
    expect(bars[0].spacingMult).toBeCloseTo(0.1 / sBar, 12);
    expect(bars[1].spacingMult).toBeCloseTo(0.05 / sBar, 12);
    expect(bars[2].spacingMult).toBeCloseTo(0.2 / sBar, 12);
    // The cap bites on an isolated far-wing quote: eleven crowded strikes
    // (cells 0.001) and one lone wing quote (cell 1.0) — s̄ ≈ 0.084, so the
    // wing's raw multiplier ≈ 11.9 is clipped to the cap.
    const crowded = Array.from({ length: 11 }, (_, i) => entry({ index: i, k: -0.1 + 0.001 * i, spacing: 0.001 }));
    const capped = buildWeightBars(
      [...crowded, entry({ index: 11, k: 2.0, spacing: 1.0 })],
      { scheme: "tv_density", maxMult: 10 },
    );
    expect(capped[11].spacingMult).toBe(10);
    expect(capped[0].spacingMult).toBeCloseTo(0.001 / (1.011 / 12), 12);
  });

  it("reports a unit multiplier under the equal scheme (no correction is applied)", () => {
    const bars = buildWeightBars(
      [entry({ index: 0, k: -0.1, spacing: 0.1 }), entry({ index: 1, k: 0.0, spacing: 0.02 })],
      { scheme: "equal", maxMult: 10 },
    );
    expect(bars.map((b) => b.spacingMult)).toEqual([1, 1]);
    expect(bars.map((b) => b.target)).toEqual([1, 1]); // flat target
  });

  it("zeroes excluded rows and leaves them out of the normalization and s̄", () => {
    const bars = buildWeightBars(
      [
        entry({ index: 0, k: -0.1, spacing: 0.1, weight: 1.0 }),
        // Excluded row with extreme values: must NOT set either series' scale.
        entry({ index: 1, k: 0.0, spacing: 0.0001, weightRaw: 99, weight: 99, excluded: true }),
        entry({ index: 2, k: 0.1, spacing: 0.1, weight: 0.5 }),
      ],
      { scheme: "vega_density", maxMult: 10 },
    );
    expect(bars[1].excluded).toBe(true);
    expect(bars[1].target).toBe(0);
    expect(bars[1].weightNorm).toBe(0);
    expect(bars[1].weight).toBe(0);
    expect(bars[1].targetRaw).toBe(0);
    expect(bars[1].spacingMult).toBe(1);
    expect(bars[0].target).toBe(1); // raw 1 is the included max
    expect(bars[0].weightNorm).toBe(1); // weight 1.0 is the included max
    expect(bars[0].spacingMult).toBeCloseTo(1, 12); // s̄ over the two survivors only
  });

  it("sorts by k while preserving QuoteBand.index alignment", () => {
    const bars = buildWeightBars([
      entry({ index: 2, k: 0.2 }),
      entry({ index: 0, k: -0.2 }),
      entry({ index: 1, k: 0.0 }),
    ]);
    expect(bars.map((b) => b.k)).toEqual([-0.2, 0.0, 0.2]);
    expect(bars.map((b) => b.index)).toEqual([0, 1, 2]);
  });

  it("handles degenerate inputs (empty, all-excluded, zero spacing)", () => {
    expect(buildWeightBars([])).toEqual([]);
    const all = buildWeightBars([entry({ index: 0, k: 0, excluded: true })]);
    expect(all[0].target).toBe(0);
    const noCell = buildWeightBars([entry({ index: 0, k: 0, spacing: 0 })], { scheme: "tv_density", maxMult: 10 });
    expect(noCell[0].spacingMult).toBe(1); // spacing 0 = no Voronoi cell
    expect(noCell[0].weightNorm).toBe(1);
    expect(noCell[0].target).toBe(1);
  });
});

describe("targetLabel", () => {
  it("names every scheme's target shape and echoes unknown ids", () => {
    expect(targetLabel("equal")).toBe("one per quote");
    expect(targetLabel("uniform_density")).toBe("uniform");
    expect(targetLabel("tv_density")).toBe("time value");
    expect(targetLabel("vega_density")).toBe("vega");
    expect(targetLabel("delta_density")).toBe("|delta|");
    expect(targetLabel("mystery")).toBe("mystery");
  });
});

describe("mockWeightEntries", () => {
  it("computes the backend's Voronoi spacing rule on a uniform grid", () => {
    const quotes = [0, 1, 2, 3, 4].map((i) => ({ k: -0.2 + 0.1 * i, index: i, excluded: false }));
    const entries = mockWeightEntries(quotes);
    // Interior cells are half the two-sided gap = the grid step; the ends are
    // one-sided — on a uniform grid every cell width equals the step.
    for (const e of entries) expect(e.spacing).toBeCloseTo(0.1, 12);
    expect(entries.every((e) => e.weight === 1 && e.weightRaw === 1)).toBe(true);
  });

  it("skips excluded strikes in the cells and zeroes their rows", () => {
    const quotes = [
      { k: -0.1, index: 0, excluded: false },
      { k: 0.0, index: 1, excluded: true },
      { k: 0.1, index: 2, excluded: false },
    ];
    const entries = mockWeightEntries(quotes);
    expect(entries[1].excluded).toBe(true);
    expect(entries[1].weight).toBe(0);
    expect(entries[1].spacing).toBe(0);
    // The two survivors form a 2-point grid: one-sided cells of the full gap.
    expect(entries[0].spacing).toBeCloseTo(0.2, 12);
    expect(entries[2].spacing).toBeCloseTo(0.2, 12);
  });

  it("handles degenerate quote lists", () => {
    expect(mockWeightEntries([])).toEqual([]);
    const one = mockWeightEntries([{ k: 0.05, index: 0, excluded: false }]);
    expect(one[0].spacing).toBe(0); // no cell with a single quote
    expect(one[0].weight).toBe(1);
  });
});
