// Weight-strip binning/alignment helpers (V3.4 item 5).
import { describe, expect, it } from "vitest";
import { buildWeightBars, mockWeightEntries } from "./weightStrip";
import type { WeightEntry } from "./weightStrip";

function entry(over: Partial<WeightEntry> & { index: number; k: number }): WeightEntry {
  return { spacing: 0.1, weightRaw: 1, weight: 1, excluded: false, ...over };
}

describe("buildWeightBars", () => {
  it("normalizes each series to max 1 over the included entries", () => {
    const bars = buildWeightBars([
      entry({ index: 0, k: -0.1, spacing: 0.1, weight: 0.5 }),
      entry({ index: 1, k: 0.0, spacing: 0.05, weight: 2.0 }), // densest + heaviest
      entry({ index: 2, k: 0.1, spacing: 0.2, weight: 1.0 }),
    ]);
    expect(bars[1].density).toBe(1); // 1/0.05 is the max crowding
    expect(bars[1].weightNorm).toBe(1); // weight 2.0 is the max
    expect(bars[0].density).toBeCloseTo(0.5, 12); // (1/0.1)/(1/0.05)
    expect(bars[2].density).toBeCloseTo(0.25, 12);
    expect(bars[0].weightNorm).toBeCloseTo(0.25, 12);
    expect(bars[2].weightNorm).toBeCloseTo(0.5, 12);
    expect(bars[2].weight).toBe(1.0); // the actual mean-1 value survives
  });

  it("zeroes excluded rows and leaves them out of the normalization", () => {
    const bars = buildWeightBars([
      entry({ index: 0, k: -0.1, spacing: 0.1, weight: 1.0 }),
      // Excluded row with extreme values: must NOT set either series' scale.
      entry({ index: 1, k: 0.0, spacing: 0.0001, weight: 99, excluded: true }),
      entry({ index: 2, k: 0.1, spacing: 0.2, weight: 0.5 }),
    ]);
    expect(bars[1].excluded).toBe(true);
    expect(bars[1].density).toBe(0);
    expect(bars[1].weightNorm).toBe(0);
    expect(bars[1].weight).toBe(0);
    expect(bars[0].density).toBe(1); // 1/0.1 is the included max
    expect(bars[0].weightNorm).toBe(1); // weight 1.0 is the included max
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
    expect(all[0].density).toBe(0);
    const noCell = buildWeightBars([entry({ index: 0, k: 0, spacing: 0 })]);
    expect(noCell[0].density).toBe(0); // spacing 0 = no Voronoi cell
    expect(noCell[0].weightNorm).toBe(1);
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
