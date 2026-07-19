// U1 units lens: σ_edge = 1/√p in vol points must round-trip exactly and
// reproduce the arc's canonical sentence example ("+1.00 pt → +0.70 pt
// message · relationship uncertainty 0.80 pt").
import { describe, expect, it } from "vitest";
import {
  fmtSigmaPts,
  precisionFromSigmaPts,
  relationSentence,
  sigmaPtsFromPrecision,
} from "./precisionUnits";

describe("sigma-pts lens", () => {
  it("maps the Phase-0 seeds to trader-readable points", () => {
    expect(sigmaPtsFromPrecision(1700)).toBeCloseTo(2.4254, 3); // calendar p0
    expect(sigmaPtsFromPrecision(13000)).toBeCloseTo(0.8771, 3); // cross seed
    expect(sigmaPtsFromPrecision(4)).toBeCloseTo(50, 12); // §21 golden row
  });

  it("round-trips p → σ → p exactly", () => {
    for (const p of [4, 1700, 13000, 15625]) {
      expect(precisionFromSigmaPts(sigmaPtsFromPrecision(p))).toBeCloseTo(p, 8);
    }
  });

  it("guards the degenerate ends: p<=0 → ∞ uncertainty; σ<=0 → p 0", () => {
    expect(sigmaPtsFromPrecision(0)).toBe(Infinity);
    expect(fmtSigmaPts(0)).toBe("∞");
    expect(precisionFromSigmaPts(0)).toBe(0);
    expect(precisionFromSigmaPts(-1)).toBe(0);
  });
});

describe("relation sentence", () => {
  it("renders the arc's canonical example", () => {
    // ρβ = 0.70 and σ_edge = 0.80 pt ⇒ p = (100/0.8)² = 15625.
    expect(
      relationSentence({
        sourceLabel: "SPY 6M",
        targetLabel: "AAPL 6M",
        beta: 0.7,
        precision: 15625,
        rho: 1,
      }),
    ).toBe(
      "SPY 6M informs AAPL 6M: +1.00 pt → +0.70 pt message · relationship uncertainty 0.80 pt",
    );
  });

  it("applies the class amplitude ρ to the transfer (§21.12: ρβz)", () => {
    const s = relationSentence({
      sourceLabel: "SPY 12-18",
      targetLabel: "SPY 09-18",
      beta: 2,
      precision: 4,
      rho: 0.34,
    });
    expect(s).toContain("+0.68 pt message");
    expect(s).toContain("relationship uncertainty 50.00 pt");
  });
});
