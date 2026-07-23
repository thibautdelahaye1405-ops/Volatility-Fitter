// Layered-mode timeline math (P6 V3): the framework §5 asynchronous A/B
// machine replayed CLIENT-side — the same causal rules the production state
// layer implements (vitest-locked to the SAME numbers as
// backend/tests/fixtures/graph_dynamic_golden.json):
//
//   * A's mark is its last print (step function).
//   * B's systematic prediction is β · (last A print) — the directed parent.
//   * B's own residual u is learned ONLY at B's prints (hard update against
//     the CAUSAL source: u = d_B − β·m_A) and carried through time, decaying
//     by the half-life (2^(−Δ/H); no half-life = random walk, u persists).
//   * B's mark between prints = systematic + decayed residual. Zero reverse
//     influence: nothing here ever touches A.
//
// Exposition values are handle LEVELS against a zero baseline (doc §5.1).

/** The §5 A/B exposition fixture (golden async_ab, embedded verbatim). */
export const AB_FIXTURE = {
  snapshots: [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
  obsA: {
    "0": 10.0, "1": 11.0, "2": 12.0, "3": 13.0, "4": 14.0, "5": 15.0,
  } as Record<string, number>,
  obsB: { "0": 10.0, "3.5": 10.0 } as Record<string, number>,
};

export interface ABPoint {
  t: number;
  /** A's mark (last print). */
  a: number;
  /** B's mark: its print at print times, else systematic + residual. */
  b: number;
  /** The directed prediction β·m_A. */
  systematic: number;
  /** B's residual u AFTER this snapshot's update (decayed to t first). */
  u: number;
  aObserved: boolean;
  bObserved: boolean;
}

/** Replay the A/B machine over `snapshots` with the given β and half-life
 *  (null = random walk). Observation maps are keyed by String(t). */
export function replayAB(
  snapshots: number[],
  obsA: Record<string, number>,
  obsB: Record<string, number>,
  beta: number,
  halfLifeDays: number | null,
): ABPoint[] {
  const out: ABPoint[] = [];
  let a = NaN;
  let u = 0;
  let uAt: number | null = null; // residual learned yet?
  for (const t of snapshots) {
    const keyed = String(t);
    const aObserved = keyed in obsA;
    if (aObserved) a = obsA[keyed];
    // Decay the carried residual to now (D2 semigroup: point formula).
    let uNow =
      uAt === null || halfLifeDays === null
        ? u
        : u * Math.pow(2, -(t - uAt) / halfLifeDays);
    const systematic = beta * a;
    const bObserved = keyed in obsB;
    let b: number;
    if (bObserved) {
      b = obsB[keyed];
      // Hard update against the causal source (§6.3): the print defines u.
      uNow = b - systematic;
      u = uNow;
      uAt = t;
    } else {
      b = systematic + (uAt === null ? 0 : uNow);
      if (halfLifeDays !== null && uAt !== null) {
        u = uNow; // carry the decayed value forward
        uAt = t;
      }
    }
    out.push({ t, a, b, systematic, u: uAt === null ? 0 : uNow, aObserved, bObserved });
  }
  return out;
}
