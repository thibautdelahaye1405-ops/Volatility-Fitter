// lib/lvCompare: the Compare tab's pure helpers — sheet / difference builders
// on the compare lattice, score formatting, the repair summary, the chip
// vocabularies (v1 ships one tail target, the riders are listed disabled).
import { describe, expect, it } from "vitest";
import {
  LV_COMPARE_MODES, LV_TAIL_OPTIONS, LV_T_INTERP_OPTIONS,
  compareSmileFor, diffSheet, formatBp, formatSignedPts, maxAbs, repairDetail, repairSummary,
  repairTotals, scoreBp, sheetMesh,
} from "./lvCompare";
import { lvCompareFixture } from "./lvCompare.fixture";

describe("chip vocabularies", () => {
  it("offers smooth (first, the default) and buckets", () => {
    expect(LV_T_INTERP_OPTIONS.map((o) => o.id)).toEqual(["smooth", "buckets"]);
  });
  it("ships exactly one available tail target in v1 — the model's own wings — and lists the riders", () => {
    const available = LV_TAIL_OPTIONS.filter((o) => o.available).map((o) => o.id);
    expect(available).toEqual(["model"]);
    expect(LV_TAIL_OPTIONS.filter((o) => !o.available).map((o) => o.id)).toEqual(["matchLqd", "hull", "affine"]);
  });
  it("has the three display modes", () => {
    expect(LV_COMPARE_MODES.map((m) => m.id)).toEqual(["sheets", "diff", "smiles"]);
  });
});

describe("sheets on the compare lattice", () => {
  const c = lvCompareFixture();
  it("builds the twin and affine σ²_loc meshes (vol squared, rows = t vertices)", () => {
    const twin = sheetMesh(c, "twin")!;
    expect(twin.t).toEqual(c.tNodes);
    expect(twin.k).toEqual(c.xNodes);
    expect(twin.vol[0][0]).toBeCloseTo(0.22 * 0.22, 12);
    expect(sheetMesh(c, "affine")!.vol[2][3]).toBeCloseTo(0.21 * 0.21, 12);
  });
  it("returns null without the sheet or on a degenerate lattice", () => {
    expect(sheetMesh(null, "twin")).toBeNull();
    expect(sheetMesh(lvCompareFixture({ localVolAffine: [] }), "affine")).toBeNull();
    expect(sheetMesh(lvCompareFixture({ tNodes: [0.1], localVolTwin: [[0.2, 0.2, 0.2, 0.2]] }), "twin")).toBeNull();
  });
  it("the difference sheet exists only on the matching lattice", () => {
    expect(diffSheet(c)![0][0]).toBeCloseTo(0.02, 12);
    expect(diffSheet(lvCompareFixture({ affineLatticeMatches: false }))).toBeNull();
    expect(diffSheet(lvCompareFixture({ diffLocalVol: [] }))).toBeNull();
    expect(diffSheet(null)).toBeNull();
  });
  it("maxAbs is the ramp's half-span (0 for nothing)", () => {
    expect(maxAbs([[0.01, -0.03], [0.02, Number.NaN]])).toBeCloseTo(0.03, 12);
    expect(maxAbs([])).toBe(0);
  });
});

describe("formatting", () => {
  it("signed percentage points and whole bp, null-safe", () => {
    expect(formatSignedPts(0.0125)).toBe("+1.3 pt");
    expect(formatSignedPts(-0.004)).toBe("−0.4 pt");
    expect(formatSignedPts(0)).toBe("0.0 pt");
    expect(formatSignedPts(null)).toBe("—");
    expect(formatBp(24.4)).toBe("24");
    expect(formatBp(24.4, 1)).toBe("24.4");
    expect(formatBp(Number.NaN)).toBe("—");
    expect(formatBp(undefined)).toBe("—");
  });
  it("scoreBp reads the weighted rms in bp and passes the converged / max through", () => {
    expect(scoreBp({ rmsError: 0.0025, maxBp: 60, rmsBp: 25, convergedBp: 18 })).toEqual({ rms: 25, conv: 18, max: 60 });
    expect(scoreBp({ rmsError: 0.0005, maxBp: 12, convergedBp: null })).toEqual({ rms: 5, conv: null, max: 12 });
    expect(scoreBp(null)).toEqual({ rms: null, conv: null, max: null });
  });
});

describe("repairs", () => {
  const dirty = { butterfly: [0, 2, 0], calendar: [0, 0, 1], floored: [0, 0, 1], capped: [3, 0, 0], clean: false };
  it("totals and the one-line summary", () => {
    expect(repairTotals(dirty)).toEqual({ butterfly: 2, calendar: 1, floored: 1, capped: 3 });
    expect(repairSummary(dirty)).toBe("butterfly 2 · calendar 1 · floored 1 · capped 3");
    expect(repairSummary(lvCompareFixture().counters)).toBe("no repairs");
  });
  it("the per-row detail names only the rows that needed something", () => {
    const d = repairDetail(dirty, [0, 0.1, 0.5]);
    expect(d.split("\n")).toHaveLength(3);
    expect(d).toContain("t 0.100: butterfly 2");
    expect(repairDetail(lvCompareFixture().counters, [0, 0.1, 0.5])).toMatch(/cleanly/);
  });
});

describe("compareSmileFor", () => {
  it("picks the node's expiry, falls back to the first, null without smiles", () => {
    const c = lvCompareFixture();
    expect(compareSmileFor(c, "2026-12-10")!.expiry).toBe("2026-12-10");
    expect(compareSmileFor(c, "2099-01-01")!.expiry).toBe("2026-07-10");
    expect(compareSmileFor(c, null)!.expiry).toBe("2026-07-10");
    expect(compareSmileFor(lvCompareFixture({ smiles: [] }), null)).toBeNull();
    expect(compareSmileFor(null, null)).toBeNull();
  });
});
