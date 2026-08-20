// Frame composition for the Smile Viewer: market (prevailing / live) vs
// calibration, each in its own moneyness; live rows become pure-market quote
// bands at the live forward; fallbacks keep older payloads drawable.
import { describe, expect, it } from "vitest";
import { calibByStrike, composeFrames, frameK, liveQuoteBands } from "./smileLayers";
import { EMPTY_LIVE, type LiveTickRow, type LiveTicksState } from "../state/useLiveTicks";
import type { QuoteBand, SmileData } from "./mockData";

const q = (strike: number, k: number, extra: Partial<QuoteBand> = {}): QuoteBand => ({
  k, bid: 0.19, ask: 0.21, mid: 0.2, index: 0, excluded: false, amended: false, strike, ...extra,
});

const smile = (over: Partial<SmileData> = {}): SmileData =>
  ({
    ticker: "SPY", expiry: "2026-09-18", T: 0.08, forward: 100,
    model: [{ k: -0.1, vol: 0.22 }, { k: 0.1, vol: 0.2 }],
    prior: [], priorTransported: false,
    quotes: [q(95, Math.log(0.95), { index: 0, excluded: true }), q(105, Math.log(1.05), { index: 1, amended: true })],
    kMin: -0.2, kMax: 0.2, canUndo: false, canRedo: false,
    diagnostics: { atmVol: 0.2, skew: 0, curvature: 0 } as SmileData["diagnostics"],
    varSwap: { level: null, excluded: false, modelVol: 0, enabled: false, canUndo: false, canRedo: false },
    ...over,
  }) as SmileData;

const row = (strike: number, midIv: number, index = -1): LiveTickRow => ({
  key: strike.toFixed(4), strike, type: "C", k: 0, bidIv: midIv - 0.01, midIv, askIv: midIv + 0.01,
  bidPrice: 1, midPrice: 1, askPrice: 1, targetLo: midIv - 0.005, targetHi: midIv + 0.005, index,
});

describe("smile frames", () => {
  it("frameK / calibByStrike", () => {
    expect(frameK(110, 100)).toBeCloseTo(Math.log(1.1), 12);
    const m = calibByStrike([q(95, 0, { index: 3 })]);
    expect(m.get("95.0000")?.index).toBe(3);
  });

  it("falls back to the displayed smile + calibration quotes on an old payload", () => {
    const f = composeFrames(smile(), null);
    expect(f.calib).toBeNull();
    expect(f.market.forward).toBe(100);
    expect(f.market.quotes.length).toBe(2);
    expect(f.market.model.length).toBe(2);
    expect(f.market.live).toBe(false);
  });

  it("uses the payload market/calib layers; calibration quotes keep their edits", () => {
    const s = smile({
      market: { forward: 101, spot: 101, timestamp: "2026-08-21T14:00:00", quotes: [q(95, frameK(95, 101), { index: 0 })], model: [{ k: 0, vol: 0.21 }] },
      calib: { forward: 100, model: [{ k: 0, vol: 0.2 }] },
    });
    const f = composeFrames(s, { ...EMPTY_LIVE, streaming: true, ready: false });
    expect(f.market.forward).toBe(101);
    expect(f.market.quotes[0].excluded).toBe(false); // pure market
    expect(f.market.warming).toBe(true); // stream up, book not ready
    expect(f.calib?.forward).toBe(100);
    expect(f.calib?.quotes.some((x) => x.excluded)).toBe(true); // edits live here
    expect(f.calib?.model[0].vol).toBe(0.2);
  });

  it("a live, ready stream takes over the market frame at the live forward", () => {
    const ticks: LiveTicksState = {
      ...EMPTY_LIVE, streaming: true, ready: true, forward: 102, spot: 102, ts: "2026-08-21T14:00:05",
      rows: new Map([["110.0000", row(110, 0.19, 1)], ["95.0000", row(95, 0.23)]]),
      model: [{ k: 0, vol: 0.205 }],
    };
    const f = composeFrames(smile({ market: { forward: 101, quotes: [], model: [] }, calib: { forward: 100, model: [] } }), ticks);
    expect(f.market.live).toBe(true);
    expect(f.market.forward).toBe(102);
    expect(f.market.model).toEqual([{ k: 0, vol: 0.205 }]);
    expect(f.market.quotes.map((x) => x.strike)).toEqual([95, 110]); // sorted by k
    expect(f.market.quotes[1].k).toBeCloseTo(Math.log(110 / 102), 12);
    expect(f.market.quotes[1].index).toBe(1); // click-through to the calibration quote
    expect(f.market.quotes[0].index).toBe(-1);
    expect(f.market.quotes[1].targetLo).toBeCloseTo(0.185, 12);
    expect(f.market.timestamp).toBe("2026-08-21T14:00:05");
  });

  it("liveQuoteBands is empty without a live forward", () => {
    expect(liveQuoteBands({ ...EMPTY_LIVE, rows: new Map([["1.0000", row(1, 0.2)]]) })).toEqual([]);
  });
});
