// Surface helpers of the Series lens's SURFACE stage (SERIES ARC S5,
// roadmap §3.4): a lane's σ(k, τ) grid at a frame as the 3D mesh's data,
// the signed difference between two lanes' sheets on their common grid,
// and the value range / signed-bp formatting the stage's legends read.
// τ is the frame's own (the mesh's t), so a sheet shrinks frame by frame
// as the ladder ages. Pure — no React; unit-tested in seriesSurface.test.ts.
import { visibleLanes } from "./seriesLanes";
import type { FramePayload, LaneSpec } from "./seriesTypes";
import type { SurfaceMeshData } from "./surfaceMesh";

/** Two grid columns are the same strike when their k's agree to this. */
const K_TOL = 1e-9;

/** A σ row with its non-finite cells filled from the nearest finite
 *  neighbour on the left (the right for a leading gap) — the backend's own
 *  fill rule; null when the row has no finite cell at all. */
export function fillRow(row: readonly number[]): number[] | null {
  const out = [...row];
  let last: number | null = null;
  for (let j = 0; j < out.length; j++) {
    if (Number.isFinite(out[j])) last = out[j];
    else if (last !== null) out[j] = last;
  }
  const first = out.find((v) => Number.isFinite(v));
  if (first === undefined) return null;
  for (let j = 0; j < out.length && !Number.isFinite(out[j]); j++) out[j] = first;
  return out;
}

/** The first finite number among candidates, else NaN. */
function firstFinite(...cands: (number | null | undefined)[]): number {
  return cands.find((v): v is number => typeof v === "number" && Number.isFinite(v)) ?? NaN;
}

/** The lane's surface at a frame as mesh data: rows = the grid's expiries
 *  ascending in τ (t = τ), columns = the grid's k, vol = σ; `forward` per
 *  expiry from the frame (its forwards, else the market, else the slice)
 *  and `atmVol` from the lane's slices — each only when every row has one
 *  (the mesh's axis modes read them by row). Null when the lane has no
 *  surface, or fewer than two usable rows / columns. */
export function laneMeshData(frame: FramePayload, laneId: string): SurfaceMeshData | null {
  const lane = frame.lanes[laneId];
  const grid = lane?.surface;
  if (!lane || !grid) return null;
  const k = grid.k;
  if (k.length < 2 || !k.every((v) => Number.isFinite(v))) return null;
  const rows: { expiry: string; tau: number; vol: number[] }[] = [];
  grid.expiries.forEach((expiry, i) => {
    const tau = grid.tau[i];
    const row = grid.sigma[i];
    if (!Number.isFinite(tau) || tau <= 0 || !row || row.length !== k.length) return;
    const vol = fillRow(row);
    if (vol !== null) rows.push({ expiry, tau, vol });
  });
  if (rows.length < 2) return null;
  rows.sort((a, b) => a.tau - b.tau);
  const expiries = rows.map((r) => r.expiry);
  const sliceOf = (e: string) => lane.slices.find((s) => s.expiry === e);
  const forward = expiries.map((e) => firstFinite(frame.forwards[e], frame.market[e]?.forward, sliceOf(e)?.forward));
  const atmVol = expiries.map((e) => firstFinite(sliceOf(e)?.atmVol));
  const out: SurfaceMeshData = { expiries, t: rows.map((r) => r.tau), k: [...k], vol: rows.map((r) => r.vol) };
  if (forward.every((v) => Number.isFinite(v))) out.forward = forward;
  if (atmVol.every((v) => Number.isFinite(v))) out.atmVol = atmVol;
  return out;
}

/** A visible lane's sheet at a frame. */
export interface LaneSheet {
  lane: LaneSpec;
  /** The lane's ordinal among ALL lanes (its dash / legend swatch). */
  ordinal: number;
  mesh: SurfaceMeshData;
}

/** The visible lanes that have a surface at the frame, in lane order. */
export function laneSheets(
  frame: FramePayload,
  lanes: readonly LaneSpec[],
  hidden: ReadonlySet<string>,
): LaneSheet[] {
  const out: LaneSheet[] = [];
  for (const { lane, ordinal } of visibleLanes(lanes, hidden)) {
    const mesh = laneMeshData(frame, lane.id);
    if (mesh !== null) out.push({ lane, ordinal, mesh });
  }
  return out;
}

/** Column pairs (ja, jb) whose k's agree: the identity when the two grids
 *  are one, else the common strikes of two ASCENDING grids (a merge walk). */
export function commonColumns(ka: readonly number[], kb: readonly number[]): { ja: number; jb: number }[] {
  if (ka.length === kb.length && ka.every((v, j) => Math.abs(v - kb[j]) <= K_TOL)) {
    return ka.map((_, j) => ({ ja: j, jb: j }));
  }
  const out: { ja: number; jb: number }[] = [];
  let jb = 0;
  for (let ja = 0; ja < ka.length; ja++) {
    while (jb < kb.length && kb[jb] < ka[ja] - K_TOL) jb++;
    if (jb < kb.length && Math.abs(kb[jb] - ka[ja]) <= K_TOL) out.push({ ja, jb });
  }
  return out;
}

/** The signed sheet a − b (vol units) over the expiries the two share (in
 *  a's order) and their common strike columns (the whole grid when both sit
 *  on one, else the intersection); τ, forward and ATM vol are a's. Null
 *  with fewer than two common rows or columns. */
export function differenceMeshData(a: SurfaceMeshData, b: SurfaceMeshData): SurfaceMeshData | null {
  const cols = commonColumns(a.k, b.k);
  if (cols.length < 2) return null;
  const rows: { ia: number; ib: number }[] = [];
  a.expiries.forEach((e, ia) => {
    const ib = b.expiries.indexOf(e);
    if (ib >= 0 && a.vol[ia] !== undefined && b.vol[ib] !== undefined) rows.push({ ia, ib });
  });
  if (rows.length < 2) return null;
  const out: SurfaceMeshData = {
    expiries: rows.map((r) => a.expiries[r.ia]),
    t: rows.map((r) => a.t[r.ia]),
    k: cols.map((c) => a.k[c.ja]),
    vol: rows.map((r) => cols.map((c) => a.vol[r.ia][c.ja] - b.vol[r.ib][c.jb])),
  };
  const fa = a.forward;
  const va = a.atmVol;
  if (fa !== undefined) out.forward = rows.map((r) => fa[r.ia]);
  if (va !== undefined) out.atmVol = rows.map((r) => va[r.ia]);
  return out;
}

/** min / max of a sheet's finite values and the larger magnitude (a
 *  diverging ramp's half-span); null when the sheet has no finite value. */
export function surfaceValueRange(data: SurfaceMeshData): { min: number; max: number; absMax: number } | null {
  let lo = Infinity;
  let hi = -Infinity;
  for (const row of data.vol) {
    for (const v of row) if (Number.isFinite(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  }
  return Number.isFinite(lo) ? { min: lo, max: hi, absMax: Math.max(Math.abs(lo), Math.abs(hi)) } : null;
}

/** A signed vol difference in vol bp: "+12 bp" · "−3 bp" · "0 bp"; "—" for
 *  a null / non-finite value (the difference legend and its hover readout). */
export function formatSignedVolBp(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const bp = v * 1e4;
  const magnitude = Number(Math.abs(bp).toFixed(digits));
  const sign = magnitude === 0 ? "" : bp > 0 ? "+" : "−";
  return `${sign}${magnitude.toFixed(digits)} bp`;
}
