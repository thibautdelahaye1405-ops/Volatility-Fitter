// Quality lens: the universe fit-quality dashboard (commercial MVP, UI SHELL
// v2 S3). Headline tiles + the active tab's node certificate on the top row,
// then a per-ticker rollup (incl. the LV surface health) and the per-node
// exception table — all served from the backend's cached calibrations (GET
// /quality never fits) via the shared QualityProvider, refreshed on every
// calibration epoch like the other views.
//
// Universe-level lens: it renders without a tab, HIGHLIGHTS the active tab's
// node (ticker row + node row, kept in view) and lets a row click open that
// node's tab (click = preview, double-click = pinned) through the workbench.
import { useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, FileJson, FileSpreadsheet, RefreshCw } from "lucide-react";
import QualityNodeCard, {
  AGE_TIP,
  BELLY_TIP,
  EXTRAP_TIP,
  StatusCell,
  ageTone,
  bellyText,
  bellyTitle,
  extrapText,
  fmtAge,
} from "../components/quality/QualityNodeCard";
import QualityTiles from "../components/quality/QualityTiles";
import { fmtBp, sortNodes } from "../lib/qualityFormat";
import type { SortMode } from "../lib/qualityFormat";
import { cardClass } from "../lib/ui";
import { API_BASE_URL } from "../state/api";
import { useQualityReport } from "../state/qualityContext";
import type { QualityTicker } from "../state/useQuality";
import { useOptionalWorkbench } from "../state/workbench";

const card = `flex min-h-0 flex-col p-4 ${cardClass}`;
const th = "px-2 py-1.5 font-medium whitespace-nowrap text-right";
const td = "px-2 py-1 text-right tabular-nums";
const activeRow = "bg-accent-500/10 text-accent-200";

function LvCell({ ticker }: { ticker: QualityTicker }) {
  const lv = ticker.lv;
  if (lv === null) return <span className="text-slate-600">—</span>;
  // The headline is the CONVERGED-operator reprice RMS (the honest number);
  // a large gap to the in-operator rms means the optimizer compensated for
  // operator error — the surface is untrustworthy however good the fit looks.
  const conv = lv.rmsConvergedBp || lv.rmsIvErrorBp; // 0 = legacy cache, fall back
  const opGap = lv.rmsConvergedBp > 0 && conv > 1.5 * lv.rmsIvErrorBp + 2;
  const tone = !lv.arbitrageFree || opGap
    ? "text-rose-400"
    : lv.stale
      ? "text-amber-300"
      : "text-slate-300";
  const flags = [
    lv.stale ? "stale" : null,
    lv.arbitrageFree ? null : `arb (${lv.calendarViolations} cal)`,
    opGap ? `op-err (fit ${fmtBp(lv.rmsIvErrorBp)})` : null,
  ].filter((f): f is string => f !== null);
  return (
    <span className={tone} title="Converged-operator reprice RMS (honest LV fit error)">
      {fmtBp(conv)} bp{flags.length > 0 ? ` · ${flags.join(" · ")}` : ""}
    </span>
  );
}

export default function QualityViewer() {
  const { report, loading, error, reload, nodeOf } = useQualityReport();
  const wb = useOptionalWorkbench(); // null outside the shell (tests, legacy mounts)
  const [sortMode, setSortMode] = useState<SortMode>("exceptions");
  const [onlyExceptions, setOnlyExceptions] = useState(false);

  const rows = useMemo(() => {
    if (report === null) return [];
    const nodes = onlyExceptions ? report.nodes.filter((n) => !n.ready) : report.nodes;
    return sortNodes(nodes, sortMode);
  }, [report, sortMode, onlyExceptions]);

  // The active tab's node: undefined = no tab open; null = tab open but the
  // report has no row for it (not lit / never fitted) — the card tells apart.
  const active = wb?.activeTab ?? null;
  const activeKey = active?.key ?? null;
  const activeNode = active === null ? undefined : (nodeOf(active.ticker, active.expiry) ?? null);

  // Keep the highlighted row in view when the tab changes ("nearest" never
  // jumps a row that is already visible). jsdom lacks scrollIntoView — guard.
  const activeRowRef = useRef<HTMLTableRowElement>(null);
  useEffect(() => {
    activeRowRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [activeKey, rows]);

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
    <div className="flex h-full min-h-0 flex-col gap-3 p-3">
      {/* Top row: headline tiles + the active tab's certificate card. */}
      <div className="flex items-stretch gap-3">
        <div className="min-w-0 flex-1">
          <QualityTiles summary={s} rmsBudgetBp={report.rmsBudgetBp} />
        </div>
        <QualityNodeCard
          node={activeNode}
          rmsBudgetBp={report.rmsBudgetBp}
          fitMode={report.fitMode}
          label={active === null ? "Node certificate" : `${active.ticker} · ${active.expiry}`}
        />
      </div>

      <div className="flex min-h-0 flex-1 gap-3">
        {/* Per-ticker rollup */}
        <div className={`${card} w-[380px] shrink-0`}>
          <div className="mb-2 flex items-baseline justify-between">
            <h2 className="text-sm font-semibold text-slate-100">Tickers</h2>
            <span className="text-[10px] text-slate-600">
              mode {report.fitMode} · filter {s.filterMode} · prior {s.priorMode}
            </span>
          </div>
          {/* Publish workflow — EXPORTS, not view tabs: the HTML report opens
              in a tab (save/share from there); the surface artifacts download
              with a dated filename + reproducibility manifest. All read cached
              fits only. */}
          <div className="mb-2 flex items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-slate-600">Export</span>
            <a
              href={`${API_BASE_URL}/export/report`}
              target="_blank"
              rel="noreferrer"
              title="Open the HTML quality report in a new tab"
              className="flex items-center gap-1 whitespace-nowrap rounded-md bg-accent-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-accent-500"
            >
              <ExternalLink size={11} strokeWidth={1.75} className="opacity-90" />
              Report
            </a>
            <a
              href={`${API_BASE_URL}/export/surfaces`}
              title="Download every published surface as JSON (dated, with a reproducibility manifest)"
              className="flex items-center gap-1 whitespace-nowrap rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:border-slate-600 hover:text-slate-100"
            >
              <FileJson size={11} strokeWidth={1.75} className="opacity-80" />
              Surfaces JSON
            </a>
            <a
              href={`${API_BASE_URL}/export/surfaces?format=csv`}
              title="Download every published surface as CSV"
              className="flex items-center gap-1 whitespace-nowrap rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:border-slate-600 hover:text-slate-100"
            >
              <FileSpreadsheet size={11} strokeWidth={1.75} className="opacity-80" />
              Surfaces CSV
            </a>
          </div>
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
            <table className="w-full border-collapse font-mono text-[11px] leading-tight">
              <thead className="sticky top-0 z-10 bg-surface-800 text-slate-400">
                <tr>
                  <th className={`${th} text-left`}>Ticker</th>
                  <th className={th}>Ready</th>
                  <th className={th}>Stale</th>
                  <th className={th} title={AGE_TIP}>
                    Age
                  </th>
                  <th className={th}>RMS bp</th>
                  <th className={th}>Arb</th>
                  <th className={th}>LV</th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                {report.tickers.map((t) => (
                  <tr
                    key={t.ticker}
                    className={`border-t border-slate-800/60 ${active?.ticker === t.ticker ? "bg-accent-500/10" : ""}`}
                  >
                    <td className="px-2 py-1 text-left font-semibold">{t.ticker}</td>
                    <td className={`${td} ${t.ready === t.nodes ? "text-emerald-400" : ""}`}>
                      {t.ready}/{t.nodes}
                    </td>
                    <td className={`${td} ${t.stale > 0 ? "text-amber-300" : ""}`}>{t.stale}</td>
                    <td className={`${td} ${ageTone(t.dataAgeMin)}`}>{fmtAge(t.dataAgeMin)}</td>
                    <td className={td}>{fmtBp(t.surfaceRmsBp)}</td>
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
            <h2 className="text-sm font-semibold text-slate-100">
              Nodes {loading ? <span className="text-slate-500">· refreshing…</span> : ""}
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
                title="Re-read the cached calibrations"
                className="flex items-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1 text-[11px] font-medium text-slate-300 enabled:hover:border-slate-600 enabled:hover:text-slate-100"
              >
                <RefreshCw size={11} strokeWidth={1.75} className="opacity-80" />
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
                  <th className={th} title={EXTRAP_TIP}>Extrap g·cal</th>
                  <th className={th} title={BELLY_TIP}>Belly g</th>
                  <th className={`${th} text-left`}>Status</th>
                </tr>
              </thead>
              <tbody className="text-slate-300">
                {rows.map((n) => {
                  const key = `${n.ticker}|${n.expiry}`;
                  const isActive = key === activeKey;
                  return (
                    <tr
                      key={key}
                      ref={isActive ? activeRowRef : undefined}
                      className={`cursor-pointer border-t border-slate-800/60 ${isActive ? activeRow : "hover:bg-surface-800/60"}`}
                      title="Click: preview the node's tab · double-click: pin it"
                      onClick={() => wb?.openNode({ ticker: n.ticker, expiry: n.expiry }, { preview: true })}
                      onDoubleClick={() => wb?.openNode({ ticker: n.ticker, expiry: n.expiry })}
                    >
                      <td className="px-2 py-1 text-left">
                        <span className="font-semibold">{n.ticker}</span>{" "}
                        <span className={isActive ? "text-accent-300/80" : "text-slate-500"}>{n.expiry}</span>
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
                        {n.hasFit ? fmtBp(n.rmsBp) : "—"}
                      </td>
                      <td className={td}>{n.hasFit ? fmtBp(n.maxIvBp) : "—"}</td>
                      <td className={td}>{n.hasFit ? `${(n.atmVol * 100).toFixed(1)}%` : "—"}</td>
                      <td className={`${td} ${!n.leeOk ? "text-rose-400" : ""}`}>
                        {n.hasFit ? `${n.leeLeft.toFixed(2)}/${n.leeRight.toFixed(2)}` : "—"}
                      </td>
                      <td className={`${td} ${!n.calendarOk ? "text-rose-400" : ""}`}>
                        {n.hasFit ? (n.calendarViolation > 0 ? n.calendarViolation.toExponential(1) : "0") : "—"}
                      </td>
                      <td className={`${td} ${n.extrapOk === false || n.extrapCalOk === false ? "text-amber-300" : ""}`}>
                        {extrapText(n)}
                      </td>
                      <td
                        className={`${td} ${n.butterflyCertified === false ? "text-rose-400" : ""}`}
                        title={bellyTitle(n)}
                      >
                        {bellyText(n)}
                      </td>
                      <td className="px-2 py-1 text-left">
                        <StatusCell node={n} />
                      </td>
                    </tr>
                  );
                })}
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={11} className="px-2 py-6 text-center text-slate-500">
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
