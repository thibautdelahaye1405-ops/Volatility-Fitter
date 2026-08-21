// Quote table of the current smile node on the two-frame grammar of the chart
// (lib/tableFrames): one row per STRIKE joining
//   MARKET (primary)  the prevailing bid/mid/ask IV with their fit target, the
//                     fit ROLLED to the prevailing spot ("Model", Δ in vol bp vs
//                     the market mid) and prices at the market forward — live
//                     rows (flashing on ticks) when the node streams, else the
//                     latest fetched chain;
//   CALIB  (toggle)   the quotes + target the last calibration used (your
//                     exclusions dimmed, amended mids amber), the fit on its
//                     calibration spot, and the calibration weight.
// Footer: both frames' forwards / stamps, a LIVE badge, Copy (TSV as shown)
// and the backend CSVs (market / calibration). Live backend only.
import { useEffect, useMemo, useState } from "react";
import { api, API_BASE_URL } from "../state/api";
import type { FitMode } from "../state/useSmile";
import type { LiveTicksState } from "../state/useLiveTicks";
import { useWeights } from "../state/useWeights";
import type { SmileData } from "../lib/mockData";
import { formatPct } from "../lib/chartScale";
import { composeTableRows, deltaBp, toTsv } from "../lib/tableFrames";
import type { TableResponse, TableRow } from "../lib/tableFrames";
import { toolbarButtonClass } from "./QuoteToolbar";

interface QuoteTableProps {
  ticker: string;
  expiry: string;
  fitMode: FitMode;
  /** Current smile: its identity changes on every refit/edit, so keeping it
   *  in the fetch deps refreshes the table after quote edits. */
  smile: SmileData | null;
  /** The node's live ticks (one SSE connection hosted by SmileViewer, shared
   *  with the chart); the market frame is live when the stream is ready. */
  ticks: LiveTicksState;
  /** Show the calibration columns (the viewer's "Calib. quotes" toggle). */
  showCalib: boolean;
}

/** "HH:MM:SS UTC" of a backend (UTC-naive ISO) stamp; "" when unknown. */
const tickTime = (iso: string | null): string => (iso ? `${iso.slice(11, 19)} UTC` : "");

const MARKET_HEADERS = ["Strike", "C/P", "k", "Bid IV", "Mid IV", "Ask IV", "Target", "Model", "Δ bp", "Bid", "Mid", "Ask"];
const CALIB_HEADERS = ["Bid IV", "Mid IV", "Ask IV", "Target", "Model", "Δ bp", "Weight"];

/** Centered placeholder for loading / error states. */
const message = (text: string) => (
  <div className="flex h-full items-center justify-center text-xs text-slate-500">{text}</div>
);

const pct = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : formatPct(v, 2));
const px = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "—" : v.toFixed(2));
const bp = (v: number | null) => (v === null ? "—" : `${v > 0 ? "+" : ""}${v}`);
/** The fit target of a row for the viewed mode: the band (lo–hi, 1 dp %) or "mid". */
function targetText(r: TableRow | null, fitMode: FitMode): string {
  if (r === null) return "—";
  if (fitMode === "mid" || r.targetLo == null || r.targetHi == null) return "mid";
  return `${(r.targetLo * 100).toFixed(1)}–${(r.targetHi * 100).toFixed(1)}`;
}

export default function QuoteTable({ ticker, expiry, fitMode, smile, ticks, showCalib }: QuoteTableProps) {
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

  // The two frames joined by strike (live market rows when streaming & ready).
  const frames = useMemo(() => (data ? composeTableRows(data, ticks) : null), [data, ticks]);
  // Alternate the flash class per frame so a cell ticking on consecutive frames
  // re-triggers its animation (same class = no restart).
  const flashClass = ticks.seq % 2 ? "volfit-tick-a" : "volfit-tick-b";

  /** Copy the joined table as displayed (TSV incl. header). */
  const onCopy = () => {
    if (frames === null) return;
    void navigator.clipboard
      .writeText(toTsv(frames.rows, showCalib))
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      })
      .catch(() => {
        /* clipboard denied: silently ignore, CSV export still works */
      });
  };

  /** Open a backend CSV (market or calibration frame); the browser downloads it. */
  const onCsv = (frame: "market" | "calib") => {
    const url =
      `${API_BASE_URL}/smiles/${encodeURIComponent(ticker)}/` +
      `${encodeURIComponent(expiry)}/table.csv?fit_mode=${fitMode}&frame=${frame}`;
    window.open(url, "_blank");
  };

  if (data === null || frames === null) {
    return loading
      ? message("Loading quote table…")
      : message(`Table unavailable${error !== null ? ` (${error})` : ""}.`);
  }

  const num = "px-2 py-1 text-right tabular-nums";
  const th = "px-2 py-1 font-medium whitespace-nowrap text-right";
  const group = "px-2 py-1 text-left font-semibold tracking-wide uppercase text-[10px]";
  const marketLabel = frames.live
    ? `Market · live ${tickTime(frames.marketTimestamp)}`
    : `Market · latest chain${frames.marketTimestamp ? ` ${tickTime(frames.marketTimestamp)}` : ""}`;
  return (
    <div
      className={[
        "flex h-full min-h-0 flex-col transition-opacity",
        loading ? "opacity-60" : "opacity-100",
      ].join(" ")}
    >
      {/* Scrollable grid with a sticky two-row header (frame groups + columns) */}
      <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
        <table className="w-full border-collapse font-mono text-[11px] leading-tight">
          <thead className="sticky top-0 z-10 bg-surface-800 text-slate-400">
            <tr className="border-b border-slate-800/80">
              <th className={`${group} text-red-300/90`} colSpan={MARKET_HEADERS.length}
                title="The prevailing market (as quoted, no edits) with the fit target of the viewed mode and the fit rolled to the prevailing spot">
                {marketLabel}
                {frames.marketForward !== null ? ` · F ${frames.marketForward.toFixed(2)}` : ""}
                {frames.marketSpot != null ? ` · S ${frames.marketSpot.toFixed(2)}` : ""}
              </th>
              {showCalib && (
                <th className={`${group} border-l border-slate-700 text-slate-300/80`} colSpan={CALIB_HEADERS.length}
                  title="The quotes + target the last calibration used (with your exclusions / amended mids), the fit on its calibration spot and the calibration weight">
                  Calibration · F {frames.calibForward.toFixed(2)}
                </th>
              )}
            </tr>
            <tr>
              {MARKET_HEADERS.map((h) => (
                <th key={`m-${h}`} className={`${th} ${h === "C/P" ? "text-center" : ""}`}>{h}</th>
              ))}
              {showCalib &&
                CALIB_HEADERS.map((h, i) => (
                  <th key={`c-${h}`} className={`${th} ${i === 0 ? "border-l border-slate-700" : ""}`}>{h}</th>
                ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {frames.rows.map((row) => {
              const m = row.market;
              const c = row.calib;
              const side = m?.type ?? c?.type ?? "";
              const flash = row.hot ? flashClass : "";
              const calibCls = c?.excluded ? "text-slate-600 opacity-50" : "text-slate-300";
              return (
                <tr key={row.key} className="text-slate-200 hover:bg-surface-800/60">
                  <td className={num}>{row.strike.toFixed(2)}</td>
                  <td className="px-2 py-1 text-center text-slate-400">{side}</td>
                  <td className={`${num} text-slate-400`}>{m ? m.k.toFixed(3) : c ? c.k.toFixed(3) : "—"}</td>
                  <td className={`${num} ${flash}`}>{pct(m?.bidIv)}</td>
                  <td className={`${num} ${flash}`}>{pct(m?.midIv)}</td>
                  <td className={`${num} ${flash}`}>{pct(m?.askIv)}</td>
                  <td className={`${num} text-slate-400`}>{targetText(m, fitMode)}</td>
                  <td className={`${num} text-accent-400`}>{pct(m?.modelIv)}</td>
                  <td className={`${num} text-slate-400`}>{bp(deltaBp(m))}</td>
                  <td className={`${num} ${flash}`}>{px(m?.bidPrice)}</td>
                  <td className={`${num} ${flash}`}>{px(m?.midPrice)}</td>
                  <td className={`${num} ${flash}`}>{px(m?.askPrice)}</td>
                  {showCalib && (
                    <>
                      <td className={`${num} border-l border-slate-700 ${calibCls}`}
                        title={c?.excluded ? "excluded from calibration" : undefined}>{pct(c?.bidIv)}</td>
                      <td className={[num, calibCls, c?.amended ? "font-semibold text-amber-400" : ""].join(" ")}
                        title={c?.amended ? "mid manually amended" : c?.excluded ? "excluded from calibration" : undefined}>
                        {pct(c?.midIv)}
                      </td>
                      <td className={`${num} ${calibCls}`}>{pct(c?.askIv)}</td>
                      <td className={`${num} text-slate-400 ${c?.excluded ? "opacity-50" : ""}`}>{targetText(c, fitMode)}</td>
                      <td className={`${num} text-accent-400/80 ${c?.excluded ? "opacity-50" : ""}`}>{pct(c?.modelIv)}</td>
                      <td className={`${num} text-slate-400 ${c?.excluded ? "opacity-50" : ""}`}>{bp(deltaBp(c))}</td>
                      <td className={`${num} text-slate-400`}>
                        {c === null || c.excluded ? "—" : (weightByIndex.get(c.index)?.toFixed(2) ?? "—")}
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
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

      {/* Footer: node metadata + LIVE badge + export actions */}
      <div className="mt-2 flex shrink-0 items-center gap-2">
        <span className="font-mono text-[10px] text-slate-500">
          {frames.rows.length} strikes · T {data.t.toFixed(3)}y · df {data.discount.toFixed(4)}
          {!showCalib ? ` · calibration F ${frames.calibForward.toFixed(2)} (toggle “Calib. quotes”)` : ""}
        </span>
        {ticks.streaming && (
          <span
            className="flex items-center gap-1.5 font-mono text-[10px]"
            title={
              frames.live
                ? "Market frame off the streaming book (Model = the fit rolled to the live spot)"
                : "The stream is up but the book has not served this node yet"
            }
          >
            <span
              className={[
                "inline-block h-1.5 w-1.5 rounded-full",
                frames.live ? "bg-emerald-400 volfit-live-dot" : "bg-amber-400",
              ].join(" ")}
            />
            <span className={frames.live ? "text-emerald-400" : "text-amber-400"}>
              {frames.live ? `LIVE ${tickTime(frames.marketTimestamp)}` : "live feed warming"}
            </span>
          </span>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          <button className={toolbarButtonClass} onClick={onCopy} title="Copy the table as shown (TSV, header included)">
            {copied ? "Copied ✓" : "Copy"}
          </button>
          <button className={toolbarButtonClass} onClick={() => onCsv("market")} title="Download the market frame as CSV (rendered by the backend)">
            CSV market
          </button>
          <button className={toolbarButtonClass} onClick={() => onCsv("calib")} title="Download the calibration frame as CSV (rendered by the backend)">
            CSV calib
          </button>
        </div>
      </div>
    </div>
  );
}
