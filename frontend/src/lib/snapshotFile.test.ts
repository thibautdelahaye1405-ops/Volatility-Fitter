// Snapshot-file envelope helpers (UI SHELL v2 wave 3, A2).
import { describe, expect, it } from "vitest";
import { SNAPSHOT_SCHEMA, classifyBundle, parseSnapshotBundle, snapshotFilename, snapshotNameOf } from "./snapshotFile";

describe("parseSnapshotBundle", () => {
  it("accepts a well-formed envelope and lists its tickers", () => {
    const r = parseSnapshotBundle({ schema: SNAPSHOT_SCHEMA, asOf: "2026-08-27T14:30:00", tickers: [{ ticker: "SPY", chain: {} }, { ticker: "QQQ", chain: {} }] });
    expect(r).toEqual({ ok: true, summary: { schema: SNAPSHOT_SCHEMA, asOf: "2026-08-27T14:30:00", tickers: ["SPY", "QQQ"] } });
  });

  it.each([
    [null, "not a JSON object"],
    [{ tickers: [] }, 'missing "schema"'],
    [{ schema: "volfit-workspace/1", tickers: [{ ticker: "X" }] }, "not a snapshot file"],
    [{ schema: "volfit-snapshot/3", tickers: [{ ticker: "X" }] }, "unsupported snapshot schema"],
    [{ schema: SNAPSHOT_SCHEMA, tickers: [] }, "no tickers"],
    [{ schema: SNAPSHOT_SCHEMA, tickers: [{ nope: 1 }] }, "malformed ticker"],
  ])("refuses %j", (raw, needle) => {
    const r = parseSnapshotBundle(raw);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error).toContain(needle);
  });
});

describe("classifyBundle", () => {
  it("routes by schema family", () => {
    expect(classifyBundle({ schema: "volfit-workspace/1" })).toBe("workspace");
    expect(classifyBundle({ schema: "volfit-snapshot/1" })).toBe("snapshot");
    expect(classifyBundle({ schema: "other/1" })).toBeNull();
    expect(classifyBundle("x")).toBeNull();
  });
});

describe("filenames", () => {
  it("names the file after up to three tickers and the as-of stamp", () => {
    expect(snapshotFilename(["SPY", "QQQ"], "2026-08-27T14:30:05")).toBe("spy-qqq_20260827_1430.volfit-snapshot.json");
    expect(snapshotFilename(["A", "B", "C", "D", "E"], "")).toBe("a-b-c-plus2_snapshot.volfit-snapshot.json");
    expect(snapshotNameOf("spy_20260827.volfit-snapshot.json")).toBe("spy_20260827");
  });
});
