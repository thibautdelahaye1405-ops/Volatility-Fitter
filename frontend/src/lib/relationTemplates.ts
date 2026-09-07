// One-click relation playbooks for the Graph Ergonomics canvas (E1, roadmap
// "GRAPH ERGONOMICS ARC"): a trader picks a template instead of hand-drawing
// every arrow in a large universe. Pure data-shape transforms over
// MessageEdgeRow — no React, no DOM — layered on relationRows.ts's identity
// and upsert helpers so a template never duplicates or silently drops a row.
import type { MessageEdgeRow } from "../state/useMessageEdges";
import { relationKey, upsertRows } from "./relationRows";

export type TemplateId = "hub_to_names" | "peers" | "calendar_only";

export interface RelationTemplate {
  id: TemplateId;
  label: string;
  description: string;
  needsHub: boolean;
}

export const TEMPLATES: readonly RelationTemplate[] = [
  {
    id: "hub_to_names",
    label: "Hub → names",
    description: "Connect a named index/ETF to every other ticker's matching expiry.",
    needsHub: true,
  },
  {
    id: "peers",
    label: "Peers ⇄",
    description: "Connect every pair of tickers at their shared expiries.",
    needsHub: false,
  },
  {
    id: "calendar_only",
    label: "Calendar only",
    description: "Drop every cross-ticker relation, keeping calendar edges.",
    needsHub: false,
  },
];

export interface TemplateContext {
  nodes: { ticker: string; expiry: string }[];
  rows: MessageEdgeRow[];
  crossPrecision: number;
  hub?: string;
}

/** Tickers of the context in first-appearance order. */
export function contextTickers(ctx: TemplateContext): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const n of ctx.nodes) {
    if (seen.has(n.ticker)) continue;
    seen.add(n.ticker);
    out.push(n.ticker);
  }
  return out;
}

/** Ticker -> its set of expiries present in the context. */
function expiriesByTicker(ctx: TemplateContext): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  for (const n of ctx.nodes) {
    let s = out.get(n.ticker);
    if (s === undefined) {
      s = new Set();
      out.set(n.ticker, s);
    }
    s.add(n.expiry);
  }
  return out;
}

/** A default cross row a -> b at one shared expiry, β 1/1/1, explicit. */
function crossRow(
  sourceTicker: string,
  targetTicker: string,
  expiry: string,
  relationClass: MessageEdgeRow["relationClass"],
  crossPrecision: number,
): MessageEdgeRow {
  return {
    sourceTicker, sourceExpiry: expiry,
    targetTicker, targetExpiry: expiry,
    messagePrecision: crossPrecision,
    betaAtmVol: 1, betaSkew: 1, betaCurv: 1,
    relationClass,
    precisionRule: "explicit",
    relationSemantics: null,
  };
}

/**
 * Returns the NEW full row list (never mutates `ctx.rows`):
 *  - hub_to_names: every non-hub ticker, every expiry SHARED with the hub ->
 *    a hub -> name row (class "broad_index"), upserted over the existing rows.
 *    No hub, or a hub absent from the context, returns the rows unchanged.
 *  - peers: every unordered ticker pair, every shared expiry -> ONE row
 *    a -> b (a < b, class "sector_peer"); a pre-existing mirror b -> a peer
 *    row of the same pair/expiry is dropped first so the relation is never
 *    double-counted.
 *  - calendar_only: keeps only calendar-class rows.
 */
export function applyTemplate(id: TemplateId, ctx: TemplateContext): MessageEdgeRow[] {
  if (id === "calendar_only") {
    return ctx.rows.filter((r) => r.relationClass === "calendar");
  }

  const tickers = contextTickers(ctx);
  const expiries = expiriesByTicker(ctx);

  if (id === "hub_to_names") {
    const hub = ctx.hub;
    if (hub === undefined || !tickers.includes(hub)) return ctx.rows;
    const hubExpiries = expiries.get(hub) ?? new Set<string>();
    const newRows: MessageEdgeRow[] = [];
    for (const ticker of tickers) {
      if (ticker === hub) continue;
      for (const expiry of expiries.get(ticker) ?? []) {
        if (!hubExpiries.has(expiry)) continue;
        newRows.push(crossRow(hub, ticker, expiry, "broad_index", ctx.crossPrecision));
      }
    }
    return upsertRows(ctx.rows, newRows);
  }

  // peers
  const newRows: MessageEdgeRow[] = [];
  for (let i = 0; i < tickers.length; i++) {
    for (let j = i + 1; j < tickers.length; j++) {
      const [a, b] = tickers[i] < tickers[j] ? [tickers[i], tickers[j]] : [tickers[j], tickers[i]];
      const expA = expiries.get(a) ?? new Set<string>();
      const expB = expiries.get(b) ?? new Set<string>();
      for (const expiry of expA) {
        if (!expB.has(expiry)) continue;
        newRows.push(crossRow(a, b, expiry, "sector_peer", ctx.crossPrecision));
      }
    }
  }
  // A pre-existing b -> a peer row would double-count the same undirected
  // relation once a -> b lands (upsertRows only replaces exact-direction
  // matches), so drop those mirrors before upserting.
  const mirrorKeys = new Set(
    newRows.map((r) =>
      relationKey({
        ...r,
        sourceTicker: r.targetTicker, sourceExpiry: r.targetExpiry,
        targetTicker: r.sourceTicker, targetExpiry: r.sourceExpiry,
      }),
    ),
  );
  const withoutMirrors = ctx.rows.filter(
    (r) => !(r.relationClass === "sector_peer" && mirrorKeys.has(relationKey(r))),
  );
  return upsertRows(withoutMirrors, newRows);
}
