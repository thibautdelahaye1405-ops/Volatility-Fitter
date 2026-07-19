// Expiry×expiry drill-in for one ticker-pair cell of the edge matrix: rows =
// source ticker's expiries, columns = destination's. Each sub-cell edits a
// DIRECTED per-edge override (rule.overrides — layered last over the expanded
// block rule, exactly what the backend already supports). Cells the pair rule
// itself would expand to (same expiry off-diagonal, consecutive expiries on
// the calendar diagonal) show the inherited weight faintly; an override
// replaces that edge outright.
import { useMemo, useState } from "react";
import { CellPopover, btn, heatStyle } from "./EdgeMatrixEditor.helpers";
import type { MatrixCell } from "../lib/edgeMatrix";
import type { GraphEdge } from "../state/useGraphEdges";

interface EdgeExpiryMatrixProps {
  src: string;
  dst: string;
  srcExpiries: string[];
  dstExpiries: string[];
  /** The ticker-pair rule being drilled into (undefined = no rule: cells
   *  inherit nothing, overrides still editable over the auto-lattice). */
  baseCell?: MatrixCell;
  /** The FULL overrides list; this view edits only this pair's entries. */
  overrides: GraphEdge[];
  busy: boolean;
  onChange: (next: GraphEdge[]) => void;
  onBack: () => void;
}

const th =
  "border-b border-slate-800 bg-surface-800 px-2 py-1.5 text-center font-semibold text-slate-300";

/** MM-DD display for column headers (full ISO stays in the row labels/titles). */
const shortIso = (iso: string): string => iso.slice(5);

export default function EdgeExpiryMatrix({
  src,
  dst,
  srcExpiries,
  dstExpiries,
  baseCell,
  overrides,
  busy,
  onChange,
  onBack,
}: EdgeExpiryMatrixProps) {
  const [editing, setEditing] = useState<string | null>(null); // "srcExp|dstExp"

  const directed = useMemo(() => {
    const map = new Map<string, GraphEdge>();
    for (const o of overrides) {
      if (o.fromTicker === src && o.toTicker === dst)
        map.set(`${o.fromExpiry}|${o.toExpiry}`, o);
    }
    return map;
  }, [overrides, src, dst]);
  const mirrored = useMemo(() => {
    const map = new Map<string, GraphEdge>();
    for (const o of overrides) {
      if (o.fromTicker === dst && o.toTicker === src)
        map.set(`${o.toExpiry}|${o.fromExpiry}`, o); // keyed as the direct cell
    }
    return map;
  }, [overrides, src, dst]);

  const maxWeight = useMemo(() => {
    let m = baseCell?.weight ?? 0;
    for (const o of directed.values()) m = Math.max(m, o.weight);
    return m;
  }, [directed, baseCell]);

  /** Does the PAIR rule itself expand to this sub-cell? (Same pairing as the
   *  backend: same expiry off-diagonal, consecutive expiries on the diagonal.) */
  const inherited = (i: number, j: number): boolean => {
    if (baseCell === undefined || baseCell.weight <= 0) return false;
    if (src === dst) return Math.abs(i - j) === 1;
    return srcExpiries[i] === dstExpiries[j];
  };

  const notThisEdge = (o: GraphEdge, se: string, de: string, s: string, d: string) =>
    !(o.fromTicker === s && o.fromExpiry === se && o.toTicker === d && o.toExpiry === de);

  /** Write-through edit of one sub-cell; symmetric ⇄ keeps the mirrored
   *  directed override in lockstep. β applies to all three handles, matching
   *  the block-rule expansion. */
  const apply = (se: string, de: string, cell: MatrixCell) => {
    const edge = (a: string, ae: string, b: string, be: string): GraphEdge => ({
      fromTicker: a, fromExpiry: ae, toTicker: b, toExpiry: be,
      weight: cell.weight, betaAtmVol: cell.beta, betaSkew: cell.beta, betaCurv: cell.beta,
    });
    let next = overrides.filter((o) => notThisEdge(o, se, de, src, dst));
    next.push(edge(src, se, dst, de));
    if (cell.symmetric && !(src === dst && se === de)) {
      next = next.filter((o) => notThisEdge(o, de, se, dst, src));
      next.push(edge(dst, de, src, se));
    }
    onChange(next);
  };

  const clear = (se: string, de: string, wasSymmetric: boolean) => {
    let next = overrides.filter((o) => notThisEdge(o, se, de, src, dst));
    if (wasSymmetric) next = next.filter((o) => notThisEdge(o, de, se, dst, src));
    onChange(next);
    setEditing(null);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex shrink-0 items-center gap-2">
        <button className={btn} onClick={onBack}>
          ← Matrix
        </button>
        <span
          className="text-xs font-semibold text-slate-200"
          title="Engine convention: the column node INFORMS the row node — arrows read receiver ← informer"
        >
          {src} ← {dst} <span className="font-normal text-slate-500">per-expiry overrides</span>
        </span>
        {baseCell !== undefined && baseCell.weight > 0 && (
          <span className="rounded border border-slate-700 bg-surface-800 px-1.5 py-px font-mono text-[10px] text-slate-400">
            rule w {baseCell.weight}
            {baseCell.beta !== 1 ? ` · β ${baseCell.beta}` : ""}
          </span>
        )}
      </div>
      <p className="mb-2 shrink-0 text-[11px] text-slate-500">
        Faint cells inherit the ticker rule; click any cell to override that one
        directed edge (⇄ mirrors it). Direction: the COLUMN expiry informs the
        ROW expiry (receiver ← informer). Overrides layer last — they replace
        the expanded edge outright.
      </p>
      <div className="min-h-0 flex-1 overflow-auto rounded-md border border-slate-800">
        <table className="border-separate border-spacing-0 font-mono text-[11px] leading-tight">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-30 border-b border-r border-slate-800 bg-surface-800 px-2 py-1.5 text-left text-[9px] font-medium uppercase tracking-wide text-slate-500">
                {src} \ {dst}
              </th>
              {dstExpiries.map((de) => (
                <th key={de} className={`sticky top-0 z-20 ${th}`} title={de}>
                  {shortIso(de)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {srcExpiries.map((se, i) => (
              <tr key={se}>
                <th className="sticky left-0 z-10 border-b border-r border-slate-800 bg-surface-900 px-2 py-1 text-left font-semibold text-slate-300">
                  {se}
                </th>
                {dstExpiries.map((de, j) => {
                  const key = `${se}|${de}`;
                  const self = src === dst && se === de;
                  const ov = directed.get(key);
                  const mirror = mirrored.get(key);
                  const isSym =
                    ov !== undefined &&
                    mirror !== undefined &&
                    mirror.weight === ov.weight &&
                    mirror.betaAtmVol === ov.betaAtmVol;
                  const inh = ov === undefined && inherited(i, j);
                  const cell: MatrixCell | undefined =
                    ov !== undefined
                      ? { weight: ov.weight, beta: ov.betaAtmVol, symmetric: isSym }
                      : undefined;
                  return (
                    <td
                      key={de}
                      className="relative border-b border-r border-slate-800/60 p-0"
                    >
                      <button
                        className="group flex h-9 w-full min-w-16 flex-col items-center justify-center font-mono text-slate-200 transition-colors enabled:hover:bg-surface-700/40 disabled:cursor-not-allowed"
                        style={heatStyle(cell, src === dst, maxWeight)}
                        disabled={busy || self}
                        onClick={() => setEditing(key)}
                        title={self ? "self edge" : `${src} ${se} ← ${dst} ${de}`}
                      >
                        {self ? (
                          <span className="text-slate-700">—</span>
                        ) : ov !== undefined ? (
                          <>
                            <span>
                              {ov.weight.toFixed(1)}
                              {isSym && <span className="ml-0.5 text-slate-400">⇄</span>}
                            </span>
                            {ov.betaAtmVol !== 1 && (
                              <span className="text-[9px] text-slate-400">β {ov.betaAtmVol}</span>
                            )}
                          </>
                        ) : inh ? (
                          /* Inherited from the ticker rule — not an override. */
                          <span className="text-slate-500/60">{baseCell?.weight.toFixed(1)}</span>
                        ) : (
                          <span className="text-slate-600 opacity-0 transition-opacity group-hover:opacity-100">
                            ·
                          </span>
                        )}
                      </button>
                      {editing === key && !self && (
                        <CellPopover
                          cell={
                            cell ?? {
                              weight: baseCell?.weight ?? 1,
                              beta: baseCell?.beta ?? 1,
                              symmetric: false,
                            }
                          }
                          diagonal={false}
                          onChange={(c) => apply(se, de, c)}
                          onClear={() => clear(se, de, isSym)}
                          onClose={() => setEditing(null)}
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
    </div>
  );
}
