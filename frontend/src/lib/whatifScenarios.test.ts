// U3 scenario shortcuts: deterministic pulse sets on the richest ticker,
// null when the universe can't host the story.
import { describe, expect, it } from "vitest";
import { buildScenario } from "./whatifScenarios";
import type { GraphNodeBase } from "../state/useGraph";

function node(ticker: string, expiry: string, t: number): GraphNodeBase {
  return { ticker, expiry, t, atmVol: 0.2, skew: 0, curvature: 0, lit: false };
}

const UNIVERSE = [
  node("SPY", "2026-08-21", 0.09),
  node("SPY", "2026-10-16", 0.25),
  node("SPY", "2027-01-15", 0.5),
  node("NVDA", "2026-10-16", 0.25),
];

describe("buildScenario", () => {
  it("calendar pulse: one mid-ladder node of the richest ticker at +1pt", () => {
    expect(buildScenario("calendar_pulse", UNIVERSE)).toEqual({
      "SPY|2026-10-16": 0.01,
    });
  });

  it("competing signals: ±1pt around a middle rung", () => {
    expect(buildScenario("competing_signals", UNIVERSE)).toEqual({
      "SPY|2026-08-21": 0.01,
      "SPY|2027-01-15": -0.01,
    });
  });

  it("cross basket: the whole richest ticker at +1pt", () => {
    expect(buildScenario("cross_basket", UNIVERSE)).toEqual({
      "SPY|2026-08-21": 0.01,
      "SPY|2026-10-16": 0.01,
      "SPY|2027-01-15": 0.01,
    });
  });

  it("returns null when the universe cannot host the story", () => {
    const single = [node("SPY", "2026-10-16", 0.25)];
    expect(buildScenario("calendar_pulse", single)).toBeNull();
    expect(buildScenario("competing_signals", UNIVERSE.slice(0, 2))).toBeNull();
    expect(buildScenario("cross_basket", UNIVERSE.slice(0, 3))).toBeNull(); // one ticker only
    // Expired nodes carry no pulse: t=0 rungs are excluded from ladders.
    expect(
      buildScenario("calendar_pulse", [node("SPY", "2026-06-10", 0), node("SPY", "2026-08-21", 0.09)]),
    ).toBeNull();
  });
});
