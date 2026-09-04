// The ATM forward-variance ladder read on both clocks.
//
// Between consecutive expiries the ATM total variance w grows by Δw; divided
// by the interval's length it is the forward variance. Read per CALENDAR year
// (Δw/Δt) it is invariant to the event calendar — prices fix w — so an event
// can never move it. Read per EVENT-TIME year (Δw/Δτ, the clock every fit
// works in) an event lengthens its interval and pulls a hot interval down:
// that is the ladder the auto-calibrator flattens, and the one that shows an
// event's effect on either maturity axis. Pure helpers, shared by the Term
// chart (both steps) and the Term panel (the before/after readout).
import type { TermPoint } from "../state/useTerm";

/** One inter-expiry interval of the ladder (the first runs from the origin). */
export interface LadderInterval {
  /** The interval's far expiry (ISO date). */
  expiry: string;
  /** Calendar bounds, years. */
  t0: number;
  t1: number;
  /** Event-time bounds, years (equal to t0 / t1 with no active events). */
  tau0: number;
  tau1: number;
  /** Forward variance per calendar year, Δw/Δt — event-invariant. */
  calendar: number;
  /** Forward variance per event-time year, Δw/Δτ — the working clock's. */
  eventTime: number;
}

/** Guard against a degenerate (zero-length) interval. */
const rate = (dw: number, dx: number): number => (dx > 1e-9 ? dw / dx : 0);

/** The ladder in ascending calendar maturity, both readings per interval. */
export function forwardLadder(points: TermPoint[]): LadderInterval[] {
  const sorted = [...points].sort((a, b) => a.t - b.t);
  const out: LadderInterval[] = [];
  let t0 = 0;
  let tau0 = 0;
  let w0 = 0;
  for (const p of sorted) {
    const dw = p.w0 - w0;
    out.push({
      expiry: p.expiry,
      t0,
      t1: p.t,
      tau0,
      tau1: p.tau,
      calendar: rate(dw, p.t - t0),
      eventTime: rate(dw, p.tau - tau0),
    });
    t0 = p.t;
    tau0 = p.tau;
    w0 = p.w0;
  }
  return out;
}

/** True when an active event calendar separates the two clocks (τ ≠ t). */
export function clocksDiffer(points: TermPoint[], tol = 1e-9): boolean {
  return points.some((p) => Math.abs(p.tau - p.t) > tol);
}

/**
 * Spread of a ladder, max − min of its levels, in variance bp (×1e4) — the
 * one number that says how uneven the forward variance is across the ladder.
 * Null with fewer than two intervals (no spread to speak of).
 */
export function ladderSpreadBp(levels: number[]): number | null {
  if (levels.length < 2) return null;
  let lo = Infinity;
  let hi = -Infinity;
  for (const v of levels) {
    lo = Math.min(lo, v);
    hi = Math.max(hi, v);
  }
  return (hi - lo) * 1e4;
}
