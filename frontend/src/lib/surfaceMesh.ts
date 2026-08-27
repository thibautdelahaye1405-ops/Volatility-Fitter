// Scene geometry of the 3D surface charts — pure helpers behind
// components/SurfaceMesh.tsx (extracted for the file-size policy, wave 3 B).
//
//   buildSceneMesh  (k, T, value) grid + brush window + axis mode → vertices
//                   in scene coordinates (x, y ∈ [-1, 1], z ∈ [0, Z_HEIGHT])
//                   with the colour range and the display-x of every vertex
//   buildFacets     projected vertices → painter-sorted SVG facets (one quad
//                   per cell, or the model's two triangles when triangulated)
import { axisTransform, makeVolAt } from "./axisModes";
import type { AxisMode } from "./axisModes";
import { timeAxisValue } from "./timeAxis";
import type { TimeAxisMode } from "./timeAxis";
import { volColor } from "./volColormap";

/** Mesh data: one vol row per expiry over a shared grid k. `forward` /
 *  `atmVol` (per expiry) are optional context the strike / %ATM / Δ /
 *  normalized x-axis modes need; absent ⇒ only the log-moneyness axis. */
export interface SurfaceMeshData {
  expiries: string[];
  t: number[];
  k: number[];
  vol: number[][];
  forward?: number[];
  atmVol?: number[];
}

/** Height of the value axis in scene units (x, y span [-1, 1]). */
export const Z_HEIGHT = 0.85;
/** Cap on rendered mesh columns: dense k grids are strided down to this. */
export const MAX_COLS = 48;

export interface SceneVertex { x: number; y: number; z: number; vol: number }

export interface SceneMesh {
  rows: SceneVertex[][];
  /** Original k column index of each rendered column. */
  cols: number[];
  /** Display-x (axis-mode units) of every rendered vertex. */
  displayX: number[][];
  vMin: number;
  vMax: number;
  xMin: number;
  xMax: number;
  tMin: number;
  tMax: number;
}

/**
 * Normalize the grid into scene coordinates: x = the display coordinate (the
 * chosen axis mode) within the brushed window in [-1, 1], y = T or √T in
 * [-1, 1], z = value in [0, Z_HEIGHT]. The window selects COLUMNS in the
 * grid's own k; each expiry's display-x is its own monotone transform of k
 * (forward / ATM vol differ per expiry), so e.g. strike shears the sheet.
 */
export function buildSceneMesh(
  data: SurfaceMeshData,
  kLo: number,
  kHi: number,
  timeMode: TimeAxisMode,
  axisMode: AxisMode,
  rowXTransform?: (x: number, row: number) => number,
): SceneMesh | null {
  const { k, t, vol, forward, atmVol } = data;
  if (k.length < 2 || t.length < 2 || vol.length !== t.length) return null;
  const inWin: number[] = [];
  for (let j = 0; j < k.length; j++) if (k[j] >= kLo && k[j] <= kHi) inWin.push(j);
  if (inWin.length < 2) return null;
  const stride = Math.max(1, Math.ceil(inWin.length / MAX_COLS));
  const cols: number[] = [];
  for (let c = 0; c < inWin.length; c += stride) cols.push(inWin[c]);
  if (cols[cols.length - 1] !== inWin[inWin.length - 1]) cols.push(inWin[inWin.length - 1]);
  const kRange: readonly [number, number] = [k[0], k[k.length - 1]];

  const useTransform = axisMode !== "logmoneyness" && forward !== undefined;
  const displayX: number[][] = t.map((ti, i) => {
    if (rowXTransform) return cols.map((j) => rowXTransform(k[j], i));
    if (!useTransform) return cols.map((j) => k[j]);
    const volAt = makeVolAt(k.map((kk, idx) => ({ k: kk, vol: vol[i][idx] })));
    const ctx = { forward: forward[i], t: ti, atmVol: atmVol?.[i] ?? volAt(0) ?? 0, volAt, kRange };
    return cols.map((j) => axisTransform(axisMode, k[j], ctx));
  });
  let dMin = Infinity;
  let dMax = -Infinity;
  for (const row of displayX)
    for (const x of row) if (Number.isFinite(x)) { dMin = Math.min(dMin, x); dMax = Math.max(dMax, x); }
  const dSpan = dMax - dMin || 1;
  const sval = (tt: number) => timeAxisValue(tt, timeMode);
  const sMin = sval(t[0]);
  const sMax = sval(t[t.length - 1]);
  let vMin = Infinity;
  let vMax = -Infinity;
  for (let i = 0; i < t.length; i++)
    for (const j of cols) { vMin = Math.min(vMin, vol[i][j]); vMax = Math.max(vMax, vol[i][j]); }
  const vSpan = vMax - vMin || 1;
  const rows = t.map((ti, i) =>
    cols.map((j, c) => ({
      x: (2 * (displayX[i][c] - dMin)) / dSpan - 1,
      y: sMax > sMin ? (2 * (sval(ti) - sMin)) / (sMax - sMin) - 1 : 0,
      z: ((vol[i][j] - vMin) / vSpan) * Z_HEIGHT,
      vol: vol[i][j],
    })),
  );
  return { rows, cols, displayX, vMin, vMax, xMin: dMin, xMax: dMax, tMin: t[0], tMax: t[t.length - 1] };
}

export interface Facet { d: string; depth: number; color: string }

/**
 * Painter-sorted facets from the projected PIXEL vertices `pts[i][j]`
 * ({x, y, depth}). One quad per cell, or — when triangulated — the cell's
 * two triangles split along the diagonal the model's own (qhull)
 * triangulation chose (`cellDiagMain[tRow][kCol]`, true = (i,j)→(i+1,j+1)),
 * falling back to the main diagonal when absent or when brushing leaves
 * mesh columns non-adjacent.
 */
export function buildFacets(
  mesh: SceneMesh,
  pts: { x: number; y: number; depth: number }[][],
  triangulate: boolean,
  cellDiagMain?: boolean[][],
): Facet[] {
  const vSpan = mesh.vMax - mesh.vMin || 1;
  const out: Facet[] = [];
  const push = (cs: { x: number; y: number; depth: number }[], vols: number[]) => {
    const vAvg = vols.reduce((a, v) => a + v, 0) / vols.length;
    out.push({
      d: `M${cs.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join("L")}Z`,
      depth: cs.reduce((a, p) => a + p.depth, 0) / cs.length,
      color: volColor((vAvg - mesh.vMin) / vSpan),
    });
  };
  for (let i = 0; i < pts.length - 1; i++) {
    for (let j = 0; j < pts[i].length - 1; j++) {
      const [p00, p01, p11, p10] = [pts[i][j], pts[i][j + 1], pts[i + 1][j + 1], pts[i + 1][j]];
      const [v00, v01, v11, v10] = [
        mesh.rows[i][j].vol, mesh.rows[i][j + 1].vol, mesh.rows[i + 1][j + 1].vol, mesh.rows[i + 1][j].vol,
      ];
      if (triangulate) {
        const j0 = mesh.cols[j];
        const mainDiag =
          cellDiagMain === undefined || mesh.cols[j + 1] !== j0 + 1 ? true : (cellDiagMain[i]?.[j0] ?? true);
        if (mainDiag) { push([p00, p01, p11], [v00, v01, v11]); push([p00, p11, p10], [v00, v11, v10]); }
        else { push([p00, p01, p10], [v00, v01, v10]); push([p01, p11, p10], [v01, v11, v10]); }
      } else {
        push([p00, p01, p11, p10], [v00, v01, v11, v10]);
      }
    }
  }
  out.sort((a, b) => b.depth - a.depth);
  return out;
}
