// Pure helpers of the Local Vol lens's Compare tab (LV Dupire-twin arc, D3):
// the chip vocabularies (t-interpolation · tail target · display mode), the
// sheet / difference builders on the compare lattice, the score formatting
// and the repair summary. No React, no DOM — unit-tested in lvCompare.test.ts;
// the components (components/localvol/LvCompare*.tsx) stay presentation only.
import type { SurfaceMeshData } from "./surfaceMesh";
import type {
  LvCompareCounters, LvCompareResponse, LvCompareScore, LvCompareSmile, LvTInterp,
} from "../state/useLvCompare";

/** The t-interpolation chips: how the parametric total-variance surface is
 *  carried between listed expiries BEFORE it is differentiated. */
export const LV_T_INTERP_OPTIONS: { id: LvTInterp; label: string; title: string }[] = [
  {
    id: "smooth",
    label: "Smooth",
    title:
      "Monotone C¹ (PCHIP) total variance in τ through every slice — the twin is continuous in both directions (default)",
  },
  {
    id: "buckets",
    label: "Buckets",
    title:
      "Constant forward variance between listed expiries — the market staircase, what the classical extraction returns",
  },
];

/** Tail targets: what the parametric surface IS beyond the quoted range before
 *  it is differentiated. v1 ships the displayed model's own wings; the other
 *  targets (match LQD tails · quoted range · affine wings) are recorded riders
 *  and appear here disabled so the group reads as the axis it is. */
export type LvTailTarget = "model" | "matchLqd" | "hull" | "affine";
export const LV_TAIL_OPTIONS: { id: LvTailTarget; label: string; title: string; available: boolean }[] = [
  {
    id: "model",
    label: "Model wings",
    title:
      "The displayed model's own analytic wings (LQD generalized tails, SVI-JW Lee slopes, MCS). " +
      "An exponential-class wing gives a local variance growing without bound in |k| — the affine sheet is Gaussian-class there, so the wings are where the two structurally differ",
    available: true,
  },
  { id: "matchLqd", label: "Match LQD", title: "Rider — the overlay refit with the Compare tail-match rows so its wings sit on LQD's", available: false },
  { id: "hull", label: "Quoted range", title: "Rider — differentiate inside each expiry's quoted hull only, flat local vol beyond", available: false },
  { id: "affine", label: "Affine wings", title: "Rider — the twin inside the hull, the calibrated affine sheet outside", available: false },
];

/** What the card draws: the two σ²_loc sheets side by side, the signed
 *  difference heatmap, or the four-curve smiles + the score table. */
export type LvCompareMode = "sheets" | "diff" | "smiles";
export const LV_COMPARE_MODES: { id: LvCompareMode; label: string }[] = [
  { id: "sheets", label: "Sheets" },
  { id: "diff", label: "Difference" },
  { id: "smiles", label: "Smiles" },
];

/** Curve colours of the smile panel: the affine reconstruction keeps the LV
 *  lens's sky blue (LocalVolSmile's model stroke); the parametric source is
 *  lime, the Dupire twin orange and dashed — never a family colour, so it
 *  cannot read as a fourth calibrated model. */
export const PARAMETRIC_COLOR = "#a3e635";
export const TWIN_COLOR = "#fb923c";
export const AFFINE_COLOR = "rgb(56 189 248)";
export const TWIN_DASH = "6 3";

/** The σ²_loc mesh of a sheet on the compare lattice (rows = t vertices,
 *  columns = x vertices — the LV-surface view's convention), or null when
 *  the sheet is absent / degenerate. Takes the arrays themselves so a view
 *  can memoize on their identity (an unchanged record keeps its arrays). */
export function meshOf(
  tNodes: number[] | undefined, xNodes: number[] | undefined, rows: number[][] | undefined,
): SurfaceMeshData | null {
  if (!tNodes || !xNodes || tNodes.length < 2 || xNodes.length < 2) return null;
  if (!rows || rows.length !== tNodes.length) return null;
  return {
    expiries: tNodes.map((t) => t.toFixed(2)),
    t: tNodes,
    k: xNodes,
    vol: rows.map((row) => row.map((v) => v * v)),
  };
}

/** The twin's DRAWN sheet: the smooth sample when the payload carries one
 *  (its vertices are the lattice's, bit-for-bit), else the vertex sheet. */
export function twinSheetArrays(c: LvCompareResponse): {
  tNodes: number[]; xNodes: number[]; rows: number[][]; smooth: boolean;
} {
  const fine = c.localVolTwinFine;
  if (fine && fine.length > 1 && c.tNodesFine && c.xNodesFine && fine.length === c.tNodesFine.length)
    return { tNodes: c.tNodesFine, xNodes: c.xNodesFine, rows: fine, smooth: true };
  return { tNodes: c.tNodes, xNodes: c.xNodes, rows: c.localVolTwin, smooth: false };
}

/** `meshOf` for one named sheet of a payload (the twin from its smooth sample). */
export function sheetMesh(c: LvCompareResponse | null, which: "twin" | "affine"): SurfaceMeshData | null {
  if (c === null) return null;
  if (which === "affine") return meshOf(c.tNodes, c.xNodes, c.localVolAffine);
  const a = twinSheetArrays(c);
  return meshOf(a.tNodes, a.xNodes, a.rows);
}

/** The signed difference sheet twin − affine (vol), only on the matching
 *  lattice; null otherwise. */
export function diffSheet(c: LvCompareResponse | null): number[][] | null {
  if (c === null || !c.affineLatticeMatches || !c.diffLocalVol || c.diffLocalVol.length === 0) return null;
  return c.diffLocalVol;
}

/** Largest |value| of a sheet (0 for an empty one) — the diverging ramp's half-span. */
export function maxAbs(rows: number[][]): number {
  let m = 0;
  for (const row of rows) for (const v of row) if (Number.isFinite(v)) m = Math.max(m, Math.abs(v));
  return m;
}

/** Signed vol difference in percentage points, e.g. "+1.3 pt" / "−0.4 pt". */
export function formatSignedPts(v: number | null | undefined, digits = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const pts = v * 100;
  const sign = pts > 0 ? "+" : pts < 0 ? "−" : "";
  return `${sign}${Math.abs(pts).toFixed(digits)} pt`;
}

/** Whole-bp figure that survives a null / NaN metric ("—", never a crash). */
export function formatBp(v: number | null | undefined, digits = 0): string {
  return v == null || !Number.isFinite(v) ? "—" : v.toFixed(digits);
}

/** One score as bp columns: `rms` = the WEIGHTED fit-target RMS (rmsError
 *  × 1e4 — comparable across the three surfaces), `conv` the converged-
 *  operator RMS, `max` the worst quote. */
export function scoreBp(s: LvCompareScore | null | undefined): {
  rms: number | null; conv: number | null; max: number | null;
} {
  if (!s) return { rms: null, conv: null, max: null };
  return {
    rms: Number.isFinite(s.rmsError) ? s.rmsError * 1e4 : null,
    conv: s.convergedBp == null ? null : s.convergedBp,
    max: Number.isFinite(s.maxBp) ? s.maxBp : null,
  };
}

/** Totals of the per-row repair counters. */
export function repairTotals(c: LvCompareCounters): {
  butterfly: number; calendar: number; floored: number; capped: number;
} {
  const sum = (a: number[]) => a.reduce((acc, v) => acc + v, 0);
  return {
    butterfly: sum(c.butterfly), calendar: sum(c.calendar), floored: sum(c.floored), capped: sum(c.capped),
  };
}

/** One-line repair summary for the strip ("no repairs" when the extraction
 *  touched nothing). */
export function repairSummary(c: LvCompareCounters): string {
  const t = repairTotals(c);
  if (c.clean) return "no repairs";
  const parts: string[] = [];
  if (t.butterfly > 0) parts.push(`butterfly ${t.butterfly}`);
  if (t.calendar > 0) parts.push(`calendar ${t.calendar}`);
  if (t.floored > 0) parts.push(`floored ${t.floored}`);
  if (t.capped > 0) parts.push(`capped ${t.capped}`);
  return parts.join(" · ") || "no repairs";
}

/** Per-row repair detail for a tooltip: one line per t vertex that needed any. */
export function repairDetail(c: LvCompareCounters, tNodes: number[]): string {
  const lines: string[] = [];
  tNodes.forEach((t, i) => {
    const b = c.butterfly[i] ?? 0, k = c.calendar[i] ?? 0, f = c.floored[i] ?? 0, p = c.capped[i] ?? 0;
    if (b + k + f + p === 0) return;
    lines.push(`t ${t.toFixed(3)}: butterfly ${b} · calendar ${k} · floored ${f} · capped ${p}`);
  });
  return lines.length > 0 ? lines.join("\n") : "Every vertex differentiated cleanly — nothing floored, capped or filled";
}

/** The compare smile of an expiry (the node's), or the first one; null when
 *  the payload has none. */
export function compareSmileFor(c: LvCompareResponse | null, expiry: string | null): LvCompareSmile | null {
  if (c === null || c.smiles.length === 0) return null;
  return c.smiles.find((s) => s.expiry === expiry) ?? c.smiles[0];
}
