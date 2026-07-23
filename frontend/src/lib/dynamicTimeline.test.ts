// P6 V3 locks: the client-side §5 A/B replay reproduces the SAME golden
// numbers as backend/tests/fixtures/graph_dynamic_golden.json (async_ab,
// async_ab_beta15, residual_half_life) — the timeline preview shows exactly
// what the production state layer computes.
import { describe, expect, it } from "vitest";
import { AB_FIXTURE, replayAB } from "./dynamicTimeline";

const run = (beta: number, halfLife: number | null) =>
  replayAB(AB_FIXTURE.snapshots, AB_FIXTURE.obsA, AB_FIXTURE.obsB, beta, halfLife);

describe("dynamicTimeline (golden async_ab)", () => {
  it("β=1 random walk: B rides A with the −3 dislocation remembered", () => {
    const points = run(1, null);
    expect(points.map((p) => p.b)).toEqual([
      10, 10, 11, 11, 12, 12, 13, 10, 11, 11, 12,
    ]);
    // u after B's t=3.5 print = −3 (hard update vs the causal source).
    const at35 = points.find((p) => p.t === 3.5);
    expect(at35?.u).toBe(-3);
    expect(at35?.bObserved).toBe(true);
    // Attribution at t=4.0: systematic 14, residual −3, mark 11.
    const at4 = points.find((p) => p.t === 4.0);
    expect(at4?.systematic).toBe(14);
    expect(at4?.u).toBe(-3);
    expect(at4?.b).toBe(11);
  });

  it("β=1.5: transfer slope scales the systematic AND the learned residual", () => {
    const points = run(1.5, null);
    expect(points.map((p) => p.b)).toEqual([
      10, 10, 11.5, 11.5, 13, 13, 14.5, 10, 11.5, 11.5, 13,
    ]);
    expect(points.find((p) => p.t === 0)?.u).toBe(-5);
    expect(points.find((p) => p.t === 3.5)?.u).toBe(-9.5);
  });

  it("half-life 1d: the dislocation decays by 2^(−Δ/H) (semigroup path)", () => {
    const points = run(1, 1);
    const at45 = points.find((p) => p.t === 4.5);
    expect(at45?.u).toBeCloseTo(-1.5, 10); // golden expected_u_at_4_5
    const at4 = points.find((p) => p.t === 4.0);
    expect(at4?.b).toBeCloseTo(11.878679656440357, 10); // golden b@4.0
  });
});
