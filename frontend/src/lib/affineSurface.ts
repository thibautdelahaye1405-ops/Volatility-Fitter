// Pure helpers for the Local Vol workspace's derived views (moved out of
// LocalVolViewer.tsx — the 400-line policy: the viewer keeps mount points,
// logic lives in lib/ modules).
import type { SurfaceMeshData } from "../components/SurfaceMesh";
import { makeVolAt } from "./axisModes";

/** Linear interpolation of a sorted (k, vol) curve at log-moneyness k. */
export function interpVol(model: { k: number; vol: number }[], k: number): number {
  if (model.length === 0) return NaN;
  if (k <= model[0].k) return model[0].vol;
  const last = model[model.length - 1];
  if (k >= last.k) return last.vol;
  for (let i = 1; i < model.length; i++) {
    if (k <= model[i].k) {
      const a = model[i - 1];
      const b = model[i];
      const f = (k - a.k) / (b.k - a.k);
      return a.vol + f * (b.vol - a.vol);
    }
  }
  return last.vol;
}

/** Reconstructed IV surface from the per-expiry affine smiles: resample each on
 *  a shared log-moneyness grid (the intersection range, so no curve is
 *  extrapolated) and return it as a (T × k → σ) mesh for the 3D SurfaceMesh. */
export function buildIvSurface(
  smiles: { expiry: string; t: number; forward?: number; model: { k: number; vol: number }[] }[],
): SurfaceMeshData | null {
  const usable = smiles.filter((s) => s.model.length >= 2);
  if (usable.length < 2) return null;
  const kLo = Math.max(...usable.map((s) => s.model[0].k));
  const kHi = Math.min(...usable.map((s) => s.model[s.model.length - 1].k));
  if (!(kHi > kLo)) return null;
  const N = 41;
  const kGrid = Array.from({ length: N }, (_, j) => kLo + ((kHi - kLo) * j) / (N - 1));
  return {
    expiries: usable.map((s) => s.expiry),
    t: usable.map((s) => s.t),
    k: kGrid,
    vol: usable.map((s) => kGrid.map((k) => interpVol(s.model, k))),
    // Forward per expiry + ATM vol (vol at k=0) so SurfaceMesh can re-coordinate
    // the x-axis to strike / %ATM / Δ / normalized per row.
    forward: usable.map((s) => s.forward ?? 0),
    atmVol: usable.map((s) => interpVol(s.model, 0)),
  };
}

/** AxisContext for one reconstructed affine smile: forward + ATM vol from the
 *  model curve, with a vol lookup for the Δ axis. */
export function smileAxisContext(s: {
  t: number;
  forward?: number;
  model: { k: number; vol: number }[];
}) {
  const volAt = makeVolAt(s.model);
  return {
    forward: s.forward ?? 0,
    t: s.t,
    atmVol: volAt(0) ?? 0,
    volAt,
    kRange: [s.model[0]?.k ?? -1, s.model[s.model.length - 1]?.k ?? 1] as [number, number],
  };
}
