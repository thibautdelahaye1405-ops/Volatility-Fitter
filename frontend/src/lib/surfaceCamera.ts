// Orthographic camera of the 3D surface charts (UI SHELL v2 wave 3, B1/B2) —
// pure math, vitest-locked in surfaceCamera.test.ts.
//
// Scene: x (strike axis) and y (maturity axis) span [-1, 1] on the floor,
// z (value) rises to Z_HEIGHT. The camera yaws around z, pitches (elevation
// above the floor, clamped 10–80°), zooms and pans in screen space.
//   project     scene → normalized screen (sx, sy) + paint depth
//   fitViewport bounds + zoom/pan → the pixel mapping (scale, origin)
//   unprojectFloor pixel → the floor point (z = 0) under the pointer — the
//               crosshair's inverse projection
//   zoomAt      zoom about the pointer (the floor point under it stays put)
//   nearestVertex / snapHysteresis  crosshair snapping to the mesh grid

export interface Camera {
  /** Yaw around the vertical axis, radians. */
  yaw: number;
  /** Elevation above the floor, radians (PITCH_RANGE). */
  pitch: number;
  /** Scene zoom factor (ZOOM_RANGE). */
  zoom: number;
  /** Screen-space pan, pixels. */
  panX: number;
  panY: number;
}

export const PITCH_RANGE = { min: (10 * Math.PI) / 180, max: (80 * Math.PI) / 180 } as const;
export const ZOOM_RANGE = { min: 0.3, max: 8 } as const;

export const DEFAULT_CAMERA: Camera = {
  yaw: -0.55,
  pitch: (30 * Math.PI) / 180,
  zoom: 1,
  panX: 0,
  panY: 0,
};

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export function clampCamera(c: Camera): Camera {
  return {
    yaw: Number.isFinite(c.yaw) ? c.yaw : DEFAULT_CAMERA.yaw,
    pitch: clamp(Number.isFinite(c.pitch) ? c.pitch : DEFAULT_CAMERA.pitch, PITCH_RANGE.min, PITCH_RANGE.max),
    zoom: clamp(Number.isFinite(c.zoom) ? c.zoom : 1, ZOOM_RANGE.min, ZOOM_RANGE.max),
    panX: Number.isFinite(c.panX) ? c.panX : 0,
    panY: Number.isFinite(c.panY) ? c.panY : 0,
  };
}

/** True when any knob left its default (the ⌂ reset chip shows). */
export function isCameraMoved(c: Camera, eps = 1e-9): boolean {
  return (
    Math.abs(c.yaw - DEFAULT_CAMERA.yaw) > eps ||
    Math.abs(c.pitch - DEFAULT_CAMERA.pitch) > eps ||
    Math.abs(c.zoom - 1) > eps ||
    Math.abs(c.panX) > eps ||
    Math.abs(c.panY) > eps
  );
}

export interface ScenePoint { x: number; y: number; z: number }
export interface Projected { sx: number; sy: number; depth: number }

/** Scene → normalized screen coordinates (pre-scale) + painter depth. */
export function project(cam: Camera, p: ScenePoint): Projected {
  const ca = Math.cos(cam.yaw);
  const sa = Math.sin(cam.yaw);
  const sinE = Math.sin(cam.pitch);
  const cosE = Math.cos(cam.pitch);
  const x1 = p.x * ca - p.y * sa;
  const y1 = p.x * sa + p.y * ca;
  return { sx: x1, sy: -(y1 * sinE + p.z * cosE), depth: y1 * cosE - p.z * sinE };
}

export interface Bounds { xMin: number; xMax: number; yMin: number; yMax: number }

export interface Viewport {
  scale: number;
  ox: number;
  oy: number;
  w: number;
  h: number;
}

/** Pixel mapping that fits `bounds` (projected units) into w × h at the
 *  camera's zoom, then applies its pan. */
export function fitViewport(bounds: Bounds, cam: Camera, w: number, h: number): Viewport {
  const s0 = 0.88 * Math.min(w / (bounds.xMax - bounds.xMin || 1), h / (bounds.yMax - bounds.yMin || 1));
  const scale = s0 * cam.zoom;
  return {
    scale,
    ox: w / 2 - (scale * (bounds.xMin + bounds.xMax)) / 2 + cam.panX,
    oy: h / 2 - (scale * (bounds.yMin + bounds.yMax)) / 2 + cam.panY,
    w,
    h,
  };
}

export function toPixel(vp: Viewport, p: { sx: number; sy: number }): { x: number; y: number } {
  return { x: vp.ox + p.sx * vp.scale, y: vp.oy + p.sy * vp.scale };
}

/** Pixel → the floor point (z = 0) under it, or null when the view is edge-on. */
export function unprojectFloor(cam: Camera, vp: Viewport, px: number, py: number): { x: number; y: number } | null {
  const sinE = Math.sin(cam.pitch);
  if (Math.abs(sinE) < 1e-6 || vp.scale <= 0) return null;
  const sx = (px - vp.ox) / vp.scale;
  const sy = (py - vp.oy) / vp.scale;
  const x1 = sx;
  const y1 = -sy / sinE;
  const ca = Math.cos(cam.yaw);
  const sa = Math.sin(cam.yaw);
  return { x: x1 * ca + y1 * sa, y: -x1 * sa + y1 * ca };
}

/** Zoom by `factor` about the pixel (px, py): the floor point under the
 *  pointer stays under the pointer. `vp` is the CURRENT viewport. */
export function zoomAt(cam: Camera, vp: Viewport, px: number, py: number, factor: number): Camera {
  const zoom = clamp(cam.zoom * factor, ZOOM_RANGE.min, ZOOM_RANGE.max);
  if (zoom === cam.zoom || vp.scale <= 0) return cam;
  const scale2 = (vp.scale * zoom) / cam.zoom;
  // Normalized screen point under the pointer, and the bounds centre the
  // fit anchors on (recovered from the current origin).
  const sx = (px - vp.ox) / vp.scale;
  const sy = (py - vp.oy) / vp.scale;
  const cx = (vp.w / 2 + cam.panX - vp.ox) / vp.scale;
  const cy = (vp.h / 2 + cam.panY - vp.oy) / vp.scale;
  return {
    ...cam,
    zoom,
    panX: cam.panX + (vp.scale - scale2) * (sx - cx),
    panY: cam.panY + (vp.scale - scale2) * (sy - cy),
  };
}

export function panBy(cam: Camera, dx: number, dy: number): Camera {
  return { ...cam, panX: cam.panX + dx, panY: cam.panY + dy };
}

export function yawBy(cam: Camera, d: number): Camera {
  return { ...cam, yaw: cam.yaw + d };
}

export function pitchBy(cam: Camera, d: number): Camera {
  return { ...cam, pitch: clamp(cam.pitch + d, PITCH_RANGE.min, PITCH_RANGE.max) };
}

// ---- crosshair snapping ----------------------------------------------------
export interface GridHit { i: number; j: number; d2: number }

/** Nearest grid vertex (by floor distance) to the floor point (x, y);
 *  `rows[i][j]` are the vertices' floor coordinates. Null on an empty grid. */
export function nearestVertex(rows: { x: number; y: number }[][], x: number, y: number): GridHit | null {
  let best: GridHit | null = null;
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    for (let j = 0; j < row.length; j++) {
      const dx = row[j].x - x;
      const dy = row[j].y - y;
      const d2 = dx * dx + dy * dy;
      if (best === null || d2 < best.d2) best = { i, j, d2 };
    }
  }
  return best;
}

/** Keep the previous hit unless the candidate is closer by a margin — stops
 *  the badge flickering on a cell boundary. `margin` is a fraction of the
 *  candidate's distance (0.35 ⇒ switch only when ≥ 35 % closer). */
export function snapHysteresis(
  prev: GridHit | null,
  cand: GridHit | null,
  rows: { x: number; y: number }[][],
  x: number,
  y: number,
  margin = 0.35,
): GridHit | null {
  if (cand === null) return null;
  if (prev === null || !rows[prev.i]?.[prev.j]) return cand;
  if (prev.i === cand.i && prev.j === cand.j) return cand;
  const p = rows[prev.i][prev.j];
  const dPrev = Math.hypot(p.x - x, p.y - y);
  const dCand = Math.sqrt(cand.d2);
  return dCand < dPrev * (1 - margin) ? cand : { ...prev, d2: dPrev * dPrev };
}
