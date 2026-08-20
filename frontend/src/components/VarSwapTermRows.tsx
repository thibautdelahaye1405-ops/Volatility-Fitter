// Per-expiry variance-swap editor of the Term view (V3.6 item 14).
//
// One compact row per fitted expiry — level input, model var-swap, basis chip,
// exclude toggle, undo/redo — each row dispatching to ITS OWN node's var-swap
// endpoints (N independent one-scalar sessions; the shared /smiles/.../varswap
// routes). Undo/redo buttons reflect each rung's REAL history state from the
// term payload (TermPoint.varSwapCanUndo/CanRedo) — no more hardcoded-true
// buttons. A batch "shift all" issues sequential per-node "set" edits (one
// refit per quoted expiry, acknowledged in the hint).
//
// Level entry commits on blur / Enter (one refit per gesture); drafts are
// view-local and resync from the payload after every reload.
import { useEffect, useState } from "react";
import type { TermPoint } from "../state/useTerm";
import type { VarSwapAction } from "../state/useSmile";
import { formatExpiry } from "../lib/expiryFormat";
import type { ExpiryFormat } from "../lib/expiryFormat";
import { formatPct } from "../lib/chartScale";
import { formatBasisBp, varswapBasisBp, varswapShiftEdits } from "../lib/varswap";

interface VarSwapTermRowsProps {
  points: TermPoint[];
  /** Live backend? Edits are disabled in mock mode. */
  live: boolean;
  format: ExpiryFormat;
  /** Row highlighted as the chart's selected rung; clicking a row selects it. */
  selectedExpiry: string;
  onSelect: (expiry: string) => void;
  /** Per-node var-swap dispatchers (useTerm): each row edits its own node. */
  applyVarSwap: (expiry: string, action: VarSwapAction, level?: number) => Promise<void>;
  undoVarSwap: (expiry: string) => Promise<void>;
  redoVarSwap: (expiry: string) => Promise<void>;
  /** Batch shift of every QUOTED rung by x vol bp (sequential per-node sets). */
  shiftAll: (bp: number) => Promise<number>;
}

const rowBtn =
  "rounded border border-slate-700 bg-surface-800 px-1 py-0.5 text-[10px] " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

/** Percent string at the shared 2-dp display precision. */
const pctStr = (decimal: number) => (decimal * 100).toFixed(2);

export default function VarSwapTermRows({
  points,
  live,
  format,
  selectedExpiry,
  onSelect,
  applyVarSwap,
  undoVarSwap,
  redoVarSwap,
  shiftAll,
}: VarSwapTermRowsProps) {
  // Per-row level drafts (percent strings), keyed by expiry; a committed or
  // reloaded payload clears the row's draft so the wire value shows again.
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  useEffect(() => {
    setDrafts({});
  }, [points]);

  // Batch shift input (vol bp) + in-flight flag (N sequential refits).
  const [shiftBp, setShiftBp] = useState("10");
  const [shiftBusy, setShiftBusy] = useState(false);
  const quoted = points.filter((p) => p.varSwapQuote != null).length;
  const shiftCount = varswapShiftEdits(points, Number(shiftBp) || 0).length;

  const commitLevel = (expiry: string, pct: number) => {
    if (Number.isFinite(pct) && pct > 0) {
      void applyVarSwap(expiry, "set", pct / 100);
    } else {
      // Invalid entry: drop the draft so the wire value shows again.
      setDrafts((d) => {
        const rest = { ...d };
        delete rest[expiry];
        return rest;
      });
    }
  };

  const runShift = () => {
    const bp = Number(shiftBp);
    if (!Number.isFinite(bp) || bp === 0 || shiftCount === 0) return;
    setShiftBusy(true);
    void shiftAll(bp).finally(() => setShiftBusy(false));
  };

  return (
    <div>
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Variance swaps</h3>
      <p className="mb-2 text-[11px] text-slate-500">
        One quote per expiry — each row edits its own node session (undo/redo
        per rung). Weight is set in Options ▸ Calibration.
      </p>

      {/* Column header */}
      <div className="flex items-center gap-1.5 text-[9px] uppercase tracking-wider text-slate-600">
        <span className="w-14 text-left">expiry</span>
        <span className="w-14 text-right">quote %</span>
        <span className="w-11 text-right">model</span>
        <span className="w-12 text-right">basis</span>
        <span className="flex-1" />
      </div>

      <div className="max-h-48 overflow-y-auto">
        <div className="divide-y divide-slate-800/60">
          {points.map((p) => {
            const quote = p.varSwapQuote ?? null;
            const basis = varswapBasisBp(quote, p.varSwapVol);
            const excluded = p.varSwapExcluded ?? false;
            const selectedRow = p.expiry === selectedExpiry;
            return (
              <div key={p.expiry} className="flex items-center gap-1.5 py-1">
                <button
                  onClick={() => onSelect(p.expiry)}
                  title="Select this rung on the chart"
                  className={[
                    "w-14 shrink-0 text-left font-mono text-[10px] transition-colors",
                    selectedRow ? "text-accent-400" : "text-slate-400 hover:text-slate-200",
                  ].join(" ")}
                >
                  {formatExpiry(p.expiry, p.t, format)}
                </button>
                {quote == null ? (
                  <button
                    className={`${rowBtn} w-14 shrink-0 text-right`}
                    disabled={!live}
                    title={
                      live
                        ? `Add a var-swap quote at the model level (${formatPct(p.varSwapVol, 2)})`
                        : "requires live backend"
                    }
                    onClick={() => void applyVarSwap(p.expiry, "set", p.varSwapVol)}
                  >
                    + add
                  </button>
                ) : (
                  <input
                    type="number"
                    step={0.05}
                    min={0}
                    value={drafts[p.expiry] ?? pctStr(quote)}
                    disabled={!live}
                    title="Var-swap vol (%) — commits on blur / Enter (one refit)"
                    onChange={(e) =>
                      setDrafts((d) => ({ ...d, [p.expiry]: e.target.value }))
                    }
                    onBlur={(e) => commitLevel(p.expiry, Number(e.target.value))}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitLevel(p.expiry, Number(drafts[p.expiry] ?? pctStr(quote)));
                    }}
                    className={[
                      "w-14 shrink-0 rounded border border-slate-700 bg-surface-800 px-1 py-0.5",
                      "text-right font-mono text-[10px] outline-none",
                      "hover:border-slate-600 focus:border-accent-500",
                      excluded ? "text-slate-500" : "text-slate-100",
                    ].join(" ")}
                  />
                )}
                <span className="w-11 shrink-0 text-right font-mono text-[10px] text-slate-400">
                  {formatPct(p.varSwapVol, 2)}
                </span>
                <span
                  title="Basis = quote − model, vol bp"
                  className={[
                    "w-12 shrink-0 text-right font-mono text-[10px]",
                    basis == null || excluded
                      ? "text-slate-600"
                      : basis >= 0
                        ? "text-teal-300"
                        : "text-rose-300",
                  ].join(" ")}
                >
                  {excluded ? "excl" : formatBasisBp(basis)}
                </span>
                <div className="ml-auto flex shrink-0 gap-1">
                  <button
                    className={rowBtn}
                    disabled={!live || quote == null}
                    title={excluded ? "Include in the fit" : "Exclude from the fit"}
                    onClick={() =>
                      void applyVarSwap(p.expiry, excluded ? "include" : "exclude")
                    }
                  >
                    {excluded ? "inc" : "exc"}
                  </button>
                  <button
                    className={rowBtn}
                    disabled={!live || p.varSwapCanUndo !== true}
                    title="Undo this rung's last var-swap edit"
                    onClick={() => void undoVarSwap(p.expiry)}
                  >
                    ↺
                  </button>
                  <button
                    className={rowBtn}
                    disabled={!live || p.varSwapCanRedo !== true}
                    title="Redo this rung's last undone var-swap edit"
                    onClick={() => void redoVarSwap(p.expiry)}
                  >
                    ↻
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Batch shift: sequential per-node "set" edits (one refit per rung). */}
      <div className="mt-2 flex items-center gap-2 border-t border-slate-800 pt-2">
        <span className="text-[11px] text-slate-500">Shift all by</span>
        <input
          type="number"
          step={1}
          value={shiftBp}
          disabled={!live}
          title="Vol basis points added to every quoted rung"
          onChange={(e) => setShiftBp(e.target.value)}
          className="w-14 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500"
        />
        <span className="text-[11px] text-slate-500">bp</span>
        <button
          className={`${rowBtn} ml-auto px-2 py-1 text-[11px]`}
          disabled={!live || shiftBusy || shiftCount === 0}
          onClick={runShift}
          title="Sequential per-node edits — each quoted rung refits once"
        >
          {shiftBusy ? "…" : "Apply"}
        </button>
      </div>
      <p className="mt-1 text-[10px] text-slate-600">
        {quoted === 0
          ? "No quoted rungs — add a quote first; the shift never invents one."
          : `Shifts ${shiftCount || quoted} quoted rung${(shiftCount || quoted) > 1 ? "s" : ""} — ${shiftCount || quoted} refits, one per node.`}
      </p>
    </div>
  );
}
