// Production extrapolation aside (plan Phase 7/8 UI): runs the prior-anchored
// solve + the leave-one-node-out backtest and lists each node's prior -> posterior
// ATM move with provenance. Distinct from the manual-shift sandbox observations.
import { useMemo, useState } from "react";
import EdgeEditor from "./EdgeEditor";
import GraphAttributionCard from "./GraphAttributionCard";
import type { UseGraphExtrapolationResult } from "../state/useGraphExtrapolation";

interface ExtrapolatePanelProps {
  extra: UseGraphExtrapolationResult;
  /** The /graph/extrapolate request body (built in the parent so the drill-in
   *  overlay reconstructs with the same knobs). */
  body: Record<string, string | number | boolean>;
  flatAtm: boolean;
  setFlatAtm: (v: boolean) => void;
  crossBeta: number;
  setCrossBeta: (v: number) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
}

/** The node whose attribution card is open, or null. */
interface SelectedNode {
  ticker: string;
  expiry: string;
}

const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

export default function ExtrapolatePanel({
  extra,
  body,
  flatAtm,
  setFlatAtm,
  crossBeta,
  setCrossBeta,
  onOpenSmile,
}: ExtrapolatePanelProps) {
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const rows = useMemo(
    () =>
      (extra.nodes ?? [])
        .slice()
        .sort((a, b) => a.ticker.localeCompare(b.ticker) || a.expiry.localeCompare(b.expiry)),
    [extra.nodes],
  );
  const editorNodes = useMemo(
    () => (extra.nodes ?? []).map((n) => ({ ticker: n.ticker, expiry: n.expiry })),
    [extra.nodes],
  );

  return (
    <aside className="flex w-80 shrink-0 flex-col rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
      <h3 className="mb-1 text-sm font-semibold text-slate-100">Extrapolate</h3>
      <p className="mb-3 text-[11px] text-slate-500">
        Transported priors → lit-calibration innovations → graph posterior, over the
        selected lit+dark universe.
      </p>

      {/* Production-only knobs */}
      <div className="mb-3 space-y-2 text-[11px] text-slate-400">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={flatAtm}
            onChange={(e) => setFlatAtm(e.target.checked)}
            className="accent-accent-500"
          />
          Flat baselines (diagnostic)
        </label>
        <label className="flex items-center justify-between gap-2">
          <span>Cross-ticker β</span>
          <input
            type="number"
            step={0.1}
            value={crossBeta}
            onChange={(e) => {
              const v = e.target.valueAsNumber;
              if (Number.isFinite(v)) setCrossBeta(v);
            }}
            className="w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500"
          />
        </label>
      </div>

      <div className="mb-3 flex shrink-0 gap-2">
        <button
          className={buttonClass}
          disabled={extra.running}
          onClick={() => void extra.run(body)}
        >
          {extra.running ? "Extrapolating…" : "Extrapolate"}
        </button>
        <button
          className={buttonClass}
          disabled={extra.backtesting}
          onClick={() => void extra.runBacktest(body)}
        >
          {extra.backtesting ? "Backtesting…" : "Backtest"}
        </button>
        <button
          className={buttonClass}
          title="Edit the per-edge graph weights + beta"
          onClick={() => setEditing((v) => !v)}
        >
          {editing ? "Done" : "Edges"}
        </button>
      </div>

      {extra.error !== null && (
        <p className="mb-2 truncate text-[10px] text-amber-400/80" title={extra.error}>
          {extra.error}
        </p>
      )}

      {/* Backtest summary */}
      {extra.backtest !== null && (
        <div className="mb-3 rounded-md border border-slate-800 bg-surface-800/60 p-2 font-mono text-[10px] text-slate-400">
          <div className="text-slate-300">
            LOO backtest · {extra.backtest.nScored} scored
            {extra.backtest.nExcludedBootstrap > 0 &&
              ` · ${extra.backtest.nExcludedBootstrap} bootstrap excluded`}
          </div>
          <div>
            RMSE {extra.backtest.rmseBp.toFixed(1)} bp · ζ mean{" "}
            {extra.backtest.zetaMean.toFixed(2)} · ζ std {extra.backtest.zetaStd.toFixed(2)}
          </div>
        </div>
      )}

      {/* Edge editor (Phase 7) replaces the node table when open */}
      {editing ? (
        <EdgeEditor
          nodes={editorNodes}
          onSaved={() => void extra.run(body)}
          onClose={() => setEditing(false)}
        />
      ) : (
      <>
      {/* Attribution card (explainability): why the selected node moved */}
      {selected !== null && (
        <GraphAttributionCard
          ticker={selected.ticker}
          expiry={selected.expiry}
          body={body}
          onClose={() => setSelected(null)}
          onOpenSmile={onOpenSmile}
        />
      )}
      {/* Per-node prior -> posterior table */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {rows.length === 0 ? (
          <p className="py-2 text-xs text-slate-500">
            Press Extrapolate to propagate the lit calibrations.
          </p>
        ) : (
          <div className="divide-y divide-slate-800">
            {rows.map((n) => {
              const isSelected =
                selected !== null &&
                selected.ticker === n.ticker &&
                selected.expiry === n.expiry;
              return (
              <div
                key={`${n.ticker}|${n.expiry}`}
                className={`flex w-full items-center gap-2 py-1.5 transition-colors hover:bg-surface-800/40 ${
                  isSelected ? "bg-surface-800/60" : ""
                }`}
              >
                <button
                  onClick={() => setSelected(isSelected ? null : { ticker: n.ticker, expiry: n.expiry })}
                  title="Attribute this node's move to the lit observations"
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <span className="min-w-0 flex-1 truncate text-xs text-slate-300">
                    <span className="font-medium text-slate-100">{n.ticker}</span>{" "}
                    <span className="font-mono text-[10px] text-slate-500">{n.expiry}</span>
                    <span
                      className={`ml-1 text-[9px] ${n.lit ? "text-amber-400" : "text-slate-600"}`}
                    >
                      {n.lit ? "lit" : "dark"}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[10px] text-slate-400">
                    {(n.priorAtmVol * 100).toFixed(1)}→{(n.postAtmVol * 100).toFixed(1)}%
                  </span>
                  <span
                    className={`w-12 shrink-0 text-right font-mono text-[10px] ${
                      n.shiftBp >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {n.shiftBp >= 0 ? "+" : ""}
                    {n.shiftBp.toFixed(0)}bp
                  </span>
                </button>
                <button
                  onClick={() => onOpenSmile(n.ticker, n.expiry)}
                  title="Open this node's reconstructed smile"
                  className="shrink-0 text-[11px] text-slate-600 hover:text-slate-300"
                >
                  ↗
                </button>
              </div>
              );
            })}
          </div>
        )}
      </div>
      </>
      )}

      <p className="mt-1 shrink-0 text-[10px] text-slate-600">
        Click a node to attribute its move · ↗ opens its reconstructed smile.
      </p>
    </aside>
  );
}
