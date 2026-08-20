// V3.3 item 10: the Stacked-Variance evidence helpers — Δ-mode series algebra
// and the calendar-cross marker mapping (quality row → adjacent pair → circle).
import { describe, expect, it } from "vitest";
import {
  CAL_TOL,
  calendarMarkers,
  deltaRows,
  interpOnGrid,
  lvCalendarMarker,
} from "./stackedVariance";
import type { VarianceGrid } from "./stackedVariance";

/** Three expiries on a shared 3-point k grid; the far pair crosses at k=0. */
const GRID: VarianceGrid = {
  expiries: ["2026-07-10", "2026-08-10", "2026-09-10"],
  k: [-0.2, 0.0, 0.2],
  w: [
    [0.010, 0.008, 0.011],
    [0.020, 0.016, 0.022],
    [0.030, 0.024, 0.033],
  ],
};

describe("deltaRows", () => {
  it("builds adjacent-pair differences on the shared grid", () => {
    const rows = deltaRows(GRID);
    expect(rows.length).toBe(2);
    expect(rows[0].label).toBe("2026-07-10→2026-08-10");
    expect(rows[0].ys).toEqual([0.010, 0.008, 0.011]);
    expect(rows[1].ys.map((v) => Number(v.toFixed(6)))).toEqual([0.010, 0.008, 0.011]);
  });

  it("is empty for a single expiry", () => {
    expect(deltaRows({ expiries: ["e"], k: [0], w: [[0.01]] })).toEqual([]);
  });
});

describe("interpOnGrid", () => {
  it("interpolates linearly and clamps at the edges", () => {
    expect(interpOnGrid([-0.2, 0.0, 0.2], [1, 2, 4], 0.1)).toBeCloseTo(3, 12);
    expect(interpOnGrid([-0.2, 0.0, 0.2], [1, 2, 4], -1)).toBe(1);
    expect(interpOnGrid([-0.2, 0.0, 0.2], [1, 2, 4], 1)).toBe(4);
    expect(interpOnGrid([], [], 0)).toBeNull();
  });
});

describe("calendarMarkers", () => {
  const flagged = {
    expiry: "2026-09-10",
    ledgerGapMin: -0.0025, // 25bp crossing — far below the certificate tol
    ledgerGapK: 0.1,
  };

  it("maps a refuted far-expiry row onto its pair's midpoint (levels)", () => {
    const [m, ...rest] = calendarMarkers([flagged], GRID, "levels");
    expect(rest).toEqual([]);
    expect(m.farIndex).toBe(2);
    expect(m.k).toBe(0.1);
    // w_near(0.1) = 0.019, w_far(0.1) = 0.0285 -> midpoint 0.02375
    expect(m.y).toBeCloseTo(0.5 * (0.019 + 0.0285), 12);
    expect(m.label).toContain("ΔG min -25.0bp");
    expect(m.label).toContain("2026-08-10→2026-09-10");
  });

  it("Δ mode places the circle on the pair's gap", () => {
    const [m] = calendarMarkers([flagged], GRID, "delta");
    expect(m.y).toBeCloseTo(0.0285 - 0.019, 12);
  });

  it("certified rows / sub-tolerance gaps / first expiry yield nothing", () => {
    // gap within the certificate tolerance: NOT flagged (never invent one).
    expect(
      calendarMarkers([{ ...flagged, ledgerGapMin: -CAL_TOL / 2 }], GRID, "levels"),
    ).toEqual([]);
    // positive gap (certified) and null fields (first expiry): nothing.
    expect(calendarMarkers([{ ...flagged, ledgerGapMin: 0.001 }], GRID, "levels")).toEqual([]);
    expect(
      calendarMarkers([{ expiry: "2026-09-10", ledgerGapMin: null, ledgerGapK: null }], GRID, "levels"),
    ).toEqual([]);
    // the ladder's FIRST expiry has no pair to circle.
    expect(
      calendarMarkers([{ ...flagged, expiry: "2026-07-10" }], GRID, "levels"),
    ).toEqual([]);
    // unknown expiry (stale report vs fresh surface): skipped, never thrown.
    expect(
      calendarMarkers([{ ...flagged, expiry: "2099-01-01" }], GRID, "levels"),
    ).toEqual([]);
  });
});

describe("lvCalendarMarker", () => {
  const smiles = [
    {
      expiry: "2026-07-10",
      t: 0.1,
      tau: 0.1,
      model: [
        { k: -0.2, vol: 0.2 },
        { k: 0.2, vol: 0.2 },
      ],
    },
    {
      expiry: "2026-08-10",
      t: 0.2,
      tau: 0.2,
      model: [
        { k: -0.2, vol: 0.25 },
        { k: 0.2, vol: 0.25 },
      ],
      // modelExt preferred when present (the untruncated curve).
      modelExt: [
        { k: -1.4, vol: 0.3 },
        { k: 1.0, vol: 0.3 },
      ],
    },
  ];

  it("places the circle at the pair's total-variance midpoint", () => {
    const m = lvCalendarMarker(smiles, 0, 0.0);
    expect(m).not.toBeNull();
    // near w = 0.2² · 0.1 = 0.004; far uses modelExt: 0.3² · 0.2 = 0.018
    expect(m!.k).toBe(0.0);
    expect(m!.y).toBeCloseTo(0.5 * (0.004 + 0.018), 12);
    expect(m!.label).toContain("2026-07-10→2026-08-10");
    expect(m!.label).toContain("at k 0.00");
  });

  it("returns null when clean or out of range", () => {
    expect(lvCalendarMarker(smiles, null, null)).toBeNull();
    expect(lvCalendarMarker(smiles, undefined, 0.1)).toBeNull();
    expect(lvCalendarMarker(smiles, 1, 0.0)).toBeNull(); // no smiles[2]
  });
});
