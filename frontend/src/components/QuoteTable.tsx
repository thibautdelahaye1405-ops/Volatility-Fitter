// Quote table view of the current smile node: per-strike quotes (IV and
// price space) side by side with the fitted model vol, in a dense monospace
// grid. Mirrors the chart's visual language — excluded rows are dimmed,
// amended mids are amber. Footer actions copy the table as TSV to the
// clipboard or download the backend-rendered CSV. Live backend only (the
// parent gates mock mode).
//
// Live ticks: while the active source streams (Massive WS / Bloomberg
// subscription book) the node's live market is pushed over SSE (useLiveTicks)
// and overlaid on the calibrated rows by "type:strike" key — bid/mid/ask IV and
// prices tick (flash on change), the Model IV column stays the fit's. Amended
// rows are user-pinned calibration inputs and never tick. A LIVE badge with
// the newest provider stamp sits in the footer; without a stream the table is
// exactly the calibrated snapshot as before.
import { useEffect, useMemo, useState } from "react";
import { api, API_BASE_URL } from "../state/api";
import type { FitMode } from "../state/useSmile";
import { liveKey, useLiveTicks } from "../state/useLiveTicks";
import { useWeights } from "../state/useWeights";
import type { SmileData } from "../lib/mockData";
import { formatPct } from "../lib/chartScale";
import { toolbarButtonClass } from "./QuoteToolbar";

/** One row of GET /smiles/{ticker}/{expiry}/table. */
interface TableRow {
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
}

/** Response of GET /smiles/{ticker}/{expiry}/table. */
interface TableResponse {
  ticker: string;
  expiry: string;
  t: number;
  forward: number;
  discount: number;
  rows: TableRow[];
}

/** A table row with the live market overlaid (when streaming and not pinned). */
interface ShownRow extends TableRow {
  key: string;
  live: boolean;
}

interface QuoteTableProps {
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  /** Current smile: its identity changes on every refit/edit, so keeping it
   *  in the fetch deps refreshes the table after quote edits. */
  smile: SmileData | null;
}

/** "HH:MM:SS UTC" of a backend (UTC-naive ISO) stamp; "" when unknown. */
const tickTime = (iso: string | null): string => (iso ? `${iso.slice(11, 19)} UTC` : "");

/** Column headers (numeric columns are right-aligned; C/P is centered).
 *  "Weight" is the mean-1 calibration weight (V3.4 item 5; em-dash when
 *  excluded), served by GET /smiles/{t}/{e}/weights. */
const HEADERS = ["Strike", "C/P", "k", "Bid IV", "Mid IV", "Ask IV", "Model IV", "Bid", "Mid", "Ask", "Weight"];

/** Serialize the table as tab-separated values (header included). */
function toTsv(rows: TableRow[]): string {
  const header = [
    "strike", "type", "k", "bid_iv", "mid_iv", "ask_iv", "model_iv",
    "bid_price", "mid_price", "ask_price", "excluded", "amended",
  ].join("\t");
  const lines = rows.map((r) =>
    [
      r.strike.toFixed(2), r.type, r.k.toFixed(4),
      r.bidIv.toFixed(4), r.midIv.toFixed(4), r.askIv.toFixed(4), r.modelIv.toFixed(4),
      r.bidPrice.toFixed(2), r.midPrice.toFixed(2), r.askPrice.toFixed(2),
      String(r.excluded), String(r.amended),
    ].join("\t"),
  );
  return [header, ...lines].join("\n");
}

/** Centered placeholder for loading / error states. */
const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

export default function QuoteTable({ ticker, expiry, fitMode, smile }: QuoteTableProps) {
  const [data, setData] = useState<TableResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Per-quote calibration weights (poll-safe read; refetches with the smile).
  const weights = useWeights(true, true, ticker, expiry, fitMode, smile);
  const weightByIndex = useMemo(() => {
    const m = new Map<number, number>();
    for (const e of weights?.entries ?? []) if (!e.excluded) m.set(e.index, e.weight);
    return m;
  }, [weights]);

  // Live market overlay (SSE off the streaming book; empty when not streaming).
  const ticks = useLiveTicks(ticker, expiry, ticker !== "" && expiry !== "");
  const shown = useMemo<ShownRow[]>(() => {
    if (data === null) return [];
    return data.rows.map((r) => {
      const key = liveKey(r.type, r.strike);
      const live = r.amended ? undefined : ticks.rows.get(key); // pinned rows never tick
      if (live === undefined) return { ...r, key, live: false };
      const { bidIv, midIv, askIv, bidPrice, midPrice, askPrice } = live;
      return { ...r, key, live: true, bidIv, midIv, askIv, bidPrice, midPrice, askPrice };
    });
  }, [data, ticks.rows]);
  // Alternate the flash class per frame so a cell ticking on consecutive frames
  // re-triggers its animation (same class = no restart).
  const flashClass = ticks.seq % 2 ? "volfit-tick-a" : "volfit-tick-b";
  const flash = (key: string) => (ticks.flash.has(key) ? flashClass : "");

  // Fetch on open; refetch when the node / fit mode changes or the smile is
  // refitted (edits, undo/redo, hyperparameter changes all swap `smile`).
  useEffect(() => {
    if (ticker === "" || expiry === "") return;
    const controller = new AbortController();
    setLoading(true);
    api
      .get<TableResponse>(`/smiles/${ticker}/${expiry}/table`, {
        params: { fit_mode: fitMode },
        signal: controller.signal,
      })
      .then((d) => {
        setData(d);
        setError(null);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return; // superseded or unmounted
        setData(null);
        setLoading(false);
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [ticker, expiry, fitMode, smile]);

  /** Copy the whole table as displayed (TSV incl. header, live overlay applied). */
  const onCopy = () => {
    if (data === null) return;
    void navigator.clipboard
      .writeText(toTsv(shown))
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      })
      .catch(() => {
        /* clipboard denied: silently ignore, CSV export still works */
      });
  };

  /** Open the backend CSV endpoint; the browser handles the download. */
  const onCsv = () => {
    const url =
      `${API_BASE_URL}/smiles/${encodeURIComponent(ticker)}/` +
      `${encodeURIComponent(expiry)}/table.csv?fit_mode=${fitMode}`;
    window.open(url, "_blank");
  };

  if (data === null) {
    return loading
      ? message("Loading quote table…")
      : message(`Table unavailable${error !== null ? ` (${error})` : ""}.`);
  }

  const num = "px-2 py-1 text-right tabular-nums";
  return (
    <div
      className={[
        "flex h-full min-h-0 flex-col transition-opacity",
        loading ? "opacity-60" : "opacity-100",
      ].join(" ")}
    >
      {/* Scrollable grid with a sticky header */}
      <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
        <table className="w-full border-collapse font-mono text-[11px] leading-tight">
          <thead className="sticky top-0 z-10 bg-surface-800 text-slate-400">
            <tr>
              {HEADERS.map((h) => (
                <th
                  key={h}
                  className={[
                    "px-2 py-1.5 font-medium whitespace-nowrap",
                    h === "C/P" ? "text-center" : "text-right",
                  ].join(" ")}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {shown.map((r) => (
              <tr
                key={r.index}
                className={[
                  "hover:bg-surface-800/60",
                  r.excluded ? "text-slate-600 opacity-50" : "text-slate-200",
                ].join(" ")}
                title={r.excluded ? "excluded from calibration" : r.live ? "live market (streaming)" : undefined}
              >
                <td className={num}>{r.strike.toFixed(2)}</td>
                <td className="px-2 py-1 text-center text-slate-400">{r.type}</td>
                <td className={`${num} text-slate-400`}>{r.k.toFixed(3)}</td>
                <td className={`${num} ${flash(r.key)}`}>{formatPct(r.bidIv, 2)}</td>
                <td
                  className={[num, flash(r.key), r.amended ? "font-semibold text-amber-400" : ""].join(" ")}
                  title={r.amended ? "mid manually amended (pinned — does not tick)" : undefined}
                >
                  {formatPct(r.midIv, 2)}
                </td>
                <td className={`${num} ${flash(r.key)}`}>{formatPct(r.askIv, 2)}</td>
                <td className={`${num} text-accent-400`}>{formatPct(r.modelIv, 2)}</td>
                <td className={`${num} ${flash(r.key)}`}>{r.bidPrice.toFixed(2)}</td>
                <td className={`${num} ${flash(r.key)}`}>{r.midPrice.toFixed(2)}</td>
                <td className={`${num} ${flash(r.key)}`}>{r.askPrice.toFixed(2)}</td>
                <td className={`${num} text-slate-400`}>
                  {r.excluded ? "—" : (weightByIndex.get(r.index)?.toFixed(2) ?? "—")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Var-swap quote row (Options-gated): quoted level vs the model's own */}
      {smile?.varSwap.enabled && (
        <div className="mt-2 flex shrink-0 items-center gap-3 rounded-md border border-slate-800 bg-surface-950/40 px-2 py-1 font-mono text-[11px]">
          <span className="text-slate-400">Variance swap</span>
          <span className="text-teal-300">
            quote{" "}
            {smile.varSwap.level === null
              ? "—"
              : `${formatPct(smile.varSwap.level, 2)}${smile.varSwap.excluded ? " (excl)" : ""}`}
          </span>
          <span className="text-slate-500">model {formatPct(smile.varSwap.modelVol, 2)}</span>
          <span className="text-slate-600">(edit in the aside)</span>
        </div>
      )}

      {/* Footer: node metadata + export actions */}
      <div className="mt-2 flex shrink-0 items-center gap-2">
        <span className="font-mono text-[10px] text-slate-500">
          {data.rows.length} quotes · T {data.t.toFixed(3)}y · F {data.forward.toFixed(2)} · df{" "}
          {data.discount.toFixed(4)}
        </span>
        {ticks.streaming && (
          <span
            className="flex items-center gap-1.5 font-mono text-[10px]"
            title={
              ticks.ready
                ? "Live market off the streaming book, overlaid on the calibrated rows (Model IV stays the fit's; amended rows are pinned)"
                : "The stream is up but the book has not served this node yet"
            }
          >
            <span
              className={[
                "inline-block h-1.5 w-1.5 rounded-full",
                ticks.ready ? "bg-emerald-400 volfit-live-dot" : "bg-amber-400",
              ].join(" ")}
            />
            <span className={ticks.ready ? "text-emerald-400" : "text-amber-400"}>
              {ticks.ready
                ? `LIVE ${ticks.rows.size} · ${tickTime(ticks.ts)}` +
                  (ticks.spot !== null ? ` · S ${ticks.spot.toFixed(2)}` : "")
                : "live feed warming"}
            </span>
          </span>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          <button
            className={toolbarButtonClass}
            onClick={onCopy}
            title="Copy the table to the clipboard (TSV, header included)"
          >
            {copied ? "Copied ✓" : "Copy"}
          </button>
          <button
            className={toolbarButtonClass}
            onClick={onCsv}
            title="Download as CSV (rendered by the backend)"
          >
            CSV
          </button>
        </div>
      </div>
    </div>
  );
}
