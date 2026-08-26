// Nodes pane (UI SHELL v2, S2): the universe as a tree, right of the
// activity bar, 1/5 of the screen by default (resizable, Ctrl+B).
//
//   TICKER group   chevron · ticker · "lit/total" · hover: lit-all / dark-all
//   expiry row     lit/dark dot (click = toggle designation, shared with the
//                  Graph canvas + Universe dialog) · expiry · tenor · quality
//                  glyph (ready / stale / arb / no fit) · RMS bp
//
// Single click = preview tab, double click = pinned tab (VS Code). The active
// tab's row is highlighted. A filter box + "lit only" toggle narrow the tree;
// ⚙ opens the Universe dialog (add / remove tickers, expiry selection).
import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Filter, Settings2 } from "lucide-react";
import { useSmileSession } from "../../state/smileSession";
import { useWorkbench } from "../../state/workbench";
import { useLitMap } from "../../state/litMap";
import { useQualityReport } from "../../state/qualityContext";
import { useExpiryFormat } from "../../state/expiryFormat";
import { formatExpiry } from "../../lib/expiryFormat";
import { tabKey } from "../../lib/workbenchTabs";
import type { QualityNode } from "../../state/useQuality";

/** Quality glyph colour + tooltip for a node row. */
function glyphOf(q: QualityNode | undefined): { dot: string; title: string } {
  if (q === undefined) return { dot: "bg-slate-700", title: "no quality data" };
  if (!q.hasFit) return { dot: "bg-slate-600", title: "no fit yet" };
  if (!q.leeOk || !q.calendarOk || q.butterflyCertified === false)
    return { dot: "bg-rose-500", title: `arbitrage flag · ${q.issues.join(", ")}` };
  if (q.stale) return { dot: "bg-amber-400", title: "stale — inputs changed since the last calibration" };
  if (q.ready) return { dot: "bg-emerald-500", title: "publish-ready" };
  return { dot: "bg-amber-300", title: q.issues.join(", ") || "not ready" };
}

const iconBtn =
  "rounded p-1 text-slate-500 transition-colors hover:bg-slate-800 hover:text-slate-200";

export default function NodesPane() {
  const { universe, source } = useSmileSession();
  const wb = useWorkbench();
  const lit = useLitMap();
  const { nodeOf } = useQualityReport();
  const { format } = useExpiryFormat();
  const [query, setQuery] = useState("");
  const [litOnly, setLitOnly] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const tickers = universe?.tickers ?? [];
  const q = query.trim().toUpperCase();
  const activeKey = wb.activeTab?.key ?? null;
  const openKeys = useMemo(() => new Set(wb.tabs.map((t) => t.key)), [wb.tabs]);
  const live = source === "live";

  const toggleGroup = (t: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });

  const nodeCount = tickers.reduce((n, t) => n + (universe?.expiries[t] ?? []).length, 0);
  const litCount = lit.nodes.filter((n) => n.lit).length;

  return (
    <aside
      aria-label="Nodes"
      className="flex min-w-0 shrink-0 flex-col border-r border-slate-800 bg-surface-950"
      style={{ width: wb.layout.nodesWidth }}
    >
      {/* Header */}
      <div className="flex h-9 shrink-0 items-center gap-1 px-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Nodes</span>
        <span className="truncate text-[10px] text-slate-600" title="tickers · nodes · lit">
          {tickers.length} · {nodeCount}
          {live ? ` · ${litCount} lit` : ""}
        </span>
        <span className="ml-auto flex items-center">
          <button
            className={`${iconBtn} ${litOnly ? "text-accent-400" : ""}`}
            title="Show lit (observed) nodes only"
            aria-pressed={litOnly}
            onClick={() => setLitOnly((v) => !v)}
          >
            <Filter size={13} strokeWidth={1.75} />
          </button>
          <button
            className={iconBtn}
            title="Manage universe — add / remove tickers, choose expiries, saved universes"
            onClick={() => wb.openDialog("universe")}
          >
            <Settings2 size={13} strokeWidth={1.75} />
          </button>
        </span>
      </div>
      <div className="shrink-0 px-2 pb-1.5">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter nodes…"
          aria-label="Filter nodes"
          className="w-full rounded-md border border-slate-800 bg-surface-900 px-2 py-1 text-[11px] text-slate-200 outline-none placeholder:text-slate-600 focus:border-accent-500"
        />
      </div>

      {/* Tree */}
      <div role="tree" className="min-h-0 flex-1 overflow-y-auto pb-2">
        {universe === null && (
          <p className="px-3 py-2 text-[11px] text-slate-500">Loading universe…</p>
        )}
        {tickers.map((ticker) => {
          const ladder = universe?.expiries[ticker] ?? [];
          const rows = ladder.filter((r) => {
            const isLit = lit.litOf(ticker, r.expiry);
            if (litOnly && isLit !== true) return false;
            if (q === "") return true;
            return (
              ticker.includes(q) ||
              r.expiry.includes(q) ||
              formatExpiry(r.expiry, r.t, format).toUpperCase().includes(q)
            );
          });
          if (rows.length === 0 && q !== "") return null;
          const litN = ladder.filter((r) => lit.litOf(ticker, r.expiry) === true).length;
          const open = !collapsed.has(ticker);
          const activeHere = wb.activeTab?.ticker === ticker;
          return (
            <div key={ticker} role="treeitem" aria-expanded={open}>
              <div
                className={[
                  "group flex h-7 items-center gap-1 pr-2 pl-1 text-xs",
                  activeHere ? "text-slate-100" : "text-slate-300",
                ].join(" ")}
              >
                <button
                  className="flex min-w-0 flex-1 items-center gap-1 text-left"
                  onClick={() => toggleGroup(ticker)}
                  title={open ? "Collapse" : "Expand"}
                >
                  {open ? (
                    <ChevronDown size={13} className="shrink-0 text-slate-600" />
                  ) : (
                    <ChevronRight size={13} className="shrink-0 text-slate-600" />
                  )}
                  <span className="truncate font-mono font-semibold">{ticker}</span>
                  {live && (
                    <span className="ml-1 font-mono text-[10px] text-slate-600">
                      {litN}/{ladder.length}
                    </span>
                  )}
                </button>
                {live && (
                  <span className="hidden shrink-0 gap-0.5 group-hover:flex">
                    <button
                      className="rounded border border-slate-800 px-1 text-[9px] text-accent-300 hover:border-accent-500/50"
                      title="Light every expiry (observed)"
                      onClick={() => lit.setTicker(ticker, true)}
                    >
                      lit
                    </button>
                    <button
                      className="rounded border border-slate-800 px-1 text-[9px] text-slate-500 hover:border-slate-600"
                      title="Darken every expiry (extrapolated)"
                      onClick={() => lit.setTicker(ticker, false)}
                    >
                      dark
                    </button>
                  </span>
                )}
              </div>

              {open &&
                rows.map((r) => {
                  const key = tabKey(ticker, r.expiry);
                  const isActive = key === activeKey;
                  const isOpen = openKeys.has(key);
                  const isLit = lit.litOf(ticker, r.expiry);
                  const qn = nodeOf(ticker, r.expiry);
                  const g = glyphOf(qn);
                  return (
                    <div
                      key={key}
                      role="treeitem"
                      aria-selected={isActive}
                      onClick={() => wb.openNode({ ticker, expiry: r.expiry }, { preview: true })}
                      onDoubleClick={() => wb.openNode({ ticker, expiry: r.expiry })}
                      className={[
                        "flex h-6 cursor-pointer items-center gap-1.5 pr-2 pl-5 text-[11px] transition-colors",
                        isActive
                          ? "bg-accent-500/10 text-slate-100"
                          : isOpen
                            ? "text-slate-200 hover:bg-slate-800/50"
                            : "text-slate-400 hover:bg-slate-800/50 hover:text-slate-200",
                      ].join(" ")}
                    >
                      {isActive && <span className="-ml-5 mr-3 h-4 w-0.5 rounded-r bg-accent-400" />}
                      {/* Lit/dark designation dot */}
                      <button
                        aria-label={isLit ? "lit (observed) — click to darken" : "dark (extrapolated) — click to light"}
                        title={
                          isLit === undefined
                            ? "designation unavailable"
                            : isLit
                              ? "lit — observed source for the graph solver (click to darken)"
                              : "dark — extrapolated by the graph solver (click to light)"
                        }
                        disabled={isLit === undefined}
                        onClick={(e) => {
                          e.stopPropagation();
                          lit.toggleNode(ticker, r.expiry);
                        }}
                        className={[
                          "h-2.5 w-2.5 shrink-0 rounded-full border transition-colors",
                          isLit === undefined
                            ? "border-slate-700"
                            : isLit
                              ? "border-accent-400 bg-accent-400 shadow-[0_0_6px_rgba(56,189,248,0.6)]"
                              : "border-slate-600 hover:border-slate-400",
                        ].join(" ")}
                      />
                      <span className={["truncate font-mono", isOpen && !isActive ? "" : ""].join(" ")}>
                        {formatExpiry(r.expiry, r.t, format)}
                      </span>
                      <span className="ml-auto shrink-0 font-mono text-[10px] text-slate-600">
                        {r.t < 0.1 ? `${Math.round(r.t * 365)}d` : `${r.t.toFixed(2)}y`}
                      </span>
                      {qn?.hasFit && (
                        <span className="w-8 shrink-0 text-right font-mono text-[10px] text-slate-500" title="RMS fit error (bp)">
                          {qn.rmsBp.toFixed(0)}
                        </span>
                      )}
                      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${g.dot}`} title={g.title} />
                    </div>
                  );
                })}
            </div>
          );
        })}
        {universe !== null && tickers.length === 0 && (
          <p className="px-3 py-2 text-[11px] text-slate-500">
            Universe is empty — add tickers via ⚙.
          </p>
        )}
      </div>
    </aside>
  );
}
