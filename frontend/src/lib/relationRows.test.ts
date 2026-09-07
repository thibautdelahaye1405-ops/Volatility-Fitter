// Relation-row helpers: identity keys, class inference, the connect-gesture
// default row, the §7.6/§8.3 direction flip, chart-topology mapping and the
// pair/upsert lookups used by the canvas editor and the templates.
import { describe, expect, it } from "vitest";
import {
  flipRelation,
  inferRelationClass,
  newRelationRow,
  parseRelationKey,
  relationKey,
  rowsForCalendarPair,
  rowsForTickerPair,
  rowsToLayoutEdges,
  upsertRows,
} from "./relationRows";
import type { MessageEdgeRow } from "../state/useMessageEdges";

function row(over: Partial<MessageEdgeRow> = {}): MessageEdgeRow {
  return {
    sourceTicker: "SPY", sourceExpiry: "2026-12-18",
    targetTicker: "SPY", targetExpiry: "2026-09-18",
    messagePrecision: 4, betaAtmVol: 2, betaSkew: 2, betaCurv: 2,
    relationClass: "calendar", precisionRule: "explicit",
    ...over,
  };
}

describe("relationKey / parseRelationKey", () => {
  it("round-trips the directed identity", () => {
    const r = row({ sourceTicker: "QQQ", targetTicker: "SPY" });
    const key = relationKey(r);
    expect(key).toBe("QQQ|2026-12-18>SPY|2026-09-18");
    expect(parseRelationKey(key)).toEqual({
      source: { ticker: "QQQ", expiry: "2026-12-18" },
      target: { ticker: "SPY", expiry: "2026-09-18" },
    });
  });

  it("rejects malformed keys", () => {
    expect(parseRelationKey("garbage")).toBeNull();
    expect(parseRelationKey("A|B>C")).toBeNull();
    expect(parseRelationKey("A|B>C|D>E")).toBeNull();
    expect(parseRelationKey("|B>C|D")).toBeNull();
  });
});

describe("inferRelationClass", () => {
  it("same ticker is always calendar, regardless of hubs", () => {
    const s = { ticker: "SPY", expiry: "2026-09-18" };
    const t = { ticker: "SPY", expiry: "2026-12-18" };
    expect(inferRelationClass(s, t)).toBe("calendar");
    expect(inferRelationClass(s, t, ["SPY"])).toBe("calendar");
  });

  it("cross-ticker is custom unless the source is a hub", () => {
    const s = { ticker: "SPY", expiry: "2026-09-18" };
    const t = { ticker: "AAPL", expiry: "2026-09-18" };
    expect(inferRelationClass(s, t)).toBe("custom");
    expect(inferRelationClass(s, t, ["QQQ"])).toBe("custom");
    expect(inferRelationClass(s, t, ["SPY", "QQQ"])).toBe("broad_index");
    // a hub as the TARGET doesn't count.
    expect(inferRelationClass(t, s, ["SPY"])).toBe("custom");
  });
});

describe("newRelationRow", () => {
  const scales = { calPrecision: 1700, crossPrecision: 13000 };

  it("returns null for a self-loop", () => {
    const n = { ticker: "SPY", expiry: "2026-09-18" };
    expect(newRelationRow(n, { ...n }, scales)).toBeNull();
  });

  it("builds a calendar_distance placeholder for a same-ticker connect", () => {
    const s = { ticker: "SPY", expiry: "2026-09-18" };
    const t = { ticker: "SPY", expiry: "2026-12-18" };
    const r = newRelationRow(s, t, scales);
    expect(r).toEqual({
      sourceTicker: "SPY", sourceExpiry: "2026-09-18",
      targetTicker: "SPY", targetExpiry: "2026-12-18",
      messagePrecision: 1700, betaAtmVol: 1, betaSkew: 1, betaCurv: 1,
      relationClass: "calendar", precisionRule: "calendar_distance",
      relationSemantics: null,
    });
  });

  it("builds an explicit cross row at crossPrecision otherwise", () => {
    const s = { ticker: "SPY", expiry: "2026-09-18" };
    const t = { ticker: "AAPL", expiry: "2026-09-18" };
    const r = newRelationRow(s, t, scales);
    expect(r?.relationClass).toBe("custom");
    expect(r?.precisionRule).toBe("explicit");
    expect(r?.messagePrecision).toBe(13000);
  });

  it("honours an explicit class override (e.g. broad_index)", () => {
    const s = { ticker: "SPY", expiry: "2026-09-18" };
    const t = { ticker: "AAPL", expiry: "2026-09-18" };
    const r = newRelationRow(s, t, scales, "broad_index");
    expect(r?.relationClass).toBe("broad_index");
    expect(r?.precisionRule).toBe("explicit"); // only "calendar" gets the distance rule
  });
});

describe("flipRelation", () => {
  it("swaps direction, inverts betas, and re-expresses an explicit precision as p*beta^2", () => {
    const r = row({ messagePrecision: 4, betaAtmVol: 2, betaSkew: 4, betaCurv: 0.5 });
    const flipped = flipRelation(r);
    expect(flipped.sourceTicker).toBe(r.targetTicker);
    expect(flipped.sourceExpiry).toBe(r.targetExpiry);
    expect(flipped.targetTicker).toBe(r.sourceTicker);
    expect(flipped.targetExpiry).toBe(r.sourceExpiry);
    expect(flipped.betaAtmVol).toBe(0.5); // 1/2
    expect(flipped.betaSkew).toBe(0.25); // 1/4
    expect(flipped.betaCurv).toBe(2); // 1/0.5
    expect(flipped.messagePrecision).toBe(16); // 4 * 2^2
  });

  it("keeps a zero beta at zero", () => {
    const flipped = flipRelation(row({ betaAtmVol: 0 }));
    expect(flipped.betaAtmVol).toBe(0);
  });

  it("keeps a calendar_distance row's rule and number untouched", () => {
    const r = row({ precisionRule: "calendar_distance", messagePrecision: 1700, betaAtmVol: 3 });
    const flipped = flipRelation(r);
    expect(flipped.precisionRule).toBe("calendar_distance");
    expect(flipped.messagePrecision).toBe(1700);
  });
});

describe("rowsToLayoutEdges", () => {
  it("maps from=receiver, to=informer, weight=precision, beta=betaAtmVol", () => {
    const r = row({ sourceTicker: "SPY", targetTicker: "QQQ", messagePrecision: 9, betaAtmVol: 1.5 });
    const [edge] = rowsToLayoutEdges([r]);
    expect(edge).toEqual({
      fromTicker: "QQQ", fromExpiry: r.targetExpiry,
      toTicker: "SPY", toExpiry: r.sourceExpiry,
      weight: 9, beta: 1.5,
    });
  });
});

describe("rowsForTickerPair / rowsForCalendarPair", () => {
  const rows: MessageEdgeRow[] = [
    row({ sourceTicker: "SPY", targetTicker: "QQQ" }),
    row({ sourceTicker: "QQQ", targetTicker: "SPY", sourceExpiry: "2026-06-19" }),
    row({ sourceTicker: "SPY", targetTicker: "SPY" }), // calendar — excluded from ticker pairs
    row({ sourceTicker: "AAPL", targetTicker: "MSFT" }),
  ];

  it("finds cross rows either direction, excluding calendar", () => {
    const found = rowsForTickerPair(rows, "QQQ", "SPY");
    expect(found).toHaveLength(2);
    expect(rowsForTickerPair(rows, "SPY", "SPY")).toEqual([]);
    expect(rowsForTickerPair(rows, "AAPL", "TSLA")).toEqual([]);
  });

  it("finds calendar rows joining two expiries either direction", () => {
    const calRows: MessageEdgeRow[] = [
      row({ sourceTicker: "SPY", targetTicker: "SPY", sourceExpiry: "2026-12-18", targetExpiry: "2026-09-18" }),
      row({ sourceTicker: "SPY", targetTicker: "SPY", sourceExpiry: "2026-09-18", targetExpiry: "2027-03-19" }),
    ];
    expect(rowsForCalendarPair(calRows, "SPY", "2026-09-18", "2026-12-18")).toHaveLength(1);
    expect(rowsForCalendarPair(calRows, "SPY", "2026-12-18", "2026-09-18")).toHaveLength(1);
    expect(rowsForCalendarPair(calRows, "SPY", "2026-09-18", "2028-01-01")).toEqual([]);
  });
});

describe("upsertRows", () => {
  it("replaces an existing key in place and appends new ones at the end", () => {
    const a = row({ sourceTicker: "A", messagePrecision: 1 });
    const b = row({ sourceTicker: "B", messagePrecision: 2 });
    const c = row({ sourceTicker: "C", messagePrecision: 3 });
    const bReplaced = row({ sourceTicker: "B", messagePrecision: 99 });
    const result = upsertRows([a, b], [bReplaced, c]);
    expect(result).toEqual([a, bReplaced, c]);
  });

  it("de-dupes repeated keys within the incoming batch (last wins)", () => {
    const a = row({ sourceTicker: "A", messagePrecision: 1 });
    const aAgain = row({ sourceTicker: "A", messagePrecision: 2 });
    expect(upsertRows([], [a, aAgain])).toEqual([aAgain]);
  });
});
