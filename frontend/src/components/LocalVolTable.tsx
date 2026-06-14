// Quote / reconstructed-IV / price table of one Local Vol expiry (Phase 10).
//
// Presentational: the parent (LocalVolViewer) fetches POST /fit/affine/{ticker}
// /table?expiry= via useAffineView and passes the payload here. Mirrors the
// Parametric QuoteTable's dense monospace grid (model IV = the reconstructed
// affine smile at each strike). Copy-as-TSV only — the affine table is a POST
// endpoint, so there is no CSV download link.
import { useState } from "react";
import { formatPct } from "../lib/chartScale";
import { toolbarButtonClass } from "./QuoteToolbar";

/** One row of POST /fit/affine/{ticker}/table (backend TableRow). */
export interface AffineTableRow {
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

/** Response of POST /fit/affine/{ticker}/table (backend TableResponse). */
export interface AffineTableData {
  ticker: string;
  expiry: string;
  t: number;
  forward: number;
  discount: number;
  rows: AffineTableRow[];
}

const HEADERS = ["Strike", "C/P", "k", "Bid IV", "Mid IV", "Ask IV", "Model IV", "Bid", "Mid", "Ask"];

function toTsv(rows: AffineTableRow[]): string {
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

export default function LocalVolTable({ data }: { data: AffineTableData }) {
  const [copied, setCopied] = useState(false);

  const onCopy = () => {
    void navigator.clipboard
      .writeText(toTsv(data.rows))
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      })
      .catch(() => {
        /* clipboard denied: ignore */
      });
  };

  const num = "px-2 py-1 text-right tabular-nums";
  return (
    <div className="flex h-full min-h-0 flex-col">
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
            {data.rows.map((r) => (
              <tr
                key={r.index}
                className={[
                  "hover:bg-surface-800/60",
                  r.excluded ? "text-slate-600 opacity-50" : "text-slate-200",
                ].join(" ")}
              >
                <td className={num}>{r.strike.toFixed(2)}</td>
                <td className="px-2 py-1 text-center text-slate-400">{r.type}</td>
                <td className={`${num} text-slate-400`}>{r.k.toFixed(3)}</td>
                <td className={num}>{formatPct(r.bidIv, 2)}</td>
                <td className={num}>{formatPct(r.midIv, 2)}</td>
                <td className={num}>{formatPct(r.askIv, 2)}</td>
                <td className={`${num} text-accent-400`}>{formatPct(r.modelIv, 2)}</td>
                <td className={num}>{r.bidPrice.toFixed(2)}</td>
                <td className={num}>{r.midPrice.toFixed(2)}</td>
                <td className={num}>{r.askPrice.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex shrink-0 items-center gap-2">
        <span className="font-mono text-[10px] text-slate-500">
          {data.rows.length} quotes · T {data.t.toFixed(3)}y · F {data.forward.toFixed(2)} · df{" "}
          {data.discount.toFixed(4)} · reconstructed from the local-vol surface
        </span>
        <button className={`${toolbarButtonClass} ml-auto`} onClick={onCopy}>
          {copied ? "Copied ✓" : "Copy"}
        </button>
      </div>
    </div>
  );
}
