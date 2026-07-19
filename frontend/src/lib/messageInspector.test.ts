// U4 message-inspector math: incoming relations (direct + implied reverse +
// distance-derived precision under the U2 policy) and the exact §21 receiver
// conditional over them.
import { describe, expect, it } from "vitest";
import { incomingRelations, receiverConsensus } from "./messageInspector";
import type { SolverParams } from "../state/useGraph";
import type { ExtrapolateNode } from "../state/useGraphExtrapolation";
import type { MessageEdgeRow } from "../state/useMessageEdges";

function params(over: Partial<SolverParams> = {}): SolverParams {
  return {
    etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1,
    calendarWeight: null, crossWeight: null,
    propagationMode: "precision_messages", alphaT: 1, ampCal: 1, ampCross: 1,
    calPrecision: 1700, calEpsilon: 0.97,
    calDecay: "inverse_sqrt_gap", crossPrecision: 13000,
    calendarEnabled: true, calendarOverrides: {},
    ...over,
  };
}

function node(
  ticker: string, expiry: string, t: number, shift = 0,
): ExtrapolateNode {
  return {
    ticker, expiry, t, lit: false, calibrated: false, priorSource: "stored",
    priorAsOf: null, transportDistance: 0, validForValidation: true,
    priorAtmVol: 0.2, priorSkew: 0, priorCurv: 0,
    postAtmVol: 0.2 + shift, postSkew: 0, postCurv: 0,
    shiftBp: shift * 1e4, sd: 0.005, bandLo: 0.19, bandHi: 0.21,
    innovationBp: null, baselinePrecision: [1, 1, 1], obsPrecision: null,
    precisionFactors: {}, qIncoming: null, noLitPath: false,
  };
}

/** §21.1 shape: 12-18 (0.5y) informs 09-18 (0.25y) at β=2, p=4. */
const ROW: MessageEdgeRow = {
  sourceTicker: "SPY", sourceExpiry: "2026-12-18",
  targetTicker: "SPY", targetExpiry: "2026-09-18",
  messagePrecision: 4, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
  relationClass: "calendar", precisionRule: "explicit",
};

const NODES = [
  node("SPY", "2026-09-18", 0.25),
  node("SPY", "2026-12-18", 0.5, 0.01), // informer moved +1pt
];

describe("incomingRelations", () => {
  it("reads a direct row toward the receiver with the informer's innovation", () => {
    const rel = incomingRelations(
      { ticker: "SPY", expiry: "2026-09-18" }, [ROW], NODES, params(),
    );
    expect(rel).toHaveLength(1);
    expect(rel[0]).toMatchObject({
      informerTicker: "SPY", informerExpiry: "2026-12-18",
      beta: 2, precision: 4, implied: false, rho: 1,
    });
    expect(rel[0]!.z).toBeCloseTo(0.01, 12);
    expect(rel[0]!.mappedPts).toBeCloseTo(2.0, 12); // β·z in vol pts
  });

  it("reads a source-side row in reverse: 1/β and p·β² (§7.6/§8.3)", () => {
    const rel = incomingRelations(
      { ticker: "SPY", expiry: "2026-12-18" }, [ROW], NODES, params(),
    );
    expect(rel).toHaveLength(1);
    expect(rel[0]).toMatchObject({ implied: true, beta: 0.5, precision: 16 });
  });

  it("derives distance-rule precision under the receiver's effective policy", () => {
    const distRow = { ...ROW, precisionRule: "calendar_distance" as const };
    const base = incomingRelations(
      { ticker: "SPY", expiry: "2026-09-18" }, [distRow], NODES, params(),
    );
    expect(base[0]!.precision).toBeCloseTo(1700 / (0.97 + Math.sqrt(0.25)), 9);
    const tuned = incomingRelations(
      { ticker: "SPY", expiry: "2026-09-18" }, [distRow], NODES,
      params({
        calendarOverrides: {
          SPY: { enabled: true, precisionScale: 3400, betaExponent: null },
        },
      }),
    );
    expect(tuned[0]!.precision).toBeCloseTo(2 * base[0]!.precision, 9);
  });

  it("suppresses calendar factors when the receiver's policy is disabled", () => {
    const rel = incomingRelations(
      { ticker: "SPY", expiry: "2026-09-18" }, [ROW], NODES,
      params({ calendarEnabled: false }),
    );
    expect(rel).toHaveLength(0);
  });
});

describe("receiverConsensus", () => {
  it("reproduces the §21.1 full-transmission conditional", () => {
    const rel = incomingRelations(
      { ticker: "SPY", expiry: "2026-09-18" }, [ROW], NODES, params(),
    );
    const c = receiverConsensus(rel);
    expect(c.mean).toBeCloseTo(0.02, 12); // +2 pts in decimal vol
    expect(c.q).toBe(4);
    expect(c.kappa).toBe(0);
  });
});
