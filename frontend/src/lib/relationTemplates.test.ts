// Relation templates: one-click playbooks over a node/row context. Each
// template must be non-mutating, respect shared-expiry intersections, and
// never double-count an undirected relation (peers) or touch anything but
// calendar rows (calendar_only).
import { describe, expect, it } from "vitest";
import { applyTemplate, contextTickers, TEMPLATES } from "./relationTemplates";
import type { TemplateContext } from "./relationTemplates";
import type { MessageEdgeRow } from "../state/useMessageEdges";

function row(over: Partial<MessageEdgeRow> = {}): MessageEdgeRow {
  return {
    sourceTicker: "A", sourceExpiry: "E1",
    targetTicker: "B", targetExpiry: "E1",
    messagePrecision: 1, betaAtmVol: 1, betaSkew: 1, betaCurv: 1,
    relationClass: "custom", precisionRule: "explicit",
    ...over,
  };
}

describe("TEMPLATES", () => {
  it("declares the three playbooks with needsHub set correctly", () => {
    expect(TEMPLATES.map((t) => t.id)).toEqual(["hub_to_names", "peers", "calendar_only"]);
    expect(TEMPLATES.find((t) => t.id === "hub_to_names")?.needsHub).toBe(true);
    expect(TEMPLATES.find((t) => t.id === "peers")?.needsHub).toBe(false);
    expect(TEMPLATES.find((t) => t.id === "calendar_only")?.needsHub).toBe(false);
  });
});

describe("contextTickers", () => {
  it("returns tickers in first-appearance order, deduped", () => {
    const ctx: TemplateContext = {
      nodes: [
        { ticker: "TSLA", expiry: "E1" }, { ticker: "TSLA", expiry: "E2" },
        { ticker: "AAPL", expiry: "E1" }, { ticker: "MSFT", expiry: "E2" },
      ],
      rows: [], crossPrecision: 500,
    };
    expect(contextTickers(ctx)).toEqual(["TSLA", "AAPL", "MSFT"]);
  });
});

describe("applyTemplate: hub_to_names", () => {
  const ctx: TemplateContext = {
    nodes: [
      { ticker: "SPY", expiry: "E1" }, { ticker: "SPY", expiry: "E2" },
      { ticker: "QQQ", expiry: "E1" }, { ticker: "QQQ", expiry: "E2" },
      { ticker: "AAPL", expiry: "E1" }, // shares only E1 with the hub
    ],
    rows: [],
    crossPrecision: 13000,
    hub: "SPY",
  };

  it("connects the hub to every non-hub ticker's shared expiries", () => {
    const rows = applyTemplate("hub_to_names", ctx);
    expect(rows).toHaveLength(3);
    for (const r of rows) {
      expect(r.sourceTicker).toBe("SPY");
      expect(r.relationClass).toBe("broad_index");
      expect(r.precisionRule).toBe("explicit");
      expect(r.messagePrecision).toBe(13000);
      expect([r.betaAtmVol, r.betaSkew, r.betaCurv]).toEqual([1, 1, 1]);
    }
    expect(rows.map((r) => `${r.targetTicker}@${r.targetExpiry}`).sort()).toEqual([
      "AAPL@E1", "QQQ@E1", "QQQ@E2",
    ]);
  });

  it("returns the rows unchanged when the hub is missing or absent from the context", () => {
    const existing = [row()];
    expect(applyTemplate("hub_to_names", { ...ctx, rows: existing, hub: undefined })).toBe(existing);
    expect(applyTemplate("hub_to_names", { ...ctx, rows: existing, hub: "NFLX" })).toBe(existing);
  });

  it("upserts over existing rows by directed identity", () => {
    const stale = row({ sourceTicker: "SPY", sourceExpiry: "E1", targetTicker: "AAPL", targetExpiry: "E1", messagePrecision: 1 });
    const rows = applyTemplate("hub_to_names", { ...ctx, rows: [stale] });
    const spyAapl = rows.find((r) => r.targetTicker === "AAPL");
    expect(spyAapl?.messagePrecision).toBe(13000); // replaced, not duplicated
    expect(rows).toHaveLength(3);
  });
});

describe("applyTemplate: peers", () => {
  // Appearance order TSLA, AAPL, MSFT — proves the a<b row direction is
  // lexicographic, not iteration order.
  const nodes = [
    { ticker: "TSLA", expiry: "E1" }, { ticker: "TSLA", expiry: "E2" },
    { ticker: "AAPL", expiry: "E1" }, // shares E1 with TSLA only
    { ticker: "MSFT", expiry: "E2" }, // shares E2 with TSLA only
  ];

  it("emits one lexicographically-ordered row per pair per shared expiry", () => {
    const ctx: TemplateContext = { nodes, rows: [], crossPrecision: 500 };
    const rows = applyTemplate("peers", ctx);
    expect(rows).toHaveLength(2); // AAPL/MSFT share nothing
    const aaplTsla = rows.find((r) => r.sourceTicker === "AAPL");
    expect(aaplTsla).toMatchObject({ sourceTicker: "AAPL", targetTicker: "TSLA", sourceExpiry: "E1", relationClass: "sector_peer" });
    const msftTsla = rows.find((r) => r.sourceTicker === "MSFT");
    expect(msftTsla).toMatchObject({ sourceTicker: "MSFT", targetTicker: "TSLA", sourceExpiry: "E2", relationClass: "sector_peer" });
  });

  it("drops a pre-existing reverse-direction peer row instead of double-counting", () => {
    const calRow = row({ sourceTicker: "TSLA", targetTicker: "TSLA", sourceExpiry: "E1", targetExpiry: "E2", relationClass: "calendar" });
    const mirror = row({ sourceTicker: "TSLA", sourceExpiry: "E1", targetTicker: "AAPL", targetExpiry: "E1", relationClass: "sector_peer", messagePrecision: 999 });
    const unrelated = row({ sourceTicker: "AAPL", sourceExpiry: "E1", targetTicker: "MSFT", targetExpiry: "E1", relationClass: "custom" });
    const ctx: TemplateContext = { nodes, rows: [calRow, mirror, unrelated], crossPrecision: 500 };
    const rows = applyTemplate("peers", ctx);

    // The old reverse-direction peer row is gone; a fresh AAPL->TSLA row
    // replaces it (never both at once).
    expect(rows.filter((r) => r.sourceTicker === "AAPL" && r.targetTicker === "TSLA")).toHaveLength(1);
    expect(rows.some((r) => r.sourceTicker === "TSLA" && r.targetTicker === "AAPL")).toBe(false);
    // Untouched rows survive.
    expect(rows).toContainEqual(calRow);
    expect(rows).toContainEqual(unrelated);
    expect(rows).toHaveLength(4); // calRow, unrelated, AAPL->TSLA, MSFT->TSLA
  });
});

describe("applyTemplate: calendar_only", () => {
  it("keeps only calendar-class rows", () => {
    const cal = row({ relationClass: "calendar" });
    const cross = row({ relationClass: "sector_peer" });
    const ctx: TemplateContext = { nodes: [], rows: [cal, cross], crossPrecision: 500 };
    expect(applyTemplate("calendar_only", ctx)).toEqual([cal]);
  });
});
