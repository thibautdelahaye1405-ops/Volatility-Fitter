// Relationship-uncertainty units (P5b U1 — language & units).
//
// The wire/solver unit for a relation factor is its conditional precision p
// (receiver ATM-vol units, 1/vol² with vol in DECIMAL). Traders think in vol
// POINTS, so the DEFAULT UI lens is the relationship uncertainty
//
//     σ_edge = 1/√p   (decimal vol)  →  ×100  (vol points)
//
// with raw precision behind a toggle. Conversions here are the single source
// of truth for that lens, plus the sentence renderer used by relation-row
// tooltips ("SPY 6M informs AAPL 6M: +1.00 pt → +0.70 pt message ·
// relationship uncertainty 0.80 pt").
//
// Three-name taxonomy (used verbatim across the graph UI):
//   Relationship uncertainty  — σ_edge = 1/√p of ONE relation factor.
//   Incoming message confidence — q = Σp, the receiver conditional (§7.6).
//   Final posterior confidence  — the solved marginal (folds in source
//                                 uncertainty and shared routes; authoritative).

/** Relationship uncertainty σ_edge in VOL POINTS from a precision (1/vol²). */
export function sigmaPtsFromPrecision(precision: number): number {
  if (!(precision > 0)) return Infinity;
  return 100 / Math.sqrt(precision);
}

/** Precision (1/vol²) from a relationship uncertainty in VOL POINTS. */
export function precisionFromSigmaPts(sigmaPts: number): number {
  if (!(sigmaPts > 0)) return 0;
  return (100 / sigmaPts) ** 2;
}

/** σ_edge display string ("0.88" pts; "∞" for a dead relation). */
export function fmtSigmaPts(precision: number): string {
  const s = sigmaPtsFromPrecision(precision);
  return Number.isFinite(s) ? s.toFixed(2) : "∞";
}

/**
 * The relation-row sentence: what a +1.00 pt informer innovation does to the
 * receiver through THIS single factor (single-source transfer is exactly
 * ρ·β·z — spec §21.12), and how uncertain the relationship is.
 */
export function relationSentence(args: {
  sourceLabel: string;
  targetLabel: string;
  /** Directed ATM amplitude β (receiver units per informer unit). */
  beta: number;
  /** Conditional relation precision p (1/vol²). */
  precision: number;
  /** Amplitude multiplier ρ of the relation class (§8.4). */
  rho: number;
}): string {
  const transfer = args.rho * args.beta;
  const signed = `${transfer >= 0 ? "+" : ""}${transfer.toFixed(2)}`;
  return (
    `${args.sourceLabel} informs ${args.targetLabel}: ` +
    `+1.00 pt → ${signed} pt message · ` +
    `relationship uncertainty ${fmtSigmaPts(args.precision)} pt`
  );
}
