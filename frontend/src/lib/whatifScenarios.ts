// Canonical what-if scenario shortcuts (P5b U3): deterministic pulse sets a
// user can drop onto the unified test pulse with one click. Each scenario
// picks the RICHEST ticker (most live expiries, alphabetical tie-break) so
// the story reads on any selected universe; a scenario that the universe
// cannot host returns null (its button disables).
//
//   calendar_pulse    — one mid-ladder node +1pt: watch it ride the ladder.
//   competing_signals — +1pt and −1pt around a middle rung: the receiver
//                       takes the precision-weighted average while the
//                       confidences ADD (§21.2/§21.3).
//   cross_basket      — a whole ticker +1pt: watch the cross-asset transfer.
import { nodeKey, type GraphNodeBase } from "../state/useGraph";

/** +1 vol pt in decimal-vol units — every scenario's pulse magnitude. */
const PULSE = 0.01;

export type ScenarioId = "calendar_pulse" | "competing_signals" | "cross_basket";

export interface WhatifScenario {
  id: ScenarioId;
  label: string;
  /** Tooltip: what the scenario demonstrates. */
  description: string;
}

export const SCENARIOS: WhatifScenario[] = [
  {
    id: "calendar_pulse",
    label: "Calendar pulse",
    description:
      "+1.00 pt on one mid-ladder expiry — watch the pulse ride the maturity ladder (β per rung).",
  },
  {
    id: "competing_signals",
    label: "Competing signals",
    description:
      "+1.00 pt and −1.00 pt on the rungs around a middle expiry — the receiver takes the precision-weighted average while the confidences ADD (q = Σp).",
  },
  {
    id: "cross_basket",
    label: "Cross basket",
    description:
      "+1.00 pt on a whole ticker — watch the level move transfer across assets.",
  },
];

/** The richest ticker's ladder (most live expiries; alphabetical tie-break),
 *  sorted by year-fraction ascending. */
function richestLadder(nodes: GraphNodeBase[]): GraphNodeBase[] {
  const by = new Map<string, GraphNodeBase[]>();
  for (const n of nodes) {
    if (n.t > 0) {
      const list = by.get(n.ticker) ?? [];
      list.push(n);
      by.set(n.ticker, list);
    }
  }
  let best: GraphNodeBase[] = [];
  let bestTicker = "";
  for (const [ticker, list] of by) {
    if (
      list.length > best.length ||
      (list.length === best.length && ticker < bestTicker)
    ) {
      best = list;
      bestTicker = ticker;
    }
  }
  return best.slice().sort((a, b) => a.t - b.t);
}

/** The pulse set for a scenario, or null when the universe can't host it. */
export function buildScenario(
  id: ScenarioId,
  nodes: GraphNodeBase[],
): Record<string, number> | null {
  const ladder = richestLadder(nodes);
  if (id === "calendar_pulse") {
    if (ladder.length < 2) return null; // needs a ladder to ride
    const mid = ladder[Math.floor(ladder.length / 2)]!;
    return { [nodeKey(mid.ticker, mid.expiry)]: PULSE };
  }
  if (id === "competing_signals") {
    if (ladder.length < 3) return null; // needs a rung BETWEEN the signals
    const lo = ladder[0]!;
    const hi = ladder[2]!;
    return {
      [nodeKey(lo.ticker, lo.expiry)]: PULSE,
      [nodeKey(hi.ticker, hi.expiry)]: -PULSE,
    };
  }
  // cross_basket: the whole richest ticker, +1pt — needs somewhere to send it.
  const tickers = new Set(nodes.map((n) => n.ticker));
  if (ladder.length === 0 || tickers.size < 2) return null;
  return Object.fromEntries(ladder.map((n) => [nodeKey(n.ticker, n.expiry), PULSE]));
}
