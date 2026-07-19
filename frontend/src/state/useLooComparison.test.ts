// U7 comparison math: client-side coverage from standardized residuals and
// the transported-prior comparator from priorAtmVol.
import { describe, expect, it } from "vitest";
import { operatorColumn, priorColumn } from "./useLooComparison";
import type { BacktestResult } from "./useGraphExtrapolation";

function resp(): BacktestResult {
  const node = (zeta: number, prior: number, calibrated: number) => ({
    ticker: "SPY", expiry: "2026-09-18", priorSource: "active_transported",
    calibratedAtmVol: calibrated, postAtmVol: calibrated, residualBp: 0,
    standardizedResidual: zeta, priorAtmVol: prior,
  });
  return {
    nodes: [
      node(0.5, 0.20, 0.21), // +100bp prior residual, inside both bands
      node(1.5, 0.20, 0.20), //  0bp, outside 80%, inside 95%
      node(2.5, 0.21, 0.20), // −100bp, outside both
      node(-0.2, 0.20, 0.20),
    ],
    nScored: 4, nExcludedBootstrap: 0, rmseBp: 12.3, zetaMean: 1.07, zetaStd: 1.0,
  };
}

describe("LOO comparison columns", () => {
  it("computes coverage 80/95 from |ζ| client-side", () => {
    const col = operatorColumn("Messages", resp());
    expect(col.n).toBe(4);
    expect(col.rmseBp).toBe(12.3);
    expect(col.cov80).toBeCloseTo(2 / 4, 12); // |ζ| ≤ 1.2816: 0.5, 0.2
    expect(col.cov95).toBeCloseTo(3 / 4, 12); // + 1.5
  });

  it("derives the transported-prior comparator (RMSE only; ζ/cov n/a)", () => {
    const col = priorColumn(resp());
    // residuals: +100, 0, −100, 0 bp → RMSE = sqrt(20000/4) ≈ 70.7 bp.
    expect(col.rmseBp).toBeCloseTo(Math.sqrt(20000 / 4), 6);
    expect(col.zetaMean).toBeNull();
    expect(col.cov95).toBeNull();
  });
});
