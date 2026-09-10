// Locks the Surface stage's helpers (SERIES ARC S5): a lane's grid as mesh
// data (rows ascending in τ, forwards / ATM vols by row, the fill rule),
// the signed difference on the common grid, the value range and the
// signed-bp formatting.
import { describe, expect, it } from "vitest";
import {
  commonColumns,
  differenceMeshData,
  fillRow,
  formatSignedVolBp,
  laneMeshData,
  laneSheets,
  surfaceValueRange,
} from "./seriesSurface";
import type { FramePayload, LaneFrameDoc, LaneSpec, SliceCurveDoc, SurfaceGridDoc } from "./seriesTypes";

const K = [-0.2, -0.1, 0, 0.1];
const grid = (expiries: string[], tau: number[], sigma: number[][], k: number[] = K): SurfaceGridDoc =>
  ({ k, tau, expiries, sigma });
const slice = (expiry: string, t: number, atmVol: number, forward = 100): SliceCurveDoc =>
  ({ expiry, t, forward, k: [0], iv: [atmVol], atmVol, skew: null, curvature: null, metrics: {} });
const laneDoc = (laneId: string, surface: SurfaceGridDoc | null, slices: SliceCurveDoc[] = []): LaneFrameDoc =>
  ({ laneId, slices, surface, term: [], metrics: {}, status: "done" });
const spec = (id: string, patch: Partial<LaneSpec> = {}): LaneSpec => ({
  id, name: id.toUpperCase(), family: "lqd", colour: null, fitMode: null,
  patchFit: {}, patchOptions: {}, production: false, seed: "cold", ...patch,
});

const frame: FramePayload = {
  seriesId: "s", idx: 0, ts: "2026-09-08T15:45:00", quoteKind: "quotes", spot: 100,
  expiries: ["2026-09-18", "2026-10-16", "2026-12-18"],
  forwards: { "2026-09-18": 100.1, "2026-10-16": 100.5, "2026-12-18": 101 },
  market: {},
  lanes: {
    // Rows out of τ order on purpose, one non-finite cell.
    a: laneDoc(
      "a",
      grid(["2026-10-16", "2026-09-18", "2026-12-18"], [0.1, 0.03, 0.28], [
        [0.24, 0.22, 0.2, 0.21],
        [0.3, 0.25, NaN, 0.23],
        [0.22, 0.21, 0.2, 0.2],
      ]),
      [slice("2026-09-18", 0.03, 0.25), slice("2026-10-16", 0.1, 0.2), slice("2026-12-18", 0.28, 0.2)],
    ),
    // A row the frame has no forward for, no slices.
    b: laneDoc("b", grid(["2026-09-18", "2026-10-16", "2027-01-15"], [0.03, 0.1, 0.35], [
      [0.31, 0.26, 0.21, 0.24],
      [0.25, 0.23, 0.2, 0.22],
      [0.2, 0.2, 0.2, 0.2],
    ])),
    c: laneDoc("c", null),
  },
};

describe("fillRow", () => {
  it("fills gaps from the left, a leading gap from the right; all-NaN is null", () => {
    expect(fillRow([NaN, 1, NaN, 2])).toEqual([1, 1, 1, 2]);
    expect(fillRow([NaN, NaN])).toBeNull();
  });
});

describe("laneMeshData", () => {
  it("rows ascending in τ, t = τ, forwards from the frame, ATM vols from the slices", () => {
    const m = laneMeshData(frame, "a")!;
    expect(m.expiries).toEqual(["2026-09-18", "2026-10-16", "2026-12-18"]);
    expect(m.t).toEqual([0.03, 0.1, 0.28]);
    expect(m.k).toEqual(K);
    expect(m.vol[0]).toEqual([0.3, 0.25, 0.25, 0.23]); // the NaN filled from its left neighbour
    expect(m.vol[1]).toEqual([0.24, 0.22, 0.2, 0.21]);
    expect(m.forward).toEqual([100.1, 100.5, 101]);
    expect(m.atmVol).toEqual([0.25, 0.2, 0.2]);
  });
  it("omits forward / atmVol unless every row has one", () => {
    const m = laneMeshData(frame, "b")!;
    expect(m.forward).toBeUndefined();
    expect(m.atmVol).toBeUndefined();
    expect(m.t).toEqual([0.03, 0.1, 0.35]);
  });
  it("null without a surface, for an unknown lane, or with fewer than two usable rows", () => {
    expect(laneMeshData(frame, "c")).toBeNull();
    expect(laneMeshData(frame, "zzz")).toBeNull();
    const thin: FramePayload = {
      ...frame,
      lanes: { d: laneDoc("d", grid(["x", "y", "z"], [0.1, NaN, 0.3], [[0.2, 0.2, 0.2, 0.2], [0.2, 0.2, 0.2, 0.2], [0.2, 0.2]])) },
    };
    expect(laneMeshData(thin, "d")).toBeNull(); // y: non-finite τ · z: wrong length → one row left
  });
});

describe("commonColumns / differenceMeshData", () => {
  it("one grid → the identity; a subset → the common strikes; disjoint → none", () => {
    expect(commonColumns(K, [...K])).toEqual(K.map((_, j) => ({ ja: j, jb: j })));
    expect(commonColumns(K, [-0.1, 0, 0.3])).toEqual([{ ja: 1, jb: 0 }, { ja: 2, jb: 1 }]);
    expect(commonColumns(K, [0.5, 0.6])).toEqual([]);
  });
  it("a − b over the common expiries, signed, τ / forward / ATM from a", () => {
    const a = laneMeshData(frame, "a")!;
    const b = laneMeshData(frame, "b")!;
    const d = differenceMeshData(a, b)!;
    expect(d.expiries).toEqual(["2026-09-18", "2026-10-16"]);
    expect(d.t).toEqual([0.03, 0.1]);
    expect(d.k).toEqual(K);
    [-0.01, -0.01, 0.04, -0.01].forEach((v, j) => expect(d.vol[0][j]).toBeCloseTo(v, 12));
    [-0.01, -0.01, 0, -0.01].forEach((v, j) => expect(d.vol[1][j]).toBeCloseTo(v, 12));
    expect(d.forward).toEqual([100.1, 100.5]);
    expect(d.atmVol).toEqual([0.25, 0.2]);
  });
  it("clips to the common strike columns; null below two rows or two columns", () => {
    const a = laneMeshData(frame, "a")!;
    const narrow = { ...laneMeshData(frame, "b")!, k: [-0.1, 0, 0.3] };
    narrow.vol = narrow.vol.map((row) => row.slice(0, 3));
    const d = differenceMeshData(a, narrow)!;
    expect(d.k).toEqual([-0.1, 0]);
    expect(d.vol[0].length).toBe(2);
    expect(differenceMeshData(a, { ...narrow, k: [-0.1, 0.3, 0.4] })).toBeNull();
    expect(differenceMeshData(a, { ...narrow, expiries: ["2026-09-18", "x", "y"] })).toBeNull();
  });
});

describe("surfaceValueRange / formatSignedVolBp", () => {
  it("range over the finite values, with the larger magnitude", () => {
    expect(surfaceValueRange({ expiries: [], t: [], k: [], vol: [[-0.02, NaN], [0.01, 0.005]] }))
      .toEqual({ min: -0.02, max: 0.01, absMax: 0.02 });
    expect(surfaceValueRange({ expiries: [], t: [], k: [], vol: [[NaN]] })).toBeNull();
  });
  it("signed vol bp with a true minus sign; no sign at zero; — when absent", () => {
    expect(formatSignedVolBp(0.0012)).toBe("+12 bp");
    expect(formatSignedVolBp(-0.0003)).toBe("−3 bp");
    expect(formatSignedVolBp(0)).toBe("0 bp");
    expect(formatSignedVolBp(-0.00004)).toBe("0 bp");
    expect(formatSignedVolBp(0.00125, 1)).toBe("+12.5 bp");
    expect(formatSignedVolBp(null)).toBe("—");
    expect(formatSignedVolBp(NaN)).toBe("—");
  });
});

describe("laneSheets", () => {
  it("the visible lanes with a surface, in lane order, with their ordinals", () => {
    const lanes = [spec("a", { production: true }), spec("b"), spec("c")];
    const sheets = laneSheets(frame, lanes, new Set());
    expect(sheets.map((s) => [s.lane.id, s.ordinal])).toEqual([["a", 0], ["b", 1]]);
    expect(laneSheets(frame, lanes, new Set(["a"])).map((s) => s.lane.id)).toEqual(["b"]);
  });
});
