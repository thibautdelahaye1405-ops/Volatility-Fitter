// Pure SVG-path builders for the fit-target overlay of the smile chart
// (V3.4 item 4): the thin mid polyline and the bid-ask / haircut band
// ribbons. Kept out of SmileChart.tsx (file-size policy) and free of React
// so the geometry is unit-testable: the builders take the chart's display
// transforms as plain functions and return `d` attribute strings.
/** The quote fields the builders read. Both the Parametric QuoteBand
 *  (lib/mockData) and the Local-Vol QuoteBand (state/useAffine) satisfy it,
 *  so one set of builders draws the target overlay on both charts. */
export interface TargetQuote {
  k: number;
  mid: number;
  excluded: boolean;
}

/** Map a quote's k to a pixel x (the chart's axis transform + x scale). */
export type ToX = (k: number) => number;
/** Map a vol to a pixel y (the chart's y scale). */
export type ToY = (vol: number) => number;
/** Read one band edge off a quote; null/undefined ⇒ no value (path gap). */
export type EdgeOf<Q extends TargetQuote = TargetQuote> = (q: Q) => number | null | undefined;

const fmt = (v: number): string => v.toFixed(2);

/** Ascending-k copy (payloads arrive sorted; defensive for mock callers). */
function sortedByK<Q extends TargetQuote>(quotes: readonly Q[]): Q[] {
  return [...quotes].sort((a, b) => a.k - b.k);
}

/**
 * Thin polyline through the (possibly amended) mids of non-excluded quotes —
 * the fit target in "mid" mode, the soft anchor in the band modes. Excluded
 * strikes are skipped (the line interpolates straight across them); fewer
 * than 2 drawable points yield "" (nothing to draw).
 */
export function midLinePath(
  quotes: readonly TargetQuote[],
  toX: ToX,
  toY: ToY,
): string {
  const pts = sortedByK(quotes).filter((q) => !q.excluded && Number.isFinite(q.mid));
  if (pts.length < 2) return "";
  return pts
    .map((q, i) => `${i === 0 ? "M" : "L"}${fmt(toX(q.k))},${fmt(toY(q.mid))}`)
    .join("");
}

/**
 * Band ribbon through non-excluded quotes' [lo, hi] edges: one closed subpath
 * (forward along hi, back along lo) per run of consecutive included strikes,
 * so an excluded strike leaves a visible GAP in the ribbon. A quote missing
 * either edge (null / non-finite — e.g. a "mid"-mode payload without target
 * fields) also breaks the run; a run of a single quote has no drawable area
 * and is skipped. Returns "" when nothing is drawable.
 */
export function ribbonPath<Q extends TargetQuote>(
  quotes: readonly Q[],
  lo: EdgeOf<Q>,
  hi: EdgeOf<Q>,
  toX: ToX,
  toY: ToY,
): string {
  const subpaths: string[] = [];
  let run: { x: number; lo: number; hi: number }[] = [];
  const flush = () => {
    if (run.length >= 2) {
      let d = "";
      for (const p of run) d += `${d === "" ? "M" : "L"}${fmt(p.x)},${fmt(toY(p.hi))}`;
      for (let i = run.length - 1; i >= 0; i--) d += `L${fmt(run[i].x)},${fmt(toY(run[i].lo))}`;
      subpaths.push(d + "Z");
    }
    run = [];
  };
  for (const q of sortedByK(quotes)) {
    const l = lo(q);
    const h = hi(q);
    if (
      !q.excluded &&
      typeof l === "number" &&
      typeof h === "number" &&
      Number.isFinite(l) &&
      Number.isFinite(h)
    ) {
      run.push({ x: toX(q.k), lo: l, hi: h });
    } else {
      flush();
    }
  }
  flush();
  return subpaths.join(" ");
}
