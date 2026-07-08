// Attribution-wave BFS staging: chain distances, multi-source min-hop,
// unreachable bucketing and the degenerate empty-lit / empty-edge cases.
import { describe, expect, it } from "vitest";
import { waveHops } from "./graphWave";
import type { LayoutEdgeIn } from "./graphLayout";

const E = ["2026-08-21", "2026-09-18", "2026-12-18", "2027-06-18", "2027-12-17"];

function key(ticker: string, expiry: string): string {
  return `${ticker}|${expiry}`;
}

function e(
  fromTicker: string, fromExpiry: string,
  toTicker: string, toExpiry: string,
): LayoutEdgeIn {
  return { fromTicker, fromExpiry, toTicker, toExpiry, weight: 1 };
}

/** SPX calendar chain over the first n expiries (one edge per adjacent hop). */
function chain(n: number): { keys: string[]; edges: LayoutEdgeIn[] } {
  const keys = E.slice(0, n).map((x) => key("SPX", x));
  const edges = E.slice(0, n - 1).map((x, i) => e("SPX", x, "SPX", E[i + 1]));
  return { keys, edges };
}

describe("waveHops", () => {
  it("counts chain hops from a single lit source (direction-free)", () => {
    const { keys, edges } = chain(4);
    // Reverse one edge to prove the adjacency is undirected.
    edges[2] = e("SPX", E[3], "SPX", E[2]);
    const { hopOf, maxHop } = waveHops(keys, edges, new Set([keys[0]]));
    expect(keys.map((k) => hopOf.get(k))).toEqual([0, 1, 2, 3]);
    expect(maxHop).toBe(3);
  });

  it("takes the minimum hop when two lit sources meet in the middle", () => {
    const { keys, edges } = chain(5);
    const lit = new Set([keys[0], keys[4]]);
    const { hopOf, maxHop } = waveHops(keys, edges, lit);
    expect(keys.map((k) => hopOf.get(k))).toEqual([0, 1, 2, 1, 0]);
    expect(maxHop).toBe(2);
  });

  it("buckets unreachable nodes at maxFiniteHop + 1 (they reveal last)", () => {
    const { keys, edges } = chain(3); // hops 0, 1, 2 from the first node
    const island = key("NDX", E[0]); // no edges touch it
    const { hopOf, maxHop } = waveHops([...keys, island], edges, new Set([keys[0]]));
    expect(hopOf.get(island)).toBe(3); // maxFinite 2 + 1
    expect(maxHop).toBe(3);
  });

  it("stages nothing on an empty lit set: everything hop 0", () => {
    const { keys, edges } = chain(4);
    const { hopOf, maxHop } = waveHops(keys, edges, new Set());
    for (const k of keys) expect(hopOf.get(k)).toBe(0);
    expect(maxHop).toBe(0);
  });

  it("puts every non-lit node at hop 1 when there are no edges", () => {
    const keys = E.slice(0, 3).map((x) => key("SPX", x));
    const { hopOf, maxHop } = waveHops(keys, [], new Set([keys[1]]));
    expect(keys.map((k) => hopOf.get(k))).toEqual([1, 0, 1]);
    expect(maxHop).toBe(1);
  });
});
