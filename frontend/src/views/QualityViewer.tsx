// Quality workspace: the universe fit-quality dashboard (commercial MVP).
// Headline tiles (ready / stale / arb / RMS), a per-ticker rollup (incl. the
// LV surface health) and the per-node exception table — all served from the
// backend's cached calibrations (GET /quality never fits), refreshed on every
// calibration epoch like the other views.
import { useMemo, useState } from "react";
import { useQuality } from "../state/useQuality";
import type { QualityNode, QualityTicker } from "../state/useQuality";

const card =
  "flex min-h-0 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30";
const th = "px-2 py-1.5 font-medium whitespace-nowrap text-right";
const td = "px-2 py-1 text-right tabular-nums";

type SortMode = "exceptions" | "rms" | "node";

/** Order rows for the table: exceptions first (not-ready, worst RMS on top),
 *  by RMS, or in natural ticker/expiry order. */
function sortNodes(nodes: QualityNode[], mode: SortMode): QualityNode[] {
  const rows = [...nodes];
  if (mode === "node") return rows; // backend order: ticker, ascending expiry
  if (mode === "rms") return rows.sort((a, b) => b.rmsBp - a.rmsBp);
  return rows.sort((a, b) => {
    if (a.ready !== b.ready) return a.ready ? 1 : -1;
    return b.rmsBp - a.rmsBp;
  });
}

function Tile({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col rounded-lg border border-slate-800 bg-surface-800 px-3 py-2">
      <span className="text-[10px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className={`font-mono text-lg leading-tight ${tone ?? "text-slate-200"}`}>
        {value}
      </span>
    </div>
  );
}

function StatusCell({ node }: { node: QualityNode }) {
  if (node.ready) {
    return (
      <span className="inline-flex items-center gap-1.5 text-emerald-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> ready
      </span>
    );
  }
  const arb = !node.leeOk || !node.calendarOk;
  const tone = !node.hasFit ? "text-slate-500" : arb ? "text-rose-400" : "text-amber-300";
  const dot = !node.hasFit ? "bg-slate-600" : arb ? "bg-rose-500" : "bg-amber-400";
  return (
    <span className={`inline-flex items-center gap-1.5 ${tone}`} title={node.issues.join("; ")}>
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {node.issues.join(" · ")}
    </span>
  );
}

function LvCell({ ticker }: { ticker: QualityTicker }) {
  const lv = ticker.lv;
  if (lv === null) return <span className="text-slate-600">—</span>;
  const tone = !lv.arbitrageFree ? "text-rose-400" : lv.stale ? "text-amber-300" : "text-slate-300";
  const flags = [
    lv.stale ? "stale" : null,
    lv.arbitrageFree ? null : `arb (${lv.calendarViolations} cal)`,
  ].filter((f): f is string => f !== null);
  return (
    <span className={tone}>
      {lv.rmsIvErrorBp.toFixed(1)} bp{flags.length > 0 ? ` · ${flags.join(" · ")}` : ""}
    </span>
  );
}

export default function QualityViewer() {
  const { report, loading, error, reload } = useQuality();
  const [sortMode, setSortMode] = useState<SortMode>("exceptions");
  const [onlyExceptions, setOnlyExceptions] = useState(false);

  const rows = useMemo(() => {
    if (report === null) return [];
    const nodes = onlyExceptions ? report.nodes.filter((n) => !n.ready) : report.nodes;
    return sortNodes(nodes, sortMode);
  }, [report, sortMode, onlyExceptions]);

  // Live-only view: without the backend there is nothing meaningful to show.
  if (error !== null && report === null) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className={`${card} max-w-md items-center text-center`}>
          <p className="text-sm font-medium text-slate-200">Quality dashboard requires the live backend</p>
          <p className="mt-2 text-xs text-slate-500">{error}</p>
          <button
            onClick={reload}
            className="mt-4 rounded-md bg-accent-600 px-3 py-1.5 text-xs font-medium text-white enabled:hover:bg-accent-500"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }
  if (report === null) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Loading quality report…
      </div>
    );
  }

  const s = report.summary;
  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4">
      {/* Headline tiles */}
      <div className="grid grid-cols-4 gap-2 lg:grid-cols-8">
        <Tile
          label="Publish ready"
          value={`${s.readyNodes}/${s.litNodes}`}
          tone={s.readyNodes === s.litNodes && s.litNodes > 0 ? "text-emerald-400" : "text-slate-200"}
        />
        <Tile label="Fitted" value={`${s.fitted}`} />
        <Tile label="Stale" value={`${s.stale}`} tone={s.stale > 0 ? "text-amber-300" : undefined} />
        <Tile label="No fit" value={`${s.noFit}`} tone={s.noFit > 0 ? "text-slate-400" : undefined} />
        <Tile label="Arb flags" value={`${s.arbFlags}`} tone={s.arbFlags > 0 ? "text-rose-400" : undefined} />
        <Tile label="Median RMS" value={`${s.medianRmsBp.toFixed(1)} bp`} />
        <Tile
          label="Worst RMS"
          value={`${s.worstRmsBp.toFixed(1)} bp`}
          tone={s.worstRmsBp > report.rmsBudgetBp ? "text-amber-300" : undefined}
        />
        <Tile
          label="LV surfaces"
          value={s.lvTickers > 0 ? `${s.lvArbFree}/${s.lvTickers} arb-free` : "—"}
          tone={s.lvTickers > 0 && s.lvArbFree < s.lvTickers ? "text-rose-400" : undefined}
        />
      </div>

      <div className="flex min-h-0 flex-1 gap-3">
        {/* Per-ticker rollup */}
        <div className={`${card} w-[380px] shrink-0`}>
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Tickers</h2>
            <span className="text-[10px] text-slate-600">
              mode {report.fitMode} · filter {s.filterMode} · prior {s.priorMode}
            </span>
          </div>
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
            <table className="w-full border-collapse font-mono text-[11px] leading-tight">
              <thead className="sticky top-0 z-10 bg-surface-800 text-slate-400">
                <tr>
                  <th className={`${th} text-left`}>Ticker</th>
                  <th className={th}>Ready</th>
                  <th className={th}>Stale</th>
                  <th className={th}>RMS bp</th>
                  <th className={th}>Arb</th>
                  <th className={th}>LV</th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                {report.tickers.map((t) => (
                  <tr key={t.ticker} className="border-t border-slate-800/60">
                    <td className="px-2 py-1 text-left font-semibold">{t.ticker}</td>
                    <td className={`${td} ${t.ready === t.nodes ? "text-emerald-400" : ""}`}>
                      {t.ready}/{t.nodes}
                    </td>
                    <td className={`${td} ${t.stale > 0 ? "text-amber-300" : ""}`}>{t.stale}</td>
                    <td className={td}>{t.surfaceRmsBp.toFixed(1)}</td>
                    <td className={`${td} ${t.arbFlags > 0 ? "text-rose-400" : ""}`}>{t.arbFlags}</td>
                    <td className={`${td} text-left`}>
                      <LvCell ticker={t} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Per-node table */}
        <div className={`${card} min-w-0 flex-1`}>
          <div className="mb-2 flex items-center justify-between gap-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Nodes {loading ? "· refreshing…" : ""}
            </h2>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <label className="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={onlyExceptions}
                  onChange={(e) => setOnlyExceptions(e.target.checked)}
                  className="accent-accent-600"
                />
                exceptions only
              </label>
              <select
                value={sortMode}
                onChange={(e) => setSortMode(e.target.value as SortMode)}
                className="rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-[11px] text-slate-300"
              >
                <option value="exceptions">Exceptions first</option>
                <option value="rms">Worst RMS first</option>
                <option value="node">Ticker · expiry</option>
              </select>
              <button
                onClick={reload}
                className="rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1 text-[11px] font-medium text-slate-300 enabled:hover:border-slate-600"
              >
                Refresh
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
            <table className="w-full border-collapse font-mono text-[11px] leading-tight">
              <thead className="sticky top-0 z-10 bg-surface-800 text-slate-400">
                <tr>
                  <th className={`${th} text-left`}>Node</th>
                  <th className={th}>Model</th>
                  <th className={th}>#Q</th>
                  <th className={th}>RMS bp</th>
                  <th className={th}>Max IV bp</th>
                  <th className={th}>ATM</th>
                  <th className={th}>Lee L/R</th>
                  <th className={th}>Cal viol</th>
                  <th className={`${th} text-left`}>Status</th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                {rows.map((n) => (
                  <tr key={`${n.ticker}|${n.expiry}`} className="border-t border-slate-800/60">
                    <td className="px-2 py-1 text-left">
                      <span className="font-semibold">{n.ticker}</span>{" "}
                      <span className="text-slate-500">{n.expiry}</span>
                      {n.varSwapQuoted ? <span className="ml-1 text-accent-400" title="var-swap quote active">VS</span> : null}
                      {n.filterActive ? (
                        <span
                          className={`ml-1 ${n.filterContaminated ? "text-amber-300" : "text-slate-500"}`}
                          title={n.filterContaminated ? "filter active (contaminated measurement)" : "filter active"}
                        >
                          F
                        </span>
                      ) : null}
                    </td>
                    <td className={td}>{n.hasFit ? n.model : "—"}</td>
                    <td className={td}>{n.hasFit ? n.nQuotes : "—"}</td>
                    <td className={`${td} ${n.hasFit && n.rmsBp > report.rmsBudgetBp ? "text-amber-300" : ""}`}>
                      {n.hasFit ? n.rmsBp.toFixed(1) : "—"}
                    </td>
                    <td className={td}>{n.hasFit ? n.maxIvBp.toFixed(1) : "—"}</td>
                    <td className={td}>{n.hasFit ? `${(n.atmVol * 100).toFixed(1)}%` : "—"}</td>
                    <td className={`${td} ${!n.leeOk ? "text-rose-400" : ""}`}>
                      {n.hasFit ? `${n.leeLeft.toFixed(2)}/${n.leeRight.toFixed(2)}` : "—"}
                    </td>
                    <td className={`${td} ${!n.calendarOk ? "text-rose-400" : ""}`}>
                      {n.hasFit ? (n.calendarViolation > 0 ? n.calendarViolation.toExponential(1) : "0") : "—"}
                    </td>
                    <td className="px-2 py-1 text-left">
                      <StatusCell node={n} />
                    </td>
                  </tr>
                ))}
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="px-2 py-6 text-center text-slate-500">
                      {onlyExceptions ? "No exceptions — every node is publish-ready." : "No lit nodes (fetch a universe first)."}
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
