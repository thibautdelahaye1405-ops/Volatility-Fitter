// U7 plan annotations: bridges (no-lit-path), weakly connected (low q vs the
// field), resolves competing signals (opposite-sign incoming votes).
import { describe, expect, it } from "vitest";
import { planAnnotations } from "./planAnnotations";
import type { SolverParams } from "../state/useGraph";
import type { ExtrapolateNode } from "../state/useGraphExtrapolation";
import type { MessageEdgeRow } from "../state/useMessageEdges";

function params(): SolverParams {
  return {
    etaScale: 1, kappaScale: 1, lambdaScale: 0, nu: 0.1,
    calendarWeight: null, crossWeight: null,
    propagationMode: "precision_messages", alphaT: 1, ampCal: 1, ampCross: 1,
    calPrecision: 1700, calEpsilon: 0.97,
    calDecay: "inverse_sqrt_gap", crossPrecision: 13000,
    calendarEnabled: true, calendarOverrides: {},
  };
}

function node(
  ticker: string, expiry: string, t: number, over: Partial<ExtrapolateNode> = {},
): ExtrapolateNode {
  return {
    ticker, expiry, t, lit: false, calibrated: false, priorSource: "stored",
    priorAsOf: null, transportDistance: 0, validForValidation: true,
    priorAtmVol: 0.2, priorSkew: 0, priorCurv: 0,
    postAtmVol: 0.2, postSkew: 0, postCurv: 0,
    shiftBp: 0, sd: 0.005, bandLo: 0.19, bandHi: 0.21,
    innovationBp: null, baselinePrecision: [1, 1, 1], obsPrecision: null,
    precisionFactors: {}, qIncoming: 1000, noLitPath: false,
    ...over,
  };
}

/** Two informers voting in OPPOSITE directions on the candidate. */
const COMPETING_ROWS: MessageEdgeRow[] = [
  {
    sourceTicker: "SPY", sourceExpiry: "2026-12-18",
    targetTicker: "SPY", targetExpiry: "2026-09-18",
    messagePrecision: 1000, betaAtmVol: 1, betaSkew: 1, betaCurv: 1,
    relationClass: "calendar", precisionRule: "explicit",
  },
  {
    sourceTicker: "QQQ", sourceExpiry: "2026-09-18",
    targetTicker: "SPY", targetExpiry: "2026-09-18",
    messagePrecision: 1000, betaAtmVol: 1, betaSkew: 1, betaCurv: 1,
    relationClass: "broad_index", precisionRule: "explicit",
  },
];

describe("planAnnotations", () => {
  it("flags a no-lit-path candidate as bridging", () => {
    const nodes = [node("SPY", "2026-09-18", 0.25, { noLitPath: true })];
    const out = planAnnotations(
      { ticker: "SPY", expiry: "2026-09-18" }, nodes, [], params(), true,
    );
    expect(out.map((a) => a.id)).toEqual(["bridges"]);
  });

  it("flags a weakly connected candidate (q far below the field median)", () => {
    const nodes = [
      node("SPY", "2026-09-18", 0.25, { qIncoming: 10 }), // the candidate
      node("SPY", "2026-12-18", 0.5, { qIncoming: 1000 }),
      node("QQQ", "2026-09-18", 0.25, { qIncoming: 2000 }),
    ];
    const out = planAnnotations(
      { ticker: "SPY", expiry: "2026-09-18" }, nodes, [], params(), true,
    );
    expect(out.map((a) => a.id)).toEqual(["weak"]);
  });

  it("flags competing signals when incoming votes disagree", () => {
    const nodes = [
      node("SPY", "2026-09-18", 0.25),
      node("SPY", "2026-12-18", 0.5, { postAtmVol: 0.21 }), // votes +1pt
      node("QQQ", "2026-09-18", 0.25, { postAtmVol: 0.19 }), // votes −1pt
    ];
    const out = planAnnotations(
      { ticker: "SPY", expiry: "2026-09-18" }, nodes, COMPETING_ROWS, params(), true,
    );
    expect(out.map((a) => a.id)).toContain("competing");
  });

  it("stays quiet without a solved field or in smooth mode", () => {
    expect(
      planAnnotations({ ticker: "SPY", expiry: "2026-09-18" }, null, [], params(), true),
    ).toEqual([]);
    const nodes = [node("SPY", "2026-09-18", 0.25, { qIncoming: 10 })];
    expect(
      planAnnotations({ ticker: "SPY", expiry: "2026-09-18" }, nodes, [], params(), false),
    ).toEqual([]);
  });
});
