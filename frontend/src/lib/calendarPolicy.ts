// Calendar-policy helpers (P5b U2): the client mirror of the backend's
// per-ticker policy resolution (volfit/api/graph_message.calendar_policy_for)
// and of the auto calendar-ladder expansion (volfit/graph/message.
// expand_calendar_ladder) — canonical receiver = the SHORTER maturity, one
// factor per ADJACENT expiry pair, β = (T_long/T_short)^αT, precision from
// the §9.2 distance family. Powers the policy card's ladder view and the
// |β|-cap warnings; the solver runs the backend copy of this math.
import { calendarBeta, calendarPrecision } from "./messagePreview";
import { sigmaPtsFromPrecision } from "./precisionUnits";
import type { SolverParams } from "../state/useGraph";

/** UI warning threshold: a relation amplifying |β| beyond this is flagged
 *  (a wide maturity gap — check the ladder, consider an override). */
export const BETA_CAP = 3;

/** The resolved calendar policy a ticker's ladder actually runs under
 *  (per-ticker override shape: state/useGraph CalendarOverride). */
export interface EffectiveCalendarPolicy {
  enabled: boolean;
  scale: number;
  alphaT: number;
}

/** Mirror of the backend resolution: global switch gates everything; an
 *  override refines enable/scale/shape for its ticker. */
export function effectiveCalendarPolicy(
  params: SolverParams,
  ticker: string,
): EffectiveCalendarPolicy {
  const o = params.calendarOverrides[ticker];
  return {
    enabled: params.calendarEnabled && (o === undefined || o.enabled),
    scale: o?.precisionScale ?? params.calPrecision,
    alphaT: o?.betaExponent ?? params.alphaT,
  };
}

/** One rung of a ticker's auto calendar ladder (short ← long). */
export interface CalendarRung {
  shortExpiry: string;
  longExpiry: string;
  tShort: number;
  tLong: number;
  /** ATM amplitude β = (T_long/T_short)^αT (receiver = short). */
  beta: number;
  precision: number;
  sigmaPts: number;
  /** |β| exceeds BETA_CAP — surface a warning chip. */
  capped: boolean;
}

/** The auto ladder for one ticker's selected expiries under a policy. */
export function calendarLadder(
  expiries: { expiry: string; t: number }[],
  policy: { alphaT: number; scale: number; epsilon: number; decay: SolverParams["calDecay"] },
): CalendarRung[] {
  const live = expiries.filter((e) => e.t > 0).slice().sort((a, b) => a.t - b.t);
  const rungs: CalendarRung[] = [];
  for (let i = 0; i + 1 < live.length; i++) {
    const s = live[i]!;
    const l = live[i + 1]!;
    const beta = calendarBeta(s.t, l.t, policy.alphaT);
    const precision = calendarPrecision(s.t, l.t, policy.scale, policy.epsilon, policy.decay);
    rungs.push({
      shortExpiry: s.expiry,
      longExpiry: l.expiry,
      tShort: s.t,
      tLong: l.t,
      beta,
      precision,
      sigmaPts: sigmaPtsFromPrecision(precision),
      capped: Math.abs(beta) > BETA_CAP,
    });
  }
  return rungs;
}
