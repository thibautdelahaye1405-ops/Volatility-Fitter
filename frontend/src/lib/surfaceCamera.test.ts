// 3D surface camera math (UI SHELL v2 wave 3, B1/B2): project ∘ unproject on
// the floor plane, zoom-about-the-pointer invariance, clamping, snapping.
import { describe, expect, it } from "vitest";
import {
  DEFAULT_CAMERA, PITCH_RANGE, ZOOM_RANGE, clampCamera, clampPan, fitViewport, isCameraMoved,
  nearestVertex, panBy, pitchBy, project, snapHysteresis, toPixel, unprojectFloor, zoomAbout, zoomAt,
} from "./surfaceCamera";
import type { Camera } from "./surfaceCamera";

const BOUNDS = { xMin: -1.5, xMax: 1.5, yMin: -1.2, yMax: 0.9 };
const cams: Camera[] = [
  DEFAULT_CAMERA,
  { yaw: 1.1, pitch: 0.9, zoom: 2.3, panX: 40, panY: -25 },
  { yaw: -2.4, pitch: PITCH_RANGE.min, zoom: 0.5, panX: -100, panY: 60 },
  { yaw: 3.0, pitch: PITCH_RANGE.max, zoom: 1, panX: 0, panY: 0 },
];

describe("project / unprojectFloor", () => {
  it("round-trips floor points through the pixel mapping for every camera", () => {
    for (const cam of cams) {
      const vp = fitViewport(BOUNDS, cam, 800, 500);
      for (const [x, y] of [[0, 0], [1, -1], [-0.3, 0.7], [0.95, 0.95]]) {
        const px = toPixel(vp, project(cam, { x, y, z: 0 }));
        const back = unprojectFloor(cam, vp, px.x, px.y)!;
        expect(back.x).toBeCloseTo(x, 9);
        expect(back.y).toBeCloseTo(y, 9);
      }
    }
  });

  it("lifts z straight up on screen (a raised point projects above its floor point)", () => {
    const p0 = project(DEFAULT_CAMERA, { x: 0.2, y: 0.3, z: 0 });
    const p1 = project(DEFAULT_CAMERA, { x: 0.2, y: 0.3, z: 0.5 });
    expect(p1.sx).toBeCloseTo(p0.sx, 12);
    expect(p1.sy).toBeLessThan(p0.sy);
  });
});

describe("zoomAt", () => {
  it("keeps the floor point under the pointer fixed and clamps the zoom", () => {
    for (const cam of cams) {
      const vp = fitViewport(BOUNDS, cam, 800, 500);
      const [px, py] = [523, 187];
      const before = unprojectFloor(cam, vp, px, py)!;
      const next = zoomAt(cam, vp, px, py, 1.4);
      const vp2 = fitViewport(BOUNDS, next, 800, 500);
      const after = unprojectFloor(next, vp2, px, py)!;
      expect(after.x).toBeCloseTo(before.x, 9);
      expect(after.y).toBeCloseTo(before.y, 9);
    }
    const vp = fitViewport(BOUNDS, DEFAULT_CAMERA, 800, 500);
    expect(zoomAt({ ...DEFAULT_CAMERA, zoom: ZOOM_RANGE.max }, vp, 1, 1, 2)).toEqual({ ...DEFAULT_CAMERA, zoom: ZOOM_RANGE.max });
  });
});

describe("clamping + moved flag", () => {
  it("clamps pitch / zoom and repairs non-finite values", () => {
    const c = clampCamera({ yaw: NaN, pitch: 5, zoom: 100, panX: Infinity, panY: 3 });
    expect(c).toEqual({ yaw: DEFAULT_CAMERA.yaw, pitch: PITCH_RANGE.max, zoom: ZOOM_RANGE.max, panX: 0, panY: 3 });
    expect(pitchBy(DEFAULT_CAMERA, -10).pitch).toBe(PITCH_RANGE.min);
  });

  it("flags any departure from the default", () => {
    expect(isCameraMoved(DEFAULT_CAMERA)).toBe(false);
    expect(isCameraMoved(panBy(DEFAULT_CAMERA, 1, 0))).toBe(true);
    expect(isCameraMoved({ ...DEFAULT_CAMERA, zoom: 1.5 })).toBe(true);
  });
});

describe("snapping", () => {
  const rows = [
    [{ x: -1, y: -1 }, { x: 0, y: -1 }, { x: 1, y: -1 }],
    [{ x: -1, y: 1 }, { x: 0, y: 1 }, { x: 1, y: 1 }],
  ];
  it("finds the nearest vertex", () => {
    expect(nearestVertex(rows, 0.9, 0.8)).toMatchObject({ i: 1, j: 2 });
    expect(nearestVertex(rows, -0.6, -0.9)).toMatchObject({ i: 0, j: 0 });
    expect(nearestVertex([], 0, 0)).toBeNull();
  });
  it("holds the previous hit near a boundary and switches once clearly closer", () => {
    const prev = nearestVertex(rows, -1, -1)!; // (0,0)
    // Just past the midpoint between (0,0) and (0,1): candidate (0,1) barely closer → hold.
    const near = nearestVertex(rows, -0.45, -1)!;
    expect(near).toMatchObject({ i: 0, j: 1 });
    expect(snapHysteresis(prev, near, rows, -0.45, -1)).toMatchObject({ i: 0, j: 0 });
    // Clearly closer → switch.
    const far = nearestVertex(rows, -0.1, -1)!;
    expect(snapHysteresis(prev, far, rows, -0.1, -1)).toMatchObject({ i: 0, j: 1 });
    expect(snapHysteresis(null, far, rows, -0.1, -1)).toMatchObject({ i: 0, j: 1 });
    expect(snapHysteresis(prev, null, rows, 0, 0)).toBeNull();
  });
});

describe("containment (2026-09-08)", () => {
  it("zoomAbout scales the zoom, keeps the pan and clamps to the range", () => {
    const cam: Camera = { yaw: 0.3, pitch: 0.7, zoom: 2, panX: 40, panY: -25 };
    const z = zoomAbout(cam, 1.5);
    expect(z.zoom).toBeCloseTo(3, 12);
    expect(z.panX).toBe(40);
    expect(z.panY).toBe(-25);
    expect(zoomAbout(cam, 100).zoom).toBe(ZOOM_RANGE.max);
    expect(zoomAbout(cam, 0.001).zoom).toBe(ZOOM_RANGE.min);
    // Zooming about the centre keeps the fitted centre pixel where it was.
    const vp0 = fitViewport(BOUNDS, cam, 800, 500);
    const vp1 = fitViewport(BOUNDS, z, 800, 500);
    const c = { sx: (BOUNDS.xMin + BOUNDS.xMax) / 2, sy: (BOUNDS.yMin + BOUNDS.yMax) / 2 };
    expect(toPixel(vp1, c).x).toBeCloseTo(toPixel(vp0, c).x, 9);
    expect(toPixel(vp1, c).y).toBeCloseTo(toPixel(vp0, c).y, 9);
  });

  it("clampPan keeps a quarter of the window covered by the sheet's box", () => {
    // A box of half-extents 300 × 200 px in an 800 × 500 window: the right
    // edge may retreat to x = 200 (a quarter of the width), the left edge
    // advance to x = 600.
    const wild: Camera = { ...DEFAULT_CAMERA, panX: 5000, panY: -4000 };
    const c = clampPan(wild, 800, 500, 300, 200);
    expect(c.panX).toBe(600 - 400 + 300); // left edge at (1 − ¼)·w
    expect(c.panY).toBe(125 - 250 - 200); // bottom edge at ¼·h
    const inside: Camera = { ...DEFAULT_CAMERA, panX: 120, panY: -60 };
    expect(clampPan(inside, 800, 500, 300, 200)).toEqual(inside);
    // Zoomed far in (a huge box) every corner stays reachable; zoomed out
    // (a tiny box) the sheet cannot leave the middle half.
    expect(clampPan(wild, 800, 500, 4000, 3000).panX).toBe(600 - 400 + 4000);
    expect(clampPan(wild, 800, 500, 10, 10).panX).toBe(210);
    expect(clampPan(wild, 800, 500, 10, 10).panY).toBe(-135);
  });
});
