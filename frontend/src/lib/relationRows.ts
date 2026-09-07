// Relation-row helpers for the Graph Ergonomics canvas editor (E1, roadmap
// "GRAPH ERGONOMICS ARC"). Pure data-shape utilities over MessageEdgeRow —
// no React, no DOM — shared by the connect gesture, the relation inspector,
// the templates and the chart topology mapper (useGraphTopology.ts).
import type { MessageEdgeRow, RelationClass } from "../state/useMessageEdges";
import type { LayoutEdgeIn } from "./graphLayout";
import { reverseBeta, reversePrecision } from "./messagePreview";

export interface NodeRef {
  ticker: string;
  expiry: string;
}

/** Directed identity "S|sExp>T|tExp" (the U6 diff key; mirrors
 *  useMessageConfig.ts's rowKey so both stay interchangeable). */
export function relationKey(r: MessageEdgeRow): string {
  return `${r.sourceTicker}|${r.sourceExpiry}>${r.targetTicker}|${r.targetExpiry}`;
}

/** Inverse of relationKey; null for anything malformed. */
export function parseRelationKey(key: string): { source: NodeRef; target: NodeRef } | null {
  const parts = key.split(">");
  if (parts.length !== 2) return null;
  const [sourcePart, targetPart] = parts;
  const sourceFields = sourcePart.split("|");
  const targetFields = targetPart.split("|");
  if (sourceFields.length !== 2 || targetFields.length !== 2) return null;
  const [sourceTicker, sourceExpiry] = sourceFields;
  const [targetTicker, targetExpiry] = targetFields;
  if (!sourceTicker || !sourceExpiry || !targetTicker || !targetExpiry) return null;
  return {
    source: { ticker: sourceTicker, expiry: sourceExpiry },
    target: { ticker: targetTicker, expiry: targetExpiry },
  };
}

/** Same ticker -> "calendar"; else "custom" (or "broad_index" when the
 *  SOURCE ticker is a hub, e.g. an index/ETF the desk names explicitly). */
export function inferRelationClass(
  source: NodeRef,
  target: NodeRef,
  hubs?: readonly string[],
): RelationClass {
  if (source.ticker === target.ticker) return "calendar";
  if (hubs !== undefined && hubs.includes(source.ticker)) return "broad_index";
  return "custom";
}

/**
 * A fresh row for a connect gesture source -> target: β 1/1/1; a same-ticker
 * (calendar) relation gets precisionRule "calendar_distance" and a
 * placeholder messagePrecision (the §9.2 maturity-gap rule re-derives the
 * real number at solve time); any other class is "explicit" at the desk's
 * cross-relation precision. Returns null for a self-loop (source === target).
 */
export function newRelationRow(
  source: NodeRef,
  target: NodeRef,
  scales: { calPrecision: number; crossPrecision: number },
  cls?: RelationClass,
): MessageEdgeRow | null {
  if (source.ticker === target.ticker && source.expiry === target.expiry) return null;
  const relationClass = cls ?? inferRelationClass(source, target);
  const isCalendar = relationClass === "calendar";
  return {
    sourceTicker: source.ticker,
    sourceExpiry: source.expiry,
    targetTicker: target.ticker,
    targetExpiry: target.expiry,
    messagePrecision: isCalendar ? scales.calPrecision : scales.crossPrecision,
    betaAtmVol: 1,
    betaSkew: 1,
    betaCurv: 1,
    relationClass,
    precisionRule: isCalendar ? "calendar_distance" : "explicit",
    relationSemantics: null,
  };
}

/**
 * Reverse the direction with the §7.6/§8.3 one-factor identities: swap
 * source/target, β -> 1/β per handle (0 stays 0 — reverseBeta's convention),
 * and an EXPLICIT precision re-expresses in the new receiver's units as
 * p·β_atm² (reversePrecision). A "calendar_distance" row keeps its rule and
 * its number — the maturity-gap formula is symmetric in the two expiries, so
 * re-deriving at solve time already gives the flipped answer.
 */
export function flipRelation(r: MessageEdgeRow): MessageEdgeRow {
  const messagePrecision =
    r.precisionRule === "calendar_distance"
      ? r.messagePrecision
      : reversePrecision(r.messagePrecision, r.betaAtmVol);
  return {
    ...r,
    sourceTicker: r.targetTicker,
    sourceExpiry: r.targetExpiry,
    targetTicker: r.sourceTicker,
    targetExpiry: r.sourceExpiry,
    messagePrecision,
    betaAtmVol: reverseBeta(r.betaAtmVol),
    betaSkew: reverseBeta(r.betaSkew),
    betaCurv: reverseBeta(r.betaCurv),
  };
}

/** Chart topology from rows: `from` = the RECEIVER (target), `to` = the
 *  INFORMER (source), weight = messagePrecision, beta = betaAtmVol — the
 *  same convention useGraphTopology.ts already builds by hand. */
export function rowsToLayoutEdges(rows: MessageEdgeRow[]): LayoutEdgeIn[] {
  return rows.map((r) => ({
    fromTicker: r.targetTicker,
    fromExpiry: r.targetExpiry,
    toTicker: r.sourceTicker,
    toExpiry: r.sourceExpiry,
    weight: r.messagePrecision,
    beta: r.betaAtmVol,
  }));
}

/** Rows between two tickers (cross only — same-ticker/calendar rows are
 *  excluded even when a === b), either direction. */
export function rowsForTickerPair(
  rows: MessageEdgeRow[],
  a: string,
  b: string,
): MessageEdgeRow[] {
  return rows.filter(
    (r) =>
      r.sourceTicker !== r.targetTicker &&
      ((r.sourceTicker === a && r.targetTicker === b) ||
        (r.sourceTicker === b && r.targetTicker === a)),
  );
}

/** Rows joining two expiries of one ticker (either direction). */
export function rowsForCalendarPair(
  rows: MessageEdgeRow[],
  ticker: string,
  e1: string,
  e2: string,
): MessageEdgeRow[] {
  return rows.filter(
    (r) =>
      r.sourceTicker === ticker &&
      r.targetTicker === ticker &&
      ((r.sourceExpiry === e1 && r.targetExpiry === e2) ||
        (r.sourceExpiry === e2 && r.targetExpiry === e1)),
  );
}

/** Replace-or-append by relationKey. Returns a new array; existing rows keep
 *  their position, appended (genuinely new) rows land last. A repeated key
 *  within `incoming` itself collapses to its LAST occurrence (Map semantics). */
export function upsertRows(
  rows: MessageEdgeRow[],
  incoming: MessageEdgeRow[],
): MessageEdgeRow[] {
  const incomingByKey = new Map(incoming.map((r) => [relationKey(r), r]));
  const used = new Set<string>();
  const result = rows.map((r) => {
    const key = relationKey(r);
    const replacement = incomingByKey.get(key);
    if (replacement === undefined) return r;
    used.add(key);
    return replacement;
  });
  for (const [key, r] of incomingByKey) {
    if (used.has(key)) continue;
    result.push(r);
  }
  return result;
}
