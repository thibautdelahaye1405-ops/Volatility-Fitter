// Per-node prior -> posterior table for the production (calibrations) solve —
// the Diagnostics drawer tab's main body. Selection is LIFTED to the shell:
// clicking a row selects the node for the right-hand Inspector (attribution +
// smile drill-in live there); the backtest chip and observation plan render in
// their own drawer tabs.
import { useMemo } from "react";
import type { UseGraphExtrapolationResult } from "../state/useGraphExtrapolation";

interface ExtrapolateResultsProps {
  extra: UseGraphExtrapolationResult;
  /** The node highlighted in the Inspector, or null. */
  selected: { ticker: string; expiry: string } | null;
  /** Row click: select (or re-click to deselect — the shell decides). */
  onSelect: (ticker: string, expiry: string) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
}

export default function ExtrapolateResults({
  extra,
  selected,
  onSelect,
  onOpenSmile,
}: ExtrapolateResultsProps) {
  const rows = useMemo(
    () =>
      (extra.nodes ?? [])
        .slice()
        .sort((a, b) => a.ticker.localeCompare(b.ticker) || a.expiry.localeCompare(b.expiry)),
    [extra.nodes],
  );

  if (rows.length === 0) {
    return (
      <p className="py-2 text-xs text-slate-500">
        Press Run to transport the priors and spread the observations — lit
        calibrations or what-if pulses — across the selected universe.
      </p>
    );
  }

  return (
    <>
      <div className="min-h-0 flex-1 overflow-y-auto">
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
                  onClick={() => onSelect(n.ticker, n.expiry)}
                  title="Inspect this node (attribution of its move to the lit observations)"
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
                    {n.noLitPath === true && (
                      <span
                        className="ml-1 rounded bg-rose-500/15 px-1 text-[8px] uppercase tracking-wide text-rose-300"
                        title="No lit path: this node's component has no observation — it stays at its transported prior with explicitly broad uncertainty (spec §14.3)"
                      >
                        no path
                      </span>
                    )}
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
                  {/* Posterior ATM credible half-width (functional band's
                      level marginal, idio-floored on dark names). In message
                      mode the tooltip names the U1 taxonomy: incoming message
                      confidence q (receiver conditional, §7.6) vs the FINAL
                      posterior confidence (the marginal — authoritative). */}
                  <span
                    className="w-10 shrink-0 text-right font-mono text-[9px] text-slate-500"
                    title={
                      "Final posterior confidence — ATM-vol sd (1σ, bp)" +
                      (n.qIncoming !== null && n.qIncoming !== undefined
                        ? ` · incoming message confidence q ${n.qIncoming.toFixed(0)}` +
                          ` · final posterior (marginal) precision ${(1 / (n.sd * n.sd)).toFixed(0)}` +
                          " (the marginal is authoritative — it folds in source uncertainty and shared routes)"
                        : "")
                    }
                  >
                    ±{(n.sd * 1e4).toFixed(0)}
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
      </div>

      <p className="mt-1 shrink-0 text-[10px] text-slate-600">
        Click a node to inspect it · ↗ opens its reconstructed smile.
      </p>
    </>
  );
}
