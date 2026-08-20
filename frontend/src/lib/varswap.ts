// Pure var-swap display + dispatch helpers (V3.6 item 14).
//
// Kept out of the components so the slider-bound derivation and the batch
// "shift all" mapping are locked by vitest without a DOM (varswap.test.ts).
// All percent quantities are PERCENT vol (0.20 decimal ⇒ 20); all bp
// quantities are VOL BASIS POINTS ((quote − model) · 1e4, sign = quote − model,
// matching the backend VarSwapInfo.basisBp convention).

/** Slider/input step in PERCENT vol — every var-swap control quantizes to it. */
export const VS_SLIDER_STEP = 0.05;

/** Hard floor of the slider range, percent vol (a var-swap level must be > 0). */
export const VS_SLIDER_MIN_PCT = 0.5;

/** Smallest level (decimal vol) a batch shift may produce — the backend
 *  rejects non-positive levels, so a large downward shift clamps here. */
export const VS_MIN_LEVEL = 0.0001; // 0.01 % vol

/** Basis (quote − model) in vol basis points; null without a quote. */
export function varswapBasisBp(
  level: number | null | undefined,
  modelVol: number,
): number | null {
  return level == null ? null : (level - modelVol) * 1e4;
}

/** Signed whole-bp label for a basis chip: "+12 bp" / "−4 bp" / "0 bp".
 *  Whole bp is exactly the 2-decimal percent precision used everywhere else. */
export function formatBasisBp(bp: number | null | undefined): string {
  if (bp == null || !Number.isFinite(bp)) return "—";
  const r = Math.round(bp);
  return `${r > 0 ? "+" : ""}${r} bp`;
}

/**
 * Data-derived slider bounds in PERCENT vol (replaces the old ×0.5 / ×1.5
 * heuristic): the quote∪model envelope padded by max(2 vol pts, 2·|basis|):
 *
 *   pad = max(2, 2·|basisBp| / 100)
 *   min = max(0.5, min(quote, model)·100 − pad)
 *   max = max(quote, model)·100 + pad
 *
 * Without a quote the envelope collapses to the model level (pad = 2), so a
 * fresh quote seeded at the model gets a ±2-vol-point window. Step is the
 * shared VS_SLIDER_STEP.
 */
export function varswapSliderBounds(
  level: number | null | undefined,
  modelVol: number,
): { min: number; max: number; step: number } {
  const quote = level ?? modelVol;
  const basisBp = (quote - modelVol) * 1e4;
  const pad = Math.max(2, (2 * Math.abs(basisBp)) / 100);
  return {
    min: Math.max(VS_SLIDER_MIN_PCT, Math.min(quote, modelVol) * 100 - pad),
    max: Math.max(quote, modelVol) * 100 + pad,
    step: VS_SLIDER_STEP,
  };
}

/** One per-node "set" edit of a batch shift (decimal vol level). */
export interface VarSwapSetEdit {
  expiry: string;
  level: number;
}

/**
 * Per-node "set" edits for shifting every QUOTED rung by `bp` vol basis
 * points. Rungs without a quote are skipped (a shift never invents a quote);
 * shifted levels are floored at VS_MIN_LEVEL. Each returned edit dispatches to
 * its own node's var-swap session — N independent edits ⇒ N refits.
 */
export function varswapShiftEdits(
  points: { expiry: string; varSwapQuote?: number | null }[],
  bp: number,
): VarSwapSetEdit[] {
  if (!Number.isFinite(bp) || bp === 0) return [];
  return points
    .filter((p) => p.varSwapQuote != null)
    .map((p) => ({
      expiry: p.expiry,
      level: Math.max(VS_MIN_LEVEL, (p.varSwapQuote as number) + bp / 1e4),
    }));
}
