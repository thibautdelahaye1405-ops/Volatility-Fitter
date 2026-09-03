import { describe, expect, it } from "vitest";
import { cropPoints, cropRangeAt, cropRow, intersectRanges } from "./stackCrop";
import type { CropRanges } from "./stackCrop";

// A table as the backend emits it: levels from 1e-2 down to 1e-12, ranges
// widening as u shrinks (already widened to the quoted range [-0.2, 0.15]).
const TABLE: CropRanges = {
  u: [1e-2, 1e-3, 1e-4, 1e-5, 1e-6, 1e-7, 1e-8, 1e-9, 1e-10, 1e-11, 1e-12],
  lo: [-0.2, -0.25, -0.3, -0.35, -0.4, -0.45, -0.5, -0.55, -0.6, -0.65, -0.7],
  hi: [0.15, 0.18, 0.21, 0.24, 0.27, 0.3, 0.33, 0.36, 0.39, 0.42, 0.45],
};

describe("cropRangeAt", () => {
  it("returns the tabulated range at a tabulated level", () => {
    expect(cropRangeAt(TABLE, 1e-7)).toEqual([-0.45, 0.3]);
    expect(cropRangeAt(TABLE, 1e-2)).toEqual([-0.2, 0.15]);
    expect(cropRangeAt(TABLE, 1e-12)).toEqual([-0.7, 0.45]);
  });
  it("interpolates in log10(u) between levels", () => {
    const r = cropRangeAt(TABLE, 10 ** -7.5)!;
    expect(r[0]).toBeCloseTo(-0.475, 12);
    expect(r[1]).toBeCloseTo(0.315, 12);
  });
  it("clamps outside the table and rejects bad inputs", () => {
    expect(cropRangeAt(TABLE, 0.5)).toEqual([-0.2, 0.15]);
    expect(cropRangeAt(TABLE, 1e-15)).toEqual([-0.7, 0.45]);
    expect(cropRangeAt(null, 1e-7)).toBeNull();
    expect(cropRangeAt(TABLE, 0)).toBeNull();
    expect(cropRangeAt({ u: [], lo: [], hi: [] }, 1e-7)).toBeNull();
  });
});

describe("cropPoints / cropRow", () => {
  const pts = [-1, -0.5, -0.3, 0, 0.2, 0.5, 1].map((k) => ({ k, vol: 0.2 }));
  it("keeps only the points inside the range", () => {
    const kept = cropPoints(pts, (p) => p.k, [-0.45, 0.3]);
    expect(kept.map((p) => p.k)).toEqual([-0.3, 0, 0.2]);
  });
  it("never reduces a curve below two points, and a null range is a no-op", () => {
    expect(cropPoints(pts, (p) => p.k, [0.05, 0.1])).toBe(pts);
    expect(cropPoints(pts, (p) => p.k, null)).toBe(pts);
  });
  it("crops a shared-grid row into parallel arrays", () => {
    const k = [-1, -0.5, 0, 0.5, 1];
    const ys = [5, 4, 3, 2, 1];
    expect(cropRow(k, ys, [-0.6, 0.6])).toEqual({ k: [-0.5, 0, 0.5], ys: [4, 3, 2] });
    expect(cropRow(k, ys, null)).toEqual({ k, ys });
  });
});

describe("intersectRanges", () => {
  it("is the overlap of two ranges, null when disjoint or missing", () => {
    expect(intersectRanges([-0.5, 0.3], [-0.3, 0.6])).toEqual([-0.3, 0.3]);
    expect(intersectRanges([-0.5, -0.3], [0.1, 0.6])).toBeNull();
    expect(intersectRanges(null, [0.1, 0.6])).toBeNull();
  });
});
