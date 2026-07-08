// Graph workspace: smile-node graph for cross-asset signal propagation.
//
// ONE workflow: pick the observation source (lit calibrations vs manual
// what-if shifts), press PROPAGATE, read the posterior field on the
// ticker-pod network view (pods positioned by edge-weight springs, expiries
// as calendar spines). Click a node to light/dim it, double-click to drill
// into its smile; drag to pan, wheel to zoom.
//
// When a propagation lands, the posterior field reveals outward from the lit
// nodes by real BFS hop (the solve cinematics — lib/graphWave) and attribution
// particles travel the top gain × innovation paths.
//
// This view requires the live backend (GET /graph/nodes, POST /graph/solve,
// POST /graph/extrapolate) — there is deliberately no mock fallback.
import { useEffect, useMemo, useState } from "react";
import GraphNetworkChart from "../components/GraphNetworkChart";
import PropagatePanel, { type ObservationSource } from "../components/PropagatePanel";
import { useGraph, nodeKey, type GraphNodeBase } from "../state/useGraph";
import { useGraphEdges } from "../state/useGraphEdges";
import { useGraphExtrapolation, buildExtrapolateBody } from "../state/useGraphExtrapolation";
import { useGraphFocus } from "../state/graphFocus";
import { useSmileSession } from "../state/smileSession";
import { useWaveTimeline } from "../state/useWaveTimeline";
import { useAttributionParticles } from "../state/useAttributionParticles";
import { waveHops } from "../lib/graphWave";
import type { LayoutEdgeIn } from "../lib/graphLayout";

/** No-op chart handler for the calibrations source (the lit/dark set is the
 *  selected universe — edited in the Universe tab, not by clicking). */
const noop = (_key: string): void => undefined;

/** Small bordered button, matching the smile toolbar style. */
const buttonClass =
  "rounded-md border border-slate-700 bg-surface-800 px-2.5 py-1.5 text-xs " +
  "font-medium text-slate-300 transition-colors enabled:hover:border-slate-600 " +
  "enabled:hover:text-slate-100 disabled:cursor-not-allowed disabled:opacity-40";

interface GraphViewerProps {
  /** Switch the app to the Smile tab (after this view sets the node). */
  onNavigateToSmile: () => void;
}

export default function GraphViewer({ onNavigateToSmile }: GraphViewerProps) {
  const graph = useGraph();
  const extra = useGraphExtrapolation();
  const { setTicker, setExpiry } = useSmileSession();
  const { setFocus } = useGraphFocus();
  const [source, setSource] = useState<ObservationSource>("calibrations");

  // Calibrations-only solver flags (owned here so the drill-in focus can
  // rebuild the exact request body the panel propagated with).
  const [flatAtm, setFlatAtm] = useState(false);
  const [crossBeta, setCrossBeta] = useState(1);
  const extrapolateBody = useMemo(
    () => buildExtrapolateBody(graph.params, flatAtm, crossBeta),
    [graph.params, flatAtm, crossBeta],
  );

  // The REAL solver topology for the network view: persisted per-edge
  // overrides when any exist, else the auto-lattice the solver would build.
  // Re-fetched when the edge editor saves (edgesVersion bump).
  const { fetchEdges, fetchLattice } = useGraphEdges();
  const [edges, setEdges] = useState<LayoutEdgeIn[]>([]);
  const [edgesVersion, setEdgesVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    fetchEdges()
      .then((e) => (e.length > 0 ? e : fetchLattice()))
      .then((e) => {
        if (alive)
          setEdges(
            e.map((r) => ({
              fromTicker: r.fromTicker,
              fromExpiry: r.fromExpiry,
              toTicker: r.toTicker,
              toExpiry: r.toExpiry,
              weight: r.weight,
            })),
          );
      })
      .catch(() => {
        /* topology is display-only; the solver builds its own — keep last */
      });
    return () => {
      alive = false;
    };
  }, [fetchEdges, fetchLattice, edgesVersion]);

  // With the calibrations source the chart is driven by the production solve:
  // the full SELECTED lit+dark universe (prior handles as the baseline), the
  // calibrated nodes lit (amber ring = an observation), and the posterior
  // field. Before the first Propagate (extra.nodes null) it falls back to the
  // baseline universe so the chart is never blank.
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

  const manual = source === "manual";
  const extrapolating = !manual && extraChartNodes !== null;
  const chartNodes = extrapolating ? extraChartNodes : graph.nodes;
  const chartLit = extrapolating ? extraChartLit : manual ? graph.lit : {};
  const chartResults = manual ? graph.results : extra.results;

  // Solve cinematics: stage the posterior reveal by REAL BFS hop from the lit
  // set over the real edge topology (honest distance, not decoration).
  const litKeySet = useMemo(() => new Set(Object.keys(chartLit)), [chartLit]);
  const hops = useMemo(
    () =>
      waveHops(
        (chartNodes ?? []).map((n) => nodeKey(n.ticker, n.expiry)),
        edges,
        litKeySet,
      ),
    [chartNodes, edges, litKeySet],
  );
  // Wave epoch: bump when a NEW result set lands. Keyed off the underlying
  // state identities (graph.results / extra.nodes) — extra.results is rebuilt
  // every render, so watching chartResults directly would loop.
  const resultsIdentity = manual ? graph.results : extra.nodes;
  const [waveEpoch, setWaveEpoch] = useState(0);
  useEffect(() => {
    if (resultsIdentity !== null) setWaveEpoch((v) => v + 1);
  }, [resultsIdentity]);
  const timeline = useWaveTimeline(waveEpoch, hops.maxHop);

  // Attribution particles (calibrations source only): fetch as soon as the
  // results land — the overlay's own epoch timer drives when they display.
  // Candidates = the dark nodes the propagation moved most.
  const particleCandidates = useMemo(
    () =>
      manual || extra.nodes === null
        ? []
        : extra.nodes
            .filter((n) => !n.lit)
            .sort((a, b) => Math.abs(b.shiftBp) - Math.abs(a.shiftBp))
            .slice(0, 5)
            .map((n) => ({ ticker: n.ticker, expiry: n.expiry, shiftBp: n.shiftBp })),
    [manual, extra.nodes],
  );
  const particles = useAttributionParticles(
    !manual && extra.nodes !== null,
    particleCandidates,
    extrapolateBody,
  );

  /** Drill into a node's smile: point the shared session at it, then jump.
   *  With the calibrations source also set the graph-extrapolation focus so
   *  the Smile viewer overlays this node's reconstructed smile + band. */
  const openSmile = (ticker: string, expiry: string) => {
    setTicker(ticker); // also picks a default expiry on the ladder…
    setExpiry(expiry); // …which this immediately overrides with the node's
    setFocus(manual ? null : { ticker, expiry, body: extrapolateBody });
    onNavigateToSmile();
  };

  // Summary strip: observed / extrapolated counts + the solve's max |shift|.
  const summary = useMemo(() => {
    if (chartResults === null) return null;
    const all = Object.values(chartResults);
    const observed = all.filter((n) => n.observed).length;
    const maxAbs = all.reduce((m, n) => Math.max(m, Math.abs(n.shiftBp)), 0);
    return { observed, extrapolated: all.length - observed, maxAbs };
  }, [chartResults]);

  // Backend offline (and nothing loaded): centered empty-state card.
  if (graph.error !== null && graph.nodes === null) {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="max-w-sm rounded-xl border border-slate-800 bg-surface-900 p-8 text-center shadow-xl shadow-black/30">
          <h2 className="mb-2 text-sm font-semibold text-slate-100">
            Graph solver requires the live backend
          </h2>
          <p className="mb-1 text-xs text-slate-500">
            Start the FastAPI server on :8000 and retry.
          </p>
          <p className="mb-5 truncate text-[10px] text-amber-400/80" title={graph.error}>
            {graph.error}
          </p>
          <button className={buttonClass} onClick={graph.reload}>
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
          <h2 className="text-sm font-semibold text-slate-100">Smile universe</h2>
          {/* Post-propagation summary strip */}
          {summary !== null && (
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
          {(graph.loading || graph.nodes === null) && !extrapolating ? (
            <div className="flex h-full items-center justify-center text-xs text-slate-500">
              Fitting baseline nodes… (first load can take a second)
            </div>
          ) : (chartNodes ?? []).length === 0 ? (
            <div className="flex h-full items-center justify-center px-6 text-center text-xs text-slate-500">
              No calibrated nodes yet — calibrate from the Parametric tab, or
              press Propagate to spread the transported priors across the
              selected universe.
            </div>
          ) : (
            <GraphNetworkChart
              nodes={chartNodes ?? []}
              edges={edges}
              lit={chartLit}
              results={chartResults}
              onToggle={manual ? graph.toggleLit : noop}
              onOpenSmile={openSmile}
              wave={{
                hopOf: hops.hopOf,
                revealedHop: timeline.revealedHop,
                animating: timeline.animating,
                skip: timeline.skip,
              }}
              particles={particles}
              waveEpoch={waveEpoch}
            />
          )}
        </div>

        {/* Interaction hint */}
        <p className="mt-1 shrink-0 text-[10px] text-slate-600">
          {manual
            ? "Click to light/dim · double-click to open smile · drag to pan, wheel to zoom · Propagate to spread"
            : "Selected lit+dark universe · amber ring = calibrated observation · double-click to open smile · drag to pan, wheel to zoom"}
        </p>
      </div>

      <PropagatePanel
        source={source}
        setSource={setSource}
        graph={graph}
        extra={extra}
        body={extrapolateBody}
        flatAtm={flatAtm}
        setFlatAtm={setFlatAtm}
        crossBeta={crossBeta}
        setCrossBeta={setCrossBeta}
        onOpenSmile={openSmile}
        onEdgesSaved={() => setEdgesVersion((v) => v + 1)}
      />
    </div>
  );
}
