// Graph workspace: smile-node graph for cross-asset signal propagation.
// Click nodes to light them (mark an observed ATM-vol shift), tune the
// propagation reach η, then Solve: the backend OT-Bayesian engine returns
// posterior shifts + uncertainty bands for every node in the universe,
// overlaid on the lattice. Double-click any node to drill into its smile.
//
// This view requires the live backend (GET /graph/nodes, POST /graph/solve)
// — there is deliberately no mock fallback for the solver.
import { useMemo, useState } from "react";
import GraphChart from "../components/GraphChart";
import SolverPanel from "../components/SolverPanel";
import ExtrapolatePanel from "../components/ExtrapolatePanel";
import { useGraph, nodeKey, type GraphNodeBase } from "../state/useGraph";
import { useGraphExtrapolation } from "../state/useGraphExtrapolation";
import { useSmileSession } from "../state/smileSession";

/** Graph workspace mode: the manual-shift sandbox vs the prior-anchored
 *  production extrapolation over the selected lit+dark universe. */
type GraphMode = "sandbox" | "extrapolate";

/** No-op chart handlers for Extrapolate mode (nodes aren't lit by clicking;
 *  the lit/dark set is the selected universe, edited in the Universe tab). */
const noop = (_key: string): void => undefined;
const noopArray = (_keys: string[]): void => undefined;

interface GraphViewerProps {
  /** Switch the app to the Smile tab (after this view sets the node). */
  onNavigateToSmile: () => void;
}

/** Small bordered button, matching the smile toolbar style. */
const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

export default function GraphViewer({ onNavigateToSmile }: GraphViewerProps) {
  const {
    nodes,
    loading,
    error,
    reload,
    lit,
    toggleLit,
    setShift,
    lightMany,
    unlight,
    params,
    setParam,
    resetParams,
    solve,
    solving,
    solveError,
    results,
    clear,
    autotune,
    autotuning,
    autotuneResult,
    autotuneError,
  } = useGraph();
  const { setTicker, setExpiry } = useSmileSession();
  const [mode, setMode] = useState<GraphMode>("sandbox");
  const extra = useGraphExtrapolation();

  // In Extrapolate mode the chart is driven by the production solve: the full
  // SELECTED lit+dark universe (its prior handles as the baseline), the
  // calibrated nodes lit (amber ring = an observation), and the posterior field.
  // Before the first solve (extra.nodes null) it falls back to the sandbox
  // lattice so the chart is never blank.
  const extraChartNodes = useMemo<GraphNodeBase[] | null>(
    () =>
      extra.nodes === null
        ? null
        : extra.nodes.map((n) => ({
            ticker: n.ticker,
            expiry: n.expiry,
            t: n.t,
            atmVol: n.priorAtmVol,
            skew: n.priorSkew,
            curvature: n.priorCurv,
            lit: n.lit,
          })),
    [extra.nodes],
  );
  const extraChartLit = useMemo<Record<string, number>>(
    () =>
      extra.nodes === null
        ? {}
        : Object.fromEntries(
            extra.nodes
              .filter((n) => n.calibrated)
              .map((n) => [nodeKey(n.ticker, n.expiry), 0]),
          ),
    [extra.nodes],
  );

  const extrapolating = mode === "extrapolate" && extraChartNodes !== null;
  const chartNodes = extrapolating ? extraChartNodes : nodes;
  const chartLit = extrapolating ? extraChartLit : lit;
  const chartResults = mode === "extrapolate" ? extra.results : results;

  /** Drill into a node's smile: point the shared session at it, then jump. */
  const openSmile = (ticker: string, expiry: string) => {
    setTicker(ticker); // also picks a default expiry on the ladder…
    setExpiry(expiry); // …which this immediately overrides with the node's
    onNavigateToSmile();
  };

  // Lit entries in a stable display order (by key: ticker, then expiry).
  const litEntries = useMemo(
    () => Object.entries(lit).sort(([a], [b]) => a.localeCompare(b)),
    [lit],
  );

  // Summary strip: observed / extrapolated counts + the solve's max |shift|.
  const summary = useMemo(() => {
    if (results === null) return null;
    const all = Object.values(results);
    const observed = all.filter((n) => n.observed).length;
    const maxAbs = all.reduce((m, n) => Math.max(m, Math.abs(n.shiftBp)), 0);
    return { observed, extrapolated: all.length - observed, maxAbs };
  }, [results]);

  // Backend offline (and nothing loaded): centered empty-state card.
  if (error !== null && nodes === null) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-slate-800 bg-surface-900 p-8 text-center shadow-xl shadow-black/30">
          <h2 className="mb-2 text-sm font-semibold text-slate-100">
            Graph solver requires the live backend
          </h2>
          <p className="mb-1 text-xs text-slate-500">
            Start the FastAPI server on :8000 and retry.
          </p>
          <p className="mb-5 truncate text-[10px] text-amber-400/80" title={error}>
            {error}
          </p>
          <button className={buttonClass} onClick={reload}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full gap-4 p-4">
      {/* Graph card */}
      <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
        <div className="mb-2 flex shrink-0 items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-100">
            Smile universe
          </h2>
          {/* Sandbox (manual shifts) vs production Extrapolate (prior-anchored) */}
          <div className="flex overflow-hidden rounded-md border border-slate-700 text-[11px]">
            {(["sandbox", "extrapolate"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-2 py-0.5 transition-colors ${
                  mode === m
                    ? "bg-accent-600 text-white"
                    : "bg-surface-800 text-slate-400 hover:text-slate-200"
                }`}
              >
                {m === "sandbox" ? "Sandbox" : "Extrapolate"}
              </button>
            ))}
          </div>
          {/* Post-solve summary strip (sandbox only) */}
          {mode === "sandbox" && summary !== null && (
            <span className="ml-auto font-mono text-[11px] text-slate-400">
              <span className="text-amber-400">{summary.observed} observed</span>
              {" · "}
              {summary.extrapolated} extrapolated
              {" · "}
              max |shift| {summary.maxAbs.toFixed(1)} bp
            </span>
          )}
        </div>

        <div className="min-h-0 flex-1">
          {(loading || nodes === null) && !extrapolating ? (
            <div className="flex h-full items-center justify-center text-xs text-slate-500">
              Fitting baseline nodes… (first load can take a second)
            </div>
          ) : (
            <GraphChart
              nodes={chartNodes ?? []}
              lit={chartLit}
              results={chartResults}
              onToggle={mode === "sandbox" ? toggleLit : noop}
              onLasso={mode === "sandbox" ? lightMany : noopArray}
              onOpenSmile={openSmile}
            />
          )}
        </div>

        {/* Interaction hint */}
        <p className="mt-1 shrink-0 text-[10px] text-slate-600">
          {mode === "sandbox"
            ? "Click to light/dim · drag to lasso · double-click to open smile · Solve to propagate"
            : "Selected lit+dark universe · amber ring = calibrated observation · double-click to open smile · Extrapolate to propagate"}
        </p>
      </div>

      {/* Production extrapolation aside (prior-anchored) */}
      {mode === "extrapolate" && (
        <ExtrapolatePanel extra={extra} params={params} onOpenSmile={openSmile} />
      )}

      {/* Observations + solver panel (sandbox) */}
      {mode === "sandbox" && (
      <aside className="flex w-72 shrink-0 flex-col rounded-xl border border-slate-800 bg-surface-900 p-5 shadow-xl shadow-black/30">
        <h3 className="mb-1 text-sm font-semibold text-slate-100">
          Observations
        </h3>
        <p className="mb-3 text-[11px] text-slate-500">
          Lit nodes feed the solver as ATM-vol shifts, in vol points.
        </p>

        {/* One row per lit node: shift input (vol pts) + unlight */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {litEntries.length === 0 ? (
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
                      <span className="font-mono text-[10px] text-slate-500">
                        {expiry}
                      </span>
                    </span>
                    {/* Vol points: +2.0 means dAtmVol = +0.02 (stored as
                        decimal). Uncontrolled (defaultValue) so partial
                        entries like "-" don't snap back while typing. */}
                    <input
                      type="number"
                      step={0.5}
                      defaultValue={Number((dAtmVol * 100).toFixed(1))}
                      onChange={(e) => {
                        const pts = e.target.valueAsNumber;
                        if (Number.isFinite(pts)) setShift(key, pts / 100);
                      }}
                      className="w-16 rounded-md border border-slate-700 bg-surface-800 px-1.5 py-1 text-right font-mono text-xs text-slate-100 outline-none hover:border-slate-600 focus:border-accent-500"
                    />
                    <span className="text-[10px] text-slate-500">pts</span>
                    <button
                      onClick={() => unlight(key)}
                      title="Remove observation"
                      className="px-0.5 text-sm leading-none text-slate-500 transition-colors hover:text-slate-200"
                    >
                      ×
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          <SolverPanel
            params={params}
            setParam={setParam}
            resetParams={resetParams}
            litCount={litEntries.length}
            autotune={() => void autotune()}
            autotuning={autotuning}
            autotuneResult={autotuneResult}
            autotuneError={autotuneError}
          />
        </div>

        {/* Solve / Clear (pinned below the scroll area) */}
        <div className="mt-3 border-t border-slate-800 pt-3">
          <div className="flex items-center gap-2">
            <button
              disabled={litEntries.length === 0 || solving}
              onClick={() => void solve()}
              className="flex flex-1 items-center justify-center gap-2 rounded-md bg-accent-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors enabled:hover:bg-accent-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {solving && (
                <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              )}
              {solving ? "Solving…" : "Solve"}
            </button>
            <button
              disabled={results === null}
              onClick={clear}
              className={buttonClass}
            >
              Clear results
            </button>
          </div>
          {solveError !== null && (
            <p className="mt-2 text-[10px] text-amber-400">{solveError}</p>
          )}

          {/* Visual legend */}
          <div className="mt-3 space-y-1 border-t border-slate-800 pt-3 text-[10px] text-slate-500">
            <p>
              <span className="text-amber-400">amber ring</span> observed ·{" "}
              <span className="text-sky-400">blue</span>→
              <span className="text-red-400">red</span> posterior shift
            </p>
            <p>halo size/fade = posterior uncertainty (sd)</p>
          </div>
        </div>
      </aside>
      )}
    </div>
  );
}
