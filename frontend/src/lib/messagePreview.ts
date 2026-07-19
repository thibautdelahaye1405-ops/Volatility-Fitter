// Deterministic local preview of the precision-message receiver conditional
// (spec Docs/graph_precision_message_framework.md §7.3/§14.2/§20.4).
//
// Pure math, mirrored from the backend operator so the edge editor can show
// the EXACT posterior mean and conditional precision a configuration implies
// before saving — the Phase-5 exit gate. The canonical §21 examples are
// vitest-locked against the backend's golden fixture numbers.

/** One incoming message at the previewed receiver. */
export interface PreviewMessage {
  /** Directed amplitude β (receiver units per informer unit). */
  beta: number;
  /** Conditional relation precision p (receiver ATM-vol units). */
  precision: number;
  /** The informer's innovation z (same units as the propagated handle). */
  z: number;
  /** Amplitude multiplier ρ of the message's relation class (spec §8.4). */
  rho: number;
}

export interface PreviewResult {
  /** Conditional posterior mean Σpβz / (κ + Σp). */
  mean: number;
  /** Receiver conditional incoming precision q = Σp (spec §7.6). */
  q: number;
  /** Node-linked innovation anchor κ = p_primary·(1−ρ)/ρ (spec §14.2). */
  kappa: number;
  /** Conditional sd 1/√(κ + q) — the band BEFORE source uncertainty. */
  conditionalSd: number;
}

/**
 * The receiver conditional given its informers, clamped (spec §7.3) — with
 * the node-linked anchor derived from the PRIMARY (max-precision) incoming
 * relation's amplitude multiplier, fixed regardless of corroboration count
 * (the mechanization validated in backtest/results/message_phase0.json).
 */
export function receiverPreview(messages: PreviewMessage[]): PreviewResult {
  const live = messages.filter((m) => m.precision > 0);
  if (live.length === 0) return { mean: 0, q: 0, kappa: 0, conditionalSd: Infinity };
  const q = live.reduce((s, m) => s + m.precision, 0);
  const primary = live.reduce((a, b) => (b.precision > a.precision ? b : a));
  const rho = Math.min(Math.max(primary.rho, 1e-9), 1);
  const kappa = primary.precision * ((1 - rho) / rho);
  const num = live.reduce((s, m) => s + m.precision * m.beta * m.z, 0);
  return {
    mean: num / (kappa + q),
    q,
    kappa,
    conditionalSd: 1 / Math.sqrt(kappa + q),
  };
}

/** §8.3 reciprocal implied reverse amplitude of a relation factor. */
export function reverseBeta(beta: number): number {
  return beta === 0 ? 0 : 1 / beta;
}

/** §7.6 implied reverse precision (the factor read in the informer's units). */
export function reversePrecision(precision: number, beta: number): number {
  return precision * beta * beta;
}

/** §8.1 calendar amplitude shape (T_informer / T_receiver)^alphaT. */
export function calendarBeta(
  tReceiver: number,
  tInformer: number,
  alphaT: number,
): number {
  if (tReceiver <= 0 || tInformer <= 0) return 1;
  return (tInformer / tReceiver) ** alphaT;
}

/** §9.2 calendar relation precision families (Phase-0 seeds as defaults). */
export function calendarPrecision(
  tA: number,
  tB: number,
  scale: number,
  epsilon: number,
  decay: "inverse_sqrt_gap" | "constant" | "log_distance",
): number {
  if (decay === "constant") return scale;
  if (decay === "log_distance")
    return tA > 0 && tB > 0 ? scale * Math.exp(-Math.abs(Math.log(tA / tB))) : scale;
  return scale / (epsilon + Math.sqrt(Math.abs(tA - tB)));
}

/** The §8.4 amplitude presets (learned = the Phase-0 day-horizon targets). */
export const AMPLITUDE_PRESETS = {
  desk: { ampCal: 1.0, ampCross: 1.0 },
  learned: { ampCal: 0.23, ampCross: 0.39 },
} as const;
