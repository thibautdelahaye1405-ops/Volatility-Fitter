// Lit/dark node matrix of the Universe dialog (ROADMAP Phase 10 follow-up;
// UI SHELL v2 rewires it onto the shared lit map).
//
// Every selected (ticker × expiry) node carries a lit/dark designation
// (GET/PUT /universe/lit, state/litMap.tsx): lit = an observed source for the
// graph solver, dark = an extrapolation target. Rows are tickers, cells are
// their selected expiries; click a cell to toggle it, or use the per-ticker
// bulk buttons — the nodes pane and the Graph canvas reflect the change
// immediately because all three read the same context. The optional row
// slots let the Universe dialog fold ticker management into the SAME rows
// (▸ name expands the expiry picker, `actions` renders e.g. a Remove chip,
// `sourceColumn` shows the data source each ticker fetches from).
import { useMemo } from "react";
import type { ReactNode } from "react";
import { useLitMap } from "../state/litMap";
import { useExpiryFormat } from "../state/expiryFormat";
import { formatExpiry } from "../lib/expiryFormat";
import type { UniverseResponse } from "../state/useSmile";

const bulkBtn =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-[10px] font-medium " +
  "text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200";
/** Tiny per-row source <select> (selectClass grammar at chip scale). */
const sourceSelect =
  "shrink-0 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 font-mono text-[10px] " +
  "text-slate-400 outline-none hover:border-slate-600 focus:border-accent-500 " +
  "disabled:cursor-not-allowed disabled:opacity-60";

/** Per-ticker data-source column (state/tickerSources.ts, the multi-source
 *  engine): the select's value is the ticker's PIN (an `options[].id`, "" =
 *  follow the universe source) and `onChange` pins / unpins it on the server. */
export interface SourceColumn {
  /** Source id (an `options[].id`) shown for this ticker's row. */
  label: (ticker: string) => string;
  options: { id: string; label: string }[];
  disabled?: boolean;
  /** Tooltip of the select. */
  title?: string;
  onChange?: (ticker: string, sourceId: string) => void;
}

interface Props {
  universe: UniverseResponse | null;
  /** Trailing per-ticker actions (e.g. the Remove chip). */
  actions?: (ticker: string) => ReactNode;
  /** Per-ticker data-source select after the ticker name. */
  sourceColumn?: SourceColumn;
  /** Which ticker's expanded editor is open (controlled by the caller). */
  expanded?: string | null;
  /** Clicking the ▸ ticker name toggles its expanded editor. */
  onToggleExpand?: (ticker: string) => void;
  /** Expanded row content (e.g. the expiry-selection picker). */
  renderExpanded?: (ticker: string) => ReactNode;
}

export default function LitDarkMatrix({
  universe,
  actions,
  sourceColumn,
  expanded = null,
  onToggleExpand,
  renderExpanded,
}: Props) {
  const { format } = useExpiryFormat();
  const { nodes, error, toggleNode, setTicker } = useLitMap();

  // Year-fraction lookup for cell labels (from the universe ladders).
  const tOf = useMemo(() => {
    const map = new Map<string, number>();
    if (universe) {
      for (const t of universe.tickers) {
        for (const e of universe.expiries[t] ?? []) map.set(`${t}|${e.expiry}`, e.t);
      }
    }
    return map;
  }, [universe]);

  // Group by ticker, in universe order (tickers without a lit entry still
  // get a row so Remove / the picker stay reachable).
  const byTicker = useMemo(() => {
    const groups = new Map<string, typeof nodes>();
    for (const t of universe?.tickers ?? []) groups.set(t, []);
    for (const n of nodes) {
      const arr = groups.get(n.ticker) ?? [];
      arr.push(n);
      groups.set(n.ticker, arr);
    }
    return groups;
  }, [nodes, universe]);

  if (error !== null) {
    return <p className="text-[11px] text-amber-400/80">Lit/dark unavailable ({error}).</p>;
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-1 flex shrink-0 items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-100">Universe nodes</h2>
        <span className="text-[11px] text-slate-500">
          click a chip to toggle · <span className="text-accent-300">lit</span> = observed source ·
          dark = extrapolated by the graph solver
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {[...byTicker.entries()].map(([ticker, rows]) => {
          const open = expanded === ticker;
          return (
            <div key={ticker} className="border-t border-slate-800/60 py-1.5">
              <div className="flex items-center gap-2">
                {onToggleExpand ? (
                  <button
                    className="w-16 shrink-0 text-left font-mono text-xs font-medium text-slate-100 hover:text-accent-400"
                    title="Edit this ticker's selected expiries"
                    onClick={() => onToggleExpand(ticker)}
                  >
                    {open ? "▾ " : "▸ "}
                    {ticker}
                  </button>
                ) : (
                  <span className="w-16 shrink-0 font-mono text-xs font-medium text-slate-100">{ticker}</span>
                )}
                {sourceColumn && (
                  <select
                    className={sourceSelect}
                    value={sourceColumn.label(ticker)}
                    disabled={sourceColumn.disabled}
                    title={sourceColumn.title}
                    aria-label={`${ticker} data source`}
                    onChange={(e) => sourceColumn.onChange?.(ticker, e.target.value)}
                  >
                    {sourceColumn.options.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                )}
                <div className="flex shrink-0 gap-1">
                  <button className={bulkBtn} onClick={() => setTicker(ticker, true)} title="Light all">lit</button>
                  <button className={bulkBtn} onClick={() => setTicker(ticker, false)} title="Darken all">dark</button>
                </div>
                <div className="flex min-w-0 flex-1 flex-wrap gap-1">
                  {rows.map((n) => {
                    const t = tOf.get(`${n.ticker}|${n.expiry}`);
                    const label = t !== undefined ? formatExpiry(n.expiry, t, format) : n.expiry.slice(5);
                    return (
                      <button
                        key={n.expiry}
                        onClick={() => toggleNode(n.ticker, n.expiry)}
                        title={`${n.expiry} · ${n.lit ? "lit (observed)" : "dark (extrapolated)"}`}
                        className={[
                          "rounded border px-1.5 py-0.5 font-mono text-[10px] transition-colors",
                          n.lit
                            ? "border-accent-500/50 bg-accent-500/10 text-accent-300"
                            : "border-slate-700 bg-surface-800 text-slate-600 hover:text-slate-400",
                        ].join(" ")}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                {actions && <div className="ml-auto shrink-0">{actions(ticker)}</div>}
              </div>
              {open && renderExpanded && renderExpanded(ticker)}
            </div>
          );
        })}
        {byTicker.size === 0 && <p className="py-2 text-[11px] text-slate-500">No nodes yet.</p>}
      </div>
    </div>
  );
}
