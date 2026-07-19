// The preview math must reproduce the backend's golden fixture numbers
// (backend/tests/fixtures/graph_message_golden.json) EXACTLY — the Phase-5
// exit gate: configure the canonical cases, see their expected mean and
// conditional precision before saving.
import { describe, expect, it } from "vitest";
import {
  calendarBeta,
  calendarPrecision,
  receiverPreview,
  reverseBeta,
  reversePrecision,
} from "./messagePreview";

describe("receiverPreview — golden §21 contracts", () => {
  it("§21.1 full calendar transmission: β2 at ρ=1 transfers exactly", () => {
    const r = receiverPreview([{ beta: 2, precision: 4, z: 1, rho: 1 }]);
    expect(r.mean).toBeCloseTo(2.0, 12);
    expect(r.q).toBe(4);
    expect(r.kappa).toBe(0);
  });

  it("§21.2 equal competing signals cancel; precisions ADD (q = 2p)", () => {
    const r = receiverPreview([
      { beta: 1, precision: 4, z: -1, rho: 1 },
      { beta: 1, precision: 4, z: 1, rho: 1 },
    ]);
    expect(r.mean).toBeCloseTo(0, 12);
    expect(r.q).toBe(8);
    expect(r.conditionalSd).toBeCloseTo(1 / Math.sqrt(8), 12);
  });

  it("§21.3 unequal precision: precision-weighted average, q = 4p", () => {
    const r = receiverPreview([
      { beta: 1, precision: 12, z: -1, rho: 1 },
      { beta: 1, precision: 4, z: 1, rho: 1 },
    ]);
    expect(r.mean).toBeCloseTo(-0.5, 12);
    expect(r.q).toBe(16);
  });

  it("§10.3 beta-adjusted competition: (0.5·(−1) + 2·(+1)) / 2 = +0.75", () => {
    const r = receiverPreview([
      { beta: 0.5, precision: 4, z: -1, rho: 1 },
      { beta: 2, precision: 4, z: 1, rho: 1 },
    ]);
    expect(r.mean).toBeCloseTo(0.75, 12);
  });

  it("§21.12 shrunk single source: transfer is EXACTLY ρβz", () => {
    const r = receiverPreview([{ beta: 2, precision: 4, z: 1, rho: 0.34 }]);
    expect(r.mean).toBeCloseTo(0.68, 12);
    expect(r.kappa).toBeCloseTo(4 * (1 - 0.34) / 0.34, 12);
  });

  it("corroboration: fixed κ lifts two agreeing sources to 2ρ/(1+ρ)", () => {
    const r = receiverPreview([
      { beta: 2, precision: 4, z: 1, rho: 0.34 },
      { beta: 2, precision: 4, z: 1, rho: 0.34 },
    ]);
    expect(r.mean).toBeCloseTo(1.0149253731343284, 12); // golden fixture value
  });

  it("no live messages → zero mean, infinite conditional sd", () => {
    const r = receiverPreview([]);
    expect(r.mean).toBe(0);
    expect(r.conditionalSd).toBe(Infinity);
  });
});

describe("relation identities and rules", () => {
  it("§8.2 calendar shape: T=(0.25, 0.5, 1.0) gives β 2 and 0.5", () => {
    expect(calendarBeta(0.25, 0.5, 1)).toBeCloseTo(2, 12);
    expect(calendarBeta(1.0, 0.5, 1)).toBeCloseTo(0.5, 12);
    expect(calendarBeta(0.25, 0.5, 0.5)).toBeCloseTo(Math.SQRT2, 12);
  });

  it("§7.6/§8.3 reverse identities: 1/β and p·β²", () => {
    expect(reverseBeta(2) * 2).toBeCloseTo(1, 12);
    expect(reversePrecision(4, 2)).toBe(16);
  });

  it("§9.2 precision families: inverse-sqrt-gap default + constant", () => {
    expect(calendarPrecision(0.25, 0.5, 1700, 0.97, "inverse_sqrt_gap")).toBeCloseTo(
      1700 / (0.97 + Math.sqrt(0.25)),
      9,
    );
    expect(calendarPrecision(0.25, 0.5, 1700, 0.97, "constant")).toBe(1700);
    const near = calendarPrecision(0.4, 0.5, 1700, 0.97, "log_distance");
    const far = calendarPrecision(0.1, 0.5, 1700, 0.97, "log_distance");
    expect(near).toBeGreaterThan(far);
  });
});
