// The Smile Viewer's two comparable frames, composed client-side (pure, tested):
//
//   MARKET  (layers 1 + 3)  the prevailing bid/ask quotes with their fit target,
//                           and the fit ROLLED to the prevailing spot;
//   CALIB   (layers 2 + 4)  the quotes + target the last calibration used, and
//                           the fit on its CALIBRATION spot.
//
// Each frame carries its own forward: every quote is placed at
// log(strike / frame forward) and each curve is already in its frame's
// moneyness, so the two frames are internally comparable and can be drawn on
// one chart whose x reference is the market forward. The market frame is the
// payload's `market` layer (latest fetched chain) unless the node's SSE tick
// stream is live and ready — then the live rows / forward / rolled model take
// over at ~1 Hz (state/useLiveTicks). Calibration quotes keep the user's edits
// (excluded / amended); market quotes are the market as quoted.
import type { QuoteBand, SmileData, SmilePoint } from "./mockData";
import type { LiveTicksState } from "../state/useLiveTicks";

/** One drawable frame: quotes + curve in the frame's own moneyness. */
export interface SmileFrame {
  forward: number;
  quotes: QuoteBand[];
  model: SmilePoint[];
}

export interface MarketFrame extends SmileFrame {
  /** Fed by the live stream (vs the latest fetched chain). */
  live: boolean;
  /** Stream up but the book has not served this node yet. */
  warming: boolean;
  spot: number | null;
  /** ISO UTC stamp of the market (chain timestamp, or newest live tick). */
  timestamp: string | null;
}

export interface SmileFrames {
  market: MarketFrame;
  calib: SmileFrame | null;
}

/** Log-moneyness of a strike against a frame's forward. */
export const frameK = (strike: number, forward: number): number => Math.log(strike / forward);

/** `{strike key -> calibration quote}` for click-through / strike lookups. */
export function calibByStrike(quotes: readonly QuoteBand[]): Map<string, QuoteBand> {
  const m = new Map<string, QuoteBand>();
  for (const q of quotes) if (q.strike != null) m.set(q.strike.toFixed(4), q);
  return m;
}

/** Live tick rows -> market quote bands (pure market: no edits), at the live forward. */
export function liveQuoteBands(ticks: LiveTicksState): QuoteBand[] {
  const f = ticks.forward;
  if (f === null || !(f > 0)) return [];
  const out: QuoteBand[] = [];
  for (const r of ticks.rows.values()) {
    out.push({
      k: frameK(r.strike, f),
      bid: r.bidIv,
      ask: r.askIv,
      mid: r.midIv,
      index: r.index ?? -1,
      excluded: false,
      amended: false,
      strike: r.strike,
      targetLo: r.targetLo ?? null,
      targetHi: r.targetHi ?? null,
    });
  }
  return out.sort((a, b) => a.k - b.k);
}

/**
 * Compose the frames for the chart. Without a payload `market` layer (older
 * backend / mock) the market frame falls back to the payload's displayed smile
 * and calibration quotes, so the chart still draws what it always did.
 */
export function composeFrames(smile: SmileData, ticks: LiveTicksState | null): SmileFrames {
  const calib: SmileFrame | null = smile.calib
    ? { forward: smile.calib.forward, quotes: smile.quotes, model: smile.calib.model }
    : null;
  const liveReady = !!ticks && ticks.streaming && ticks.ready && ticks.forward !== null;
  if (liveReady && ticks) {
    return {
      market: {
        forward: ticks.forward as number,
        quotes: liveQuoteBands(ticks),
        // Rolled fit at the live spot when the stream has sent one; else the
        // payload's (≤ one spot-poll stale) until the first frame carries it.
        model: ticks.model ?? smile.market?.model ?? smile.model,
        live: true,
        warming: false,
        spot: ticks.spot,
        timestamp: ticks.ts,
      },
      calib,
    };
  }
  const m = smile.market;
  return {
    market: m
      ? {
          forward: m.forward,
          quotes: m.quotes,
          model: m.model,
          live: !!(ticks && ticks.streaming),
          warming: !!(ticks && ticks.streaming && !ticks.ready),
          spot: m.spot ?? null,
          timestamp: m.timestamp ?? null,
        }
      : {
          forward: smile.forward,
          quotes: smile.quotes,
          model: smile.model,
          live: false,
          warming: false,
          spot: null,
          timestamp: null,
        },
    calib,
  };
}
