// The Quote Table's two comparable frames (same grammar as the smile chart,
// lib/smileLayers): one row per STRIKE joining
//
//   market  (primary)  the prevailing bid/ask/mid IV with their fit target, the
//                      fit ROLLED to the prevailing spot ("Model") and prices at
//                      the market forward — live rows when the node's SSE tick
//                      stream is ready, else the payload's market rows (latest
//                      fetched chain), else (old backend) the calibration rows;
//   calib   (toggle)   the quotes + target the last calibration used (with the
//                      user's exclusions / amended mids), the fit on its
//                      calibration spot and the calibration weight.
//
// Pure and unit-tested; the component only renders what this composes.
import type { LiveTickRow, LiveTicksState } from "../state/useLiveTicks";

/** One row of GET /smiles/{ticker}/{expiry}/table (either frame). */
export interface TableRow {
  index: number;
  strike: number;
  type: "C" | "P";
  k: number;
  bidIv: number;
  midIv: number;
  askIv: number;
  modelIv: number;
  bidPrice: number;
  midPrice: number;
  askPrice: number;
  excluded: boolean;
  amended: boolean;
  targetLo?: number | null;
  targetHi?: number | null;
}

/** Response of GET /smiles/{ticker}/{expiry}/table. */
export interface TableResponse {
  ticker: string;
  expiry: string;
  t: number;
  forward: number;
  discount: number;
  /** The calibration frame (with edits). */
  rows: TableRow[];
  /** The prevailing-market frame (optional: older backends omit it). */
  marketForward?: number | null;
  marketSpot?: number | null;
  marketTimestamp?: string | null;
  marketLive?: boolean;
  marketRows?: TableRow[];
}

/** One strike of the joined table. */
export interface MergedRow {
  key: string;
  strike: number;
  market: TableRow | null;
  calib: TableRow | null;
  /** The market band moved in the last live frame (cell flash). */
  hot: boolean;
}

export interface TableFrames {
  rows: MergedRow[];
  marketForward: number | null;
  marketSpot: number | null;
  marketTimestamp: string | null;
  calibForward: number;
  /** Market rows come from the live stream. */
  live: boolean;
  /** Stream up but the book has not served this node yet. */
  warming: boolean;
}

export const strikeKey = (strike: number): string => strike.toFixed(4);

/** A live tick row as a table row (the market frame, no edits). */
export function liveRowToTableRow(r: LiveTickRow): TableRow {
  return {
    index: r.index ?? -1,
    strike: r.strike,
    type: r.type,
    k: r.k,
    bidIv: r.bidIv,
    midIv: r.midIv,
    askIv: r.askIv,
    modelIv: r.modelIv ?? Number.NaN,
    bidPrice: r.bidPrice,
    midPrice: r.midPrice,
    askPrice: r.askPrice,
    excluded: false,
    amended: false,
    targetLo: r.targetLo ?? null,
    targetHi: r.targetHi ?? null,
  };
}

/** Join the two frames by strike (ascending). */
export function composeTableRows(table: TableResponse, ticks: LiveTicksState | null): TableFrames {
  const liveReady = !!ticks && ticks.streaming && ticks.ready && ticks.forward !== null;
  let marketRows: TableRow[];
  let marketForward: number | null;
  let marketSpot: number | null;
  let marketTimestamp: string | null;
  if (liveReady && ticks) {
    marketRows = [...ticks.rows.values()].map(liveRowToTableRow);
    marketForward = ticks.forward;
    marketSpot = ticks.spot;
    marketTimestamp = ticks.ts;
  } else if (table.marketRows && table.marketRows.length > 0) {
    marketRows = table.marketRows;
    marketForward = table.marketForward ?? table.forward;
    marketSpot = table.marketSpot ?? null;
    marketTimestamp = table.marketTimestamp ?? null;
  } else {
    // Old backend / no chain: the calibration rows are the only market we know.
    marketRows = table.rows;
    marketForward = table.forward;
    marketSpot = null;
    marketTimestamp = null;
  }
  const byKey = new Map<string, MergedRow>();
  for (const r of table.rows) {
    const key = strikeKey(r.strike);
    byKey.set(key, { key, strike: r.strike, market: null, calib: r, hot: false });
  }
  for (const r of marketRows) {
    const key = strikeKey(r.strike);
    const row = byKey.get(key);
    const hot = !!ticks && liveReady && ticks.flash.has(key);
    if (row) {
      row.market = r;
      row.hot = hot;
    } else {
      byKey.set(key, { key, strike: r.strike, market: r, calib: null, hot });
    }
  }
  return {
    rows: [...byKey.values()].sort((a, b) => a.strike - b.strike),
    marketForward,
    marketSpot,
    marketTimestamp,
    calibForward: table.forward,
    live: liveReady,
    warming: !!ticks && ticks.streaming && !ticks.ready,
  };
}

/** Vol-bp distance of the fit from the market mid (model − mid, in 0.01% vol). */
export const deltaBp = (r: TableRow | null): number | null =>
  r === null || !Number.isFinite(r.modelIv) ? null : Math.round((r.modelIv - r.midIv) * 1e4);

/** Serialize the joined table as TSV (header included; both frames). */
export function toTsv(rows: readonly MergedRow[], withCalib: boolean): string {
  const head = [
    "strike", "type", "k", "mkt_bid_iv", "mkt_mid_iv", "mkt_ask_iv", "mkt_target_lo", "mkt_target_hi",
    "mkt_model_iv", "mkt_bid_price", "mkt_mid_price", "mkt_ask_price",
  ];
  if (withCalib) head.push("cal_bid_iv", "cal_mid_iv", "cal_ask_iv", "cal_target_lo", "cal_target_hi", "cal_model_iv", "excluded", "amended");
  const f4 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "" : v.toFixed(4));
  const f2 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "" : v.toFixed(2));
  const lines = rows.map((row) => {
    const m = row.market;
    const c = row.calib;
    const base = m ?? c;
    const cells = [
      row.strike.toFixed(2), base?.type ?? "", f4(m?.k ?? c?.k),
      f4(m?.bidIv), f4(m?.midIv), f4(m?.askIv), f4(m?.targetLo), f4(m?.targetHi), f4(m?.modelIv),
      f2(m?.bidPrice), f2(m?.midPrice), f2(m?.askPrice),
    ];
    if (withCalib) {
      cells.push(f4(c?.bidIv), f4(c?.midIv), f4(c?.askIv), f4(c?.targetLo), f4(c?.targetHi), f4(c?.modelIv),
        c ? String(c.excluded) : "", c ? String(c.amended) : "");
    }
    return cells.join("\t");
  });
  return [head.join("\t"), ...lines].join("\n");
}
