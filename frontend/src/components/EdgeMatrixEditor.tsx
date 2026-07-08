// Sparse ticker×ticker edge-weight matrix: the block-rule editor that
// replaces the row-list edge editor as the primary Edges surface. One cell
// per ticker pair — an off-diagonal cell is a same-expiry cross-ticker pair
// rule (both directions when symmetric ⇄), the tinted diagonal is each
// ticker's own consecutive-expiry calendar chain. A cell's popover drills
// into its expiry×expiry sub-matrix (EdgeExpiryMatrix) to override single
// directed edges, and the old per-edge row editor survives behind "Per-edge
// overrides…" as the advanced view — both write rule.overrides, layered last
// over the expanded rule. Persists via PUT /graph/edges/blocks; an all-empty
// rule falls back to the auto-lattice. Rendered as a large modal — the Graph
// aside is too narrow for a matrix.
import { useCallback, useEffect, useMemo, useState } from "react";
import EdgeEditor from "./EdgeEditor";
import EdgeExpiryMatrix from "./EdgeExpiryMatrix";
import {
  CellPopover,
  PasteTsvPanel,
  btn,
  downloadCsv,
  heatStyle,
} from "./EdgeMatrixEditor.helpers";
import { cellAt, cellKey, gridToRule, parseTsv, ruleToGrid, toCsv } from "../lib/edgeMatrix";
import type { MatrixCell } from "../lib/edgeMatrix";
import { useGraphBlocks } from "../state/useGraphBlocks";
import type { GraphEdge } from "../state/useGraphEdges";

interface EdgeMatrixEditorProps {
  /** Universe tickers, in display order (matrix rows and columns). */
  tickers: string[];
  /** Selected-universe nodes, for the advanced per-edge overrides editor. */
  nodes: { ticker: string; expiry: string }[];
  /** Called after a successful save so the parent can re-solve. */
  onSaved?: () => void;
  onClose: () => void;
}

const th =
  "border-b border-slate-800 bg-surface-800 px-2 py-1.5 text-center font-semibold text-slate-300";

export default function EdgeMatrixEditor({
  tickers,
  nodes,
  onSaved,
  onClose,
}: EdgeMatrixEditorProps) {
  const { fetchRule, putRule } = useGraphBlocks();
  const [grid, setGrid] = useState<Map<string, MatrixCell>>(new Map());
  const [overrides, setOverrides] = useState<GraphEdge[]>([]);
  const [expandedCount, setExpandedCount] = useState<number | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null); // clicked "src|dst"
  const [pasting, setPasting] = useState(false);
  const [pasteErrors, setPasteErrors] = useState<string[]>([]);
  const [showOverrides, setShowOverrides] = useState(false);
  const [drill, setDrill] = useState<{ src: string; dst: string } | null>(null);

  // Ladder per ticker for the expiry×expiry drill-in (selected universe order).
  const expiriesByTicker = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const n of nodes) {
      const arr = m.get(n.ticker) ?? [];
      if (!arr.includes(n.expiry)) arr.push(n.expiry);
      m.set(n.ticker, arr);
    }
    for (const arr of m.values()) arr.sort();
    return m;
  }, [nodes]);

  /** Per-expiry overrides touching a ticker pair (either direction) — the
   *  drill-in badge on the ticker cell. */
  const overrideCount = useCallback(
    (s: string, d: string) =>
      overrides.filter(
        (o) =>
          (o.fromTicker === s && o.toTicker === d) ||
          (o.fromTicker === d && o.toTicker === s),
      ).length,
    [overrides],
  );

  const load = useCallback(() => {
    setBusy(true);
    setError(null);
    fetchRule()
      .then((r) => {
        setGrid(ruleToGrid(r.rule));
        setOverrides(r.rule.overrides);
        setExpandedCount(r.expandedCount);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false));
  }, [fetchRule]);
  useEffect(() => {
    load();
  }, [load]);

  // Escape unwinds one layer at a time: cell popover, paste panel, the
  // expiry drill-in, the modal. (The popover swallows its own Escape.)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      if (editing !== null) setEditing(null);
      else if (pasting) setPasting(false);
      else if (drill !== null) setDrill(null);
      else onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, pasting, drill, onClose]);

  const maxWeight = useMemo(() => {
    let m = 0;
    for (const c of grid.values()) m = Math.max(m, c.weight);
    return m;
  }, [grid]);

  /** Stored key for a clicked (src, dst): the direct key, or the mirrored one
   *  when a symmetric cell already rules this direction. */
  const canonicalKey = (src: string, dst: string): string => {
    if (grid.has(cellKey(src, dst))) return cellKey(src, dst);
    const mirror = grid.get(cellKey(dst, src));
    return mirror !== undefined && mirror.symmetric ? cellKey(dst, src) : cellKey(src, dst);
  };

  const applyCell = (key: string, cell: MatrixCell) => {
    setGrid((g) => {
      const next = new Map(g);
      next.set(key, cell);
      if (cell.symmetric) {
        // A symmetric cell rules both directions — drop a now-redundant mirror.
        const [a = "", b = ""] = key.split("|");
        if (a !== b) next.delete(cellKey(b, a));
      }
      return next;
    });
  };

  const clearCell = (key: string) => {
    setGrid((g) => {
      const next = new Map(g);
      next.delete(key);
      return next;
    });
    setEditing(null);
  };

  // parseTsv collapses equal mirrored cells to symmetric internally. The
  // paste REPLACES the grid (it is the full matrix); errors keep the panel
  // open so the user sees what was skipped.
  const applyTsv = (text: string) => {
    const { grid: parsed, errors } = parseTsv(text, tickers);
    setPasteErrors(errors);
    setGrid(parsed);
    if (errors.length === 0) setPasting(false);
  };

  // Empty rule (pairs + calendar + overrides) = back to the auto-lattice.
  const resetAll = () => {
    setGrid(new Map());
    setOverrides([]);
    setPasteErrors([]);
  };

  const save = () => {
    setBusy(true);
    setError(null);
    putRule(gridToRule(grid, overrides))
      .then((r) => {
        setExpandedCount(r.expandedCount);
        onSaved?.();
        onClose();
      })
      .catch((e) => {
        setError(String(e));
        setBusy(false);
      });
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-6">
      <div className="flex h-[80vh] w-full max-w-4xl flex-col rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
        {/* Header */}
        <div className="mb-1 flex shrink-0 items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-100">Edge weights</h3>
          {expandedCount !== null && (
            <span className="rounded border border-slate-700 bg-surface-800 px-1.5 py-px font-mono text-[10px] text-slate-400">
              {expandedCount} edges
            </span>
          )}
          <button className="ml-auto text-slate-500 hover:text-slate-200" onClick={onClose} title="Close">
            ✕
          </button>
        </div>
        <p className="mb-2 shrink-0 text-[11px] text-slate-500">
          Off-diagonal cells link two tickers expiry-by-expiry (⇄ = both directions);
          the amber diagonal is each ticker&apos;s own calendar chain. Click a cell to edit.
        </p>

        {/* Toolbar */}
        <div className="mb-2 flex shrink-0 flex-wrap items-center gap-1.5">
          <button
            className={btn}
            disabled={busy || showOverrides || drill !== null}
            onClick={() => {
              setPasting((v) => !v);
              setPasteErrors([]);
            }}
          >
            Paste TSV
          </button>
          <button
            className={btn}
            disabled={busy || showOverrides || drill !== null || grid.size === 0}
            onClick={() => downloadCsv(toCsv(grid, tickers))}
          >
            Export CSV
          </button>
          <button className={btn} disabled={busy || showOverrides || drill !== null} onClick={resetAll}>
            Reset all
          </button>
          <button
            className={btn + " ml-auto"}
            disabled={busy || drill !== null}
            onClick={() => setShowOverrides((v) => !v)}
          >
            {showOverrides ? "Back to matrix" : `Per-edge overrides… (${overrides.length})`}
          </button>
        </div>
        {error !== null && (
          <p className="mb-1 shrink-0 truncate text-[10px] text-amber-400/80" title={error}>
            {error}
          </p>
        )}

        {/* Body: overrides advanced view / paste panel / the grid */}
        {showOverrides ? (
          /* The original row editor, demoted to an advanced view. NB its own
             Save persists the raw edge list via PUT /graph/edges, which clears
             the block rule server-side — we refetch on save so the matrix
             shows the truth when the user switches back. */
          <EdgeEditor
            nodes={nodes}
            onSaved={() => {
              onSaved?.();
              load();
            }}
            onClose={() => setShowOverrides(false)}
          />
        ) : pasting ? (
          <PasteTsvPanel errors={pasteErrors} busy={busy} onApply={applyTsv} onCancel={() => setPasting(false)} />
        ) : drill !== null ? (
          <EdgeExpiryMatrix
            src={drill.src}
            dst={drill.dst}
            srcExpiries={expiriesByTicker.get(drill.src) ?? []}
            dstExpiries={expiriesByTicker.get(drill.dst) ?? []}
            baseCell={cellAt(grid, drill.src, drill.dst)}
            overrides={overrides}
            busy={busy}
            onChange={setOverrides}
            onBack={() => setDrill(null)}
          />
        ) : tickers.length === 0 ? (
          <div className="flex min-h-0 flex-1 items-center justify-center rounded-md border border-slate-800 px-6 text-center text-xs text-slate-500">
            No universe selected — pick tickers and expiries in the Universe tab
            to populate the matrix.
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
            <table className="border-separate border-spacing-0 font-mono text-[11px] leading-tight">
              <thead>
                <tr>
                  <th className="sticky left-0 top-0 z-30 border-b border-r border-slate-800 bg-surface-800 px-2 py-1.5 text-left text-[9px] font-medium uppercase tracking-wide text-slate-500">
                    src \ dst
                  </th>
                  {tickers.map((t) => (
                    <th key={t} className={`sticky top-0 z-20 ${th}`}>
                      {t}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tickers.map((src) => (
                  <tr key={src}>
                    <th className="sticky left-0 z-10 border-b border-r border-slate-800 bg-surface-900 px-2 py-1 text-left font-semibold text-slate-300">
                      {src}
                    </th>
                    {tickers.map((dst) => {
                      const rawKey = cellKey(src, dst);
                      const cell = cellAt(grid, src, dst);
                      const diagonal = src === dst;
                      const nOverrides = overrideCount(src, dst);
                      return (
                        <td
                          key={dst}
                          className={`relative border-b border-r border-slate-800/60 p-0 ${
                            diagonal && cell === undefined ? "bg-amber-500/5" : ""
                          }`}
                        >
                          <button
                            className="group flex h-9 w-full min-w-16 flex-col items-center justify-center font-mono text-slate-200 transition-colors enabled:hover:bg-surface-700/40 disabled:cursor-not-allowed"
                            style={heatStyle(cell, diagonal, maxWeight)}
                            disabled={busy}
                            onClick={() => setEditing(rawKey)}
                            title={diagonal ? `${src} calendar chain` : `${src} → ${dst}`}
                          >
                            {cell !== undefined ? (
                              <>
                                <span>
                                  {cell.weight.toFixed(1)}
                                  {cell.symmetric && !diagonal ? (
                                    <span className="ml-0.5 text-slate-400">⇄</span>
                                  ) : null}
                                </span>
                                {cell.beta !== 1 && (
                                  <span className="text-[9px] text-slate-400">β {cell.beta}</span>
                                )}
                              </>
                            ) : (
                              /* Faint dot invites a click on empty cells. */
                              <span className="text-slate-600 opacity-0 transition-opacity group-hover:opacity-100">
                                ·
                              </span>
                            )}
                            {/* Per-expiry overrides live under this pair. */}
                            {nOverrides > 0 && (
                              <span className="absolute right-0.5 top-0 text-[8px] text-accent-400">
                                {nOverrides}
                              </span>
                            )}
                          </button>
                          {editing === rawKey && (
                            <CellPopover
                              cell={cell ?? { weight: 1, beta: 1, symmetric: diagonal }}
                              diagonal={diagonal}
                              onChange={(c) => applyCell(canonicalKey(src, dst), c)}
                              onClear={() => clearCell(canonicalKey(src, dst))}
                              onClose={() => setEditing(null)}
                              onDrill={() => {
                                setEditing(null);
                                setDrill({ src, dst });
                              }}
                            />
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer */}
        <div className="mt-3 flex shrink-0 items-center gap-2 border-t border-slate-800 pt-3">
          <button
            className="flex items-center gap-2 rounded-md bg-accent-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors enabled:hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-40"
            disabled={busy || showOverrides}
            onClick={save}
            title={showOverrides ? "The per-edge editor has its own Save" : "Persist the block rule"}
          >
            {busy && (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
            )}
            Save
          </button>
          <button className={btn} disabled={busy} onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
