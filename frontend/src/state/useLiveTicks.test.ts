// Live quote-table tick reducer: frames are deltas keyed "type:strike"; a
// status-off frame drops the overlay; `full` repaints; `gone` removes; the
// flash set is exactly the rows that moved in the last frame.
import { describe, expect, it } from "vitest";
import { EMPTY_LIVE, applyFrame, liveKey, type LiveTickRow } from "./useLiveTicks";

const row = (type: "C" | "P", strike: number, midIv: number): LiveTickRow => ({
  key: liveKey(type, strike),
  strike,
  type,
  k: 0,
  bidIv: midIv - 0.01,
  midIv,
  askIv: midIv + 0.01,
  bidPrice: 1,
  midPrice: 1.1,
  askPrice: 1.2,
});

describe("live ticks reducer", () => {
  it("keys rows like the backend (type:strike at 4 dp)", () => {
    expect(liveKey("C", 123.45)).toBe("C:123.4500");
    expect(liveKey("P", 100)).toBe("P:100.0000");
  });

  it("applies a full frame, then merges deltas and drops gone keys", () => {
    const s1 = applyFrame(EMPTY_LIVE, {
      type: "ticks", streaming: true, ready: true, full: true, ts: "2026-08-20T18:30:58",
      spot: 763.5, rows: [row("C", 770, 0.2), row("P", 750, 0.22)], nLive: 2,
    });
    expect(s1.streaming && s1.ready).toBe(true);
    expect([...s1.rows.keys()].sort()).toEqual(["C:770.0000", "P:750.0000"]);
    expect(s1.flash).toEqual(new Set(["C:770.0000", "P:750.0000"]));
    expect(s1.seq).toBe(1);
    expect(s1.ts).toBe("2026-08-20T18:30:58");
    expect(s1.spot).toBe(763.5);

    const s2 = applyFrame(s1, {
      type: "ticks", streaming: true, ready: true, rows: [row("C", 770, 0.21)], gone: ["P:750.0000"],
      ts: "2026-08-20T18:30:59",
    });
    expect(s2.rows.get("C:770.0000")?.midIv).toBe(0.21);
    expect(s2.rows.has("P:750.0000")).toBe(false);
    expect(s2.flash).toEqual(new Set(["C:770.0000"]));
    expect(s2.seq).toBe(2);
    expect(s2.spot).toBe(763.5); // carried when the frame omits it
  });

  it("a full frame replaces rather than merges", () => {
    const s1 = applyFrame(EMPTY_LIVE, { type: "ticks", streaming: true, ready: true, full: true, rows: [row("C", 1, 0.2)] });
    const s2 = applyFrame(s1, { type: "ticks", streaming: true, ready: true, full: true, rows: [row("C", 2, 0.2)] });
    expect([...s2.rows.keys()]).toEqual(["C:2.0000"]);
  });

  it("status frames: off drops the overlay, warming keeps streaming without rows", () => {
    const live = applyFrame(EMPTY_LIVE, { type: "ticks", streaming: true, ready: true, full: true, rows: [row("C", 1, 0.2)] });
    const warming = applyFrame(live, { type: "status", streaming: true, ready: false });
    expect(warming.streaming).toBe(true);
    expect(warming.ready).toBe(false);
    expect(warming.rows.size).toBe(0);
    const off = applyFrame(live, { type: "status", streaming: false, ready: false });
    expect(off.streaming).toBe(false);
    expect(off.rows.size).toBe(0);
    expect(off.flash.size).toBe(0);
    expect(off.ts).toBeNull();
  });
});
