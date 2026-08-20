// Pure binning/alignment helpers for the calibration weight strip (V3.4
// item 5). The WeightStrip component stays thin: normalization and the mock
// fallback are testable here, free of React.

/** One entry of GET /smiles/{ticker}/{expiry}/weights (index == QuoteBand.index). */
export interface WeightEntry {
  index: number;
  k: number;
  /** Voronoi cell width s_i in k over the included quotes (0 when excluded
   *  or fewer than 2 quotes remain). Quote crowding is its inverse. */
  spacing: number;
  /** Pre-normalization economic weight (max(TV, eps) for tv_density; 1 for
   *  equal; 0 when excluded). */
  weightRaw: number;
  /** Final mean-1 weight the fit uses (0 when excluded). */
  weight: number;
  excluded: boolean;
}

/** Response of GET /smiles/{ticker}/{expiry}/weights. */
export interface WeightsData {
  ticker: string;
  expiry: string;
  scheme: string;
  maxMult: number;
  meanNormalized?: boolean;
  entries: WeightEntry[];
}

/** One drawable bar pair, aligned to the chart's x transform via `k`. */
export interface WeightBar {
  index: number;
  k: number;
  excluded: boolean;
  /** Quote crowding 1/s_i, normalized to max 1 over the included entries. */
  density: number;
  /** Final weight normalized to the included max (bar height in [0, 1]). */
  weightNorm: number;
  /** The actual mean-1 weight (hover/label readout; 0 when excluded). */
  weight: number;
}

/**
 * Normalize weight entries into drawable bars, in ascending-k order:
 * `density` = (1/s_i) / max(1/s_i) and `weightNorm` = w_i / max(w_i) over the
 * INCLUDED entries (each series peaks at 1 on its own scale); excluded rows
 * keep zeros so the component can draw them as hollow outlines.
 */
export function buildWeightBars(entries: readonly WeightEntry[]): WeightBar[] {
  let maxInvSpacing = 0;
  let maxWeight = 0;
  for (const e of entries) {
    if (e.excluded) continue;
    if (e.spacing > 0) maxInvSpacing = Math.max(maxInvSpacing, 1 / e.spacing);
    maxWeight = Math.max(maxWeight, e.weight);
  }
  return [...entries]
    .sort((a, b) => a.k - b.k)
    .map((e) => ({
      index: e.index,
      k: e.k,
      excluded: e.excluded,
      density:
        !e.excluded && e.spacing > 0 && maxInvSpacing > 0
          ? 1 / e.spacing / maxInvSpacing
          : 0,
      weightNorm: !e.excluded && maxWeight > 0 ? e.weight / maxWeight : 0,
      weight: e.excluded ? 0 : e.weight,
    }));
}

/**
 * Mock fallback entries (equal scheme) derived from quote strikes: unit
 * weights plus the 1-D Voronoi spacing of the INCLUDED strikes (half the gap
 * to each neighbour, one-sided at the ends — the backend's own rule over the
 * post-edit array). Excluded quotes get zeros, mirroring the live payload.
 */
export function mockWeightEntries(
  quotes: readonly { k: number; index: number; excluded: boolean }[],
): WeightEntry[] {
  const included = [...quotes].filter((q) => !q.excluded).sort((a, b) => a.k - b.k);
  const m = included.length;
  const spacing = new Map<number, number>();
  for (let j = 0; j < m; j++) {
    let s = 0;
    if (m >= 2) {
      if (j === 0) s = included[1].k - included[0].k;
      else if (j === m - 1) s = included[m - 1].k - included[m - 2].k;
      else s = 0.5 * (included[j + 1].k - included[j - 1].k);
    }
    spacing.set(included[j].index, s);
  }
  return quotes.map((q) => ({
    index: q.index,
    k: q.k,
    spacing: spacing.get(q.index) ?? 0,
    weightRaw: q.excluded ? 0 : 1,
    weight: q.excluded ? 0 : 1,
    excluded: q.excluded,
  }));
}
