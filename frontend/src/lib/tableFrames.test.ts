// Quote-table frame join: market (live > payload market > calibration fallback)
// vs calibration, one row per strike, hot flags from the live flash set.
import { describe, expect, it } from "vitest";
import { composeTableRows, deltaBp, liveRowToTableRow, toTsv, type TableResponse, type TableRow } from "./tableFrames";
import { EMPTY_LIVE, type LiveTickRow, type LiveTicksState } from "../state/useLiveTicks";

const row = (strike: number, midIv: number, over: Partial<TableRow> = {}): TableRow => ({
  index: 0, strike, type: strike >= 100 ? "C" : "P", k: Math.log(strike / 100), bidIv: midIv - 0.01, midIv,
  askIv: midIv + 0.01, modelIv: midIv + 0.002, bidPrice: 1, midPrice: 1.1, askPrice: 1.2, excluded: false, amended: false,
  ...over,
});

const table = (over: Partial<TableResponse> = {}): TableResponse => ({
  ticker: "SPY", expiry: "2026-09-18", t: 0.08, forward: 100, discount: 0.99,
  rows: [row(95, 0.22, { index: 0, excluded: true }), row(105, 0.2, { index: 1, amended: true })],
  ...over,
});

const live = (strike: number, midIv: number, index = -1, modelIv: number | null = 0.21): LiveTickRow => ({
  key: strike.toFixed(4), strike, type: "C", k: Math.log(strike / 101), bidIv: midIv - 0.01, midIv, askIv: midIv + 0.01,
  bidPrice: 1, midPrice: 1, askPrice: 1, targetLo: midIv - 0.005, targetHi: midIv + 0.005, index, modelIv,
});

describe("table frames", () => {
  it("old payload: market falls back to the calibration rows", () => {
    const f = composeTableRows(table(), null);
    expect(f.rows.map((r) => r.strike)).toEqual([95, 105]);
    expect(f.rows[0].market).toBe(f.rows[0].calib);
    expect(f.live).toBe(false);
    expect(f.marketForward).toBe(100);
  });

  it("payload market rows are primary; calibration keeps edits; union by strike", () => {
    const t = table({
      marketForward: 101, marketSpot: 101, marketTimestamp: "2026-08-21T14:00:00",
      marketRows: [row(105, 0.205, { index: 1 }), row(110, 0.19, { index: -1 })],
    });
    const f = composeTableRows(t, { ...EMPTY_LIVE, streaming: true, ready: false });
    expect(f.rows.map((r) => r.strike)).toEqual([95, 105, 110]);
    expect(f.rows[0].market).toBeNull(); // 95 no longer two-sided in the market
    expect(f.rows[0].calib?.excluded).toBe(true);
    expect(f.rows[1].market?.midIv).toBe(0.205);
    expect(f.rows[1].calib?.amended).toBe(true);
    expect(f.rows[2].calib).toBeNull(); // newly two-sided: market only
    expect(f.warming).toBe(true);
    expect(f.marketTimestamp).toBe("2026-08-21T14:00:00");
  });

  it("a ready live stream takes over the market frame, hot from the flash set", () => {
    const ticks: LiveTicksState = {
      ...EMPTY_LIVE, streaming: true, ready: true, forward: 101, spot: 101.2, ts: "2026-08-21T14:00:05",
      rows: new Map([["105.0000", live(105, 0.21, 1)], ["120.0000", live(120, 0.18, -1, null)]]),
      flash: new Set(["105.0000"]),
    };
    const f = composeTableRows(table({ marketRows: [row(105, 0.2)] }), ticks);
    expect(f.live).toBe(true);
    expect(f.marketForward).toBe(101);
    const r105 = f.rows.find((r) => r.strike === 105)!;
    expect(r105.market?.midIv).toBe(0.21);
    expect(r105.market?.targetLo).toBeCloseTo(0.205, 12);
    expect(r105.hot).toBe(true);
    const r120 = f.rows.find((r) => r.strike === 120)!;
    expect(Number.isNaN(r120.market?.modelIv)).toBe(true); // no fit -> NaN (rendered as —)
    expect(r120.hot).toBe(false);
    expect(deltaBp(r105.market)).toBe(Math.round((0.21 - 0.21) * 1e4));
    expect(deltaBp(r120.market)).toBeNull();
  });

  it("liveRowToTableRow / deltaBp / toTsv", () => {
    const r = liveRowToTableRow(live(100, 0.2, 3, 0.2025));
    expect(r.type).toBe("C");
    expect(r.index).toBe(3);
    expect(deltaBp(r)).toBe(25);
    const f = composeTableRows(table({ marketRows: [row(105, 0.2)] }), null);
    const tsv = toTsv(f.rows, true);
    expect(tsv.split("\n")[0].split("\t")).toContain("cal_model_iv");
    expect(tsv.split("\n").length).toBe(3);
    expect(toTsv(f.rows, false).split("\n")[0].split("\t")).not.toContain("cal_model_iv");
  });
});
