// U2 client mirror of the backend calendar policy: ladder expansion goldens
// (adjacent pairs, short receiver, §8.2 shape / §9.2 family) + per-ticker
// resolution + the |β|-cap flag.
import { describe, expect, it } from "vitest";
import { BETA_CAP, calendarLadder, effectiveCalendarPolicy } from "./calendarPolicy";
import type { SolverParams } from "../state/useGraph";

const POLICY = { alphaT: 1, scale: 1700, epsilon: 0.97, decay: "inverse_sqrt_gap" as const };

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

describe("calendarLadder", () => {
  it("expands adjacent pairs with the §8.2 shape and §9.2 precisions", () => {
    const rungs = calendarLadder(
      [{ expiry: "1Y", t: 1.0 }, { expiry: "3M", t: 0.25 }, { expiry: "6M", t: 0.5 }],
      POLICY,
    );
    expect(rungs).toHaveLength(2);
    expect(rungs[0]).toMatchObject({ shortExpiry: "3M", longExpiry: "6M" });
    expect(rungs[0]!.beta).toBeCloseTo(2, 12);
    expect(rungs[0]!.precision).toBeCloseTo(1700 / (0.97 + Math.sqrt(0.25)), 9);
    expect(rungs[1]!.beta).toBeCloseTo(2, 12);
    expect(rungs[0]!.capped).toBe(false);
  });

  it("flags rungs whose |β| exceeds the cap and drops expired nodes", () => {
    const rungs = calendarLadder(
      [{ expiry: "0D", t: 0 }, { expiry: "1W", t: 0.02 }, { expiry: "3M", t: 0.25 }],
      POLICY,
    );
    expect(rungs).toHaveLength(1); // t=0 node carries no maturity shape
    expect(rungs[0]!.beta).toBeCloseTo(12.5, 9);
    expect(rungs[0]!.capped).toBe(true);
    expect(BETA_CAP).toBe(3);
  });
});

describe("effectiveCalendarPolicy", () => {
  it("inherits, refines per ticker, and gates on the global switch", () => {
    const p = params({
      calendarOverrides: {
        NVDA: { enabled: true, precisionScale: 3400, betaExponent: 0.5 },
        AAPL: { enabled: false, precisionScale: null, betaExponent: null },
      },
    });
    expect(effectiveCalendarPolicy(p, "SPY")).toEqual({ enabled: true, scale: 1700, alphaT: 1 });
    expect(effectiveCalendarPolicy(p, "NVDA")).toEqual({ enabled: true, scale: 3400, alphaT: 0.5 });
    expect(effectiveCalendarPolicy(p, "AAPL").enabled).toBe(false);
    const off = params({ calendarEnabled: false });
    expect(effectiveCalendarPolicy(off, "SPY").enabled).toBe(false);
  });
});
