// 3D surface camera math (UI SHELL v2 wave 3, B1/B2): project ∘ unproject on
// the floor plane, zoom-about-the-pointer invariance, clamping, snapping.
import { describe, expect, it } from "vitest";
import {
  DEFAULT_CAMERA, PITCH_RANGE, ZOOM_RANGE, clampCamera, fitViewport, isCameraMoved,
  nearestVertex, panBy, pitchBy, project, snapHysteresis, toPixel, unprojectFloor, zoomAt,
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
