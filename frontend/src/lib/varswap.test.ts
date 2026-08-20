// Var-swap helper locks (V3.6 item 14): the data-derived slider-bound formula
// and the batch-shift → per-node dispatch mapping.
import { describe, expect, it } from "vitest";
import {
  VS_MIN_LEVEL,
  VS_SLIDER_STEP,
  formatBasisBp,
  varswapBasisBp,
  varswapShiftEdits,
  varswapSliderBounds,
} from "./varswap";

describe("varswapSliderBounds", () => {
  it("no quote: ±2 vol points around the model level", () => {
    const b = varswapSliderBounds(null, 0.2);
    expect(b.min).toBeCloseTo(18, 10);
    expect(b.max).toBeCloseTo(22, 10);
    expect(b.step).toBe(VS_SLIDER_STEP);
  });

  it("small basis: the 2-vol-point pad dominates", () => {
    // quote 20.5 %, model 20 % ⇒ |basis| = 50 bp ⇒ 2·|basis| = 1 pt < 2 pts.
    const b = varswapSliderBounds(0.205, 0.2);
    expect(b.min).toBeCloseTo(18, 10); // min(20.5, 20) − 2
    expect(b.max).toBeCloseTo(22.5, 10); // max(20.5, 20) + 2
  });

  it("large basis: pad = 2·|basis| in vol points, envelope spans quote∪model", () => {
    // quote 26 %, model 20 % ⇒ basis 600 bp ⇒ pad 12 vol points.
    const b = varswapSliderBounds(0.26, 0.2);
    expect(b.min).toBeCloseTo(8, 10); // 20 − 12
    expect(b.max).toBeCloseTo(38, 10); // 26 + 12
    // Symmetric when the quote sits BELOW the model (sign-free pad).
    const lo = varswapSliderBounds(0.14, 0.2);
    expect(lo.min).toBeCloseTo(2, 10); // 14 − 12
    expect(lo.max).toBeCloseTo(32, 10); // 20 + 12
  });

  it("floors the lower bound at 0.5 % vol", () => {
    const b = varswapSliderBounds(0.01, 0.02);
    expect(b.min).toBe(0.5);
  });
});

describe("varswapBasisBp / formatBasisBp", () => {
  it("basis is (quote − model)·1e4, null without a quote", () => {
    expect(varswapBasisBp(0.21, 0.2)).toBeCloseTo(100, 8);
    expect(varswapBasisBp(0.19, 0.2)).toBeCloseTo(-100, 8);
    expect(varswapBasisBp(null, 0.2)).toBeNull();
  });

  it("formats signed whole bp", () => {
    expect(formatBasisBp(123.4)).toBe("+123 bp");
    expect(formatBasisBp(-4.6)).toBe("-5 bp");
    expect(formatBasisBp(0)).toBe("0 bp");
    expect(formatBasisBp(null)).toBe("—");
    expect(formatBasisBp(Number.NaN)).toBe("—");
  });
});

describe("varswapShiftEdits", () => {
  const points = [
    { expiry: "2026-09-18", varSwapQuote: 0.2 },
    { expiry: "2026-10-16", varSwapQuote: null },
    { expiry: "2026-12-18", varSwapQuote: 0.22 },
    { expiry: "2027-03-19" }, // no quote field at all
  ];

  it("maps each QUOTED rung to its own node edit, +bp in decimal vol", () => {
    const edits = varswapShiftEdits(points, 25);
    expect(edits).toEqual([
      { expiry: "2026-09-18", level: 0.2 + 25e-4 },
      { expiry: "2026-12-18", level: 0.22 + 25e-4 },
    ]);
  });

  it("skips unquoted rungs and never invents a quote", () => {
    expect(varswapShiftEdits(points, 25).map((e) => e.expiry)).not.toContain(
      "2026-10-16",
    );
  });

  it("zero / non-finite shift produces no edits", () => {
    expect(varswapShiftEdits(points, 0)).toEqual([]);
    expect(varswapShiftEdits(points, Number.NaN)).toEqual([]);
  });

  it("floors a large downward shift at the positive-level minimum", () => {
    const edits = varswapShiftEdits(points, -5000); // −50 vol points
    expect(edits.every((e) => e.level === VS_MIN_LEVEL)).toBe(true);
  });
});
