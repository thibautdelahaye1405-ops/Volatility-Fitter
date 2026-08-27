// Linked (k, T) hover across the surface charts (UI SHELL v2 wave 3, B2).
//
// Whichever chart the pointer is over — the Parametric IV surface, the LV
// meshes / heatmap, the Stacked IV / Densities overlays — publishes the grid
// point under it (ticker, log-moneyness k, maturity T, its own id); every
// other visible chart of the SAME ticker shows the matching crosshair at its
// nearest vertex (the split-editor case). A tiny module store with
// useSyncExternalStore: no provider, works in tests and legacy mounts.
import { useCallback, useSyncExternalStore } from "react";

export interface SurfaceHoverPoint {
  ticker: string;
  /** Log-moneyness ln(K/F) (LV grids convert from x = K/F). */
  k: number;
  /** Year-fraction to maturity. */
  t: number;
  /** Publishing chart id (a chart ignores its own echo). */
  source: string;
}

let current: SurfaceHoverPoint | null = null;
const listeners = new Set<() => void>();

function subscribe(l: () => void): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
const getSnapshot = () => current;
const getServerSnapshot = () => null;

/** Publish (or clear with null) the hovered point. Clearing only clears the
 *  caller's own hover, never another chart's. */
export function publishSurfaceHover(point: SurfaceHoverPoint | null, source: string): void {
  if (point === null) {
    if (current === null || current.source !== source) return;
    current = null;
  } else {
    current = point;
  }
  listeners.forEach((l) => l());
}

/** The live hover point + a bound publisher for this chart id. */
export function useSurfaceHover(source: string): {
  hover: SurfaceHoverPoint | null;
  publish: (p: Omit<SurfaceHoverPoint, "source"> | null) => void;
} {
  const hover = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  const publish = useCallback(
    (p: Omit<SurfaceHoverPoint, "source"> | null) => publishSurfaceHover(p === null ? null : { ...p, source }, source),
    [source],
  );
  return { hover, publish };
}

/** Nearest grid vertex to a linked hover point — (k, t) distance with each
 *  axis normalised by its grid span. Null when either grid is empty. */
export function nearestGridPoint(
  ks: number[],
  ts: number[],
  k: number,
  t: number,
): { i: number; j: number } | null {
  if (ks.length === 0 || ts.length === 0) return null;
  const kSpan = Math.abs(ks[ks.length - 1] - ks[0]) || 1;
  const tSpan = Math.abs(ts[ts.length - 1] - ts[0]) || 1;
  let j = 0;
  for (let c = 1; c < ks.length; c++) if (Math.abs(ks[c] - k) < Math.abs(ks[j] - k)) j = c;
  let i = 0;
  for (let r = 1; r < ts.length; r++) if (Math.abs(ts[r] - t) < Math.abs(ts[i] - t)) i = r;
  // Ignore far-off links (outside half a span on either axis).
  if (Math.abs(ks[j] - k) > kSpan / 2 || Math.abs(ts[i] - t) > tSpan / 2) return null;
  return { i, j };
}
