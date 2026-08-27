// Strike-axis helpers for the 3D LV mesh (LocalVolViewer "LV surface", mesh
// render). The nodal grid lives in x = K/F per vertex-maturity row; the
// footer's AxisUnitSelect picks one of LV_AXIS_OPTIONS and these helpers turn
// it into (i) the per-row display-x transform SurfaceMesh applies and (ii) the
// matching corner-label formatter. Pure functions — no React.
import type { AffineFitResponse } from "../../state/useAffine";
import type { LvAxis } from "./LocalVolToolbar";

/** Per-row display transform of the grid's x = K/F (row = vertex-maturity index). */
export type RowXTransform = (x: number, row: number) => number;

/** Display-x transform for the chosen LV axis, or undefined to keep x = K/F.
 *  Strike interpolates ln F(t) across the expiry ladder (flat-extrapolated
 *  beyond it); when no smile carries a forward the mesh stays in x. The brush
 *  and the heatmap always stay in x. */
export function lvMeshXTransform(
  lvAxis: LvAxis,
  data: AffineFitResponse | null,
): RowXTransform | undefined {
  if (lvAxis === "moneyness" || !data) return undefined;
  if (lvAxis === "logmoneyness") return (x) => Math.log(x);
  const fwd = data.smiles
    .filter((s) => (s.forward ?? 0) > 0)
    .map((s) => ({ t: s.t, lf: Math.log(s.forward as number) }));
  if (fwd.length === 0) return undefined; // no forwards: fall back to x
  const fAt = (t: number): number => {
    if (t <= fwd[0].t) return Math.exp(fwd[0].lf);
    const last = fwd[fwd.length - 1];
    if (t >= last.t) return Math.exp(last.lf);
    for (let i = 1; i < fwd.length; i++) {
      if (t <= fwd[i].t) {
        const a = fwd[i - 1];
        const f = (t - a.t) / (fwd[i].t - a.t);
        return Math.exp(a.lf + f * (fwd[i].lf - a.lf));
      }
    }
    return Math.exp(last.lf);
  };
  const rowF = data.tNodes.map(fAt);
  return (x, row) => x * (rowF[row] ?? 1);
}

/** Corner-label formatter matching the chosen LV x-axis scale (falls back to
 *  x when the strike transform is unavailable, mirroring lvMeshXTransform). */
export function lvMeshFormatX(lvAxis: LvAxis, hasTransform: boolean): (v: number) => string {
  return (v) => {
    if (!hasTransform) return `x ${v.toFixed(2)}`;
    if (lvAxis === "strike") return `K ${v >= 100 ? v.toFixed(0) : v.toFixed(2)}`;
    return `k ${v.toFixed(2)}`;
  };
}
