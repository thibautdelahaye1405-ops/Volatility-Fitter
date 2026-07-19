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
// This view requires the live backend (GET /graph/nodes, POST
// /graph/extrapolate — BOTH observation sources ride the production solve
// since P5b U3; the what-if ships syntheticObservations, non-persisting) —
// there is deliberately no mock fallback.
import { useEffect, useMemo, useState } from "react";
import type { GraphEdgeSelection } from "../components/GraphNetworkChart";
import CanvasCard from "../components/graphshell/CanvasCard";
import GraphDrawer, { type DrawerTab } from "../components/graphshell/GraphDrawer";
import GraphTopBar, { type ObservationSource } from "../components/graphshell/GraphTopBar";
import InspectorPane from "../components/graphshell/InspectorPane";
import RelationshipsPane from "../components/graphshell/RelationshipsPane";
import { useGraph, nodeKey, type GraphNodeBase } from "../state/useGraph";
import { useGraphEdges } from "../state/useGraphEdges";
import { useMessageEdges, type MessageEdgeRow } from "../state/useMessageEdges";
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

  // Shell state: the inspected node/edge and the bottom drawer.
  const [selected, setSelected] = useState<{ ticker: string; expiry: string } | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdgeSelection | null>(null);
  // Bumped by the inspector's "Edit relations" — RelationshipsPane opens the
  // row editor on change.
  const [editorSignal, setEditorSignal] = useState(0);
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
  // The EFFECTIVE relation rows (persisted else auto) — the U4 message
  // inspector reads these raw; the chart reads their LayoutEdgeIn mapping.
  const [msgRows, setMsgRows] = useState<MessageEdgeRow[]>([]);
  const [edgesVersion, setEdgesVersion] = useState(0);
  useEffect(() => {
    let alive = true;
    const load: Promise<LayoutEdgeIn[]> = messagesMode
      ? fetchMsgEdges()
          .then((rows) => (rows.length > 0 ? rows : fetchMsgAuto()))
          .then((rows) => {
            if (alive) setMsgRows(rows);
            return rows.map((r) => ({
              fromTicker: r.targetTicker,
              fromExpiry: r.targetExpiry,
              toTicker: r.sourceTicker,
              toExpiry: r.sourceExpiry,
              weight: r.messagePrecision,
            }));
          })
      : fetchEdges()
          .then((e) => (e.length > 0 ? e : fetchLattice()))
          .then((e) => {
            if (alive) setMsgRows([]);
            return e.map((r) => ({
              fromTicker: r.fromTicker,
              fromExpiry: r.fromExpiry,
              toTicker: r.toTicker,
              toExpiry: r.toExpiry,
              weight: r.weight,
            }));
          });
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
  // U3 unification: BOTH sources render the production field. In manual the
  // lit set stays the EDITABLE pulse set (rings follow the current edits,
  // which may differ from the last run).
  const extrapolating = extraChartNodes !== null;
  const chartNodes = extrapolating ? extraChartNodes : graph.nodes;
  const chartLit = manual ? graph.lit : extrapolating ? extraChartLit : {};
  const chartResults = extra.results;

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
  // state identity (extra.nodes) — extra.results is rebuilt every render, so
  // watching chartResults directly would loop.
  const resultsIdentity = extra.nodes;
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

  // The effective run body (U3 unification): manual what-if ships the typed
  // pulse set as syntheticObservations on the PRODUCTION request — selected
  // universe, transported-prior baselines, ACTIVE operator, non-persisting.
  const syntheticObservations = useMemo(
    () =>
      Object.entries(graph.lit).map(([key, dAtmVol]) => {
        const [ticker = "", expiry = ""] = key.split("|");
        return { ticker, expiry, dAtmVol };
      }),
    [graph.lit],
  );
  const runBody = useMemo(
    () => (manual ? { ...extrapolateBody, syntheticObservations } : extrapolateBody),
    [manual, extrapolateBody, syntheticObservations],
  );

  // Run routing: one solve either way. After the attempt, reveal Diagnostics
  // (errors surface in the top bar).
  const litCount0 = Object.keys(graph.lit).length;
  const canRun = manual ? litCount0 > 0 : true;
  const busy = extra.running;
  const run = async () => {
    if (manual && litCount0 === 0) return;
    await extra.run(runBody);
    setDrawerTab("diagnostics");
    setDrawerOpen(true);
  };
  const clearField = () => extra.clear();
  const runError = extra.error;
  const hasResults = extra.nodes !== null;

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
      selected === null
        ? null
        : (extra.nodes ?? []).find(
            (n) => n.ticker === selected.ticker && n.expiry === selected.expiry,
          ) ?? null,
    [selected, extra.nodes],
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
          graph={graph}
          messages={messagesMode}
          crossBeta={crossBeta}
          setCrossBeta={setCrossBeta}
          onEdgesSaved={onEdgesSaved}
          openEditorSignal={editorSignal}
        />

        <CanvasCard
          loading={(graph.loading || graph.nodes === null) && !extrapolating}
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
          manual={manual}
          onEdgeClick={setSelectedEdge}
        />

        <InspectorPane
          selected={selected}
          base={inspectorBase}
          post={inspectorPost}
          body={extrapolateBody}
          showAttribution={!manual && extra.nodes !== null}
          manual={manual}
          messages={messagesMode}
          msgRows={msgRows}
          allNodes={extra.nodes}
          params={graph.params}
          selectedEdge={selectedEdge}
          onCloseEdge={() => setSelectedEdge(null)}
          onEditRelations={() => setEditorSignal((v) => v + 1)}
          onClose={() => setSelected(null)}
          onOpenSmile={openSmile}
        />
      </div>

      <GraphDrawer
        source={source}
        graph={graph}
        extra={extra}
        body={runBody}
        nodes={graph.nodes}
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
