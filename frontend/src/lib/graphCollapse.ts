// Collapsible ticker pods (Graph Ergonomics E1, roadmap "GRAPH ERGONOMICS
// ARC" ruling "pods collapse / expand per ticker"): folds every expiry of a
// collapsed ticker into ONE synthetic node so a busy universe reads as N
// pods instead of N x M nodes. Pure math — no React, no DOM — driven by a
// caller-held `collapsed` set of ticker names; the chart, the result panel
// and the lit map each run their payload through the matching aggregator
// keyed on the same `members` map.
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import type { LayoutEdgeIn } from "./graphLayout";

/** Placeholder expiry of a collapsed ticker's synthetic node. */
export const COLLAPSED_EXPIRY = "*";

/** The synthetic node key of a collapsed ticker (nodeKey's own format). */
export const collapsedKey = (ticker: string): string => `${ticker}|${COLLAPSED_EXPIRY}`;

/** True when `key` names a collapsed-pod synthetic node. */
export function isCollapsedKey(key: string): boolean {
  return key.endsWith(`|${COLLAPSED_EXPIRY}`);
}

export interface CollapsedUniverse {
  /** Real nodes of expanded tickers + one synthetic node per collapsed ticker. */
  nodes: GraphNodeBase[];
  /** Edges with collapsed-ticker endpoints remapped to their synthetic node. */
  edges: LayoutEdgeIn[];
  /** Collapsed key -> member node keys, input order. */
  members: Map<string, string[]>;
  /** Real node key -> the key it is drawn under (itself when not collapsed). */
  displayKeyOf: (key: string) => string;
}

/** `${ticker}|${expiry}` — matches useGraph.ts's nodeKey without importing
 *  that (React-bearing) module into this pure lib. */
const keyOf = (ticker: string, expiry: string): string => `${ticker}|${expiry}`;

function splitKey(key: string): [string, string] {
  const i = key.indexOf("|");
  return i < 0 ? [key, ""] : [key.slice(0, i), key.slice(i + 1)];
}

function mean(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((s, v) => s + v, 0) / values.length;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

/** Fold `collapsed` tickers' nodes/edges into their synthetic pod. An empty
 *  `collapsed` set is a no-op (the same node/edge arrays, identity-equal). */
export function collapseUniverse(
  nodes: GraphNodeBase[],
  edges: LayoutEdgeIn[],
  collapsed: ReadonlySet<string>,
): CollapsedUniverse {
  if (collapsed.size === 0) {
    return { nodes, edges, members: new Map(), displayKeyOf: (key) => key };
  }

  const members = new Map<string, string[]>();
  const displayKey = new Map<string, string>(); // real key -> display key
  const outNodes: GraphNodeBase[] = [];
  const byTicker = new Map<string, GraphNodeBase[]>();

  for (const n of nodes) {
    const key = keyOf(n.ticker, n.expiry);
    if (collapsed.has(n.ticker)) {
      displayKey.set(key, collapsedKey(n.ticker));
      let group = byTicker.get(n.ticker);
      if (group === undefined) {
        group = [];
        byTicker.set(n.ticker, group);
      }
      group.push(n);
    } else {
      displayKey.set(key, key);
      outNodes.push(n);
    }
  }

  for (const [ticker, group] of byTicker) {
    const dKey = collapsedKey(ticker);
    members.set(dKey, group.map((n) => keyOf(n.ticker, n.expiry)));
    outNodes.push({
      ticker,
      expiry: COLLAPSED_EXPIRY,
      t: median(group.map((n) => n.t)),
      atmVol: mean(group.map((n) => n.atmVol)),
      skew: mean(group.map((n) => n.skew)),
      curvature: mean(group.map((n) => n.curvature)),
      lit: group.some((n) => n.lit),
    });
  }

  const displayKeyOf = (key: string): string => displayKey.get(key) ?? key;

  // Remap edges through the display key: drop anything fully inside one
  // collapsed pod, merge exact-direction duplicates (weight summed, beta the
  // |weight|-weighted mean — 1 when the merged group carries no weight).
  interface Acc extends LayoutEdgeIn {
    betaNum: number;
    betaDen: number;
  }
  const remapped = new Map<string, Acc>();
  for (const e of edges) {
    const fromKey = displayKeyOf(keyOf(e.fromTicker, e.fromExpiry));
    const toKey = displayKeyOf(keyOf(e.toTicker, e.toExpiry));
    if (fromKey === toKey) continue; // fully inside one collapsed pod
    const pairKey = `${fromKey}>${toKey}`;
    const [fromTicker, fromExpiry] = splitKey(fromKey);
    const [toTicker, toExpiry] = splitKey(toKey);
    const w = Math.abs(e.weight);
    const beta = e.beta ?? 1;
    const existing = remapped.get(pairKey);
    if (existing === undefined) {
      remapped.set(pairKey, {
        fromTicker, fromExpiry, toTicker, toExpiry,
        weight: e.weight,
        beta,
        betaNum: w * beta,
        betaDen: w,
      });
    } else {
      existing.weight += e.weight;
      existing.betaNum += w * beta;
      existing.betaDen += w;
    }
  }
  const outEdges: LayoutEdgeIn[] = [...remapped.values()].map((r) => ({
    fromTicker: r.fromTicker, fromExpiry: r.fromExpiry,
    toTicker: r.toTicker, toExpiry: r.toExpiry,
    weight: r.weight,
    beta: r.betaDen > 0 ? r.betaNum / r.betaDen : 1,
  }));

  return { nodes: outNodes, edges: outEdges, members, displayKeyOf };
}

/** Adds one aggregated entry per collapsed key to a solve-result map (real
 *  per-node entries are kept alongside it): shiftBp/base/post/band are means
 *  over members that HAVE a result, sd is the max (never understate risk),
 *  observed is true if any member was, t is the median. A collapsed pod with
 *  no scored member gets no aggregated entry. `null` (no solve yet) -> `null`. */
export function aggregateResults(
  results: Record<string, GraphSolveNode> | null,
  members: Map<string, string[]>,
): Record<string, GraphSolveNode> | null {
  if (results === null) return null;
  const out: Record<string, GraphSolveNode> = { ...results };
  for (const [dKey, memberKeys] of members) {
    const rows = memberKeys
      .map((k) => results[k])
      .filter((r): r is GraphSolveNode => r !== undefined);
    if (rows.length === 0) continue;
    const [ticker, expiry] = splitKey(dKey);
    out[dKey] = {
      ticker,
      expiry,
      t: median(rows.map((r) => r.t)),
      baseAtmVol: mean(rows.map((r) => r.baseAtmVol)),
      postAtmVol: mean(rows.map((r) => r.postAtmVol)),
      shiftBp: mean(rows.map((r) => r.shiftBp)),
      sd: Math.max(...rows.map((r) => r.sd)),
      bandLo: mean(rows.map((r) => r.bandLo)),
      bandHi: mean(rows.map((r) => r.bandHi)),
      observed: rows.some((r) => r.observed),
    };
  }
  return out;
}

/** Collapsed key -> mean dAtmVol of its LIT members (absent when none lit);
 *  real entries are kept alongside it. */
export function aggregateLit(
  lit: Record<string, number>,
  members: Map<string, string[]>,
): Record<string, number> {
  const out: Record<string, number> = { ...lit };
  for (const [dKey, memberKeys] of members) {
    const values = memberKeys.filter((k) => k in lit).map((k) => lit[k]);
    if (values.length === 0) continue;
    out[dKey] = mean(values);
  }
  return out;
}
