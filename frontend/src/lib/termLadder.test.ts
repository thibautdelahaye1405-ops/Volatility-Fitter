import { describe, expect, it } from "vitest";
import { clocksDiffer, forwardLadder, ladderSpreadBp } from "./termLadder";
import type { TermPoint } from "../state/useTerm";

/** A term point with only the ladder-relevant fields filled. */
function pt(expiry: string, t: number, tau: number, w0: number): TermPoint {
  return {
    expiry,
    t,
    tau,
    w0,
    atmVol: Math.sqrt(w0 / tau),
    varSwapVol: Math.sqrt(w0 / tau),
    maxIvErrorBp: 0,
  };
}

describe("forwardLadder", () => {
  it("reads the same level on both clocks with no active events", () => {
    const points = [pt("b", 0.2, 0.2, 0.008), pt("a", 0.1, 0.1, 0.004)];
    const ladder = forwardLadder(points);
    // Sorted by maturity, first interval from the origin.
    expect(ladder.map((i) => i.expiry)).toEqual(["a", "b"]);
    expect(ladder[0]).toMatchObject({ t0: 0, t1: 0.1, tau0: 0, tau1: 0.1 });
    for (const iv of ladder) {
      expect(iv.calendar).toBeCloseTo(0.04, 12);
      expect(iv.eventTime).toBeCloseTo(0.04, 12);
    }
    expect(clocksDiffer(points)).toBe(false);
  });

  it("keeps the calendar reading and pulls the event-time reading down on the event's interval", () => {
    // A 5x spike on (0.1, 0.2] with the event of exactly its excess: 0.1 y ×
    // (0.20 / 0.04 − 1) = 0.4 y of extra clock, so τ = t + 0.4 from then on.
    const points = [
      pt("a", 0.1, 0.1, 0.004),
      pt("b", 0.2, 0.6, 0.024),
      pt("c", 0.3, 0.7, 0.028),
    ];
    const ladder = forwardLadder(points);
    expect(ladder.map((i) => i.calendar)).toEqual([0.04, 0.2, 0.04].map((v) => expect.closeTo(v, 12)));
    expect(ladder.map((i) => i.eventTime)).toEqual([0.04, 0.04, 0.04].map((v) => expect.closeTo(v, 12)));
    expect(clocksDiffer(points)).toBe(true);
  });

  it("maps a degenerate interval to a zero level instead of dividing by zero", () => {
    const ladder = forwardLadder([pt("a", 0.1, 0.1, 0.004), pt("a2", 0.1, 0.1, 0.004)]);
    expect(ladder[1].calendar).toBe(0);
    expect(ladder[1].eventTime).toBe(0);
  });
});

describe("ladderSpreadBp", () => {
  it("is max − min in variance bp, and null below two intervals", () => {
    expect(ladderSpreadBp([0.04, 0.2, 0.04])).toBeCloseTo(1600, 9);
    expect(ladderSpreadBp([0.04, 0.04])).toBe(0);
    expect(ladderSpreadBp([0.04])).toBeNull();
    expect(ladderSpreadBp([])).toBeNull();
  });
});
