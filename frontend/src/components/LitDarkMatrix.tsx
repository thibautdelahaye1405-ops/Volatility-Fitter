// Lit/dark node matrix for the Universe workspace (ROADMAP Phase 10 follow-up).
//
// Every selected (ticker × expiry) node carries a lit/dark designation (shared
// with the Graph tab via GET/PUT /universe/lit): lit = an observed source for
// the graph solver, dark = an extrapolation target (stale / filled in by the
// solver). Rows are tickers, cells are their selected expiries; click a cell to
// toggle it, or use the per-ticker bulk buttons. Live backend only.
import { useEffect, useMemo, useState } from "react";
import { api } from "../state/api";
import type { UniverseResponse } from "../state/useSmile";

interface LitNode {
  ticker: string;
  expiry: string;
  lit: boolean;
}
interface LitMapResponse {
  nodes: LitNode[];
}

const bulkBtn =
  "rounded border border-slate-700 bg-surface-800 px-1.5 py-0.5 text-[10px] font-medium " +
  "text-slate-400 transition-colors hover:border-slate-600 hover:text-slate-200";

interface Props {
  universe: UniverseResponse | null;
}

export default function LitDarkMatrix({ universe }: Props) {
  const [nodes, setNodes] = useState<LitNode[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Refetch when the universe's ticker set or any ladder length changes.
  const sig = useMemo(
    () =>
      universe
        ? universe.tickers
            .map((t) => `${t}:${(universe.expiries[t] ?? []).length}`)
            .join(",")
        : "",
    [universe],
  );

  useEffect(() => {
    const controller = new AbortController();
    api
      .get<LitMapResponse>("/universe/lit", { signal: controller.signal })
      .then((d) => {
        setNodes(d.nodes);
        setError(null);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : String(err));
      });
    return () => controller.abort();
  }, [sig]);

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

  const byTicker = useMemo(() => {
    const groups = new Map<string, LitNode[]>();
    for (const n of nodes) {
      const arr = groups.get(n.ticker) ?? [];
      arr.push(n);
      groups.set(n.ticker, arr);
    }
    return groups;
  }, [nodes]);

  const toggleNode = (n: LitNode) => {
    const lit = !n.lit;
    setNodes((prev) =>
      prev.map((m) => (m.ticker === n.ticker && m.expiry === n.expiry ? { ...m, lit } : m)),
    );
    void api
      .put(`/universe/lit/${n.ticker}/${encodeURIComponent(n.expiry)}`, { body: { lit } })
      .catch(() => {
        /* revert on failure */
        setNodes((prev) =>
          prev.map((m) =>
            m.ticker === n.ticker && m.expiry === n.expiry ? { ...m, lit: n.lit } : m,
          ),
        );
      });
  };

  const toggleTicker = (ticker: string, lit: boolean) => {
    setNodes((prev) => prev.map((m) => (m.ticker === ticker ? { ...m, lit } : m)));
    void api
      .put<LitMapResponse>(`/universe/lit/${ticker}`, { body: { lit } })
      .then((d) => setNodes(d.nodes))
      .catch(() => {
        /* leave the optimistic state; a reload will reconcile */
      });
  };

  if (error !== null) {
    return <p className="text-[11px] text-amber-400/80">Lit/dark unavailable ({error}).</p>;
  }

  return (
    <div className="flex min-h-0 flex-col">
      <div className="mb-1 flex shrink-0 items-center gap-2">
        <h2 className="text-sm font-semibold text-slate-100">Lit / dark nodes</h2>
        <span className="text-[11px] text-slate-500">
          lit = observed source · dark = extrapolated by the graph solver
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {[...byTicker.entries()].map(([ticker, rows]) => (
          <div key={ticker} className="flex items-center gap-2 border-t border-slate-800/60 py-1.5">
            <span className="w-16 shrink-0 font-mono text-xs font-medium text-slate-100">
              {ticker}
            </span>
            <div className="flex shrink-0 gap-1">
              <button className={bulkBtn} onClick={() => toggleTicker(ticker, true)} title="Light all">
                lit
              </button>
              <button className={bulkBtn} onClick={() => toggleTicker(ticker, false)} title="Darken all">
                dark
              </button>
            </div>
            <div className="flex flex-wrap gap-1">
              {rows.map((n) => {
                const t = tOf.get(`${n.ticker}|${n.expiry}`);
                const label = t !== undefined ? `${t.toFixed(2)}y` : n.expiry.slice(5);
                return (
                  <button
                    key={n.expiry}
                    onClick={() => toggleNode(n)}
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
          </div>
        ))}
        {nodes.length === 0 && (
          <p className="py-2 text-[11px] text-slate-500">No nodes yet.</p>
        )}
      </div>
    </div>
  );
}
