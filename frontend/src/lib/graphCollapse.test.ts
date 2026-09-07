// Collapsible ticker pods: an empty collapse set is a no-op, a collapsed
// pod folds its expiries into one synthetic node, cross edges remap through
// it (merging exact-direction duplicates, dropping intra-pod edges), and the
// result/lit aggregators mirror the same `members` map.
import { describe, expect, it } from "vitest";
import {
  aggregateLit,
  aggregateResults,
  collapsedKey,
  COLLAPSED_EXPIRY,
  collapseUniverse,
  isCollapsedKey,
} from "./graphCollapse";
import type { GraphNodeBase, GraphSolveNode } from "../state/useGraph";
import type { LayoutEdgeIn } from "./graphLayout";

const E1 = "2026-09-18";
const E2 = "2026-12-18";

function node(over: Partial<GraphNodeBase> & Pick<GraphNodeBase, "ticker" | "expiry">): GraphNodeBase {
  return { t: 0, atmVol: 0.2, skew: 0, curvature: 0, lit: false, ...over };
}

// 3 tickers: SPX (2 expiries, will be collapsed), NDX and AAPL (1 each).
const NODES: GraphNodeBase[] = [
  node({ ticker: "SPX", expiry: E1, t: 0.1, atmVol: 0.2, skew: -0.1, curvature: 0.05, lit: true }),
  node({ ticker: "SPX", expiry: E2, t: 0.3, atmVol: 0.22, skew: -0.12, curvature: 0.06, lit: false }),
  node({ ticker: "NDX", expiry: E1, t: 0.1, atmVol: 0.25, skew: -0.15, curvature: 0.07, lit: false }),
  node({ ticker: "AAPL", expiry: E1, t: 0.1, atmVol: 0.3, skew: -0.2, curvature: 0.08, lit: true }),
];

const EDGES: LayoutEdgeIn[] = [
  // Calendar inside SPX — dropped once SPX collapses (both ends fold to the
  // same synthetic node).
  { fromTicker: "SPX", fromExpiry: E1, toTicker: "SPX", toExpiry: E2, weight: 5, beta: 1.2 },
  // Two SPX->NDX cross edges (different SPX expiries) — merge into one once
  // SPX collapses (same direction, same endpoints post-remap).
  { fromTicker: "SPX", fromExpiry: E1, toTicker: "NDX", toExpiry: E1, weight: 3, beta: 0.8 },
  { fromTicker: "SPX", fromExpiry: E2, toTicker: "NDX", toExpiry: E1, weight: 2, beta: 1.5 },
  // Untouched by the SPX collapse.
  { fromTicker: "NDX", fromExpiry: E1, toTicker: "AAPL", toExpiry: E1, weight: 1 }, // no beta -> counts as 1
  // A distinct SPX->AAPL edge — must NOT merge with the SPX->NDX pair.
  { fromTicker: "SPX", fromExpiry: E1, toTicker: "AAPL", toExpiry: E1, weight: 4, beta: 2 },
];

describe("collapsedKey / isCollapsedKey", () => {
  it("names the synthetic node and recognizes it", () => {
    expect(collapsedKey("SPX")).toBe(`SPX|${COLLAPSED_EXPIRY}`);
    expect(isCollapsedKey("SPX|*")).toBe(true);
    expect(isCollapsedKey("SPX|2026-09-18")).toBe(false);
  });
});

describe("collapseUniverse — empty set", () => {
  it("is a no-op: identity-equal nodes/edges, no members", () => {
    const collapsed = new Set<string>();
    const out = collapseUniverse(NODES, EDGES, collapsed);
    expect(out.nodes).toBe(NODES);
    expect(out.edges).toBe(EDGES);
    expect(out.members.size).toBe(0);
    expect(out.displayKeyOf("SPX|2026-09-18")).toBe("SPX|2026-09-18");
  });
});

describe("collapseUniverse — one collapsed ticker", () => {
  const collapsed = new Set(["SPX"]);
  const out = collapseUniverse(NODES, EDGES, collapsed);

  it("keeps expanded-ticker nodes and adds one synthetic SPX node", () => {
    expect(out.nodes).toHaveLength(3); // NDX, AAPL, SPX*
    const ndx = out.nodes.find((n) => n.ticker === "NDX");
    const aapl = out.nodes.find((n) => n.ticker === "AAPL");
    expect(ndx).toEqual(NODES[2]);
    expect(aapl).toEqual(NODES[3]);

    const spx = out.nodes.find((n) => n.ticker === "SPX");
    expect(spx?.expiry).toBe(COLLAPSED_EXPIRY);
    expect(spx?.t).toBeCloseTo(0.2, 12); // median(0.1, 0.3)
    expect(spx?.atmVol).toBeCloseTo(0.21, 12); // mean(0.20, 0.22)
    expect(spx?.skew).toBeCloseTo(-0.11, 12);
    expect(spx?.curvature).toBeCloseTo(0.055, 12);
    expect(spx?.lit).toBe(true); // E1 is lit
    expect(spx?.effectiveAsOf).toBeUndefined();
  });

  it("maps members and displayKeyOf", () => {
    expect(out.members.get("SPX|*")).toEqual(["SPX|2026-09-18", "SPX|2026-12-18"]);
    expect(out.displayKeyOf("SPX|2026-09-18")).toBe("SPX|*");
    expect(out.displayKeyOf("SPX|2026-12-18")).toBe("SPX|*");
    expect(out.displayKeyOf("NDX|2026-09-18")).toBe("NDX|2026-09-18");
  });

  it("drops the intra-pod edge, merges the SPX->NDX duplicate, keeps SPX->AAPL separate", () => {
    expect(out.edges).toHaveLength(3);

    const spxNdx = out.edges.find((e) => e.fromTicker === "SPX" && e.toTicker === "NDX");
    expect(spxNdx).toEqual({
      fromTicker: "SPX", fromExpiry: "*", toTicker: "NDX", toExpiry: E1,
      weight: 5, // 3 + 2
      beta: 1.08, // (3*0.8 + 2*1.5) / 5
    });

    const spxAapl = out.edges.find((e) => e.fromTicker === "SPX" && e.toTicker === "AAPL");
    expect(spxAapl).toEqual({
      fromTicker: "SPX", fromExpiry: "*", toTicker: "AAPL", toExpiry: E1,
      weight: 4, beta: 2,
    });

    const ndxAapl = out.edges.find((e) => e.fromTicker === "NDX" && e.toTicker === "AAPL");
    expect(ndxAapl).toEqual({
      fromTicker: "NDX", fromExpiry: E1, toTicker: "AAPL", toExpiry: E1,
      weight: 1, beta: 1, // no input beta -> counts as 1
    });
  });
});

describe("aggregateResults", () => {
  const members = collapseUniverse(NODES, EDGES, new Set(["SPX"])).members;

  const spxE1: GraphSolveNode = {
    ticker: "SPX", expiry: E1, t: 0.1,
    baseAtmVol: 0.2, postAtmVol: 0.19, shiftBp: -100, sd: 0.01,
    bandLo: 0.18, bandHi: 0.2, observed: true,
  };
  const spxE2: GraphSolveNode = {
    ticker: "SPX", expiry: E2, t: 0.3,
    baseAtmVol: 0.22, postAtmVol: 0.225, shiftBp: 50, sd: 0.02,
    bandLo: 0.21, bandHi: 0.24, observed: false,
  };
  const ndxE1: GraphSolveNode = {
    ticker: "NDX", expiry: E1, t: 0.1,
    baseAtmVol: 0.25, postAtmVol: 0.25, shiftBp: 0, sd: 0.005,
    bandLo: 0.24, bandHi: 0.26, observed: true,
  };
  const results: Record<string, GraphSolveNode> = {
    "SPX|2026-09-18": spxE1,
    "SPX|2026-12-18": spxE2,
    "NDX|2026-09-18": ndxE1,
  };

  it("passes null through untouched", () => {
    expect(aggregateResults(null, members)).toBeNull();
  });

  it("aggregates the collapsed pod and keeps real entries", () => {
    const out = aggregateResults(results, members);
    expect(out?.["SPX|2026-09-18"]).toBe(spxE1);
    expect(out?.["SPX|2026-12-18"]).toBe(spxE2);
    expect(out?.["NDX|2026-09-18"]).toBe(ndxE1);

    const agg = out?.["SPX|*"];
    expect(agg).toEqual({
      ticker: "SPX", expiry: "*",
      t: expect.closeTo(0.2, 12), // median
      baseAtmVol: expect.closeTo(0.21, 12), // mean
      postAtmVol: expect.closeTo(0.2075, 12),
      shiftBp: expect.closeTo(-25, 12),
      sd: 0.02, // max
      bandLo: expect.closeTo(0.195, 12),
      bandHi: expect.closeTo(0.22, 12),
      observed: true, // any
    });
  });

  it("produces no aggregated entry for a collapsed pod with no scored member", () => {
    const emptyMembers = new Map([["MSFT|*", ["MSFT|2026-09-18"]]]);
    const out = aggregateResults(results, emptyMembers);
    expect(out).not.toHaveProperty("MSFT|*");
  });
});

describe("aggregateLit", () => {
  const members = collapseUniverse(NODES, EDGES, new Set(["SPX"])).members;

  it("means the lit members' dAtmVol and keeps real entries", () => {
    const lit = { "SPX|2026-09-18": 0, "AAPL|2026-09-18": 0.01 };
    const out = aggregateLit(lit, members);
    expect(out["SPX|2026-09-18"]).toBe(0);
    expect(out["AAPL|2026-09-18"]).toBe(0.01);
    expect(out["SPX|*"]).toBe(0); // only SPX E1 is lit -> mean([0])
  });

  it("is absent when no member of the pod is lit", () => {
    const out = aggregateLit({ "AAPL|2026-09-18": 0.02 }, members);
    expect(out).not.toHaveProperty("SPX|*");
  });
});
