// Graph shell BOTTOM drawer (P5b U0): Preview | Diagnostics | Validation |
// Observation plan.
//
//   Preview      — what the next Run will propagate: the manual what-if rows
//                  (editable shifts) or the calibrations summary + the
//                  flat-baselines diagnostic toggle.
//   Diagnostics  — the post-run field: §16.4 cycle warnings + the per-node
//                  prior → posterior table (production runs).
//   Validation   — in-app LOO backtest (RMSE, ζ); the side-by-side mode
//                  comparison + offline-artifact link is the U7 increment.
//   Observation plan — "where to quote next" ranking on the solved posterior.
//
// The shell owns tab/open state so a landing run can reveal Diagnostics.
import ExtrapolateResults from "../ExtrapolateResults";
import ObservationPlanCard from "../ObservationPlanCard";
import type { UseGraphResult } from "../../state/useGraph";
import type { UseGraphExtrapolationResult } from "../../state/useGraphExtrapolation";
import type { ObservationSource } from "./GraphTopBar";

export type DrawerTab = "preview" | "diagnostics" | "validation" | "plan";

const TABS: { id: DrawerTab; label: string }[] = [
  { id: "preview", label: "Preview" },
  { id: "diagnostics", label: "Diagnostics" },
  { id: "validation", label: "Validation" },
  { id: "plan", label: "Observation plan" },
];

interface GraphDrawerProps {
  source: ObservationSource;
  graph: UseGraphResult;
  extra: UseGraphExtrapolationResult;
  /** The /graph/extrapolate body (backtest + plan ride the same knobs). */
  body: Record<string, string | number | boolean>;
  flatAtm: boolean;
  setFlatAtm: (v: boolean) => void;
  selected: { ticker: string; expiry: string } | null;
  onSelect: (ticker: string, expiry: string) => void;
  onOpenSmile: (ticker: string, expiry: string) => void;
  tab: DrawerTab;
  setTab: (t: DrawerTab) => void;
  open: boolean;
  setOpen: (v: boolean) => void;
}

const switchHint = "Switch Observations to “From calibrations” — this reads the production solve.";

export default function GraphDrawer({
  source,
  graph,
  extra,
  body,
  flatAtm,
  setFlatAtm,
  selected,
  onSelect,
  onOpenSmile,
  tab,
  setTab,
  open,
  setOpen,
}: GraphDrawerProps) {
  const manual = source === "manual";
  const litEntries = Object.entries(graph.lit).sort(([a], [b]) => a.localeCompare(b));

  const preview = manual ? (
    litEntries.length === 0 ? (
      <p className="py-2 text-xs text-slate-500">
        No lit nodes — click nodes in the graph to add observations.
      </p>
    ) : (
      <div className="divide-y divide-slate-800">
        {litEntries.map(([key, dAtmVol]) => {
          const [ticker = "", expiry = ""] = key.split("|");
          return (
            <div key={key} className="flex items-center gap-2 py-1.5">
              <span className="min-w-0 flex-1 truncate text-xs text-slate-300">
                <span className="font-medium text-slate-100">{ticker}</span>{" "}
                <span className="font-mono text-[10px] text-slate-500">{expiry}</span>
              </span>
              {/* Vol points: +2.0 means dAtmVol = +0.02. Uncontrolled so
                  partial entries like "-" don't snap back while typing. */}
              <input
                type="number"
                step={0.5}
                defaultValue={Number((dAtmVol * 100).toFixed(1))}
                onChange={(e) => {
                  const pts = e.target.valueAsNumber;
                  if (Number.isFinite(pts)) graph.setShift(key, pts / 100);
                }}
                className="w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500"
              />
              <span className="text-[10px] text-slate-500">pts</span>
              <button
                onClick={() => graph.unlight(key)}
                title="Remove observation"
                className="px-0.5 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200"
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
    )
  ) : (
    <div className="space-y-2 text-xs text-slate-400">
      <p className="text-slate-500">
        Lit nodes' calibrated moves vs their transported priors drive the field
        — {litEntries.length} lit observation{litEntries.length === 1 ? "" : "s"}.
      </p>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={flatAtm}
          onChange={(e) => setFlatAtm(e.target.checked)}
          className="accent-accent-500"
        />
        Flat baselines (diagnostic)
      </label>
    </div>
  );

  // Manual results render on the canvas only (sandbox parity); production
  // runs get the full per-node table.
  const manualSummary =
    graph.results === null
      ? null
      : Object.values(graph.results).reduce(
          (acc, n) => ({
            count: acc.count + 1,
            maxAbs: Math.max(acc.maxAbs, Math.abs(n.shiftBp)),
          }),
          { count: 0, maxAbs: 0 },
        );
  const diagnostics = (
    <div className="flex h-full min-h-0 flex-col">
      {!manual && extra.cycles.length > 0 && (
        <p
          className="mb-2 shrink-0 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[10px] text-amber-300"
          title="Cycles whose beta product differs from 1 — an internally inconsistent edge configuration (spec §16.4)"
        >
          ⚠ {extra.cycles.length} inconsistent beta cycle
          {extra.cycles.length > 1 ? "s" : ""} · worst product{" "}
          {extra.cycles
            .reduce((m, c) => Math.max(m, Math.abs(c.betaProduct)), 0)
            .toFixed(2)}
        </p>
      )}
      {manual ? (
        <p className="py-2 text-xs text-slate-500">
          {manualSummary === null
            ? "Run the what-if to populate the field."
            : `${manualSummary.count} nodes solved · max |shift| ${manualSummary.maxAbs.toFixed(1)} bp — the posterior field renders on the canvas.`}
        </p>
      ) : (
        <ExtrapolateResults
          extra={extra}
          selected={selected}
          onSelect={onSelect}
          onOpenSmile={onOpenSmile}
        />
      )}
    </div>
  );

  const validation = manual ? (
    <p className="py-2 text-xs text-slate-500">{switchHint}</p>
  ) : (
    <div className="space-y-2">
      <button
        className="flex items-center justify-center gap-1 rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
        disabled={extra.backtesting}
        onClick={() => void extra.runBacktest(body)}
        title="Leave-one-node-out validation of the current knobs"
      >
        {extra.backtesting && (
          <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-500/40 border-t-slate-200" />
        )}
        {extra.backtesting ? "Backtesting…" : "Validate (LOO)"}
      </button>
      {extra.backtestError !== null && (
        <p className="text-[10px] text-amber-400">{extra.backtestError}</p>
      )}
      {extra.backtest !== null && (
        <div className="rounded-md border border-slate-800 bg-surface-800/60 p-2 font-mono text-[10px] text-slate-400">
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
    </div>
  );

  const plan = manual ? (
    <p className="py-2 text-xs text-slate-500">{switchHint}</p>
  ) : extra.nodes === null ? (
    <p className="py-2 text-xs text-slate-500">
      Run first — the ranking reads the solved posterior.
    </p>
  ) : (
    <ObservationPlanCard body={body} onOpenSmile={onOpenSmile} />
  );

  const content: Record<DrawerTab, React.ReactNode> = {
    preview,
    diagnostics,
    validation,
    plan,
  };

  return (
    <div className="shrink-0 rounded-xl border border-slate-800 bg-surface-900 shadow-xl shadow-black/30">
      <div className="flex items-center gap-1 px-2 pt-1.5">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => {
              // Re-clicking the active tab collapses the drawer.
              if (tab === t.id && open) setOpen(false);
              else {
                setTab(t.id);
                setOpen(true);
              }
            }}
            className={`rounded-t-md px-3 py-1.5 text-xs font-medium transition-colors ${
              tab === t.id && open
                ? "bg-surface-800 text-slate-100"
                : "text-slate-500 hover:text-slate-300"
            }`}
          >
            {t.label}
          </button>
        ))}
        <button
          onClick={() => setOpen(!open)}
          title={open ? "Collapse drawer" : "Expand drawer"}
          className="ml-auto px-2 py-1 text-xs text-slate-500 transition-colors hover:text-slate-300"
        >
          {open ? "▾" : "▴"}
        </button>
      </div>
      {open && <div className="h-52 overflow-y-auto border-t border-slate-800 px-4 py-2">{content[tab]}</div>}
    </div>
  );
}
