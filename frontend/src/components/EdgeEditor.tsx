// Per-edge graph editor (plan Phase 7): a user-supplied sparse bi-directed
// weighted graph with per-edge weight (trust) + beta (amplitude). Seeds from the
// auto-lattice; an empty saved set falls back to the lattice. Compact for the
// Graph workspace aside; the single β maps to all three handle betas (the data
// model keeps them separate; the v1 UI broadcasts one scalar).
import { useEffect, useState } from "react";
import { useGraphEdges, type GraphEdge } from "../state/useGraphEdges";

interface EdgeEditorProps {
  /** Selected-universe nodes, for the add-edge pickers. */
  nodes: { ticker: string; expiry: string }[];
  /** Called after a successful save/clear so the parent can re-solve. */
  onSaved?: () => void;
  onClose: () => void;
}

const btn =
  "rounded-md border border-slate-700 bg-surface-800 px-2 py-1 text-[11px] " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

const numCls =
  "w-12 rounded border border-slate-700 bg-surface-800 px-1 py-0.5 text-right " +
  "font-mono text-[10px] text-slate-100 outline-none focus:border-accent-500";

const key = (n: { ticker: string; expiry: string }) => `${n.ticker}|${n.expiry}`;
const short = (ticker: string, expiry: string) => `${ticker} ${expiry.slice(5)}`;

export default function EdgeEditor({ nodes, onSaved, onClose }: EdgeEditorProps) {
  const { fetchEdges, fetchLattice, putEdges } = useGraphEdges();
  const [rows, setRows] = useState<GraphEdge[]>([]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchEdges().then(setRows).catch((e) => setError(String(e)));
  }, [fetchEdges]);

  useEffect(() => {
    if (from === "" && nodes[0]) setFrom(key(nodes[0]));
    if (to === "" && nodes[1]) setTo(key(nodes[1]));
  }, [nodes, from, to]);

  const run = (p: Promise<GraphEdge[]>, persisted: boolean) => {
    setBusy(true);
    setError(null);
    p.then((e) => {
      setRows(e);
      if (persisted) onSaved?.();
    })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false));
  };

  const update = (i: number, patch: Partial<GraphEdge>) =>
    setRows((r) => r.map((e, j) => (j === i ? { ...e, ...patch } : e)));

  const addEdge = () => {
    const [ft, fe] = from.split("|");
    const [tt, te] = to.split("|");
    if (!ft || !fe || !tt || !te || (ft === tt && fe === te)) return;
    setRows((r) => [
      ...r,
      { fromTicker: ft, fromExpiry: fe, toTicker: tt, toExpiry: te, weight: 1, betaAtmVol: 1, betaSkew: 1, betaCurv: 1 },
    ]);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex shrink-0 items-center gap-2">
        <span className="text-xs font-semibold text-slate-200">Edge editor</span>
        <button className="ml-auto text-slate-500 hover:text-slate-200" onClick={onClose} title="Close">
          ✕
        </button>
      </div>
      <div className="mb-2 flex shrink-0 flex-wrap gap-1.5">
        <button className={btn} disabled={busy} onClick={() => run(fetchLattice(), false)}>
          Seed from lattice
        </button>
        <button className={btn} disabled={busy} onClick={() => run(putEdges(rows), true)}>
          Save
        </button>
        <button className={btn} disabled={busy} onClick={() => run(putEdges([]), true)}>
          Reset to lattice
        </button>
      </div>
      {error !== null && (
        <p className="mb-1 truncate text-[10px] text-amber-400/80" title={error}>{error}</p>
      )}

      {/* Header. Direction truth (volfit/graph/build.py): the SECOND endpoint
          informs the first — so rows read receiver ← informer, arrow drawn in
          the direction information flows. */}
      <div className="flex shrink-0 items-center gap-1 px-0.5 text-[9px] uppercase tracking-wide text-slate-500">
        <span className="flex-1">edge (receiver ← informer)</span>
        <span className="w-12 text-right">weight</span>
        <span className="w-12 text-right">β</span>
        <span className="w-4" />
      </div>

      {/* Rows */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {rows.length === 0 ? (
          <p className="py-2 text-[11px] text-slate-500">
            No overrides — the solve uses the auto-lattice. Seed from it or add edges.
          </p>
        ) : (
          <div className="divide-y divide-slate-800">
            {rows.map((e, i) => (
              <div key={i} className="flex items-center gap-1 py-1">
                <span
                  className="min-w-0 flex-1 truncate font-mono text-[10px] text-slate-300"
                  title="The right node INFORMS the left (engine convention); the arrow shows information flow"
                >
                  {short(e.fromTicker, e.fromExpiry)} ← {short(e.toTicker, e.toExpiry)}
                </span>
                <input
                  type="number" step={1} value={e.weight} className={numCls}
                  onChange={(ev) => {
                    const v = ev.target.valueAsNumber;
                    if (Number.isFinite(v)) update(i, { weight: v });
                  }}
                />
                <input
                  type="number" step={0.1} value={e.betaAtmVol} className={numCls}
                  onChange={(ev) => {
                    const v = ev.target.valueAsNumber;
                    if (Number.isFinite(v)) update(i, { betaAtmVol: v, betaSkew: v, betaCurv: v });
                  }}
                />
                <button
                  className="w-4 text-slate-500 hover:text-rose-300"
                  title="Remove edge"
                  onClick={() => setRows((r) => r.filter((_, j) => j !== i))}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add edge: the SECOND pick informs the FIRST (receiver ← informer) */}
      <div className="mt-2 flex shrink-0 items-center gap-1 border-t border-slate-800 pt-2">
        <select className={numCls + " w-auto flex-1"} value={from} onChange={(e) => setFrom(e.target.value)} title="Receiver (the influenced node)">
          {nodes.map((n) => (
            <option key={key(n)} value={key(n)}>{short(n.ticker, n.expiry)}</option>
          ))}
        </select>
        <span className="text-[10px] text-slate-500" title="information flow: the right node informs the left">←</span>
        <select className={numCls + " w-auto flex-1"} value={to} onChange={(e) => setTo(e.target.value)}>
          {nodes.map((n) => (
            <option key={key(n)} value={key(n)}>{short(n.ticker, n.expiry)}</option>
          ))}
        </select>
        <button className={btn} onClick={addEdge}>Add</button>
      </div>
    </div>
  );
}
