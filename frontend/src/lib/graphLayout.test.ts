// Ticker-pod force layout: determinism, spine geometry, pod separation,
// edge aggregation (bundles + calendar), pair drill-down and framing.
import { describe, expect, it } from "vitest";
import { computeGraphLayout } from "./graphLayout";
import type { BundleEdge, GraphLayout, LayoutEdgeIn, LayoutNode } from "./graphLayout";

/* --------------------------- synthetic universe --------------------------- */

const E1 = "2026-08-21"; // t = 0.12
const E2 = "2026-09-18"; // t = 0.20
const E3 = "2026-12-18"; // t = 0.45
const E4 = "2027-06-18"; // t = 0.95
const T: Record<string, number> = { [E1]: 0.12, [E2]: 0.2, [E3]: 0.45, [E4]: 0.95 };

function n(ticker: string, expiry: string): LayoutNode {
  return { ticker, expiry, t: T[expiry] };
}

function e(
  fromTicker: string, fromExpiry: string,
  toTicker: string, toExpiry: string,
  weight: number,
): LayoutEdgeIn {
  return { fromTicker, fromExpiry, toTicker, toExpiry, weight };
}

// 5 tickers; SPX carries 4 expiries (deliberately listed out of t order to
// prove the spine sorts), the rest carry 3.
const NODES: LayoutNode[] = [
  n("SPX", E1), n("SPX", E3), n("SPX", E2), n("SPX", E4),
  n("NDX", E1), n("NDX", E2), n("NDX", E3),
  n("AAPL", E1), n("AAPL", E2), n("AAPL", E3),
  n("MSFT", E1), n("MSFT", E2), n("MSFT", E3),
  n("TSLA", E1), n("TSLA", E2), n("TSLA", E3),
];

const EDGES: LayoutEdgeIn[] = [
  // SPX calendar: both directions on the first hop (max rule picks 10).
  e("SPX", E1, "SPX", E2, 10), e("SPX", E2, "SPX", E1, 4),
  e("SPX", E2, "SPX", E3, 8), e("SPX", E3, "SPX", E4, 6),
  // NDX calendar chain.
  e("NDX", E1, "NDX", E2, 9), e("NDX", E2, "NDX", E3, 7),
  // AAPL: first hop only — the E2–E3 hop must appear as a zero-weight filler.
  e("AAPL", E1, "AAPL", E2, 5),
  // MSFT full chain; TSLA has no calendar edges at all (both hops fillers).
  e("MSFT", E1, "MSFT", E2, 3), e("MSFT", E2, "MSFT", E3, 2),
  // Cross pairs: SPX↔NDX both directions, the rest one-way; one negative
  // weight to prove |weight| aggregation.
  e("SPX", E1, "NDX", E1, 5), e("NDX", E2, "SPX", E2, 3),
  e("SPX", E1, "AAPL", E1, 2),
  e("NDX", E3, "AAPL", E1, -4),
  e("MSFT", E1, "TSLA", E1, 1.5),
];

/** Bundle of an unordered ticker pair (fails loudly when absent). */
function bundleOf(layout: GraphLayout, a: string, b: string): BundleEdge {
  const [lo, hi] = a < b ? [a, b] : [b, a];
  const found = layout.bundles.find((x) => x.fromTicker === lo && x.toTicker === hi);
  expect(found).toBeDefined();
  return found as BundleEdge;
}

/* --------------------------------- tests ---------------------------------- */

describe("computeGraphLayout determinism", () => {
  it("gives deep-equal output on two calls with the same inputs", () => {
    const a = computeGraphLayout(NODES, EDGES);
    const b = computeGraphLayout(NODES, EDGES);
    expect(b.pods).toEqual(a.pods);
    expect(b.bundles).toEqual(a.bundles);
    expect(b.calendar).toEqual(a.calendar);
    expect(b.width).toBe(a.width);
    expect(b.height).toBe(a.height);
    expect([...b.nodePos.entries()]).toEqual([...a.nodePos.entries()]);
    expect(b.pairDetails("SPX", "NDX")).toEqual(a.pairDetails("SPX", "NDX"));
  });
});

describe("pod spines", () => {
  const layout = computeGraphLayout(NODES, EDGES);

  it("orders each spine by ascending t, y strictly increasing, x on the center line", () => {
    for (const pod of layout.pods) {
      for (let i = 0; i < pod.nodes.length; i++) {
        expect(pod.nodes[i].x).toBe(pod.cx);
        if (i > 0) {
          expect(pod.nodes[i].t).toBeGreaterThan(pod.nodes[i - 1].t);
          expect(pod.nodes[i].y).toBeGreaterThan(pod.nodes[i - 1].y);
        }
      }
    }
    // SPX was fed out of order — the spine must still read E1..E4 downwards.
    const spx = layout.pods.find((p) => p.ticker === "SPX");
    expect(spx?.nodes.map((x) => x.expiry)).toEqual([E1, E2, E3, E4]);
  });

  it("keeps every pod pair separated by at least rA + rB + 10", () => {
    for (let i = 0; i < layout.pods.length; i++) {
      for (let j = i + 1; j < layout.pods.length; j++) {
        const a = layout.pods[i];
        const b = layout.pods[j];
        const d = Math.hypot(a.cx - b.cx, a.cy - b.cy);
        expect(d).toBeGreaterThanOrEqual(a.radius + b.radius + 10);
      }
    }
  });
});

describe("bundle aggregation", () => {
  const layout = computeGraphLayout(NODES, EDGES);

  it("sums |weight| both directions with counts and bidirectional flags", () => {
    const spxNdx = bundleOf(layout, "SPX", "NDX");
    expect(spxNdx.totalWeight).toBeCloseTo(8, 12); // 5 + 3
    expect(spxNdx.count).toBe(2);
    expect(spxNdx.bidirectional).toBe(true);

    const spxAapl = bundleOf(layout, "AAPL", "SPX");
    expect(spxAapl.totalWeight).toBeCloseTo(2, 12);
    expect(spxAapl.count).toBe(1);
    expect(spxAapl.bidirectional).toBe(false);

    const ndxAapl = bundleOf(layout, "NDX", "AAPL");
    expect(ndxAapl.totalWeight).toBeCloseTo(4, 12); // |-4|
    expect(ndxAapl.count).toBe(1);
    expect(ndxAapl.bidirectional).toBe(false);

    const msftTsla = bundleOf(layout, "TSLA", "MSFT"); // argument order-free
    expect(msftTsla.totalWeight).toBeCloseTo(1.5, 12);
    expect(layout.bundles).toHaveLength(4);
  });

  it("names pairs lexicographically and anchors ends on the pod circles", () => {
    for (const b of layout.bundles) {
      expect(b.fromTicker < b.toTicker).toBe(true);
      const pa = layout.pods.find((p) => p.ticker === b.fromTicker);
      const pb = layout.pods.find((p) => p.ticker === b.toTicker);
      expect(Math.hypot(b.x1 - (pa?.cx ?? 0), b.y1 - (pa?.cy ?? 0))).toBeCloseTo(pa?.radius ?? -1, 6);
      expect(Math.hypot(b.x2 - (pb?.cx ?? 0), b.y2 - (pb?.cy ?? 0))).toBeCloseTo(pb?.radius ?? -1, 6);
    }
  });
});

describe("calendar continuity", () => {
  const layout = computeGraphLayout(NODES, EDGES);

  it("emits one segment per adjacent spine hop, zero-weight fillers included", () => {
    // 3 hops on SPX + 2 on each of the other four tickers.
    expect(layout.calendar).toHaveLength(3 + 2 * 4);
    for (const pod of layout.pods) {
      const hops = layout.calendar.filter((c) => c.ticker === pod.ticker);
      expect(hops.map((c) => [c.fromExpiry, c.toExpiry])).toEqual(
        pod.nodes.slice(1).map((node, i) => [pod.nodes[i].expiry, node.expiry]),
      );
    }
  });

  it("takes max |weight| of the two directions, 0 where no edge exists", () => {
    const weight = (ticker: string, from: string, to: string): number | undefined =>
      layout.calendar.find((c) => c.ticker === ticker && c.fromExpiry === from && c.toExpiry === to)?.weight;
    expect(weight("SPX", E1, E2)).toBe(10); // max(|10|, |4|)
    expect(weight("SPX", E2, E3)).toBe(8);
    expect(weight("AAPL", E1, E2)).toBe(5);
    expect(weight("AAPL", E2, E3)).toBe(0); // filler: spine stays connected
    expect(weight("TSLA", E1, E2)).toBe(0);
    expect(weight("TSLA", E2, E3)).toBe(0);
  });

  it("pins segment endpoints to the node positions", () => {
    for (const c of layout.calendar) {
      const a = layout.nodePos.get(`${c.ticker}|${c.fromExpiry}`);
      const b = layout.nodePos.get(`${c.ticker}|${c.toExpiry}`);
      expect({ x: c.x1, y: c.y1 }).toEqual(a);
      expect({ x: c.x2, y: c.y2 }).toEqual(b);
    }
  });
});

describe("pairDetails", () => {
  const layout = computeGraphLayout(NODES, EDGES);

  it("returns the individual cross edges of a pair, endpoints at node positions", () => {
    const details = layout.pairDetails("SPX", "NDX");
    expect(details).toHaveLength(2);
    const d0 = details.find((d) => d.fromTicker === "SPX");
    const d1 = details.find((d) => d.fromTicker === "NDX"); // both directions present
    expect(d0?.weight).toBe(5);
    expect(d1?.weight).toBe(3);
    for (const d of details) {
      expect({ x: d.x1, y: d.y1 }).toEqual(layout.nodePos.get(`${d.fromTicker}|${d.fromExpiry}`));
      expect({ x: d.x2, y: d.y2 }).toEqual(layout.nodePos.get(`${d.toTicker}|${d.toExpiry}`));
    }
    // Argument order-free; unconnected pairs come back empty.
    expect(layout.pairDetails("NDX", "SPX")).toEqual(details);
    expect(layout.pairDetails("AAPL", "TSLA")).toEqual([]);
  });
});

describe("framing and degenerate inputs", () => {
  it("keeps every node (and pod circle) inside [0,width] x [0,height]", () => {
    const layout = computeGraphLayout(NODES, EDGES);
    for (const { x, y } of layout.nodePos.values()) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(layout.width);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(layout.height);
    }
    for (const p of layout.pods) {
      expect(p.cx - p.radius).toBeGreaterThanOrEqual(0);
      expect(p.cx + p.radius).toBeLessThanOrEqual(layout.width);
      expect(p.cy - p.radius).toBeGreaterThanOrEqual(0);
      expect(p.cy + p.radius).toBeLessThanOrEqual(layout.height);
    }
  });

  it("handles an empty universe without crashing", () => {
    const layout = computeGraphLayout([], []);
    expect(layout.pods).toEqual([]);
    expect(layout.bundles).toEqual([]);
    expect(layout.calendar).toEqual([]);
    expect(layout.nodePos.size).toBe(0);
    expect(layout.width).toBe(200);
    expect(layout.height).toBe(200);
    expect(layout.pairDetails("SPX", "NDX")).toEqual([]);
  });

  it("frames a single pod with margins and no edges", () => {
    const layout = computeGraphLayout([n("SPX", E1), n("SPX", E2)], []);
    expect(layout.pods).toHaveLength(1);
    const pod = layout.pods[0];
    // bbox = the one circle + 40px margin on every side, pod centered.
    expect(layout.width).toBeCloseTo(2 * pod.radius + 80, 9);
    expect(layout.height).toBeCloseTo(2 * pod.radius + 80, 9);
    expect(pod.cx).toBeCloseTo(layout.width / 2, 9);
    expect(pod.cy).toBeCloseTo(layout.height / 2, 9);
    expect(layout.calendar).toEqual([
      expect.objectContaining({ ticker: "SPX", fromExpiry: E1, toExpiry: E2, weight: 0 }),
    ]);
  });
});
