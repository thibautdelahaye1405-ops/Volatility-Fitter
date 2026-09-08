// lib/surfaceMesh: the (k, T) crop of the 3D surfaces (2026-09-08) — the
// maturity window selects rows, the cropped rectangle fills the scene (so it
// sits centred), the row map survives for the crosshair, and the model's
// per-cell diagonal applies only to cells whose four vertices are grid
// neighbours after the crop.
import { describe, expect, it } from "vitest";
import { Z_HEIGHT, buildFacets, buildSceneMesh, snapWindow } from "./surfaceMesh";
import type { SurfaceMeshData } from "./surfaceMesh";

const DATA: SurfaceMeshData = {
  expiries: ["a", "b", "c", "d"],
  t: [0.1, 0.25, 0.5, 1.0],
  k: [-0.4, -0.2, 0, 0.2, 0.4],
  vol: [
    [0.30, 0.25, 0.20, 0.22, 0.26],
    [0.28, 0.24, 0.21, 0.22, 0.25],
    [0.27, 0.24, 0.22, 0.23, 0.25],
    [0.26, 0.24, 0.23, 0.23, 0.24],
  ],
};

describe("buildSceneMesh with a maturity window", () => {
  it("keeps every row without a window and maps rows to their data index", () => {
    const m = buildSceneMesh(DATA, -1, 1, "linear", "logmoneyness")!;
    expect(m.rowIdx).toEqual([0, 1, 2, 3]);
    expect(m.rows).toHaveLength(4);
    expect(m.rows[0][0].y).toBeCloseTo(-1, 12);
    expect(m.rows[3][0].y).toBeCloseTo(1, 12);
    expect([m.tMin, m.tMax]).toEqual([0.1, 1.0]);
  });

  it("crops rows to the window and re-fills the scene with the crop", () => {
    const m = buildSceneMesh(DATA, -1, 1, "linear", "logmoneyness", undefined, 0.2, 0.6)!;
    expect(m.rowIdx).toEqual([1, 2]);
    expect(m.rows).toHaveLength(2);
    // The cropped rectangle spans the full scene: centred whatever the crop.
    expect(m.rows[0][0].y).toBeCloseTo(-1, 12);
    expect(m.rows[1][0].y).toBeCloseTo(1, 12);
    expect([m.tMin, m.tMax]).toEqual([0.25, 0.5]);
    // z re-scales over the crop's own value range.
    const vals = m.rowIdx.flatMap((i) => DATA.vol[i]);
    expect(m.vMin).toBe(Math.min(...vals));
    expect(m.vMax).toBe(Math.max(...vals));
    const zs = m.rows.flatMap((r) => r.map((v) => v.z));
    expect(Math.min(...zs)).toBeCloseTo(0, 12);
    expect(Math.max(...zs)).toBeCloseTo(Z_HEIGHT, 12);
  });

  it("crops both axes at once and needs two rows and two columns", () => {
    const m = buildSceneMesh(DATA, -0.25, 0.25, "sqrt", "logmoneyness", undefined, 0.4, 1.1)!;
    expect(m.cols).toEqual([1, 2, 3]);
    expect(m.rowIdx).toEqual([2, 3]);
    expect(m.rows[0][0].x).toBeCloseTo(-1, 12);
    expect(m.rows[0][2].x).toBeCloseTo(1, 12);
    expect(buildSceneMesh(DATA, -1, 1, "linear", "logmoneyness", undefined, 0.9, 1.1)).toBeNull();
    expect(buildSceneMesh(DATA, 0.39, 0.41, "linear", "logmoneyness")).toBeNull();
  });
});

describe("buildFacets on a cropped mesh", () => {
  const pts = (m: NonNullable<ReturnType<typeof buildSceneMesh>>) =>
    m.rows.map((r, i) => r.map((v, j) => ({ x: 10 * j, y: 10 * i + v.z, depth: i + j })));

  /** The "other" split's first triangle (p00, p01, p10) of the cell at
   *  column 0 between mesh rows 0 and 1: x = 0, 10, 0 and y ≈ 0, 0, 10. */
  const OTHER_SPLIT = /^M0\.0,0\.\dL10\.0,0\.\dL0\.0,10\.\dZ$/;

  it("uses the model's diagonal for grid-adjacent cells, indexed by the DATA row after a crop", () => {
    // Every cell wants the OTHER diagonal in the model.
    const diag = [0, 1, 2].map(() => [false, false, false, false]);
    const full = buildSceneMesh(DATA, -1, 1, "linear", "logmoneyness")!;
    const f = buildFacets(full, pts(full), true, diag);
    expect(f).toHaveLength(2 * 3 * 4); // two triangles per cell
    expect(f.some((x) => OTHER_SPLIT.test(x.d))).toBe(true);
    // A maturity crop keeps rows adjacent: the cell between data rows 1 and 2
    // reads diag[1] (the other split again), through the row map.
    const crop = buildSceneMesh(DATA, -1, 1, "linear", "logmoneyness", undefined, 0.2, 0.6)!;
    const fc = buildFacets(crop, pts(crop), true, diag);
    expect(fc).toHaveLength(2 * 1 * 4);
    expect(fc.some((x) => OTHER_SPLIT.test(x.d))).toBe(true);
    // With the model asking for the MAIN diagonal there, the pattern is gone.
    const mainDiag = [0, 1, 2].map(() => [true, true, true, true]);
    expect(buildFacets(crop, pts(crop), true, mainDiag).some((x) => OTHER_SPLIT.test(x.d))).toBe(false);
  });

  it("falls back to the main diagonal when the strike stride makes columns non-adjacent", () => {
    const n = 120; // > MAX_COLS: rendered columns are strided, hence non-adjacent
    const wide: SurfaceMeshData = {
      expiries: ["a", "b"], t: [0.5, 1.0],
      k: Array.from({ length: n }, (_, j) => -1 + (2 * j) / (n - 1)),
      vol: [Array.from({ length: n }, () => 0.2), Array.from({ length: n }, () => 0.25)],
    };
    const diag = [Array.from({ length: n - 1 }, () => false)];
    const m = buildSceneMesh(wide, -1, 1, "linear", "logmoneyness")!;
    expect(m.cols[1] - m.cols[0]).toBeGreaterThan(1);
    const fw = buildFacets(m, pts(m), true, diag);
    expect(fw.some((x) => OTHER_SPLIT.test(x.d))).toBe(false); // the model's split is not trusted across a gap
  });
});

describe("snapWindow", () => {
  const t = [0.08, 0.25, 0.5, 1.0];
  it("leaves a window holding two values alone", () => {
    expect(snapWindow(t, 0.2, 0.6)).toEqual([0.2, 0.6]);
    expect(snapWindow(t, 0, 2)).toEqual([0, 2]);
  });
  it("widens a window past the last row to the two nearest values", () => {
    expect(snapWindow(t, 0.54, 1.0)).toEqual([0.5, 1.0]); // the first live drag on a 4-expiry ladder
    expect(snapWindow(t, 0.08, 0.1)).toEqual([0.08, 0.25]);
    expect(snapWindow(t, 0.3, 0.4)).toEqual([0.25, 0.5]);
  });
  it("passes a one-value grid through", () => {
    expect(snapWindow([1], 0, 2)).toEqual([0, 2]);
  });
});
