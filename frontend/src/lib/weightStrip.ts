// Pure binning/alignment helpers for the calibration weight strip (V3.4
// item 5; series redefined 2026-09-09). The WeightStrip component stays thin:
// normalization and the mock fallback are testable here, free of React.
//
// Two series per quote, both straight from GET .../weights:
//   * target — the scheme's TARGET shape at the quote (weightRaw: 1 for
//              equal / uniform, time value, Black vega or the OTM |delta|) —
//              the aggregate distribution the fit is asked to follow along
//              the smile;
//   * weight — the mean-1 weight the least squares actually sums: the target
//              times the Voronoi density correction min(s_i / s̄, maxMult),
//              which hands each quote the room it alone represents in
//              log-strike ("equal" applies no correction: one vote per quote).
// Each series draws normalized to its included max; the raw values and the
// multiplier ride along for the hover readout.

/** One entry of GET /smiles/{ticker}/{expiry}/weights (index == QuoteBand.index). */
export interface WeightEntry {
  index: number;
  k: number;
  /** Voronoi cell width s_i in k over the included quotes (0 when excluded
   *  or fewer than 2 quotes remain). Quote crowding is its inverse. */
  spacing: number;
  /** The scheme's target shape at the quote (max(TV, eps), the vega or |delta|
   *  profile, 1 for equal / uniform_density; 0 when excluded). */
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
  /** Target shape at the quote, normalized to max 1 over the included entries. */
  target: number;
  /** Final weight normalized to the included max (bar height in [0, 1]). */
  weightNorm: number;
  /** The scheme's raw target value (hover readout; 0 when excluded). */
  targetRaw: number;
  /** The density correction the fit applied at this quote:
   *  min(s_i / s̄, maxMult) over the included cells — 1 under "equal" (no
   *  correction) and when no cell exists. */
  spacingMult: number;
  /** The actual mean-1 weight (hover readout; 0 when excluded). */
  weight: number;
}

/** What the strip needs to know about the scheme the entries came from. */
export interface WeightBarOptions {
  scheme: string;
  /** Cap on the spacing multiplier (WeightsData.maxMult). */
  maxMult: number;
}

/** Short label of each scheme's target shape (the strip's legend). */
export const TARGET_LABELS: Record<string, string> = {
  equal: "one per quote",
  uniform_density: "uniform",
  tv_density: "time value",
  vega_density: "vega",
  delta_density: "|delta|",
};

export function targetLabel(scheme: string): string {
  return TARGET_LABELS[scheme] ?? scheme;
}

/**
 * Normalize weight entries into drawable bars, in ascending-k order:
 * `target` = raw_i / max(raw_i) and `weightNorm` = w_i / max(w_i) over the
 * INCLUDED entries (each series peaks at 1 on its own scale); `spacingMult`
 * is the backend's capped s_i / s̄ (s̄ = mean cell width over the included
 * quotes), reported as 1 under "equal" because that scheme never applies it.
 * Excluded rows keep zeros so the component can draw them as hollow outlines.
 */
export function buildWeightBars(
  entries: readonly WeightEntry[],
  { scheme, maxMult }: WeightBarOptions = { scheme: "equal", maxMult: 10 },
): WeightBar[] {
  let maxRaw = 0;
  let maxWeight = 0;
  let spacingSum = 0;
  let cells = 0;
  for (const e of entries) {
    if (e.excluded) continue;
    maxRaw = Math.max(maxRaw, e.weightRaw);
    maxWeight = Math.max(maxWeight, e.weight);
    if (e.spacing > 0) {
      spacingSum += e.spacing;
      cells += 1;
    }
  }
  const sBar = cells > 0 ? spacingSum / cells : 0;
  const corrects = scheme !== "equal" && sBar > 0;
  return [...entries]
    .sort((a, b) => a.k - b.k)
    .map((e) => ({
      index: e.index,
      k: e.k,
      excluded: e.excluded,
      target: !e.excluded && maxRaw > 0 ? e.weightRaw / maxRaw : 0,
      weightNorm: !e.excluded && maxWeight > 0 ? e.weight / maxWeight : 0,
      targetRaw: e.excluded ? 0 : e.weightRaw,
      spacingMult:
        !e.excluded && corrects && e.spacing > 0 ? Math.min(e.spacing / sBar, maxMult) : 1,
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
