// Graph workspace shell (P5b U0): configuring relationships between markets,
// not tuning a numerical solver. Workflow spine: Configure → Preview → Run →
// Explain → Validate.
//
//   TOP    — observation source + propagation operator, config / preflight
//            chips, Clear, RUN (the single primary action).
//   LEFT   — Relationships pane: calendar / cross-asset cards, per-relation
//            overrides (Edges editors), advanced legacy solver knobs.
//   CENTER — the smile-universe canvas (ticker pods, calendar spines; solve
//            cinematics by real BFS hop + attribution particles). Unchanged.
//   RIGHT  — Inspector: the selected node (facts + exact attribution).
//   BOTTOM — drawer: Preview | Diagnostics | Validation | Observation plan.
//
// This view requires the live backend (GET /graph/nodes, POST /graph/solve,
// POST /graph/extrapolate) — there is deliberately no mock fallback.
import { useEffect, useMemo, useState } from "react";
import GraphNetworkChart from "../components/GraphNetworkChart";
import GraphDrawer, { type DrawerTab } from "../components/graphshell/GraphDrawer";
import GraphTopBar, { type ObservationSource } from "../components/graphshell/GraphTopBar";
import InspectorPane from "../components/graphshell/InspectorPane";
import RelationshipsPane from "../components/graphshell/RelationshipsPane";
import { useGraph, nodeKey, type GraphNodeBase } from "../state/useGraph";
import { useGraphEdges } from "../state/useGraphEdges";
import { useMessageEdges } from "../state/useMessageEdges";
import { useGraphExtrapolation, buildExtrapolateBody } from "../state/useGraphExtrapolation";
import { useGraphFocus } from "../state/graphFocus";
import { useSmileSession } from "../state/smileSession";
import { useWaveTimeline } from "../state/useWaveTimeline";
import { useAttributionParticles } from "../state/useAttributionParticles";
import { waveHops } from "../lib/graphWave";
import type { LayoutEdgeIn } from "../lib/graphLayout";

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
  // rebuild the exact request body the shell ran with).
  const [flatAtm, setFlatAtm] = useState(false);
  const [crossBeta, setCrossBeta] = useState(1);
  const extrapolateBody = useMemo(
    () => buildExtrapolateBody(graph.params, flatAtm, crossBeta),
    [graph.params, flatAtm, crossBeta],
  );

  // Shell state: the inspected node and the bottom drawer.
  const [selected, setSelected] = useState<{ ticker: string; expiry: string } | null>(null);
  const [drawerTab, setDrawerTab] = useState<DrawerTab>("preview");
  const [drawerOpen, setDrawerOpen] = useState(true);

  // The REAL solver topology for the network view: persisted per-edge
  // overrides when any exist, else the auto-lattice the solver would build.
  // Under the message operator the displayed topology is the message
  // relations instead (persisted rules, else the auto relations), mapped
  // into the chart's stored-edge convention (from = receiver, to = informer)
  // so the information-flow arrows stay honest. Re-fetched when the edge
  // editor saves (edgesVersion bump) or the operator changes.
  const { fetchEdges, fetchLattice } = useGraphEdges();
  const { fetchEdges: fetchMsgEdges, fetchAuto: fetchMsgAuto } = useMessageEdges();
  const messagesMode = graph.params.propagationMode === "precision_messages";
  const [edges, setEdges] = useState<LayoutEdgeIn[]>([]);
  const [edgesVersion, setEdgesVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    const load: Promise<LayoutEdgeIn[]> = messagesMode
      ? fetchMsgEdges()
          .then((rows) => (rows.length > 0 ? rows : fetchMsgAuto()))
          .then((rows) =>
            rows.map((r) => ({
              fromTicker: r.targetTicker,
              fromExpiry: r.targetExpiry,
              toTicker: r.sourceTicker,
              toExpiry: r.sourceExpiry,
              weight: r.messagePrecision,
            })),
          )
      : fetchEdges()
          .then((e) => (e.length > 0 ? e : fetchLattice()))
          .then((e) =>
            e.map((r) => ({
              fromTicker: r.fromTicker,
              fromExpiry: r.fromExpiry,
              toTicker: r.toTicker,
              toExpiry: r.toExpiry,
              weight: r.weight,
            })),
          );
    load
      .then((e) => {
        if (alive) setEdges(e);
      })
      .catch(() => {
        /* topology is display-only; the solver builds its own — keep last */
      });
    return () => {
      alive = false;
    };
  }, [fetchEdges, fetchLattice, fetchMsgEdges, fetchMsgAuto, messagesMode, edgesVersion]);

  // With the calibrations source the chart is driven by the production solve:
  // the full SELECTED lit+dark universe (prior handles as the baseline), the
  // calibrated nodes lit (amber ring = an observation), and the posterior
  // field. Before the first Run (extra.nodes null) it falls back to the
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

  /** Row / canvas selection for the Inspector (re-click deselects). */
  const selectNode = (ticker: string, expiry: string) => {
    setSelected((prev) =>
      prev !== null && prev.ticker === ticker && prev.expiry === expiry
        ? null
        : { ticker, expiry },
    );
  };
  /** Canvas single-click: manual lights/dims; calibrations inspects. */
  const onChartToggle = (key: string) => {
    if (manual) {
      graph.toggleLit(key);
      return;
    }
    const [ticker = "", expiry = ""] = key.split("|");
    if (ticker !== "" && expiry !== "") selectNode(ticker, expiry);
  };

  // Run routing: production extrapolation vs the manual sandbox. After the
  // attempt, reveal Diagnostics (errors surface in the top bar either way).
  const litCount0 = Object.keys(graph.lit).length;
  const canRun = manual ? litCount0 > 0 : true;
  const busy = manual ? graph.solving : extra.running;
  const run = async () => {
    if (manual) await graph.solve();
    else await extra.run(extrapolateBody);
    setDrawerTab("diagnostics");
    setDrawerOpen(true);
  };
  const clearField = () => {
    if (manual) graph.clear();
    else extra.clear();
  };
  const runError = manual ? graph.solveError : extra.error;
  const hasResults = manual ? graph.results !== null : extra.nodes !== null;

  /** Relation-editor save: refresh the displayed topology and re-run the
   *  production solve so the field reflects the new relations. */
  const onEdgesSaved = () => {
    setEdgesVersion((v) => v + 1);
    if (!manual) void extra.run(extrapolateBody);
  };

  // Inspector data for the selected node.
  const inspectorBase = useMemo(
    () =>
      selected === null
        ? null
        : (chartNodes ?? []).find(
            (n) => n.ticker === selected.ticker && n.expiry === selected.expiry,
          ) ?? null,
    [selected, chartNodes],
  );
  const inspectorPost = useMemo(
    () =>
      selected === null || manual
        ? null
        : (extra.nodes ?? []).find(
            (n) => n.ticker === selected.ticker && n.expiry === selected.expiry,
          ) ?? null,
    [selected, manual, extra.nodes],
  );

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

  // Top-bar badges: lit/dark composition of the displayed universe.
  const litCount =
    extrapolating || manual
      ? Object.keys(chartLit).length
      : (chartNodes ?? []).filter((n) => n.lit).length;
  const darkCount = Math.max(0, (chartNodes ?? []).length - litCount);

  return (
    <div className="flex h-full flex-col gap-3 p-4">
      <GraphTopBar
        source={source}
        setSource={setSource}
        mode={graph.params.propagationMode}
        setMode={(m) => graph.setParam("propagationMode", m)}
        litCount={litCount}
        darkCount={darkCount}
        summary={summary}
        error={runError}
        canRun={canRun}
        busy={busy}
        onRun={() => void run()}
        hasResults={hasResults}
        onClear={clearField}
      />

      <div className="flex min-h-0 flex-1 gap-3">
        <RelationshipsPane
          source={source}
          graph={graph}
          messages={!manual && messagesMode}
          crossBeta={crossBeta}
          setCrossBeta={setCrossBeta}
          onEdgesSaved={onEdgesSaved}
        />

        {/* Canvas card (unchanged from the pre-shell workspace) */}
        <div className="flex min-w-0 flex-1 flex-col rounded-xl border border-slate-800 bg-surface-900 p-4 shadow-xl shadow-black/30">
          <div className="mb-2 flex shrink-0 items-center gap-2">
            <h2 className="text-sm font-semibold text-slate-100">Smile universe</h2>
          </div>

          <div className="min-h-0 flex-1">
            {(graph.loading || graph.nodes === null) && !extrapolating ? (
              <div className="flex h-full items-center justify-center text-xs text-slate-500">
                Fitting baseline nodes… (first load can take a second)
              </div>
            ) : (chartNodes ?? []).length === 0 ? (
              <div className="flex h-full items-center justify-center px-6 text-center text-xs text-slate-500">
                No calibrated nodes yet — calibrate from the Parametric tab, or
                press Run to spread the transported priors across the selected
                universe.
              </div>
            ) : (
              <GraphNetworkChart
                nodes={chartNodes ?? []}
                edges={edges}
                lit={chartLit}
                results={chartResults}
                onToggle={onChartToggle}
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

          {/* Interaction hint + visual legend (next to the canvas it explains) */}
          <div className="mt-1 flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-slate-600">
            <span>
              {manual
                ? "Click to light/dim · double-click to open smile · drag to pan, wheel to zoom"
                : "Click to inspect · double-click to open smile · drag to pan, wheel to zoom"}
            </span>
            <span className="ml-auto flex items-center gap-3 text-slate-500">
              <span className="flex items-center gap-1">
                <span className="h-2.5 w-2.5 rounded-full border-2 border-amber-400/90" /> observed
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="h-2 w-8 rounded-sm"
                  style={{ background: "linear-gradient(90deg, rgb(56 189 248), rgb(100 116 139), rgb(248 113 113))" }}
                />
                posterior shift
              </span>
              <span className="flex items-center gap-1">
                <span className="h-3 w-3 rounded-full bg-slate-400/25" /> halo = uncertainty (sd)
              </span>
            </span>
          </div>
        </div>

        <InspectorPane
          selected={selected}
          base={inspectorBase}
          post={inspectorPost}
          body={extrapolateBody}
          showAttribution={!manual && extra.nodes !== null}
          manual={manual}
          onClose={() => setSelected(null)}
          onOpenSmile={openSmile}
        />
      </div>

      <GraphDrawer
        source={source}
        graph={graph}
        extra={extra}
        body={extrapolateBody}
        flatAtm={flatAtm}
        setFlatAtm={setFlatAtm}
        selected={selected}
        onSelect={selectNode}
        onOpenSmile={openSmile}
        tab={drawerTab}
        setTab={setDrawerTab}
        open={drawerOpen}
        setOpen={setDrawerOpen}
      />
    </div>
  );
}
