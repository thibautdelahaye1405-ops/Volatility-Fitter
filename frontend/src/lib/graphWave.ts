// Attribution-wave staging for the graph solve cinematics.
//
// The reveal wave is REAL graph distance, not decoration: hop numbers come
// from a breadth-first search that starts at the lit (observed) node set and
// walks the actual solver edge topology as an undirected node-level adjacency.
// The chart reveals the posterior field one hop ring at a time, so information
// visibly arrives in the order the solver's coupling carries it. Pure math —
// no React, no DOM, no clocks, no randomness.
import type { LayoutEdgeIn } from "./graphLayout";

/** BFS distances from the lit set: node key -> hop, plus the largest hop. */
export interface WaveHops {
  hopOf: Map<string, number>;
  maxHop: number;
}

/**
 * Hop distance of every node from the lit (observed) set over the undirected
 * edge topology (node keys `${ticker}|${expiry}`). Lit nodes are hop 0; nodes
 * unreachable from any lit node get maxFiniteHop + 1 so they reveal last,
 * together. An empty lit set stages nothing: every node is hop 0, maxHop 0.
 */
export function waveHops(
  nodeKeys: string[],
  edges: LayoutEdgeIn[],
  litKeys: ReadonlySet<string>,
): WaveHops {
  const hopOf = new Map<string, number>();
  if (litKeys.size === 0) {
    for (const k of nodeKeys) hopOf.set(k, 0);
    return { hopOf, maxHop: 0 };
  }

  // Undirected node-level adjacency over the real edge set.
  const adj = new Map<string, string[]>();
  const link = (a: string, b: string) => {
    const list = adj.get(a);
    if (list === undefined) adj.set(a, [b]);
    else list.push(b);
  };
  for (const e of edges) {
    const from = `${e.fromTicker}|${e.fromExpiry}`;
    const to = `${e.toTicker}|${e.toExpiry}`;
    if (from === to) continue; // a self-loop carries no reveal information
    link(from, to);
    link(to, from);
  }

  // Multi-source BFS from the lit nodes (index walk — no O(n) queue shifts).
  const dist = new Map<string, number>();
  const queue: string[] = [];
  for (const k of nodeKeys) {
    if (litKeys.has(k)) {
      dist.set(k, 0);
      queue.push(k);
    }
  }
  for (let i = 0; i < queue.length; i++) {
    const cur = queue[i];
    const d = dist.get(cur) ?? 0;
    for (const nb of adj.get(cur) ?? []) {
      if (dist.has(nb)) continue;
      dist.set(nb, d + 1);
      queue.push(nb);
    }
  }

  // Assemble over the node universe. maxFinite is measured over the universe
  // only (the BFS may pass through off-universe edge endpoints; those must not
  // inflate the unreachable bucket's hop).
  let maxFinite = 0;
  for (const k of nodeKeys) {
    const h = dist.get(k);
    if (h !== undefined) maxFinite = Math.max(maxFinite, h);
  }
  const unreachableHop = maxFinite + 1;
  let maxHop = 0;
  for (const k of nodeKeys) {
    const h = dist.get(k) ?? unreachableHop;
    hopOf.set(k, h);
    maxHop = Math.max(maxHop, h);
  }
  return { hopOf, maxHop };
}
