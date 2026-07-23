// P6 V2 locks: the layered decomposition card renders the V0 exit-gate
// identity (baseline + systematic + residual + harmonic = mark) as signed
// bp rows, the boundary-class chip, the residual age, and the §12.2 χ
// badge — and self-hides on non-layered nodes (V0 fields absent).
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import DecompositionCard from "./DecompositionCard";
import type { ExtrapolateNode } from "../../state/useGraphExtrapolation";

/** A layered-run posterior node: prior 20.0%, parts +10 / −3 / +1 bp →
 *  mark 20.08% (the V0 identity). */
function node(over: Partial<ExtrapolateNode> = {}): ExtrapolateNode {
  return {
    ticker: "SPY", expiry: "2026-07-17", t: 0.02, lit: true, calibrated: true,
    priorSource: "stored", priorAsOf: "2026-07-16", transportDistance: 0,
    validForValidation: true,
    priorAtmVol: 0.2, priorSkew: 0, priorCurv: 0,
    postAtmVol: 0.2008, postSkew: 0, postCurv: 0,
    shiftBp: 8, sd: 0.005, bandLo: 0.2, bandHi: 0.22, innovationBp: 8,
    baselinePrecision: [1, 1, 1], obsPrecision: null, precisionFactors: {},
    qIncoming: null, noLitPath: false,
    boundaryClass: "fresh_certified",
    systematicAtmVol: 0.001,
    residualAtmVol: -0.0003,
    residualAgeDays: 0.5,
    harmonicAtmVol: 0.0001,
    residualSurpriseAtm: -2.1,
    ...over,
  };
}

afterEach(cleanup);

describe("DecompositionCard", () => {
  it("renders the four-part identity in bp with the mark footer", () => {
    render(<DecompositionCard node={node()} />);
    expect(screen.getByText("baseline (prior)")).toBeTruthy();
    expect(screen.getByText("20.0%")).toBeTruthy();
    expect(screen.getByText("+10.0 bp")).toBeTruthy(); // systematic
    expect(screen.getByText("-3.0 bp")).toBeTruthy(); // residual
    expect(screen.getByText("+1.0 bp")).toBeTruthy(); // harmonic
    // mark = 20.08% → 20.1%, with the parts sum spelled out.
    expect(screen.getByText(/20\.1%/)).toBeTruthy();
    expect(screen.getByText(/Σ \+8\.0 bp/)).toBeTruthy();
    // Residual age rides the residual row.
    expect(screen.getByText("· 0.5d")).toBeTruthy();
  });

  it("boundary chip follows the class; χ badge tones by magnitude", () => {
    const { rerender } = render(<DecompositionCard node={node()} />);
    expect(screen.getByText("clamped boundary")).toBeTruthy();
    // |χ| = 2.1 > 2 → loud (rose) dislocation badge.
    const chi = screen.getByText(/χ -2\.1/);
    expect(chi.className).toContain("text-rose-300");

    rerender(
      <DecompositionCard
        node={node({
          boundaryClass: "soft_stale", residualSurpriseAtm: 1.5,
        })}
      />,
    );
    expect(screen.getByText("stale · soft anchor")).toBeTruthy();
    expect(screen.getByText(/χ \+1\.5/).className).toContain("text-amber-300");

    rerender(
      <DecompositionCard
        node={node({
          boundaryClass: "unobserved", residualSurpriseAtm: null,
          residualAgeDays: null,
        })}
      />,
    );
    expect(screen.getByText("unobserved")).toBeTruthy();
    // No certified print today → no χ badge, no age note.
    expect(screen.queryByText(/^χ /)).toBeNull();
    expect(screen.queryByText(/·.*d$/)).toBeNull();
  });

  it("self-hides when the V0 fields are absent (non-layered run)", () => {
    render(
      <DecompositionCard
        node={node({
          boundaryClass: undefined, systematicAtmVol: undefined,
          residualAtmVol: undefined, residualAgeDays: undefined,
          harmonicAtmVol: undefined, residualSurpriseAtm: undefined,
        })}
      />,
    );
    expect(screen.queryByTestId("decomposition")).toBeNull();
  });
});
