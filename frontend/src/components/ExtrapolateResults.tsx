// Post-propagation results for the calibrations source: LOO backtest chip,
// per-node prior -> posterior table, and the attribution drill-in card.
// Extracted from the retired ExtrapolatePanel so the merged Propagate panel
// stays under the file-size policy.
import { useMemo, useState } from "react";
import GraphAttributionCard from "./GraphAttributionCard";
import type { UseGraphExtrapolationResult } from "../state/useGraphExtrapolation";

interface ExtrapolateResultsProps {
  extra: UseGraphExtrapolationResult;
  /** The /graph/extrapolate request body the table was solved with (the
   *  attribution card + smile overlay must reconstruct with the same knobs). */
  body: Record<string, string | number | boolean>;
  onOpenSmile: (ticker: string, expiry: string) => void;
}

/** The node whose attribution card is open, or null. */
interface SelectedNode {
  ticker: string;
  expiry: string;
}

export default function ExtrapolateResults({
  extra,
  body,
  onOpenSmile,
}: ExtrapolateResultsProps) {
  const [selected, setSelected] = useState<SelectedNode | null>(null);
  const rows = useMemo(
    () =>
      (extra.nodes ?? [])
        .slice()
        .sort((a, b) => a.ticker.localeCompare(b.ticker) || a.expiry.localeCompare(b.expiry)),
    [extra.nodes],
  );

  return (
    <>
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
            Press Propagate to transport the priors and spread the lit
            calibrations across the universe.
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
                    onClick={() =>
                      setSelected(isSelected ? null : { ticker: n.ticker, expiry: n.expiry })
                    }
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

      <p className="mt-1 shrink-0 text-[10px] text-slate-600">
        Click a node to attribute its move · ↗ opens its reconstructed smile.
      </p>
    </>
  );
}
